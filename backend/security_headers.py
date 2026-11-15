"""Adds security headers to every response the API sends.

The API only ever returns JSON to our own frontend's code, so a browser never
needs to render, frame, cache or sniff it. These headers say so, which closes
off misuse if someone opens an API address directly or embeds it in a page.
"""

SECURITY_HEADERS = [
    # Treat the declared content type as final; never guess (e.g. JSON as HTML).
    (b"x-content-type-options", b"nosniff"),
    # Answers can hold account details, so no browser or proxy should keep a copy.
    (b"cache-control", b"no-store"),
    # Never send our URLs on to another site.
    (b"referrer-policy", b"no-referrer"),
    # A JSON API loads nothing and is never shown inside another page.
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"x-frame-options", b"DENY"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(name, value) for name, value in SECURITY_HEADERS if name not in present]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)
