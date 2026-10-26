import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

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


def create_access_token(user_id: str) -> str:
    if not config.JWT_SECRET:
        raise config.NotConfigured("JWT_SECRET is not set. Add it to your .env file.")
    now =datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _not_signed_in(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None:
        raise _not_signed_in("Please sign in first.")
    if not config.JWT_SECRET:
        raise config.NotConfigured("JWT_SECRET is not set. Add it to your .env file.")
    try:
        claims = jwt.decode(
            credentials.credentials,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise _not_signed_in("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise _not_signed_in("Your login token is not valid. Please sign in again.")
    return claims["sub"]
