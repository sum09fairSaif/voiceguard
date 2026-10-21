import hashlib
import math
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError


def _key(email: str) -> str:
    # Stored as a hash, so the collection never keeps the addresses people
    # mistype or try out, only a count against each.
    return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()


def _utc(moment: datetime) -> datetime:
    # MongoDB hands dates back without a time zone; they are UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def seconds_locked(login_failures: Collection, email: str, now: datetime | None = None) -> int:
    """How many seconds until this email may try again; 0 if it isn't locked."""
    now = now or datetime.now(timezone.utc)
    record = login_failures.find_one({"_id": _key(email), "locked_until": {"$gt": now}})
    if record is None:
        return 0
    return max(1, math.ceil((_utc(record["locked_until"]) - now).total_seconds()))


def record_failure(
    login_failures: Collection,
    email: str,
    max_failures: int,
    window_seconds: int,
    lockout_seconds: int,
    now: datetime | None = None,
) -> int:
    """Count one wrong password for this email. Returns how many seconds it
    is now locked for: 0 unless this failure reached `max_failures` within
    `window_seconds` of the first one."""
    now = now or datetime.now(timezone.utc)
    key = _key(email)
    window_end = now + timedelta(seconds=window_seconds)
    record = None
    # Two tries: if another wrong password for the same email starts a
    # window at the same moment, the second try counts into that one.
    for _ in range(2):
        # Add one to the open window, reading the new count in the same
        # step, so failures arriving together can't all slip under the limit.
        record = login_failures.find_one_and_update(
            {"_id": key, "window_ends": {"$gt": now}},
            {"$inc": {"failures": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if record is not None:
            break
        try:
            # No open window: start one (replacing a finished one MongoDB
            # hasn't deleted yet).
            record = login_failures.find_one_and_update(
                {"_id": key, "window_ends": {"$lte": now}},
                {
                    "$set": {"failures": 1, "window_ends": window_end, "expires_at": window_end},
                    "$unset": {"locked_until": ""},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            break
        except DuplicateKeyError:
            continue

    if record is None or record["failures"] < max_failures:
        return 0
    locked_until = now + timedelta(seconds=lockout_seconds)
    login_failures.update_one(
        {"_id": key},
        # Kept until the later of the lockout ending and the window ending.
        {"$set": {"locked_until": locked_until, "expires_at": max(locked_until, _utc(record["window_ends"]))}},
    )
    return lockout_seconds


def clear_failures(login_failures: Collection, email: str) -> None:
    """Forget earlier wrong passwords once the right one is given."""
    login_failures.delete_one({"_id": _key(email)})
