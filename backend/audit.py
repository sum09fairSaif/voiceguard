"""A record of security events: sign-ups, sign-ins, lockouts, enrollment,
voice-check decisions and sign-outs.

Kept in our own `audit_events` collection for AUDIT_RETENTION_DAYS, and, if
POSTHOG_API_KEY is set, also sent to PostHog for dashboards and spike alerts.

Only a fixed set of fields can be recorded: the event's name, a keyed hash of
the user id and a short reason word. No email, IP address, token, password,
audio, passage or score can be passed in. Recording never fails a request: a
problem is logged as `audit_not_recorded` and the request carries on.
"""

import hashlib
import hmac
import logging
import queue
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pymongo
from pymongo.collection import Collection

import config
from db import get_audit_events_collection

logger = logging.getLogger("voiceguard.audit")

EVENTS = frozenset(
    {
        "signup",
        "login_succeeded",
        "login_failed",
        "login_locked",
        "logout",
        "enroll_sample_accepted",
        "enroll_sample_refused",
        "enrolled",
        "voice_check_approved",
        "voice_check_rejected",
        "voice_check_incomplete",
        "voice_checks_paused",
    }
)

# The database write happens inside the request, so it gets a short deadline:
# a slow database delays a request by at most this, then the event is dropped.
WRITE_SECONDS = 1.0

# PostHog calls run on one background thread, off the request's thread, so a
# slow or unreachable PostHog never slows or fails a request. Events wait in a
# queue of at most QUEUE_LIMIT; past that (a flood faster than PostHog takes
# them) new events are dropped with a log line instead of filling memory. They
# are still in our own collection.
QUEUE_LIMIT = 1000
_queue: queue.Queue = queue.Queue(maxsize=QUEUE_LIMIT)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
_dropped = 0
# One connection pool for every send, instead of a new connection each time.
_http = httpx.Client(timeout=2.0)


def _collection() -> Collection:
    # Replaced in tests.
    return get_audit_events_collection()


def _hash_key() -> bytes:
    # Derived from the server's JWT_SECRET, so no new setting is needed. A plain
    # hash of an id could be reversed: ids are predictable (a timestamp, a
    # per-process value and a counter), so anyone who saw one real id could
    # hash the ids around it. Without the server's secret, they can't.
    # Rotating JWT_SECRET starts a new set of stand-ins.
    return hmac.new(config.JWT_SECRET.encode("utf-8"), b"voiceguard-audit-user-id", hashlib.sha256).digest()


def hashed(user_id: str | None) -> str | None:
    """A stable stand-in for a user id: enough to link one person's events,
    nothing that leads back to the account without the server's secret."""
    if not user_id:
        return None
    return hmac.new(_hash_key(), str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _send_to_posthog(event: str, user: str | None, reason: str | None) -> None:
    try:
        _http.post(
            f"{config.POSTHOG_HOST.rstrip('/')}/capture/",
            json={
                "api_key": config.POSTHOG_API_KEY,
                "event": event,
                "distinct_id": user or "anonymous",
                "properties": {"reason": reason, "source": "backend"},
            },
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001  any PostHog trouble is only logged
        logger.warning("audit_not_recorded where=posthog event=%s reason=%s", event, type(exc).__name__)


def _send_queued() -> None:
    while True:
        item = _queue.get()
        try:
            _send_to_posthog(*item)
        finally:
            _queue.task_done()


def _enqueue(event: str, user: str | None, reason: str | None) -> None:
    global _worker, _dropped
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_send_queued, name="posthog", daemon=True)
            _worker.start()
    try:
        _queue.put_nowait((event, user, reason))
    except queue.Full:
        _dropped += 1
        # The first drop, then every 100th, so a flood doesn't flood the log too.
        if _dropped % 100 == 1:
            logger.warning("audit_not_recorded where=posthog_queue_full event=%s dropped=%d", event, _dropped)


def track(event: str, user_id: str | None = None, reason: str | None = None) -> None:
    """Record one security event. Never raises."""
    if event not in EVENTS:
        logger.error("audit_not_recorded where=unknown_event event=%s", event)
        return
    now = datetime.now(UTC)
    user = hashed(user_id)
    try:
        with pymongo.timeout(WRITE_SECONDS):
            _collection().insert_one(
                {
                    "at": now,
                    "event": event,
                    "user": user,
                    "reason": reason,
                    "expires_at": now + timedelta(days=config.AUDIT_RETENTION_DAYS),
                }
            )
    except Exception as exc:  # noqa: BLE001  recording must never fail the request
        logger.warning("audit_not_recorded where=database event=%s reason=%s", event, type(exc).__name__)
    if config.POSTHOG_API_KEY:
        try:
            _enqueue(event, user, reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_not_recorded where=posthog event=%s reason=%s", event, type(exc).__name__)
