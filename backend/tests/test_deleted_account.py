"""A sign-in token never outlives its account (#194)."""

import pytest
from bson import ObjectId

import config
from security import create_access_token, create_verified_token

GONE = "This account no longer exists. Please sign up or sign in again."
SIGNUP = {"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sign_up(client):
    response = client.post("/api/auth/signup", json=SIGNUP)
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


# Every route a signed-in user reaches, each with just enough of a request
# that it would otherwise get past signing in.
ROUTES = [
    ("post", "/api/challenge", {}),
    ("post", "/api/verify", {"files": {"audio": ("a", b"x", "audio/webm")}, "data": {"attempt_id": str(ObjectId())}}),
    ("get", "/api/enroll", {}),
    ("post", "/api/enroll/samples", {"files": {"audio": ("a", b"x", "audio/webm")}}),
    ("post", "/api/auth/email/code", {}),
    ("post", "/api/auth/email/verify", {"json": {"code": "123456"}}),
]


@pytest.mark.parametrize(("method", "url", "extra"), ROUTES, ids=[url for _, url, _ in ROUTES])
def test_a_token_whose_account_is_gone_gets_401(client, method, url, extra):
    token = create_access_token(str(ObjectId()), source="signup")

    response = getattr(client, method)(url, headers=auth(token), **extra)

    assert response.status_code == 401
    assert response.json()["detail"] == GONE


def test_a_voice_verified_token_whose_account_is_gone_gets_401(client):
    token = create_verified_token(str(ObjectId()), "session-1")

    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_the_same_token_works_while_the_account_exists_and_stops_once_deleted(client, users):
    token = sign_up(client)
    assert client.post("/api/challenge", headers=auth(token)).status_code == 201

    users.delete_many({})

    assert client.post("/api/challenge", headers=auth(token)).status_code == 401


def test_a_replaced_unconfirmed_account_cant_start_a_voice_check(client, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)
    old_token = sign_up(client)
    # Someone signs up again with the same, never-confirmed address: the
    # new signup replaces the old account.
    sign_up(client)

    response = client.post("/api/challenge", headers=auth(old_token))

    # 401, not the 403 an unconfirmed account gets: the account is gone.
    assert response.status_code == 401
    assert response.json()["detail"] == GONE


def test_signing_out_still_works_once_the_account_is_gone(client, users):
    token = sign_up(client)
    users.delete_many({})

    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 204
