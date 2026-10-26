import importlib

import bcrypt
import jwt
import pytest
from pymongo.errors import ServerSelectionTimeoutError

import config
from db import get_client, get_users_collection
from main import app

SIGNUP_URL = "/api/auth/signup"


def new_user(**changes):
    user = {"full_name": "Sam Lee", "email": "sam@example.com", "password": "correct-horse"}
    user.update(changes)
    return user


def test_signup_creates_account_and_returns_token(client, users):
    response = client.post(SIGNUP_URL, json=new_user())

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["full_name"] == "Sam Lee"
    assert body["user"]["email"] == "sam@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert body["token_type"] == "bearer"

    claims = jwt.decode(body["access_token"], config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    assert claims["sub"] == body["user"]["id"]
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(body["access_token"], "a-different-key-" * 4, algorithms=[config.JWT_ALGORITHM])

    saved = users.find_one({"email": "sam@example.com"})
    assert saved["password_hash"] != "correct-horse"
    assert bcrypt.checkpw(b"correct-horse", saved["password_hash"].encode("utf-8"))


def test_signup_stores_email_in_lowercase(client, users):
    response = client.post(SIGNUP_URL, json=new_user(email="Sam@Example.COM"))

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "sam@example.com"
    assert users.count_documents({"email": "sam@example.com"}) == 1


def test_signup_trims_spaces_around_name(client):
    response = client.post(SIGNUP_URL, json=new_user(full_name="  Sam Lee  "))

    assert response.status_code == 201
    assert response.json()["user"]["full_name"] == "Sam Lee"


def test_duplicate_email_is_refused_with_clear_message(client, users):
    client.post(SIGNUP_URL, json=new_user())
    response = client.post(SIGNUP_URL, json=new_user(email="SAM@example.com"))

    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists."
    assert users.count_documents({}) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "a" * 73},
        {"full_name": "   "},
        {"full_name": ""},
    ],
)
def test_bad_form_is_refused(client, users, changes):
    response = client.post(SIGNUP_URL, json=new_user(**changes))

    assert response.status_code == 422
    assert users.count_documents({}) == 0


def test_missing_field_is_refused(client, users):
    user = new_user()
    del user["password"]
    response = client.post(SIGNUP_URL, json=user)

    assert response.status_code == 422
    assert users.count_documents({}) == 0


def test_missing_jwt_secret_returns_503_and_saves_nothing(client, users, monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "")

    response = client.post(SIGNUP_URL, json=new_user())

    assert response.status_code == 503
    assert response.json()["detail"] == "The service is temporarily unavailable. Please try again shortly."
    assert "JWT_SECRET" not in response.text
    assert users.count_documents({}) == 0


def test_missing_mongo_uri_returns_503(client, monkeypatch):
    # Use the real database connection, with no address to connect to.
    del app.dependency_overrides[get_users_collection]
    monkeypatch.setattr(config, "MONGO_URI", "")
    get_client.cache_clear()
    get_users_collection.cache_clear()
    try:
        response = client.post(SIGNUP_URL, json=new_user())
    finally:
        get_client.cache_clear()
        get_users_collection.cache_clear()

    assert response.status_code == 503
    assert "MONGO_URI" not in response.text


def test_too_many_signups_are_refused(client, users, monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_RATE_LIMIT", 2)
    for n in range(2):
        assert client.post(SIGNUP_URL, json=new_user(email=f"user{n}@example.com")).status_code == 201

    response = client.post(SIGNUP_URL, json=new_user(email="one-too-many@example.com"))

    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= config.RATE_LIMIT_WINDOW_SECONDS
    assert users.count_documents({}) == 2


@pytest.mark.parametrize("password", ["mypass1", "p" * 73])
def test_rejected_password_is_not_echoed_back(client, password):
    response = client.post(SIGNUP_URL, json=new_user(password=password))

    assert response.status_code == 422
    assert password not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "password"]


class UnreachableDatabase:
    def insert_one(self, document):
        raise ServerSelectionTimeoutError("database unreachable")


def test_database_outage_returns_503(client):
    app.dependency_overrides[get_users_collection] = lambda: UnreachableDatabase()
    response = client.post(SIGNUP_URL, json=new_user())

    assert response.status_code == 503
    assert response.json()["detail"] == "The service is temporarily unavailable. Please try again shortly."


@pytest.mark.parametrize("minutes", ["0", "-5"])
def test_token_lifetime_must_be_positive(monkeypatch, minutes):
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", minutes)
    try:
        with pytest.raises(RuntimeError, match="JWT_EXPIRE_MINUTES"):
            importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)
