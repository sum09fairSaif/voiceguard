import asyncio

import pytest
from fastapi.testclient import TestClient

import body_limit
from audio_upload import MAX_AUDIO_BYTES
from body_limit import AUDIO_LIMIT, DEFAULT_LIMIT, BodyLimitMiddleware, limit_for
from main import app

client = TestClient(app)

ORIGIN = "https://app.get-voiceguard.tech"


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
    # The trailing-slash form is redirected to the same route.
    assert limit_for("POST", "/api/verify/") == AUDIO_LIMIT
    assert limit_for("POST", "/api/enroll/samples/") == AUDIO_LIMIT
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


# --- Straight through the middleware, counting what it reads -----------------


def run(scope_headers, chunks, path="/api/auth/login"):
    """Sends `chunks` as a request body; returns (status, chunks read, app called)."""
    reads = []
    sent = []
    called = []

    async def receive():
        index = len(reads)
        reads.append(index)
        if index < len(chunks):
            return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        called.append(body)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope = {"type": "http", "method": "POST", "path": path, "headers": scope_headers}
    asyncio.run(BodyLimitMiddleware(app)(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    return status, len(reads), called


def test_a_declared_oversize_body_is_never_read():
    status, reads, called = run([(b"content-length", str(DEFAULT_LIMIT + 1).encode())], [b"x" * 1024] * 20)

    assert status == 413
    assert reads == 0
    assert called == []


def test_a_streamed_body_stops_at_the_first_chunk_over_the_limit():
    chunk = b"x" * 4096
    status, reads, called = run([], [chunk] * 100)

    assert status == 413
    # 16 KB is 4 chunks; the 5th goes over, and nothing after it is read.
    assert reads == DEFAULT_LIMIT // len(chunk) + 1
    assert called == []


def test_the_app_gets_the_body_in_full_and_unchanged():
    status, _, called = run([], [b"abc", b"def", b"ghi"])

    assert status == 200
    assert called == [b"abcdefghi"]


def test_too_much_held_at_once_gets_503(monkeypatch):
    monkeypatch.setattr(body_limit, "MAX_BUFFERED_BYTES", 10)
    monkeypatch.setattr(body_limit, "_buffered", 8)

    status, _, called = run([], [b"abcd"])

    assert status == 503
    assert called == []
    assert body_limit._buffered == 8


def test_held_bytes_are_released_after_each_request():
    before = body_limit._buffered
    run([], [b"x" * 1000, b"y" * 1000])
    run([(b"content-length", b"999999")], [b"x"])
    run([], [b"x" * 4096] * 100)

    assert body_limit._buffered == before


# --- Stalled uploads (a deadline for the whole body) ------------------------------


async def _stalled_upload(chunk_size, sent):
    """An upload that sends one chunk, says more is coming, then stops."""
    calls = 0
    responses = []

    async def receive():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b"x" * chunk_size, "more_body": True}
        await asyncio.sleep(3600)  # never sends the rest

    async def send(message):
        responses.append(message)

    async def app(scope, receive, send):
        raise AssertionError("a stalled upload must never reach the app")

    scope = {"type": "http", "method": "POST", "path": "/api/verify", "headers": []}
    await BodyLimitMiddleware(app)(scope, receive, send)
    sent.extend(responses)


def test_an_upload_that_stalls_is_answered_408_and_gives_its_bytes_back(monkeypatch):
    monkeypatch.setattr(body_limit, "BODY_READ_SECONDS", 0.05)
    before = body_limit._buffered
    sent = []

    asyncio.run(_stalled_upload(1024 * 1024, sent))

    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    assert status == 408
    assert body_limit._buffered == before


def test_stalled_uploads_cant_block_a_real_one(monkeypatch):
    # Many uploads stall at once (enough to fill the shared budget); once their
    # deadline passes, a normal recording still gets through.
    monkeypatch.setattr(body_limit, "BODY_READ_SECONDS", 0.05)
    monkeypatch.setattr(body_limit, "MAX_BUFFERED_BYTES", 4 * 1024 * 1024)

    async def flood_then_real():
        sent = []
        await asyncio.gather(*(_stalled_upload(1024 * 1024, sent) for _ in range(6)))
        return sent

    sent = asyncio.run(flood_then_real())
    statuses = sorted(m["status"] for m in sent if m["type"] == "http.response.start")
    assert set(statuses) <= {408, 503}
    assert body_limit._buffered == 0

    status, _, called = run([], [b"x" * 200 * 1024], path="/api/verify")
    assert status == 200
    assert called == [b"x" * 200 * 1024]


def test_the_deadline_is_long_enough_for_a_real_recording():
    # 1 MB in 30 s is about 270 kbit/s: slower than any connection that can
    # use the app.
    assert body_limit.BODY_READ_SECONDS >= 30
