"""Per-client limits: one sender is stopped without affecting anyone else."""

import pytest
from bson import ObjectId

import config
from embedding import get_embedder
from main import app
from security import create_access_token
from transcription import get_transcriber

RECORDING = b"pretend this is a few seconds of speech"


def from_client(address: str, user_id: str | None = None) -> dict[str, str]:
    headers = {"CF-Connecting-IP": address}
    if user_id:
        headers["Authorization"] = f"Bearer {create_access_token(user_id)}"
    return headers


@pytest.fixture(autouse=True)
def cloudflare_source(monkeypatch):
    monkeypatch.setattr(config, "CLIENT_IP_SOURCE", "cf-connecting-ip")


@pytest.fixture
def no_paid_calls():
    # Never reached in these tests (the limits refuse first); stands in so
    # missing API settings can't answer 503 before the limit is checked.
    app.dependency_overrides[get_transcriber] = lambda: lambda audio, filename: ""
    app.dependency_overrides[get_embedder] = lambda: None


def signup(client, n: int, address: str):
    return client.post(
        "/api/auth/signup",
        json={"full_name": "Sam Doe", "email": f"sam{n}@example.com", "password": "correct-horse-battery"},
        headers=from_client(address),
    )


# --- Signup -----------------------------------------------------------------


def test_one_client_is_stopped_after_its_signups(client, monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_CLIENT_LIMIT", 2)
    assert signup(client, 1, "203.0.113.1").status_code == 201
    assert signup(client, 2, "203.0.113.1").status_code == 201

    refused = signup(client, 3, "203.0.113.1")

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0


def test_another_client_can_still_sign_up(client, monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_CLIENT_LIMIT", 1)
    signup(client, 1, "203.0.113.1")
    assert signup(client, 2, "203.0.113.1").status_code == 429

    assert signup(client, 3, "198.51.100.2").status_code == 201


def test_the_shared_backstop_still_applies(client, monkeypatch):
    # In case client addresses can be faked: many "clients" still hit it.
    monkeypatch.setattr(config, "SIGNUP_RATE_LIMIT", 3)
    for n in range(3):
        assert signup(client, n, f"203.0.113.{n + 1}").status_code == 201

    assert signup(client, 9, "203.0.113.99").status_code == 429


def test_a_faked_forwarded_header_does_not_reset_the_limit(client, monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_CLIENT_LIMIT", 1)
    signup(client, 1, "203.0.113.1")

    response = client.post(
        "/api/auth/signup",
        json={"full_name": "Sam Doe", "email": "sam2@example.com", "password": "correct-horse-battery"},
        headers={**from_client("203.0.113.1"), "X-Forwarded-For": "192.0.2.77"},
    )

    assert response.status_code == 429


# --- Sign-in ----------------------------------------------------------------


def test_one_client_cant_try_endless_accounts(client, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_CLIENT_LIMIT", 3)
    for n in range(3):
        response = client.post(
            "/api/auth/login",
            json={"email": f"user{n}@example.com", "password": "wrong-password-123"},
            headers=from_client("203.0.113.1"),
        )
        assert response.status_code == 401

    refused = client.post(
        "/api/auth/login",
        json={"email": "user9@example.com", "password": "wrong-password-123"},
        headers=from_client("203.0.113.1"),
    )
    other = client.post(
        "/api/auth/login",
        json={"email": "user9@example.com", "password": "wrong-password-123"},
        headers=from_client("198.51.100.2"),
    )

    assert refused.status_code == 429
    assert other.status_code == 401


# --- Signed-in routes --------------------------------------------------------


def test_one_client_is_limited_across_accounts_for_passages(client, monkeypatch):
    # One address cycling through many accounts still runs out.
    monkeypatch.setattr(config, "CHALLENGE_CLIENT_LIMIT", 2)
    for _ in range(2):
        assert client.post("/api/challenge", headers=from_client("203.0.113.1", str(ObjectId()))).status_code == 201

    assert client.post("/api/challenge", headers=from_client("203.0.113.1", str(ObjectId()))).status_code == 429
    assert client.post("/api/challenge", headers=from_client("198.51.100.2", str(ObjectId()))).status_code == 201


def test_one_client_is_limited_across_accounts_for_voice_checks(client, monkeypatch, no_paid_calls):
    monkeypatch.setattr(config, "VERIFY_CLIENT_LIMIT", 1)

    def submit(address):
        return client.post(
            "/api/verify",
            files={"audio": ("attempt", RECORDING, "audio/webm")},
            data={"attempt_id": str(ObjectId())},
            headers=from_client(address, str(ObjectId())),
        )

    assert submit("203.0.113.1").status_code == 400  # past the limit: unknown passage
    assert submit("203.0.113.1").status_code == 429
    assert submit("198.51.100.2").status_code == 400


def test_one_client_is_limited_across_accounts_for_enrollment(client, monkeypatch, no_paid_calls):
    monkeypatch.setattr(config, "ENROLL_CLIENT_LIMIT", 1)

    def send(address):
        return client.post(
            "/api/enroll/samples",
            files={"audio": ("sample", RECORDING, "audio/webm")},
            headers=from_client(address, str(ObjectId())),
        )

    assert send("203.0.113.1").status_code != 429
    assert send("203.0.113.1").status_code == 429
    assert send("198.51.100.2").status_code != 429


def test_limits_store_no_addresses_in_clear(client, rate_limits):
    signup(client, 1, "203.0.113.1")

    stored = " ".join(str(doc) for doc in rate_limits.find())
    assert "203.0.113.1" not in stored
