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
from audit import track
from client_address import client_key
from db import (
    get_email_codes_collection,
    get_login_failures_collection,
    get_rate_limits_collection,
    get_users_collection,
)
from email_sender import EmailSender, EmailUnavailable, get_email_sender, get_optional_email_sender
from email_verification import (
    CONFIRMED,
    WRONG,
    check_code,
    code_email,
    is_unverified,
    issue_code,
    mark_verified,
    unverified_fields,
)
from login_lockout import clear_failures, record_failure, seconds_locked
from rate_limit import RateLimited, count_client_request, count_request
from schemas import (
    EmailCodeRequest,
    EmailVerifiedResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    UserPublic,
)
from security import (
    _bearer,
    check_password,
    claims_for,
    create_access_token,
    get_token_claims,
    hash_password,
    request_token,
)
from session_cookie import clear_session_cookie, set_session_cookie
from sessions import revoke, revoked_sessions

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("voiceguard.auth")


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    response: Response,
    request: Request,
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_email_codes_collection),
    send: EmailSender | None = Depends(get_optional_email_sender),
) -> SignupResponse:
    # Per client first, so one sender is stopped long before the shared
    # backstop (see config.SIGNUP_RATE_LIMIT) could affect anyone else.
    count_client_request(rate_limits, "signup", request, config.SIGNUP_CLIENT_LIMIT)
    count_request(rate_limits, "signup", "all", config.SIGNUP_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

    user_id = ObjectId()
    # Make the token before saving, so a config problem never leaves
    # behind an account the user can't sign up for again.
    token = create_access_token(str(user_id), source="signup")

    now = datetime.now(UTC)
    email = body.email.lower()
    user = {
        "_id": user_id,
        "full_name": body.full_name,
        "email": email,
        "password_hash": hash_password(body.password),
        "created_at": now,
        # Made under the signup-session enrollment rule, so the one-off
        # grace period for older accounts never applies (enrollment_window.py).
        "signup_session_enrollment": True,
    }
    verify_email = config.EMAIL_VERIFICATION_REQUIRED
    if verify_email:
        # Starts unverified, and is deleted if never confirmed (#110).
        user.update(unverified_fields(now))
    try:
        users.insert_one(user)
    except DuplicateKeyError:
        # An account that never confirmed this address can't keep it from
        # its real owner: the new signup replaces it. A confirmed one (or
        # one from before verification) still gets today's answer (#111
        # will stop that answer saying the address has an account).
        if not _replace_unverified(users, codes, email):
            raise _email_taken()
        try:
            users.insert_one(user)
        except DuplicateKeyError:
            # Someone else signed up with it at the same moment.
            raise _email_taken()

    if verify_email:
        # The account exists either way; if the email can't go now, the
        # user asks for it again from the "check your email" screen.
        try:
            _send_code(codes, rate_limits, send, str(user_id), email)
        except (EmailUnavailable, RateLimited) as exc:
            logger.warning("email_code_not_sent user=%s reason=%s", user_id, type(exc).__name__)
    track("signup", str(user_id))
    return SignupResponse(user=_public(user), access_token=_issue(response, token))


def _email_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An account with this email already exists.",
    )


def _replace_unverified(users: Collection, codes: Collection, email: str) -> bool:
    """Delete the account holding `email` if it never confirmed it. True if
    one was deleted. It can't have a voiceprint: unconfirmed accounts can't
    set up Voice ID."""
    old = users.find_one_and_delete({"email": email, "email_verified": False})
    if old is None:
        return False
    codes.delete_one({"_id": str(old["_id"])})
    logger.info("unverified_account_replaced user=%s", old["_id"])
    return True


def _send_code(
    codes: Collection, rate_limits: Collection, send: EmailSender | None, user_id: str, email: str
) -> None:
    """Email the account a new code. Counted against its allowance first,
    so a refused request doesn't send anything."""
    if send is None:
        raise EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set.")
    count_request(rate_limits, "email_code", user_id, config.EMAIL_CODE_SEND_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)
    subject, text = code_email(issue_code(codes, user_id))
    send(email, subject, text, "email_verification")
    logger.info("email_code_sent user=%s", user_id)


@router.post("/email/code", status_code=status.HTTP_204_NO_CONTENT)
def send_email_code(
    claims: dict = Depends(get_token_claims),
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_email_codes_collection),
    send: EmailSender = Depends(get_email_sender),
) -> None:
    """Email a new confirmation code; any earlier code stops working.
    Limited to EMAIL_CODE_SEND_LIMIT per account per window."""
    user_id = claims["sub"]
    user = _find_user(users, user_id)
    if not is_unverified(user):
        raise _already_confirmed()
    _send_code(codes, rate_limits, send, user_id, user["email"])


@router.post("/email/verify", response_model=EmailVerifiedResponse)
def confirm_email(
    body: EmailCodeRequest,
    claims: dict = Depends(get_token_claims),
    users: Collection = Depends(get_users_collection),
    codes: Collection = Depends(get_email_codes_collection),
) -> EmailVerifiedResponse:
    """Confirm the email address with the emailed code. This sign-in may
    then set up Voice ID for a while (enrollment_window.py)."""
    user_id = claims["sub"]
    user = _find_user(users, user_id)
    if not is_unverified(user):
        raise _already_confirmed()
    outcome = check_code(codes, user_id, body.code)
    if outcome == WRONG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code isn't right. Please check the email and try again.",
        )
    if outcome != CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code has expired or has been tried too many times. Please ask for a new one.",
        )
    mark_verified(users, user_id, claims["sid"])
    logger.info("email_verified user=%s", user_id)
    return EmailVerifiedResponse(user=_public(_find_user(users, user_id)))


def _find_user(users: Collection, user_id: str) -> dict:
    user = users.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    if user is None:
        # The token is genuine but the account is gone (for example, an
        # unconfirmed one that was deleted or replaced).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _already_confirmed() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your email address is already confirmed.")


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
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
        email_verified=not is_unverified(user),
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
    track("logout", claims["sub"])
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(done)
    return done
