"""Recording a new Voice ID after the voice check keeps failing (#20).

After VOICE_MAX_FAILURES rejected checks, voice checks pause for this account
(voice_attempts.py). While they're paused, the signed-in session (the
password) can ask for a 6-digit code at the account's own address. The code
proves the inbox; with both, that one session may record a new Voice ID for
ENROLL_WINDOW_MINUTES (enrollment_window.py).

The code only ever unlocks re-recording, never the account: the person still
gets in by passing a voice check with the new Voice ID. Email isn't allowed
as an authentication factor (NIST SP 800-63B), so it rebinds the voice
instead of standing in for it. The old voiceprint keeps working until the
new one is complete; when it's replaced, every session ends and the owner
is told by email.

Codes come from email_verification.py (keyed hash, single use, limited
tries, EMAIL_CODE_MINUTES), kept in their own collection, so a signup code
can't be used here or the other way round. Never logged.
"""

from datetime import UTC, datetime, timedelta

from bson import ObjectId
from pymongo.collection import Collection

import config


def grant(users: Collection, user_id: str, session_id: str, now: datetime | None = None) -> bool:
    """Let this session record a new Voice ID for a while. False if the
    account is gone."""
    now = now or datetime.now(UTC)
    if not ObjectId.is_valid(user_id):
        return False
    result = users.update_one({"_id": ObjectId(user_id)}, {"$set": {"recovery_sid": session_id, "recovery_at": now}})
    return result.matched_count == 1


def clear_grant(users: Collection, user_id: str) -> None:
    if ObjectId.is_valid(user_id):
        users.update_one({"_id": ObjectId(user_id)}, {"$unset": {"recovery_sid": "", "recovery_at": ""}})


def _utc(moment: datetime) -> datetime:
    # MongoDB hands dates back without a time zone; they are UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def in_recovery_session(claims: dict, user: dict | None, now: datetime | None = None) -> bool:
    """Whether this session confirmed a recovery code, recently enough."""
    if user is None:
        return False
    granted_at = user.get("recovery_at")
    session_id = claims.get("sid")
    if granted_at is None or session_id is None or session_id != user.get("recovery_sid"):
        return False
    now = now or datetime.now(UTC)
    # A grant time in the future (clock trouble) never opens the window.
    return timedelta(0) <= now - _utc(granted_at) <= timedelta(minutes=config.ENROLL_WINDOW_MINUTES)


def code_email(code: str) -> tuple[str, str]:
    """The subject and plain-text body of the email with the code."""
    subject = "Your VoiceGuard code to record a new Voice ID"
    text = (
        f"Your VoiceGuard code is {code}\n\n"
        "Someone signed in to your account with your password and asked to record a new "
        "Voice ID, because the voice check kept failing. Type the code into the VoiceGuard "
        f"app to go ahead. It works once and expires in {config.EMAIL_CODE_MINUTES} minutes.\n\n"
        "If this wasn't you, don't share the code with anyone, and change your password: "
        'use "Forgot password?" on the sign-in screen. Your Voice ID stays as it is '
        "unless the code is used."
    )
    return subject, text


def replaced_email() -> tuple[str, str]:
    """Sent once a new Voice ID has replaced the old one."""
    subject = "Your VoiceGuard Voice ID was replaced"
    text = (
        "A new Voice ID was just recorded for your VoiceGuard account, after a code sent to "
        "this address was used. Your old one no longer works, and every device was signed out.\n\n"
        "If this was you, sign in again and use your new Voice ID.\n\n"
        'If it wasn\'t you, change your password straight away: use "Forgot password?" on the '
        "sign-in screen, then tell the VoiceGuard team."
    )
    return subject, text
