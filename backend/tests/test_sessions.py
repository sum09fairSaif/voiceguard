"""Signing out ends the whole sign-in on the server (#159)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

import config
from main import app
from security import create_access_token, create_verified_token
from sessions import revoked_sessions

LOGOUT_URL = "/api/auth/logout"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def claims(token):
    return jwt.decode(
        token,
        config.JWT_SECRET,
        algorithms=[config.JWT_ALGORITHM],
        audience=config.JWT_AUDIENCE,
        issuer=config.JWT_ISSUER,
    )


def sign_in(client, users, email="sam@example.com"):
    if users.find_one({"email": email}) is None:
        client.post(
            "/api/auth/signup", json={"full_name": "Sam Doe", "email": email, "password": "correct-horse-battery"}
        )
    return client.post("/api/auth/login", json={"email": email, "password": "correct-horse-battery"}).json()[
        "access_token"
    ]


def test_every_token_has_an_id_a_session_an_issuer_and_an_audience():
    token = claims(create_access_token(str(ObjectId())))

    assert token["jti"] and token["sid"]
    assert token["iss"] == "voiceguard-api"
    assert token["aud"] == "voiceguard-app"


def test_each_sign_in_is_a_new_session_and_each_token_unique():
    user = str(ObjectId())
    first, second = claims(create_access_token(user)), claims(create_access_token(user))

    assert first["sid"] != second["sid"]
    assert first["jti"] != second["jti"]


def test_signing_out_ends_the_session(client, users):
    token = sign_in(client, users)
    assert client.post("/api/challenge", headers=bearer(token)).status_code == 201

    assert client.post(LOGOUT_URL, headers=bearer(token)).status_code == 204

    refused = client.post("/api/challenge", headers=bearer(token))
    assert refused.status_code == 401
    assert refused.json()["detail"] == "You've signed out. Please sign in again."


def test_signing_out_also_ends_the_voice_verified_token(client, users):
    limited = sign_in(client, users)
    user_id = claims(limited)["sub"]
    # What an approved check would hand out for this sign-in.
    verified = create_verified_token(user_id, claims(limited)["sid"])
    assert client.get("/api/me", headers=bearer(verified)).status_code == 200

    client.post(LOGOUT_URL, headers=bearer(limited))

    assert client.get("/api/me", headers=bearer(verified)).status_code == 401


def test_signing_out_with_the_verified_token_ends_the_limited_one_too(client, users):
    limited = sign_in(client, users)
    verified = create_verified_token(claims(limited)["sub"], claims(limited)["sid"])

    client.post(LOGOUT_URL, headers=bearer(verified))

    assert client.post("/api/challenge", headers=bearer(limited)).status_code == 401


def test_other_sign_ins_are_unaffected(client, users):
    phone = sign_in(client, users)
    laptop = sign_in(client, users)

    client.post(LOGOUT_URL, headers=bearer(phone))

    assert client.post("/api/challenge", headers=bearer(laptop)).status_code == 201


def test_signing_out_twice_is_refused_the_second_time(client, users):
    token = sign_in(client, users)
    client.post(LOGOUT_URL, headers=bearer(token))

    assert client.post(LOGOUT_URL, headers=bearer(token)).status_code == 401


def test_signing_out_needs_a_token(client):
    assert client.post(LOGOUT_URL).status_code == 401


def test_the_revocation_lasts_as_long_as_the_sessions_tokens_could(client, users, revoked):
    token = sign_in(client, users)
    before = datetime.now(UTC)

    client.post(LOGOUT_URL, headers=bearer(token))

    entry = revoked.find_one({"_id": claims(token)["sid"]})
    lifetime = timedelta(minutes=config.JWT_EXPIRE_MINUTES + config.VERIFIED_TOKEN_MINUTES)
    assert entry["expires_at"].replace(tzinfo=UTC) - before >= lifetime - timedelta(seconds=5)
    # Only the session id: no email, address or token stored.
    assert set(entry) == {"_id", "revoked_at", "expires_at"}


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "some-other-app"},
        {"iss": "someone-else"},
        {"sid": None},
        {"jti": None},
        {"aud": None},
        {"iss": None},
    ],
    ids=["wrong-aud", "wrong-iss", "no-sid", "no-jti", "no-aud", "no-iss"],
)
def test_tokens_with_wrong_or_missing_claims_are_refused(client, change):
    now = datetime.now(UTC)
    payload = {
        "sub": str(ObjectId()),
        "sid": "s",
        "jti": "j",
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
        "scope": "pending",
        "amr": ["pwd"],
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **change,
    }
    token = jwt.encode({k: v for k, v in payload.items() if v is not None}, config.JWT_SECRET, algorithm="HS256")

    assert client.post("/api/challenge", headers=bearer(token)).status_code == 401


def test_an_unavailable_revocation_list_never_lets_a_token_through(client):
    class Unreachable:
        def count_documents(self, *args, **kwargs):
            raise ServerSelectionTimeoutError("database unreachable")

    app.dependency_overrides[revoked_sessions] = lambda: lambda: Unreachable()

    response = client.post("/api/challenge", headers=bearer(create_access_token(str(ObjectId()))))

    assert response.status_code == 503


def test_no_token_never_touches_the_revocation_list(client):
    def must_not_be_called():
        raise AssertionError("looked up the revocation list without a token")

    app.dependency_overrides[revoked_sessions] = lambda: must_not_be_called

    assert client.post("/api/challenge").status_code == 401
