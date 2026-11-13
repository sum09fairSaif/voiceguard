"""Sending email, for account recovery (#20), password recovery (#109) and
email verification (#110).

Uses Resend's HTTP API rather than SMTP: Render's free web services block
outbound SMTP ports (25, 465, 587). See #108 for why Resend.

Until a domain of our own is verified in Resend, EMAIL_FROM can only be
onboarding@resend.dev, and Resend then only delivers to the address the
Resend account was made with: fine for testing, not for users.

Nothing private is logged: not the API key, the recipient, the subject or
the body (which will hold one-time codes and links). The log says what kind
of email it was and Resend's id for it, enough to look it up in Resend.
"""

import logging
import re
from collections.abc import Callable
from functools import partial

import httpx

import config

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10

logger = logging.getLogger("voiceguard.email")


class EmailUnavailable(Exception):
    """Email isn't set up, or the provider refused or couldn't be reached."""


# Takes the recipient, subject, plain-text body, and what the email is for
# (a short word for the log, e.g. "account_recovery"), and sends it.
EmailSender = Callable[[str, str, str, str], None]


def send_email(api_key: str, sender: str, to: str, subject: str, text: str, purpose: str) -> None:
    """Send one plain-text email. Raises EmailUnavailable if it wasn't accepted."""
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"from": sender, "to": [to], "subject": subject, "text": text},
            )
    except httpx.HTTPError as exc:
        # The type only: the error's text could carry the request.
        raise EmailUnavailable(f"The email provider can't be reached: {type(exc).__name__}.") from exc
    if response.status_code >= 400:
        raise EmailUnavailable(
            f"The email provider refused the email: status={response.status_code} error={_field(response, 'name')}."
        )
    logger.info("email_sent purpose=%s id=%s", purpose, _field(response, "id"))


def _field(response: httpx.Response, key: str) -> str:
    """A short identifier from the provider's answer, such as an error name
    or the email's id, or "-". Anything else isn't logged: the provider's
    messages can repeat what was sent."""
    try:
        value = response.json().get(key)
    except (ValueError, AttributeError):
        return "-"
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        return value
    return "-"


def get_email_sender() -> EmailSender:
    """The sender to use, for FastAPI's Depends. Tests replace it with a
    stand-in so they never send real email."""
    if not config.EMAIL_API_KEY or not config.EMAIL_FROM:
        raise EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set.")
    return partial(send_email, config.EMAIL_API_KEY, config.EMAIL_FROM)
