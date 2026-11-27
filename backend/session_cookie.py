"""The sign-in token as a cookie the page's scripts can't read (#102).

After sign-up, sign-in and an approved voice check, the token is set in a
cookie marked HttpOnly (no script can read it, so a cross-site scripting bug
can't steal it), Secure (HTTPS only) and SameSite=Strict (the browser sends it
only on requests from our own site). Signing out clears it.

Requests that change something (anything but GET, HEAD and OPTIONS) must come
from one of our own pages: the browser's Origin header has to be on the CORS
allowlist. SameSite=Strict already keeps the cookie off other sites'
requests; this also covers a page on a sibling address of our own domain, and
a forged sign-in (logging someone into an attacker's account).

The frontend and API must share a site (e.g. app.<domain> and api.<domain>)
for the browser to send the cookie at all. Until the frontend stops reading
the token itself, TOKEN_IN_RESPONSE_BODY keeps returning it in the response
too, and an Authorization: Bearer header is still accepted.
"""

import json
import re

from fastapi import Request, Response

import config

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
NOT_OUR_PAGE = json.dumps({"detail": "This request didn't come from VoiceGuard. Please reload the page."}).encode()


def cookie_name() -> str:
    # The __Host- prefix makes the browser refuse the cookie unless it's
    # Secure, set by this exact host and for the whole site, so no other
    # address can set or overwrite it. It can only be used with Secure.
    return f"__Host-{config.SESSION_COOKIE_NAME}" if config.SESSION_COOKIE_SECURE else config.SESSION_COOKIE_NAME


def set_session_cookie(response: Response, token: str, minutes: int) -> None:
    response.set_cookie(
        cookie_name(),
        token,
        max_age=minutes * 60,
        path="/",
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        cookie_name(), path="/", httponly=True, secure=config.SESSION_COOKIE_SECURE, samesite="strict"
    )


def token_from_cookie(request: Request) -> str | None:
    return request.cookies.get(cookie_name()) or None


def origin_allowed(origin: str) -> bool:
    origin = origin.rstrip("/")
    if origin in config.ALLOWED_ORIGINS:
        return True
    return bool(config.ALLOWED_ORIGIN_REGEX and re.fullmatch(config.ALLOWED_ORIGIN_REGEX, origin))


class OriginCheckMiddleware:
    """Refuses (403) a request that changes something when it comes from a
    page that isn't ours, or carries the cookie without saying where it came
    from. Requests with neither a cookie nor an Origin (scripts and tests
    using a bearer header) aren't affected: no browser sends those."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {name: value for name, value in scope["headers"]}
        origin = headers.get(b"origin", b"").decode("latin-1")
        has_cookie = f"{cookie_name()}=".encode() in headers.get(b"cookie", b"")
        if origin:
            refused = not origin_allowed(origin)
        else:
            refused = has_cookie
        if refused:
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", b"%d" % len(NOT_OUR_PAGE))],
                }
            )
            await send({"type": "http.response.body", "body": NOT_OUR_PAGE})
            return
        await self.app(scope, receive, send)
