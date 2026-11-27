"""Recording a new Voice ID when the voice check keeps failing (#20). See
recovery.py for the rules; enrolling itself is in routers/enroll.py."""

import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.collection import Collection

import config
import switches
from audit import track
from db import (
    get_enrollments_collection,
    get_rate_limits_collection,
    get_recovery_codes_collection,
    get_users_collection,
    get_voice_failures_collection,
    get_voiceprints_collection,
)
from email_sender import EmailSender, get_email_sender
from email_verification import CONFIRMED, check_code, issue_code, require_verified_email
from login_lockout import seconds_locked
from rate_limit import count_client_request, count_request
from recovery import code_email, grant
from schemas import RecoveryCodeRequest, RecoveryCodeSent, RecoveryConfirmed
from security import get_token_claims
from voiceprints import has_voiceprint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recovery", tags=["recovery"])

NOT_PAUSED = "You can record a new Voice ID once voice checks are paused after failed tries."
NO_VOICE_ID = "There's no Voice ID to replace yet."
CODE_SENT = "We've sent a code to your email address."
CODE_NOT_ACCEPTED = "That code didn't work, or it has expired. Please ask for a new one."


# Both pause with enrollment: a confirmed code opens a window for recording,
# which would run out unused while enrollment is paused (the #217 lesson).
@router.post(
    "/code",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecoveryCodeSent,
    dependencies=[Depends(switches.require("enrollment")), Depends(require_verified_email)],
)
def send_recovery_code(
    request: Request,
    claims: dict = Depends(get_token_claims),
    users: Collection = Depends(get_users_collection),
    voiceprints: Collection = Depends(get_voiceprints_collection),
    voice_failures: Collection = Depends(get_voice_failures_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_recovery_codes_collection),
    send: EmailSender = Depends(get_email_sender),
) -> RecoveryCodeSent:
    """Email a code to the account's own address, only while its voice
    checks are paused. Any earlier code stops working."""
    user_id = claims["sub"]
    count_client_request(rate_limits, "recovery_code", request, config.EMAIL_CODE_CLIENT_LIMIT)
    if not has_voiceprint(voiceprints, user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_VOICE_ID)
    if not seconds_locked(voice_failures, user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_PAUSED)
    count_request(rate_limits, "recovery_code", user_id, config.EMAIL_CODE_SEND_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)
    user = users.find_one({"_id": ObjectId(user_id)}, {"email": 1})
    subject, text = code_email(issue_code(codes, user_id))
    # Sent now, not in the background: the person is signed in, so there's
    # nothing to hide, and a failure (503) should reach them.
    send(user["email"], subject, text, "voice_recovery")
    logger.info("recovery_code_sent user=%s", user_id)
    track("recovery_code_sent", user_id)
    return RecoveryCodeSent(detail=CODE_SENT)


@router.post(
    "/verify",
    response_model=RecoveryConfirmed,
    dependencies=[Depends(switches.require("enrollment")), Depends(require_verified_email)],
)
def confirm_recovery_code(
    body: RecoveryCodeRequest,
    request: Request,
    claims: dict = Depends(get_token_claims),
    users: Collection = Depends(get_users_collection),
    enrollments: Collection = Depends(get_enrollments_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_recovery_codes_collection),
) -> RecoveryConfirmed:
    """With the emailed code, this session may record a new Voice ID for a
    while. A wrong, used or expired code all get the same answer."""
    user_id = claims["sub"]
    count_client_request(rate_limits, "recovery_verify", request, config.EMAIL_CODE_CLIENT_LIMIT)
    if check_code(codes, user_id, body.code) != CONFIRMED or not grant(users, user_id, claims["sid"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CODE_NOT_ACCEPTED)
    # Start the new recording from nothing: no samples left over from before.
    enrollments.delete_one({"_id": user_id})
    logger.info("recovery_confirmed user=%s", user_id)
    track("recovery_confirmed", user_id)
    return RecoveryConfirmed(enroll_minutes=config.ENROLL_WINDOW_MINUTES)
