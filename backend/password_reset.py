"""Resetting a forgotten password by email (#109).

Asking for a reset always gets the same answer, whether or not the address
has an account. If it has one, we email a link holding a random token
(256 bits). The link works once, for PASSWORD_RESET_MINUTES, and asking again
makes earlier links stop working.

Only a hash of the token is stored (SHA-256: the token is far too random to
guess, so a plain hash is enough). Someone reading the database can't use a
link from it.

The token travels after a "#" in the link, so browsers never send it to a
server: it stays out of Vercel's request logs and Referer headers. The reset
screen reads it from the page address and posts it to the API.

Setting the new password uses the token up, along with any other link for
the account, clears the sign-in lockout, and ends every session the account
already had (sessions.revoke_all), so a stolen session doesn't outlive the
password it came from.

Neither the token, the link nor the new password is ever logged.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection

import config

TOKEN_BYTES = 32


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(resets: Collection, user_id: str, now: datetime | None = None) -> str:
    """Make a new reset token for the account, replacing any earlier one.
    Returns the token, to be emailed; only its hash is kept."""
    now = now or datetime.now(UTC)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    # Only the newest link works.
    resets.delete_many({"user_id": user_id})
    resets.insert_one(
        {
            "_id": _hash(token),
            "user_id": user_id,
            "expires_at": now + timedelta(minutes=config.PASSWORD_RESET_MINUTES),
        }
    )
    return token


def find_token(resets: Collection, token: str, now: datetime | None = None) -> str | None:
    """The account a token belongs to, if it's still usable; otherwise None.
    Doesn't use it up: the new password is checked first, so a refused
    password doesn't cost the user their link."""
    now = now or datetime.now(UTC)
    record = resets.find_one({"_id": _hash(token), "expires_at": {"$gt": now}})
    return record["user_id"] if record else None


def use_token(resets: Collection, token: str, now: datetime | None = None) -> str | None:
    """Use the token up, and every other link for the same account. Returns
    the account, or None if it was no longer usable (expired, or another
    request used it at the same moment)."""
    now = now or datetime.now(UTC)
    # One step: of two requests with the same link, only one gets it.
    record = resets.find_one_and_delete({"_id": _hash(token), "expires_at": {"$gt": now}})
    if record is None:
        return None
    resets.delete_many({"user_id": record["user_id"]})
    return record["user_id"]


def reset_link(token: str) -> str:
    return f"{config.PASSWORD_RESET_URL}#token={token}"


def reset_email(token: str) -> tuple[str, str]:
    """The subject and plain-text body of the email with the link."""
    subject = "Reset your VoiceGuard password"
    text = (
        "Someone (hopefully you) asked to reset the password for your VoiceGuard account.\n\n"
        f"To choose a new password, open this link:\n{reset_link(token)}\n\n"
        f"It works once and expires in {config.PASSWORD_RESET_MINUTES} minutes. "
        "Setting a new password signs your account out everywhere.\n\n"
        "If you didn't ask for this, you can ignore this email: your password stays the same."
    )
    return subject, text
