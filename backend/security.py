from datetime import datetime, timedelta, timezone

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


def create_access_token(user_id: str) -> str:
    if not config.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set. Add it to your .env file.")
    now = datetime.now(timezone.utc)
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
        raise RuntimeError("JWT_SECRET is not set. Add it to your .env file.")
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
