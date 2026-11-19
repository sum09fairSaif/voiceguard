import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config
from session_cookie import token_from_cookie
from sessions import is_revoked, revoked_sessions

# Reads the "Authorization: Bearer <token>" header. auto_error=False lets us
# send our own clear 401 message when it's missing.
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@lru_cache
def _dummy_hash() -> bytes:
    return bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt())


def check_password(password: str, password_hash: str | None) -> bool:
    """True if `password` matches `password_hash`. Pass None when there's
    no such account: a dummy hash is still checked, so the answer takes as
    long either way and doesn't give away which emails have accounts."""
    password_bytes = password.encode("utf-8")
    # Signup refuses passwords over 72 bytes (bcrypt reads no further), so
    # a longer one can't be right.
    if len(password_bytes) > 72:
        return False
    if password_hash is None:
        bcrypt.checkpw(password_bytes, _dummy_hash())
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


# Two kinds of sign-in token. A password alone gives a limited one: it can
# only start the voice check (passages, checks, enrollment). An approved voice
# check gives a voice-verified one, the only kind that opens the account.
# Both are signed, so neither the scope nor the factors can be edited.
PENDING = "pending"
VERIFIED = "verified"


def _encode(payload: dict, minutes: int) -> str:
    if not config.JWT_SECRET:
        raise config.NotConfigured("JWT_SECRET is not set. Add it to your .env file.")
    now = datetime.now(UTC)
    payload = {
        **payload,
        "jti": uuid.uuid4().hex,
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def create_access_token(user_id: str, source: str = "login") -> str:
    """A limited token after a password, starting a new session: `source` is
    "signup" or "login" (enrollment uses it to tell the signup session apart)."""
    return _encode(
        {"sub": user_id, "sid": uuid.uuid4().hex, "scope": PENDING, "amr": ["pwd"], "src": source},
        config.JWT_EXPIRE_MINUTES,
    )


def create_verified_token(user_id: str, session_id: str) -> str:
    """A voice-verified token, only after an approved voice check. It belongs
    to the same session as the limited token that ran the check, so signing
    out ends both."""
    return _encode(
        {"sub": user_id, "sid": session_id, "scope": VERIFIED, "amr": ["pwd", "voice"]},
        config.VERIFIED_TOKEN_MINUTES,
    )


def _not_signed_in(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def request_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """The sign-in token: an Authorization: Bearer header if there is one,
    otherwise the HttpOnly cookie (#102)."""
    return credentials.credentials if credentials is not None else token_from_cookie(request)


def get_token_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    revoked: Callable = Depends(revoked_sessions),
) -> dict:
    """The claims of any valid sign-in token, limited or voice-verified, whose
    session hasn't been signed out."""
    token = request_token(request, credentials)
    if token is None:
        raise _not_signed_in("Please sign in first.")
    return claims_for(token, revoked)


def claims_for(token: str, revoked: Callable) -> dict:
    if not config.JWT_SECRET:
        raise config.NotConfigured("JWT_SECRET is not set. Add it to your .env file.")
    try:
        claims = jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
            audience=config.JWT_AUDIENCE,
            issuer=config.JWT_ISSUER,
            options={"require": ["sub", "exp", "jti", "sid", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise _not_signed_in("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise _not_signed_in("Your login token is not valid. Please sign in again.")
    # Only now the database: a database error here is a 503, never access.
    if is_revoked(revoked(), claims["sid"]):
        raise _not_signed_in("You've signed out. Please sign in again.")
    return claims


def get_current_user_id(claims: dict = Depends(get_token_claims)) -> str:
    """For the steps of signing in (passages, voice checks, enrollment): any
    valid token will do."""
    return claims["sub"]


def is_voice_verified(claims: dict) -> bool:
    # Both must hold: a token without a scope (issued before these existed)
    # or with any other value counts as limited.
    # "amr" must be a real list: "voice" in a string would match a substring.
    factors = claims.get("amr")
    return claims.get("scope") == VERIFIED and isinstance(factors, list) and "voice" in factors


def get_verified_user_id(claims: dict = Depends(get_token_claims)) -> str:
    """For the account itself: only a voice-verified token. A limited one is
    a real sign-in that hasn't passed the voice check yet, so 403, not 401."""
    if not is_voice_verified(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please complete the voice check first.",
        )
    return claims["sub"]
