import hashlib
import logging
import math
import uuid
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

import config
import switches
from audit import track
from client_address import client_key
from db import (
    get_email_codes_collection,
    get_login_failures_collection,
    get_rate_limits_collection,
    get_users_collection,
)
from email_sender import EmailSender, EmailUnavailable, get_optional_email_sender
from email_verification import (
    CONFIRMED,
    NO_CODE,
    account_exists_email,
    check_code,
    code_email,
    is_unverified,
    issue_code,
    mark_verified,
    unverified_fields,
)
from login_lockout import clear_failures, record_failure, seconds_locked
from rate_limit import count_client_request, count_request
from schemas import (
    EmailAddressRequest,
    EmailCodeRequest,
    LoginRequest,
    LoginResponse,
    SignupAccepted,
    SignupRequest,
    SignupResponse,
    UserPublic,
)
from security import (
    _bearer,
    check_password,
    claims_for,
    create_access_token,
    hash_password,
    request_token,
)
from session_cookie import clear_session_cookie, set_session_cookie
from sessions import revoke, revoked_sessions

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("voiceguard.auth")


# Signup's answer while email confirmation is on, and asking for a new code:
# the same for every address, account or not (#111).
CHECK_EMAIL = "Check your email. If the address can be used, we've sent it a code to confirm it."
CODE_NOT_ACCEPTED = "That code didn't work. Please check the email, or ask for a new code."


@router.post(
    "/signup",
    response_model=SignupResponse | SignupAccepted,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(switches.require("signups"))],
)
def signup(
    body: SignupRequest,
    response: Response,
    request: Request,
    background: BackgroundTasks,
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_email_codes_collection),
    send: EmailSender | None = Depends(get_optional_email_sender),
) -> SignupResponse | SignupAccepted:
    # Per client first, so one sender is stopped long before the shared
    # backstop (see config.SIGNUP_RATE_LIMIT) could affect anyone else.
    count_client_request(rate_limits, "signup", request, config.SIGNUP_CLIENT_LIMIT)
    count_request(rate_limits, "signup", "all", config.SIGNUP_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)
    if config.EMAIL_VERIFICATION_REQUIRED:
        response.status_code = status.HTTP_202_ACCEPTED
        return _neutral_signup(body, background, rate_limits, users, codes, send)

    user_id = ObjectId()
    # Make the token before saving, so a config problem never leaves
    # behind an account the user can't sign up for again.
    token = create_access_token(str(user_id), source="signup")
    user = _new_account(user_id, body.full_name, body.email.lower(), hash_password(body.password), verified=True)
    try:
        users.insert_one(user)
    except DuplicateKeyError:
        # Only while confirmation is off: signup then answers with a
        # sign-in, so it can't hide that the address is taken.
        if not _replace_unverified(users, codes, user["email"]):
            raise _email_taken()
        try:
            users.insert_one(user)
        except DuplicateKeyError:
            # Someone else signed up with it at the same moment.
            raise _email_taken()
    track("signup", str(user_id))
    return SignupResponse(user=_public(user), access_token=_issue(response, token))


def _neutral_signup(
    body: SignupRequest,
    background: BackgroundTasks,
    rate_limits: Collection,
    users: Collection,
    codes: Collection,
    send: EmailSender | None,
) -> SignupAccepted:
    """Signup with email confirmation on (#111). The answer is the same
    whether or not the address has an account, and gives no sign-in: that
    comes with the emailed code. A new address gets a code; one that has an
    account gets a notice instead. Everything that depends on which happens
    after the answer has gone, so its timing doesn't tell either."""
    email = body.email.lower()
    # Counted for every address, so the limit says nothing either.
    count_request(
        rate_limits, "email_code", _address_key(email), config.EMAIL_CODE_SEND_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS
    )
    if send is None:
        # The same for everyone, and nothing to sign in with until it works.
        raise EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set.")
    # bcrypt is most of the work, so it's done here for every address.
    password_hash = hash_password(body.password)
    background.add_task(_finish_signup, users, codes, send, body.full_name, email, password_hash)
    return SignupAccepted(detail=CHECK_EMAIL)


def _finish_signup(
    users: Collection, codes: Collection, send: EmailSender, full_name: str, email: str, password_hash: str
) -> None:
    # After the answer: a failure can only be logged; the user asks again.
    user_id = ObjectId()
    user = _new_account(user_id, full_name, email, password_hash, verified=False)
    try:
        users.insert_one(user)
    except DuplicateKeyError:
        # An account that never confirmed this address can't keep it from
        # its real owner: the new signup replaces it.
        if not _replace_unverified(users, codes, email):
            _email_owner(send, email)
            return
        try:
            users.insert_one(user)
        except DuplicateKeyError:
            logger.info("signup_raced")
            return
    track("signup", str(user_id))
    _email_code(codes, send, str(user_id), email)


