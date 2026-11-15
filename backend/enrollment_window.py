"""Who may record a voiceprint, and when.

Enrollment sets the voice every later sign-in is compared to, so it must come
from the person who created the account. Until email verification and account
recovery exist, the only safe moment is the signup session: a token from
signup, shortly after the account was created. A one-off grace period lets
accounts made before this rule (that never enrolled) enroll after signing in,
until a cut-off.
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
    now = now or datetime.now(UTC)
    created = _utc(user["created_at"])

    in_signup_session = claims.get("src") == "signup" and now - created <= timedelta(
        minutes=config.ENROLL_WINDOW_MINUTES
    )
    grace = config.ENROLL_GRACE_UNTIL
    in_grace_period = grace is not None and created < grace and now < grace
    return in_signup_session or in_grace_period
