import jwt
import pytest
from pymongo.errors import ServerSelectionTimeoutError

import config
from db import get_users_collection
from main import app

SIGNUP_URL = "/api/auth/signup"
LOGIN_URL = "/api/auth/login"
WRONG = "The email or password is incorrect."


@pytest.fixture
def account(client):
    response = client.post(
        SIGNUP_URL, json={"full_name": "Sam Lee", "email": "sam@example.com", "password": "correct-horse"}
    )
    return response.json()["user"]


def login(client, email="sam@example.com", password="correct-horse"):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def test_right_password_logs_in_with_a_token(client, account):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    for field in ("id", "full_name", "email"):
        assert body["user"][field] == account[field]
    # The database keeps times to the millisecond, but still in UTC.
    assert body["user"]["created_at"].endswith("Z")
    assert body["user"]["created_at"][:23] == account["created_at"][:23]
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    assert claims["sub"] == account["id"]


def test_token_opens_the_voice_check(client, account):
    token = login(client).json()["access_token"]

    response = client.post("/api/challenge", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201


def test_email_case_does_not_matter(client, account):
    assert login(client, email="SAM@Example.com").status_code == 200


@pytest.mark.parametrize(
    "email, password",
    [
        ("sam@example.com", "wrong-horse"),
        ("nobody@example.com", "correct-horse"),
        ("sam@example.com", "c" * 73),
    ],
)
def test_wrong_email_or_password_gives_the_same_answer(client, account, email, password):
    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json()["detail"] == WRONG
    assert "access_token" not in response.text


@pytest.mark.parametrize("body", [{"email": "sam@example.com"}, {"email": "not-an-email", "password": "x"},
                                  {"email": "sam@example.com", "password": ""}])
def test_bad_form_is_refused(client, account, body):
    assert client.post(LOGIN_URL, json=body).status_code == 422


def test_wrong_password_is_not_echoed_back(client, account):
    response = login(client, password="my-secret-guess")

    assert "my-secret-guess" not in response.text


def test_fifth_failure_locks_with_recovery_instructions(client, account):
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        assert login(client, password="wrong-horse").status_code == 401

    response = login(client, password="wrong-horse")

    assert response.status_code == 423
    assert "try again in 30 minutes" in response.json()["detail"]
    assert "reset" in response.json()["detail"]
    assert response.headers["Retry-After"] == str(config.LOGIN_LOCKOUT_SECONDS)


def test_locked_account_refuses_even_the_right_password(client, account):
    for _ in range(config.LOGIN_MAX_FAILURES):
        login(client, password="wrong-horse")

    response = login(client)

    assert response.status_code == 423
    assert "access_token" not in response.text


def test_email_without_account_locks_the_same_way(client):
    # Otherwise the lockout would show which emails have accounts.
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        login(client, email="nobody@example.com")

    assert login(client, email="nobody@example.com").status_code == 423


def test_right_password_resets_the_count(client, account):
    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        login(client, password="wrong-horse")
    assert login(client).status_code == 200

    for _ in range(config.LOGIN_MAX_FAILURES - 1):
        assert login(client, password="wrong-horse").status_code == 401


def test_one_account_locked_leaves_others_alone(client, account):
    client.post(SIGNUP_URL, json={"full_name": "Alex Kim", "email": "alex@example.com", "password": "alex-password"})
    for _ in range(config.LOGIN_MAX_FAILURES):
        login(client, password="wrong-horse")

    assert login(client, email="alex@example.com", password="alex-password").status_code == 200


class UnreachableDatabase:
    def find_one(self, *args, **kwargs):
        raise ServerSelectionTimeoutError("database unreachable")


def test_database_outage_returns_503(client, account):
    app.dependency_overrides[get_users_collection] = lambda: UnreachableDatabase()

    response = login(client)

    assert response.status_code == 503