def _new_account(user_id: ObjectId, full_name: str, email: str, password_hash: str, verified: bool) -> dict:
    now = datetime.now(UTC)
    user = {
        "_id": user_id,
        "full_name": full_name,
        "email": email,
        "password_hash": password_hash,
        "created_at": now,
        # Made under the signup-session enrollment rule, so the one-off
        # grace period for older accounts never applies (enrollment_window.py).
        "signup_session_enrollment": True,
    }
    if not verified:
        # Starts unverified, and is deleted if never confirmed (#110).
        user.update(unverified_fields(now))
    return user


def _address_key(email: str) -> str:
    # Hashed, like the sign-in lockout: the counters never keep addresses.
    return hashlib.sha256(email.encode("utf-8")).hexdigest()


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


def _email_code(codes: Collection, send: EmailSender, user_id: str, email: str) -> None:
    """Email the account a new code; any earlier one stops working."""
    subject, text = code_email(issue_code(codes, user_id))
    try:
        send(email, subject, text, "email_verification")
        logger.info("email_code_sent user=%s", user_id)
    except EmailUnavailable as exc:
        logger.warning("email_code_not_sent user=%s reason=%s", user_id, type(exc).__name__)


def _email_owner(send: EmailSender, email: str) -> None:
    """Tell an address that already has an account that someone tried to
    sign up with it. Logged without the address or account."""
    subject, text = account_exists_email()
    try:
        send(email, subject, text, "account_exists")
        logger.info("account_exists_notice_sent")
    except EmailUnavailable as exc:
        logger.warning("account_exists_notice_not_sent reason=%s", type(exc).__name__)


@router.post("/email/code", status_code=status.HTTP_202_ACCEPTED, response_model=SignupAccepted)
def send_email_code(
    body: EmailAddressRequest,
    request: Request,
    background: BackgroundTasks,
    users: Collection = Depends(get_users_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    codes: Collection = Depends(get_email_codes_collection),
    send: EmailSender | None = Depends(get_optional_email_sender),
) -> SignupAccepted:
    """Email a new confirmation code if the address has an account waiting
    for one; any earlier code stops working. The same answer either way."""
    count_client_request(rate_limits, "email_code", request, config.EMAIL_CODE_CLIENT_LIMIT)
    email = body.email.lower()
    count_request(
        rate_limits, "email_code", _address_key(email), config.EMAIL_CODE_SEND_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS
    )
    if send is None:
        raise EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set.")
    background.add_task(_resend_code, users, codes, send, email)
    return SignupAccepted(detail=CHECK_EMAIL)


def _resend_code(users: Collection, codes: Collection, send: EmailSender, email: str) -> None:
    user = users.find_one({"email": email, "email_verified": False}, {"_id": 1})
    if user is not None:
        _email_code(codes, send, str(user["_id"]), email)


@router.post("/email/verify", response_model=SignupResponse)
def confirm_email(
    body: EmailCodeRequest,
    response: Response,
    request: Request,
    users: Collection = Depends(get_users_collection),
    codes: Collection = Depends(get_email_codes_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
) -> SignupResponse:
    """Confirm the address with the emailed code, and start the session:
    the code proves the inbox. This session may then set up Voice ID for a
    while (enrollment_window.py). Every failure gets the same answer, so it
    never says whether the address has an account."""
    count_client_request(rate_limits, "email_verify", request, config.EMAIL_CODE_CLIENT_LIMIT)
    user = users.find_one({"email": body.email.lower(), "email_verified": False}, {"_id": 1})
    user_id = str(user["_id"]) if user else None
    outcome = check_code(codes, user_id, body.code) if user_id else NO_CODE
    session_id = uuid.uuid4().hex
    # Recorded before the token is handed out; only one request confirms.
    if outcome != CONFIRMED or not mark_verified(users, user_id, session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CODE_NOT_ACCEPTED)
    token = create_access_token(user_id, source="signup", session_id=session_id)
    logger.info("email_verified user=%s", user_id)
    track("email_verified", user_id)
    confirmed = users.find_one({"_id": ObjectId(user_id)})
    return SignupResponse(user=_public(confirmed), access_token=_issue(response, token))


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
    password_ok = check_password(body.password, user["password_hash"] if user else None)
    # An account that never confirmed its address answers exactly like a
    # wrong password (#111): otherwise signing up with an address, then
    # signing in, would show whether it was free.
    if not password_ok or is_unverified(user):
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
        why = "unconfirmed" if password_ok else "wrong_password" if user else "unknown_account"
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
