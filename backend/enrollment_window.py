"""Who may record a voiceprint, and when.

Enrollment sets the voice every later sign-in is compared to, so it must come
from the person who created the account. The safe moments are the signup
session (a token from signup, shortly after the account was created) and the
sign-in that confirmed the email address (#110), shortly after confirming. An
account that hasn't confirmed its address can't enroll at all. A one-off grace period lets
accounts made before this rule (that never enrolled) enroll after signing in,
until a cut-off. Accounts made since are flagged at signup and never get it.
"""

from datetime import UTC, datetime, timedelta

import config


def _utc(moment: datetime) -> datetime:
    # MongoDB hands dates back without a time zone; they are UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def may_enroll(claims: dict, user: dict | None, now: datetime | None = None) -> bool:
    """Whether this session may add enrollment samples. Fails closed: no
    account record means no."""
    if user is None or "created_at" not in user:
        return False
    # An address not yet confirmed (#110) can't set the voice at all.
    if user.get("email_verified") is False:
        return False
    now = now or datetime.now(UTC)
    window = timedelta(minutes=config.ENROLL_WINDOW_MINUTES)
    created = _utc(user["created_at"])

    age = now - created
    # A creation time in the future (clock trouble) never opens the window.
    in_signup_session = claims.get("src") == "signup" and timedelta(0) <= age <= window
    # The sign-in that confirmed the email (#110) may also enroll for a
    # while afterwards: the code proves the inbox, the password the account.
    # Covers a user who closed the signup tab and signed in again to confirm.
    confirmed_at = user.get("email_verified_at")
    in_confirming_session = (
        confirmed_at is not None
        and claims.get("sid") is not None
        and claims.get("sid") == user.get("email_verified_sid")
        and timedelta(0) <= now - _utc(confirmed_at) <= window
    )
    # The grace period is only for accounts made before this rule existed:
    # every account made since carries the flag set at signup.
    grace = config.ENROLL_GRACE_UNTIL
    legacy = not user.get("signup_session_enrollment")
    in_grace_period = legacy and grace is not None and created < grace and now < grace
    return in_signup_session or in_confirming_session or in_grace_period
