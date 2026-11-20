"""The two kinds of sign-in token: limited (password) and voice-verified."""

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import config
from security import (
    create_access_token,
    create_verified_token,
    get_current_user_id,
    get_verified_user_id,
    user_accounts,
)
from sessions import revoked_sessions

USER = "64b000000000000000000001"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", secrets.token_urlsafe(32))


@pytest.fixture
def api(revoked, users, new_account):
    # A stand-in for the real routes: one per level, with the same in-memory
    # sign-out list and accounts as the real app in the tests.
    app = FastAPI()
    app.dependency_overrides[revoked_sessions] = lambda: (lambda: revoked)
    app.dependency_overrides[user_accounts] = lambda: (lambda: users)
    new_account(USER)

    @app.get("/step")
    def step(user_id: str = Depends(get_current_user_id)):
        return {"user": user_id}

    @app.get("/account")
    def account(user_id: str = Depends(get_verified_user_id)):
        return {"user": user_id}

    return TestClient(app)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def claims(token):
    return jwt.decode(
        token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM], audience=config.JWT_AUDIENCE, issuer=config.JWT_ISSUER
    )


def forge(payload, key=None, minutes=10):
    # Every claim a genuine token has; a test overrides or drops what it checks.
    now = datetime.now(UTC)
    standard = {
        "jti": "forged-jti",
        "sid": "forged-session",
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    claims = {key_: value for key_, value in {**standard, **payload}.items() if value is not None}
    return jwt.encode(claims, key or config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


# --- What each token says ------------------------------------------------------


def test_a_password_gives_a_limited_token():
    token = claims(create_access_token(USER, source="login"))

    assert token["sub"] == USER
    assert token["scope"] == "pending"
    assert token["amr"] == ["pwd"]
    assert token["src"] == "login"
    assert token["exp"] - token["iat"] == config.JWT_EXPIRE_MINUTES * 60


def test_a_signup_token_says_so_and_is_limited():
    token = claims(create_access_token(USER, source="signup"))

    assert token["src"] == "signup"
    assert token["scope"] == "pending"
    assert token["amr"] == ["pwd"]


def test_an_approved_voice_check_gives_a_short_voice_verified_token():
    token = claims(create_verified_token(USER, "session-1"))

    assert token["scope"] == "verified"
    assert token["amr"] == ["pwd", "voice"]
    assert token["exp"] - token["iat"] == config.VERIFIED_TOKEN_MINUTES * 60 == 15 * 60


# --- Which token opens what ------------------------------------------------------


def test_a_limited_token_reaches_the_sign_in_steps_but_not_the_account(api):
    token = create_access_token(USER)

    assert api.get("/step", headers=bearer(token)).status_code == 200
    refused = api.get("/account", headers=bearer(token))
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Please complete the voice check first."


def test_a_voice_verified_token_reaches_both(api):
    token = create_verified_token(USER, "session-1")

    assert api.get("/step", headers=bearer(token)).json() == {"user": USER}
    assert api.get("/account", headers=bearer(token)).json() == {"user": USER}


@pytest.mark.parametrize("path", ["/step", "/account"])
def test_no_token_is_401(api, path):
    assert api.get(path).status_code == 401


def test_an_expired_voice_verified_token_is_401(api):
    expired = forge({"sub": USER, "scope": "verified", "amr": ["pwd", "voice"]}, minutes=-1)

    response = api.get("/account", headers=bearer(expired))

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


def test_a_token_signed_with_another_key_is_401(api):
    forged = forge({"sub": USER, "scope": "verified", "amr": ["pwd", "voice"]}, key="not-our-secret-" * 3)

    assert api.get("/account", headers=bearer(forged)).status_code == 401


def test_editing_a_limited_token_into_a_verified_one_breaks_it(api):
    header, payload, signature = create_access_token(USER).split(".")
    claims_in = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims_in.update({"scope": "verified", "amr": ["pwd", "voice"]})
    edited = base64.urlsafe_b64encode(json.dumps(claims_in).encode()).rstrip(b"=").decode()

    assert api.get("/account", headers=bearer(f"{header}.{edited}.{signature}")).status_code == 401


def test_an_unsigned_token_is_401(api):
    unsigned = jwt.encode({"sub": USER, "scope": "verified", "amr": ["pwd", "voice"]}, None, algorithm="none")

    assert api.get("/account", headers=bearer(unsigned)).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"sub": USER},  # issued before token kinds existed
        {"sub": USER, "scope": "verified"},  # no factors
        {"sub": USER, "scope": "verified", "amr": ["pwd"]},  # voice missing
        {"sub": USER, "scope": "admin", "amr": ["pwd", "voice"]},  # unknown scope
        {"sub": USER, "scope": "verified", "amr": "pwd voice"},  # not a list
    ],
)
def test_anything_short_of_voice_verified_counts_as_limited(api, payload):
    token = forge(payload)

    assert api.get("/step", headers=bearer(token)).status_code == 200
    assert api.get("/account", headers=bearer(token)).status_code == 403


def test_signup_and_login_hand_out_limited_tokens(client):
    signup = client.post(
        "/api/auth/signup",
        json={"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"},
    )
    login = client.post("/api/auth/login", json={"email": "sam@example.com", "password": "correct-horse-battery"})

    for response, source in ((signup, "signup"), (login, "login")):
        token = claims(response.json()["access_token"])
        assert token["src"] == source
        assert token["scope"] == "pending"
        assert token["amr"] == ["pwd"]
