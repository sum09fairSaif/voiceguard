import logging
import math
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

import config
from db import get_login_failures_collection, get_rate_limits_collection, get_users_collection
from login_lockout import clear_failures, record_failure, seconds_locked
from rate_limit import count_request
from schemas import LoginRequest, LoginResponse, SignupRequest, SignupResponse, UserPublic
from security import _bearer, check_password, claims_for, create_access_token, hash_password, request_token
from session_cookie import clear_session_cookie, set_session_cookie
from sessions import revoke, revoked_sessions

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("voiceguard.auth")


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    response: Response,
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
) -> SignupResponse:
    # One count for everyone (see config.SIGNUP_RATE_LIMIT).
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

    return SignupResponse(user=_public(user), access_token=_issue(response, token))


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    users: Collection = Depends(get_users_collection),
    login_failures: Collection = Depends(get_login_failures_collection),
) -> LoginResponse:
    email = body.email.lower()
    # A locked email isn't even checked, so guessing can't go on while
    # it's locked.
    locked = seconds_locked(login_failures, email)
    if locked:
        raise _locked_out(locked)

    user = users.find_one({"email": email})
    if not check_password(body.password, user["password_hash"] if user else None):
        # Emails with no account are counted and locked the same way, so
        # the answers never give away which emails have accounts.
        locked = record_failure(
            login_failures,
            email,
            config.LOGIN_MAX_FAILURES,
            config.LOGIN_FAILURE_WINDOW_SECONDS,
            config.LOGIN_LOCKOUT_SECONDS,
        )
        if locked:
            logger.info("login_locked user=%s", user["_id"] if user else "-")
            raise _locked_out(locked)
        # Same words whether the email or the password was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The email or password is incorrect.",
        )

    token = create_access_token(str(user["_id"]), source="login")
    clear_failures(login_failures, email)
    logger.info("login user=%s", user["_id"])
    return LoginResponse(user=_public(user), access_token=_issue(response, token))


def _issue(response: Response, token: str) -> str | None:
    """Set the new limited token as the HttpOnly cookie; return it for the
    body only while TOKEN_IN_RESPONSE_BODY is on."""
    set_session_cookie(response, token, config.JWT_EXPIRE_MINUTES)
    return token if config.TOKEN_IN_RESPONSE_BODY else None


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
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    revoked=Depends(revoked_sessions),
) -> Response:
    """End this sign-in on the server: both its limited token and any
    voice-verified one stop working at once. The cookie is cleared whatever
    happens, even for a token that has already expired or been signed out."""
    token = request_token(request, credentials)
    try:
        if token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first.")
        claims = claims_for(token, revoked)
    except HTTPException as exc:
        refused = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
        clear_session_cookie(refused)
        return refused
    revoke(revoked(), claims["sid"])
    logger.info("logout user=%s", claims["sub"])
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(done)
    return done
