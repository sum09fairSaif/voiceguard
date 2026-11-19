"""Refuses request bodies over a size limit before the app reads them.

FastAPI parses an upload (into memory or a temporary file) before the route
runs, so a size check inside the route only happens after the whole body has
arrived. This sits in front of the app instead: a body that says it's too big
(Content-Length) is refused without reading it, and one that doesn't say is
counted as it arrives and refused at the limit. Memory use per request is
bounded by the limit.
"""

import asyncio
import json

from audio_upload import MAX_AUDIO_BYTES

# Everything except the audio uploads is small JSON (sign-in is a few hundred bytes).
DEFAULT_LIMIT = 16 * 1024
# A recording up to MAX_AUDIO_BYTES, plus room for the multipart wrapping and
# the attempt_id field. The route still checks the audio itself.
AUDIO_LIMIT = MAX_AUDIO_BYTES + 64 * 1024

ROUTE_LIMITS = {
    ("POST", "/api/verify"): AUDIO_LIMIT,
    ("POST", "/api/enroll/samples"): AUDIO_LIMIT,
}

# All request bodies being held at once, across every request in flight. A
# flood of uploads just under the limit gets 503 instead of filling the
# instance's memory (512 MB on Render's free plan).
MAX_BUFFERED_BYTES = 64 * 1024 * 1024

# The whole body must arrive within this many seconds. Without a deadline, an
# upload that stalls part-way would hold its share of MAX_BUFFERED_BYTES for
# as long as the connection stays open, so a handful of stalled uploads could
# leave everyone else with "busy". A real recording (about 100 KB, at most
# about 1 MB) arrives well within it even on a slow phone connection.
BODY_READ_SECONDS = 30

TOO_LARGE = json.dumps({"detail": "That request is too large."}).encode()
TOO_SLOW = json.dumps({"detail": "That request took too long to arrive. Please try again."}).encode()
BUSY = json.dumps({"detail": "The service is busy. Please try again shortly."}).encode()

# Bytes held right now by requests in flight. Only touched on the event
# loop, so no lock is needed.
_buffered = 0


def limit_for(method: str, path: str) -> int:
    # "/api/verify/" is redirected to "/api/verify", so it gets the same limit.
    return ROUTE_LIMITS.get((method, path.rstrip("/") or "/"), DEFAULT_LIMIT)


def _declared_length(scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _refuse(send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                # The rest of the body is never read, so the connection can't be reused.
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_too_large(send) -> None:
    await _refuse(send, 413, TOO_LARGE)


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        global _buffered
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limit_for(scope["method"], scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_too_large(send)
            return

        # Read the body here, stopping as soon as it passes the limit, or
        # if all requests together would hold too much.
        chunks: list[bytes] = []
        size = 0
        try:
            try:
                async with asyncio.timeout(BODY_READ_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > limit:
                            await _send_too_large(send)
                            return
                        if _buffered + len(chunk) > MAX_BUFFERED_BYTES:
                            await _refuse(send, 503, BUSY)
                            return
                        _buffered += len(chunk)
                        chunks.append(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                # The finally below gives the held bytes back.
                await _refuse(send, 408, TOO_SLOW)
                return

            # Hands the app the chunks already read, one at a time (no
            # second, joined copy), then anything after them (e.g. the
            # client disconnecting) as usual.
            pending = list(chunks)

            async def replay():
                if pending:
                    chunk = pending.pop(0)
                    return {"type": "http.request", "body": chunk, "more_body": bool(pending)}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            _buffered -= sum(len(chunk) for chunk in chunks)
