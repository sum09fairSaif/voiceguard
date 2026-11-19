"""Confirming the email address given at signup (#110).

A new account starts unverified, and we email it a 6-digit code. Typing the
code into the app (in the same tab, so the session carries on) confirms the
address. Until then the account can't set up Voice ID or run voice checks,
so nobody can take over an address they don't own.

The code:
- is stored only as a keyed hash (HMAC with JWT_SECRET), so the database
  alone can't give it away, not even by trying all million codes;
- works once, for EMAIL_CODE_MINUTES, and EMAIL_CODE_MAX_TRIES wrong tries
  use it up;
- is replaced by any newer one: asking again makes the old code stop working.

Accounts made before this existed have no `email_verified` field and count
as verified, so they keep working exactly as before. Unverified accounts are
deleted after UNVERIFIED_ACCOUNT_HOURS (a TTL index on users, see db.py), and
a new signup for the same address replaces one straight away (routers/auth.py).

The code itself is never logged.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from pymongo import ReturnDocument
from pymongo.collection import Collection

import config
from db import get_users_collection
from security import get_current_user_id

CODE_DIGITS = 6

# The outcomes of checking a code.
CONFIRMED = "confirmed"
WRONG = "wrong"
# Expired, used up by wrong tries, already used, or never sent: the user
# needs a new code either way.
NO_CODE = "no_code"

NOT_CONFIRMED = "Please confirm your email address first. We sent a code to it when you signed up."


def is_unverified(user: dict | None) -> bool:
    """Only accounts made with verification on carry `email_verified: False`.
    Older accounts have no such field and count as verified."""
    return user is not None and user.get("email_verified") is False


def unverified_fields(now: datetime) -> dict:
    """Added to a new account when verification is on."""
    return {
        "email_verified": False,
        "unverified_expires_at": now + timedelta(hours=config.UNVERIFIED_ACCOUNT_HOURS),
    }


def _hash(user_id: str, code: str) -> str:
    if not config.JWT_SECRET:
        raise config.NotConfigured("JWT_SECRET is not set. Add it to your .env file.")
    # Keyed and tied to the account: a code copied onto another account's
    # record wouldn't match.
    message = f"email-code:{user_id}:{code}".encode()
    return hmac.new(config.JWT_SECRET.encode(), message, hashlib.sha256).hexdigest()


def issue_code(codes: Collection, user_id: str, now: datetime | None = None) -> str:
    """Make a new code for the account, replacing any earlier one. Returns
    the code, to be emailed; only its hash is kept."""
    now = now or datetime.now(UTC)
    code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
    codes.replace_one(
        {"_id": user_id},
        {
            "code_hash": _hash(user_id, code),
            "tries": 0,
            "expires_at": now + timedelta(minutes=config.EMAIL_CODE_MINUTES),
        },
        upsert=True,
    )
    return code


def check_code(codes: Collection, user_id: str, code: str, now: datetime | None = None) -> str:
    """CONFIRMED (and the code is used up), WRONG, or NO_CODE."""
    now = now or datetime.now(UTC)
    # Count the try first, in one step, so many guesses sent at the same
    # moment can't all slip under the limit.
    record = codes.find_one_and_update(
        {"_id": user_id, "expires_at": {"$gt": now}, "tries": {"$lt": config.EMAIL_CODE_MAX_TRIES}},
        {"$inc": {"tries": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if record is None:
        return NO_CODE
    expected = record["code_hash"]
    if not hmac.compare_digest(expected, _hash(user_id, code)):
        return WRONG
    # Single use: only the request that removes the code succeeds.
    if codes.delete_one({"_id": user_id, "code_hash": expected}).deleted_count != 1:
        return NO_CODE
    return CONFIRMED


def mark_verified(users: Collection, user_id: str, session_id: str, now: datetime | None = None) -> bool:
    """Record the confirmation, and which sign-in did it: that session may
    set up Voice ID for a while afterwards (enrollment_window.py). False if
    the account was already confirmed or is gone."""
    now = now or datetime.now(UTC)
    if not ObjectId.is_valid(user_id):
        return False
    result = users.update_one(
        {"_id": ObjectId(user_id), "email_verified": False},
        {
            "$set": {"email_verified": True, "email_verified_at": now, "email_verified_sid": session_id},
            # Confirmed accounts are kept: drop the field the TTL index uses.
            "$unset": {"unverified_expires_at": ""},
        },
    )
    return result.modified_count == 1


def code_email(code: str) -> tuple[str, str]:
    """The subject and plain-text body of the email with the code."""
    subject = "Your VoiceGuard confirmation code"
    text = (
        f"Your VoiceGuard confirmation code is {code}\n\n"
        f"Type it into the VoiceGuard app to confirm your email address. "
        f"It works once and expires in {config.EMAIL_CODE_MINUTES} minutes.\n\n"
        "If you didn't create a VoiceGuard account, you can ignore this email: "
        "the account will be deleted unless the code is used."
    )
    return subject, text


def require_verified_email(
    user_id: str = Depends(get_current_user_id),
    users: Collection = Depends(get_users_collection),
) -> None:
    """For Voice ID setup and voice checks: refuse accounts that haven't
    confirmed their email yet. Older accounts (no field) pass."""
    user = users.find_one({"_id": ObjectId(user_id)}, {"email_verified": 1}) if ObjectId.is_valid(user_id) else None
    if is_unverified(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_CONFIRMED)
