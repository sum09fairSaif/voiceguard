"""Forgot password: ask for a reset link, then set a new password with it
(#109). See password_reset.py for how the links work."""

import hashlib
import logging

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pymongo.collection import Collection

import config
from db import (
    get_login_failures_collection,
    get_password_resets_collection,
    get_rate_limits_collection,
    get_users_collection,
)
from email_sender import EmailSender, EmailUnavailable, get_email_sender
from login_lockout import clear_failures
from password_policy import password_problem
from password_reset import find_token, issue_token, reset_email, use_token
from rate_limit import count_request
from schemas import PASSWORD_PROBLEMS, PasswordResetConfirm, PasswordResetRequest
from security import hash_password
from sessions import revoke_all, revoked_sessions

router = APIRouter(prefix="/api/auth/password-reset", tags=["auth"])

logger = logging.getLogger("voiceguard.auth")

# The same answer for every address, so it never says which have accounts.
SENT = "If there's an account with that email, we've sent it a link to reset the password."
LINK_NOT_USABLE = "This reset link has expired or has already been used. Please ask for a new one."


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def request_reset(
    body: PasswordResetRequest,
    background: BackgroundTasks,
    users: Collection = Depends(get_users_collection),
    resets: Collection = Depends(get_password_resets_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    send: EmailSender = Depends(get_email_sender),
) -> dict:
    """Email a reset link if the address has an account. The answer is the
    same either way, and the email is sent after the answer, so how long the
    answer takes doesn't give it away either."""
    email = body.email.lower()
    # Both limits count every request, account or not.
    count_request(
        rate_limits, "password_reset", "all", config.PASSWORD_RESET_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS
    )
    count_request(
        rate_limits,
        "password_reset_email",
        # Hashed, like the sign-in lockout: the counters never keep addresses.
        hashlib.sha256(email.encode("utf-8")).hexdigest(),
        config.PASSWORD_RESET_EMAIL_LIMIT,
        config.RATE_LIMIT_WINDOW_SECONDS,
    )

    user = users.find_one({"email": email}, {"_id": 1})
    if user is not None:
        user_id = str(user["_id"])
        subject, text = reset_email(issue_token(resets, user_id))
        background.add_task(_send_reset_email, send, email, subject, text, user_id)
    return {"detail": SENT}


def _send_reset_email(send: EmailSender, email: str, subject: str, text: str, user_id: str) -> None:
    # After the answer has gone: a failure can only be logged. The user
    # sees no email and asks again.
    try:
        send(email, subject, text, "password_reset")
        logger.info("password_reset_sent user=%s", user_id)
    except EmailUnavailable as exc:
        logger.warning("password_reset_not_sent user=%s reason=%s", user_id, exc)


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_reset(
    body: PasswordResetConfirm,
    users: Collection = Depends(get_users_collection),
    resets: Collection = Depends(get_password_resets_collection),
    login_failures: Collection = Depends(get_login_failures_collection),
    revoked=Depends(revoked_sessions),
) -> None:
    """Set a new password with the emailed link. The link, and any other
    link for the account, stops working; the sign-in lockout is cleared;
    every session the account had is ended. The user then signs in."""
    user_id = find_token(resets, body.token)
    user = users.find_one({"_id": ObjectId(user_id)}) if user_id and ObjectId.is_valid(user_id) else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=LINK_NOT_USABLE)

    # The signup rules that need the account's email, answered the same
    # way signup answers them. Checked before the link is used up.
    problem = password_problem(body.password, user["email"])
    if problem:
        raise RequestValidationError(
            [{"type": f"password_{problem}", "loc": ("body", "password"), "msg": PASSWORD_PROBLEMS[problem]}]
        )

    password_hash = hash_password(body.password)
    if use_token(resets, body.token) != user_id:
        # Another request used the link in the meantime.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=LINK_NOT_USABLE)
    users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": password_hash}})
    clear_failures(login_failures, user["email"])
    revoke_all(revoked(), user_id)
    logger.info("password_reset user=%s", user_id)
