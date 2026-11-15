"""Refuses request bodies over a size limit before the app reads them.

FastAPI parses an upload (into memory or a temporary file) before the route
runs, so a size check inside the route only happens after the whole body has
arrived. This sits in front of the app instead: a body that says it's too big
(Content-Length) is refused without reading it, and one that doesn't say is
counted as it arrives and refused at the limit. Memory use per request is
bounded by the limit.
"""

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

TOO_LARGE = json.dumps({"detail": "That request is too large."}).encode()


def limit_for(method: str, path: str) -> int:
    return ROUTE_LIMITS.get((method, path), DEFAULT_LIMIT)


def _declared_length(scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_too_large(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(TOO_LARGE)).encode()),
                # The rest of the body is never read, so the connection can't be reused.
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": TOO_LARGE})


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limit_for(scope["method"], scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_too_large(send)
            return

        # Read the body here, stopping as soon as it passes the limit.
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await _send_too_large(send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        # Hands the app the body we already read, then anything after it
        # (e.g. the client disconnecting) as usual.
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
