"""Ending sign-in sessions on the server.

Each sign-in (signup or password) starts a session with its own id (`sid`),
carried by its limited token and by the voice-verified token an approved check
gives it. Signing out puts the sid on a revocation list that every protected
request checks, so both tokens stop working at once. Entries delete themselves
once every token of the session would have expired anyway.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection

import config
from db import get_revoked_sessions_collection


def revoked_sessions() -> Callable[[], Collection]:
    """The revocation list, fetched only when needed: a request without a
    valid token gets its 401 without touching the database. Tests replace it."""
    return get_revoked_sessions_collection


def session_lifetime() -> timedelta:
    # A verified token can be issued near the end of the limited one's life,
    # so a session can last up to both lifetimes together.
    return timedelta(minutes=config.JWT_EXPIRE_MINUTES + config.VERIFIED_TOKEN_MINUTES)


def revoke(revoked: Collection, sid: str, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    revoked.update_one(
        {"_id": sid},
        {"$setOnInsert": {"revoked_at": now, "expires_at": now + session_lifetime()}},
        upsert=True,
    )


def is_revoked(revoked: Collection, sid: str) -> bool:
    return revoked.count_documents({"_id": sid}, limit=1) > 0
