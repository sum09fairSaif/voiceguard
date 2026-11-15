import pytest
from fastapi.testclient import TestClient

from audio_upload import MAX_AUDIO_BYTES
from body_limit import AUDIO_LIMIT, DEFAULT_LIMIT, limit_for
from main import app

client = TestClient(app)

ORIGIN = "https://voiceguard-nu.vercel.app"


def chunks(total: int, size: int = 4096):
    # A body sent in pieces with no Content-Length (chunked transfer).
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        sent += piece
        yield b"x" * piece


def test_limits_per_route():
    assert limit_for("POST", "/api/verify") == AUDIO_LIMIT
    assert limit_for("POST", "/api/enroll/samples") == AUDIO_LIMIT
    assert limit_for("POST", "/api/auth/login") == DEFAULT_LIMIT
    assert limit_for("GET", "/api/verify") == DEFAULT_LIMIT
    assert AUDIO_LIMIT > MAX_AUDIO_BYTES


def test_refuses_a_declared_body_over_the_limit_without_a_token():
    response = client.post("/api/verify", content=b"x" * (AUDIO_LIMIT + 1))

    assert response.status_code == 413
    assert response.json() == {"detail": "That request is too large."}


def test_refuses_a_streamed_body_with_no_declared_size():
    response = client.post("/api/auth/login", content=chunks(DEFAULT_LIMIT + 1))

    assert response.status_code == 413


def test_refuses_a_big_upload_streamed_to_an_audio_route():
    response = client.post("/api/enroll/samples", content=chunks(AUDIO_LIMIT + 1, size=64 * 1024))

    assert response.status_code == 413


@pytest.mark.parametrize("size", [DEFAULT_LIMIT, DEFAULT_LIMIT - 1])
def test_lets_a_body_at_the_limit_through(size):
    # Not JSON, so the app answers 422: the point is it got past the limit.
    response = client.post("/api/auth/login", content=b"x" * size, headers={"Content-Type": "application/json"})

    assert response.status_code == 422


def test_a_json_route_refuses_what_an_audio_route_allows():
    body = b"x" * (DEFAULT_LIMIT + 1)

    assert client.post("/api/auth/login", content=body).status_code == 413
    assert client.post("/api/verify", content=body).status_code != 413


def test_a_full_size_recording_reaches_the_route():
    # 1 MB of "audio" plus the form field: past the limit check, then refused
    # for having no token, not for its size.
    response = client.post(
        "/api/verify",
        files={"audio": ("attempt", b"x" * MAX_AUDIO_BYTES, "audio/webm")},
        data={"attempt_id": "a" * 32},
    )

    assert response.status_code == 401


def test_the_frontend_can_read_the_413():
    response = client.post("/api/auth/login", content=b"x" * (DEFAULT_LIMIT + 1), headers={"Origin": ORIGIN})

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_requests_without_a_body_are_unaffected():
    assert client.get("/health").status_code == 200
