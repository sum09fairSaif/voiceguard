import json
import logging

import httpx
import pytest
from starlette.requests import Request

import config
import email_sender
from email_sender import EmailUnavailable, get_email_sender, send_email
from main import email_unavailable

API_KEY = "re_secret_key_123"
SENDER = "VoiceGuard <noreply@send.example.com>"
TO = "sam@example.com"
SUBJECT = "Your VoiceGuard code"
BODY = "Your code is 482913. It expires in 10 minutes."


class FakeResend:
    """Stands in for Resend's API: answers what the test sets and remembers
    each request. Nothing leaves the machine."""

    def __init__(self):
        self.response = httpx.Response(200, json={"id": "4ef9a417-02e9-4d39-ad75-9611e0fcc33c"})
        self.error = None
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def resend(monkeypatch):
    fake = FakeResend()
    real_client = httpx.Client
    monkeypatch.setattr(
        email_sender.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs)
    )
    return fake


def send(purpose="account_recovery"):
    send_email(API_KEY, SENDER, TO, SUBJECT, BODY, purpose)


def test_the_email_goes_to_resend_as_plain_text(resend):
    send()

    [request] = resend.requests
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {"from": SENDER, "to": [TO], "subject": SUBJECT, "text": BODY}


def test_a_sent_email_is_logged_by_purpose_and_id_only(resend, caplog):
    with caplog.at_level(logging.INFO, logger="voiceguard.email"):
        send()

    [line] = [r.getMessage() for r in caplog.records if r.name == "voiceguard.email"]
    assert line == "email_sent purpose=account_recovery id=4ef9a417-02e9-4d39-ad75-9611e0fcc33c"


@pytest.mark.parametrize("status", [400, 401, 403, 422, 429, 500])
def test_a_refused_email_says_why_without_what_was_sent(resend, status):
    resend.response = httpx.Response(
        status, json={"name": "validation_error", "message": f"You can only send testing emails to {TO}: {BODY}"}
    )

    with pytest.raises(EmailUnavailable) as caught:
        send()

    reason = str(caught.value)
    assert f"status={status}" in reason
    assert "error=validation_error" in reason
    for private in (API_KEY, TO, SUBJECT, BODY, "482913"):
        assert private not in reason


def test_an_odd_error_name_isnt_repeated(resend):
    resend.response = httpx.Response(400, json={"name": f"code 482913 for {TO}"})

    with pytest.raises(EmailUnavailable) as caught:
        send()

    assert "error=-" in str(caught.value)


def test_an_answer_that_isnt_json_still_fails_cleanly(resend):
    resend.response = httpx.Response(502, text="<html>Bad gateway</html>")

    with pytest.raises(EmailUnavailable, match="status=502 error=-"):
        send()


def test_the_provider_being_unreachable_fails_cleanly(resend):
    resend.error = httpx.ConnectTimeout("timed out")

    with pytest.raises(EmailUnavailable, match="can't be reached: ConnectTimeout"):
        send()


def test_missing_settings_are_named(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_API_KEY", "")
    monkeypatch.setattr(config, "EMAIL_FROM", SENDER)

    with pytest.raises(EmailUnavailable, match="EMAIL_API_KEY or EMAIL_FROM is not set"):
        get_email_sender()


def test_with_settings_the_sender_uses_them(resend, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_API_KEY", API_KEY)
    monkeypatch.setattr(config, "EMAIL_FROM", SENDER)

    get_email_sender()(TO, SUBJECT, BODY, "test")

    [request] = resend.requests
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content)["from"] == SENDER


def test_an_email_failure_is_a_503_for_that_request_only(caplog):
    request = Request({"type": "http", "method": "POST", "path": "/api/recovery/code", "headers": []})

    with caplog.at_level(logging.WARNING, logger="voiceguard"):
        response = email_unavailable(request, EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set."))

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "We couldn't send the email right now. Please try again shortly."}
    assert "email_unavailable path=/api/recovery/code reason=EMAIL_API_KEY or EMAIL_FROM is not set." in caplog.text
