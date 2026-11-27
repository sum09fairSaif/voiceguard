"""Ending sign-in sessions on the server.

Each sign-in (signup or password) starts a session with its own id (`sid`),
carried by its limited token and by the voice-verified token an approved check
gives it. Signing out puts the sid on a revocation list that every protected
request checks, so both tokens stop working at once. Entries delete themselves
once every token of the session would have expired anyway.

A password reset ends every session of the account at once (#109): one entry,
"user:<id>", records when, and any token issued up to then stops working.
Tokens issued afterwards (the user signing in with the new password) aren't
affected.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

import config
from db import get_revoked_sessions_collection


def revoked_sessions() -> Callable[[], Collection]:
    """The revocation list, fetched only when needed: a request without a
    valid token gets its 401 without touching the database. Tests replace it."""
    return get_revoked_sessions_collection


# Revocations are kept at least this long, so shortening the token settings
# later can't let a revocation expire before a token issued under the old,
# longer ones. A few bytes per sign-out.
MINIMUM_KEEP = timedelta(hours=24)


def session_lifetime() -> timedelta:
    # A verified token can be issued near the end of the limited one's life,
    # so a session can last up to both lifetimes together.
    return timedelta(minutes=config.JWT_EXPIRE_MINUTES + config.VERIFIED_TOKEN_MINUTES)


def keep_for() -> timedelta:
    return max(session_lifetime(), MINIMUM_KEEP)


def revoke(revoked: Collection, sid: str, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    try:
        revoked.update_one(
            {"_id": sid},
            {"$setOnInsert": {"revoked_at": now, "expires_at": now + keep_for()}},
            upsert=True,
        )
    except DuplicateKeyError:
        # Two sign-outs of one session at the same moment: the other one
        # recorded it, which is all that's needed.
        pass


def _user_key(user_id: str) -> str:
    # Session ids are hex, so this can't clash with one.
    return f"user:{user_id}"


def revoke_all(revoked: Collection, user_id: str, now: datetime | None = None) -> None:
    """End every session of this account that has started by now."""
    now = now or datetime.now(UTC)
    # $max: a later reset moves the line forward; one recorded at the same
    # moment by another request can't move it back.
    revoked.update_one(
        {"_id": _user_key(user_id)},
        {"$max": {"before": now, "expires_at": now + keep_for()}},
        upsert=True,
    )


def is_revoked(revoked: Collection, sid: str, user_id: str | None = None, issued_at: float | None = None) -> bool:
    """True if this session was signed out, or (given the account and when
    the token was issued) all the account's sessions were ended after it
    was issued. One database lookup either way."""
    keys = [sid] if user_id is None else [sid, _user_key(user_id)]
    for entry in revoked.find({"_id": {"$in": keys}}):
        if entry["_id"] == sid:
            return True
        # Token times are whole seconds, rounded down: a token from the same
        # second as the reset counts as before it. A sign-in in that second
        # just has to be repeated; a stolen token never survives.
        before = entry["before"]
        before = before if before.tzinfo else before.replace(tzinfo=UTC)
        if issued_at is None or issued_at <= before.timestamp():
            return True
    return False
