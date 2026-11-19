import logging
import math
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

import config
from audit import track
from client_address import client_key
from db import get_login_failures_collection, get_rate_limits_collection, get_users_collection
from login_lockout import clear_failures, record_failure, seconds_locked
from rate_limit import count_client_request, count_request
from schemas import LoginRequest, LoginResponse, SignupRequest, SignupResponse, UserPublic
from security import check_password, create_access_token, get_token_claims, hash_password
from sessions import revoke, revoked_sessions

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("voiceguard.auth")


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    request: Request,
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
) -> SignupResponse:
    # Per client first, so one sender is stopped long before the shared
    # backstop (see config.SIGNUP_RATE_LIMIT) could affect anyone else.
    count_client_request(rate_limits, "signup", request, config.SIGNUP_CLIENT_LIMIT)
    count_request(rate_limits, "signup", "all", config.SIGNUP_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

    user_id = ObjectId()
    # Make the token before saving, so a config problem never leaves
    # behind an account the user can't sign up for again.
    token = create_access_token(str(user_id), source="signup")

    user = {
        "_id": user_id,
        "full_name": body.full_name,
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(UTC),
        # Made under the signup-session enrollment rule, so the one-off
        # grace period for older accounts never applies (enrollment_window.py).
        "signup_session_enrollment": True,
    }
    try:
        users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    track("signup", str(user_id))
    return SignupResponse(user=_public(user), access_token=token)


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    users: Collection = Depends(get_users_collection),
    login_failures: Collection = Depends(get_login_failures_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
) -> LoginResponse:
    # Every attempt counts, whichever emails it tries, so one client can't
    # work through a list of accounts.
    count_client_request(rate_limits, "login", request, config.LOGIN_CLIENT_LIMIT)
    email = body.email.lower()
    # Two counts per email: this client's failures (a lock only for this
    # client), and everyone's together (the ceiling, a lock for everyone).
    # A stranger's guesses alone can't lock the owner out, but guessing
    # spread across many addresses still stops.
    # An unknown client (no trusted address) falls back to one shared count
    # for the email: the stricter old rule, safe against guessing.
    this_client = f"client:{client_key(request) or 'unknown'}:{email}"
    everyone = f"account:{email}"
    # A locked email isn't even checked, so guessing can't go on while
    # it's locked.
    locked = max(seconds_locked(login_failures, this_client), seconds_locked(login_failures, everyone))
    if locked:
        track("login_failed", reason="locked")
        raise _locked_out(locked)

    user = users.find_one({"email": email})
    if not check_password(body.password, user["password_hash"] if user else None):
        # Emails with no account are counted and locked the same way, so
        # the answers never give away which emails have accounts.
        window, lockout = config.LOGIN_FAILURE_WINDOW_SECONDS, config.LOGIN_LOCKOUT_SECONDS
        # The account-wide count first: if the second write fails, the
        # ceiling has still counted the guess.
        locked_for_everyone = record_failure(
            login_failures, everyone, config.LOGIN_ACCOUNT_MAX_FAILURES, window, lockout
        )
        locked = max(
            locked_for_everyone,
            record_failure(login_failures, this_client, config.LOGIN_MAX_FAILURES, window, lockout),
        )
        # Our own record may say which it was; the answer never does.
        why = "wrong_password" if user else "unknown_account"
        if locked:
            logger.info("login_locked user=%s", user["_id"] if user else "-")
            track("login_locked", str(user["_id"]) if user else None, reason=why)
            raise _locked_out(locked)
        track("login_failed", str(user["_id"]) if user else None, reason=why)
        # Same words whether the email or the password was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The email or password is incorrect.",
        )

    token = create_access_token(str(user["_id"]), source="login")
    # Only this client's count: the ceiling keeps counting other clients'
    # guesses, so the owner signing in doesn't reset a guesser's progress.
    clear_failures(login_failures, this_client)
    logger.info("login user=%s", user["_id"])
    track("login_succeeded", str(user["_id"]))
    return LoginResponse(user=_public(user), access_token=token)


def _public(user: dict) -> UserPublic:
    created_at = user["created_at"]
    # MongoDB hands dates back without a time zone; they are UTC. Without
    # this, the app would read the time as its own local time.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return UserPublic(
        id=str(user["_id"]),
        full_name=user["full_name"],
        email=user["email"],
        created_at=created_at,
    )


def _locked_out(seconds: int) -> HTTPException:
    minutes = math.ceil(seconds / 60)
    wait = "1 minute" if minutes == 1 else f"{minutes} minutes"
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail=(
            "Too many failed sign-in attempts, so this account is locked for now. "
            f"Please try again in {wait}. If you've forgotten your password, reset it."
        ),
        headers={"Retry-After": str(seconds)},
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    claims: dict = Depends(get_token_claims),
    revoked=Depends(revoked_sessions),
) -> None:
    """End this sign-in on the server: both its limited token and any
    voice-verified one stop working at once."""
    revoke(revoked(), claims["sid"])
    logger.info("logout user=%s", claims["sub"])
    track("logout", claims["sub"])
