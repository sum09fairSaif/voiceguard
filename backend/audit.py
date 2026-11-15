"""A record of security events: sign-ups, sign-ins, lockouts, enrollment,
voice-check decisions and sign-outs.

Kept in our own `audit_events` collection for AUDIT_RETENTION_DAYS, and, if
POSTHOG_API_KEY is set, also sent to PostHog for dashboards and spike alerts.

Only a fixed set of fields can be recorded: the event's name, a hashed user id,
an outcome and a short reason word. No email, IP address, token, password,
audio, passage or score can be passed in. Recording never fails a request: a
problem is logged as `audit_not_recorded` and the request carries on.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
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

# PostHog calls run here, off the request's thread, so a slow or unreachable
# PostHog never slows or fails a request.
_sender = ThreadPoolExecutor(max_workers=2, thread_name_prefix="posthog")


def _collection() -> Collection:
    # Replaced in tests.
    return get_audit_events_collection()


def hashed(user_id: str | None) -> str | None:
    """A stable stand-in for a user id: enough to link one person's events,
    nothing that leads back to the account without the database."""
    if not user_id:
        return None
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]


def _send_to_posthog(event: str, user: str | None, outcome: str | None, reason: str | None) -> None:
    try:
        httpx.post(
            f"{config.POSTHOG_HOST.rstrip('/')}/capture/",
            json={
                "api_key": config.POSTHOG_API_KEY,
                "event": event,
                "distinct_id": user or "anonymous",
                "properties": {"outcome": outcome, "reason": reason, "source": "backend"},
            },
            timeout=2.0,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001  any PostHog trouble is only logged
        logger.warning("audit_not_recorded where=posthog event=%s reason=%s", event, type(exc).__name__)


def track(event: str, user_id: str | None = None, outcome: str | None = None, reason: str | None = None) -> None:
    """Record one security event. Never raises."""
    if event not in EVENTS:
        logger.error("audit_not_recorded where=unknown_event event=%s", event)
        return
    now = datetime.now(UTC)
    user = hashed(user_id)
    try:
        _collection().insert_one(
            {
                "at": now,
                "event": event,
                "user": user,
                "outcome": outcome,
                "reason": reason,
                "expires_at": now + timedelta(days=config.AUDIT_RETENTION_DAYS),
            }
        )
    except Exception as exc:  # noqa: BLE001  recording must never fail the request
        logger.warning("audit_not_recorded where=database event=%s reason=%s", event, type(exc).__name__)
    if config.POSTHOG_API_KEY:
        try:
            _sender.submit(_send_to_posthog, event, user, outcome, reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_not_recorded where=posthog event=%s reason=%s", event, type(exc).__name__)
