"""Confirming the email address at signup (#110)."""

import logging
import re
from datetime import UTC, datetime, timedelta

import mongomock
import pytest
from bson import ObjectId

import config
import db
from email_sender import EmailUnavailable, get_email_sender, get_optional_email_sender
from email_verification import CONFIRMED, NO_CODE, NOT_CONFIRMED, WRONG, check_code, issue_code
from enrollment_window import may_enroll
from main import app

SIGNUP = {"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"}
LOGIN = {"email": "sam@example.com", "password": "correct-horse-battery"}


class Outbox:
    """Stands in for the email sender and keeps what would have been sent."""

    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, text, purpose):
        self.sent.append({"to": to, "subject": subject, "text": text, "purpose": purpose})

    def last_code(self):
        return re.search(r"\b(\d{6})\b", self.sent[-1]["text"]).group(1)


@pytest.fixture
def outbox(client):
    box = Outbox()
    app.dependency_overrides[get_optional_email_sender] = lambda: box
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def required(client, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sign_up(client, body=SIGNUP):
    response = client.post("/api/auth/signup", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, token, code):
    return client.post("/api/auth/email/verify", json={"code": code}, headers=auth(token))


def resend(client, token):
    return client.post("/api/auth/email/code", headers=auth(token))


def log_in(client):
    return client.post("/api/auth/login", json=LOGIN).json()["access_token"]


def a_wrong_code(right):
    return "000000" if right != "000000" else "111111"


# --- Signup -----------------------------------------------------------------------


def test_while_switched_off_signup_is_as_before(client, outbox, users):
    body = sign_up(client)

    assert body["user"]["email_verified"] is True
    assert outbox.sent == []
    stored = users.find_one({})
    assert "email_verified" not in stored
    assert "unverified_expires_at" not in stored


def test_a_new_account_starts_unverified_and_gets_a_code(client, required, outbox, users, email_codes):
    body = sign_up(client)

    assert body["user"]["email_verified"] is False
    ((email,),) = [outbox.sent]
    assert email["to"] == "sam@example.com"
    assert email["purpose"] == "email_verification"
    code = outbox.last_code()
    # Only a hash is stored, never the code.
    (record,) = list(email_codes.find({}))
    assert code not in str(record)
    assert record["code_hash"] != code
    stored = users.find_one({})
    assert stored["email_verified"] is False


def test_an_unconfirmed_account_is_deleted_after_a_day(client, required, outbox, users):
    sign_up(client)

    stored = users.find_one({})
    kept = stored["unverified_expires_at"].replace(tzinfo=UTC) - stored["created_at"].replace(tzinfo=UTC)
    assert kept == timedelta(hours=config.UNVERIFIED_ACCOUNT_HOURS)


def test_the_database_deletes_unconfirmed_accounts_by_itself(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(db, "get_client", lambda: client)

    users = db.get_users_collection.__wrapped__()

    ttl = [i for i in users.index_information().values() if i.get("expireAfterSeconds") == 0]
    assert [i["key"] for i in ttl] == [[("unverified_expires_at", 1)]]


def test_signup_still_works_when_the_email_cant_be_sent(client, required, users, caplog):
    # The default stand-in: email isn't set up.
    with caplog.at_level(logging.WARNING, logger="voiceguard.auth"):
        body = sign_up(client)

    assert body["user"]["email_verified"] is False
    assert users.count_documents({}) == 1
    assert "email_code_not_sent" in caplog.text


def test_the_code_is_never_logged(client, required, outbox, caplog):
    with caplog.at_level(logging.DEBUG):
        token = sign_up(client)["access_token"]
        code = outbox.last_code()
        confirm(client, token, code)

    assert code not in caplog.text


# --- Confirming -------------------------------------------------------------------


def test_the_right_code_confirms_the_address(client, required, outbox, users, email_codes):
    token = sign_up(client)["access_token"]

    response = confirm(client, token, outbox.last_code())

    assert response.status_code == 200
    assert response.json()["user"]["email_verified"] is True
    stored = users.find_one({})
    assert stored["email_verified"] is True
    # Kept for good: the field the deletion runs on is gone.
    assert "unverified_expires_at" not in stored
    assert email_codes.count_documents({}) == 0


def test_spaces_in_the_code_are_fine(client, required, outbox):
    token = sign_up(client)["access_token"]
    code = outbox.last_code()

    assert confirm(client, token, f" {code[:3]} {code[3:]} ").status_code == 200


def test_a_code_works_only_once(client, required, outbox):
    token = sign_up(client)["access_token"]
    code = outbox.last_code()
    confirm(client, token, code)

    response = confirm(client, token, code)

    assert response.status_code == 409


def test_a_wrong_code_is_refused(client, required, outbox, users):
    token = sign_up(client)["access_token"]

    response = confirm(client, token, a_wrong_code(outbox.last_code()))

    assert response.status_code == 400
    assert "isn't right" in response.json()["detail"]
    assert users.find_one({})["email_verified"] is False


def test_too_many_wrong_tries_use_the_code_up(client, required, outbox):
    token = sign_up(client)["access_token"]
    code = outbox.last_code()
    for _ in range(config.EMAIL_CODE_MAX_TRIES):
        confirm(client, token, a_wrong_code(code))

    response = confirm(client, token, code)

    assert response.status_code == 400
    assert "ask for a new one" in response.json()["detail"]


def test_an_expired_code_is_refused(client, required, outbox, email_codes):
    token = sign_up(client)["access_token"]
    email_codes.update_one({}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}})

    response = confirm(client, token, outbox.last_code())

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "١٢٣٤٥٦"])
def test_a_code_must_be_six_digits(client, required, outbox, code):
    token = sign_up(client)["access_token"]

    assert confirm(client, token, code).status_code == 422


def test_confirming_needs_a_sign_in(client, required, outbox):
    sign_up(client)

    assert client.post("/api/auth/email/verify", json={"code": "123456"}).status_code == 401


def test_a_code_belongs_to_one_account(email_codes, monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret")
    code = issue_code(email_codes, "account-a")
    email_codes.insert_one({**email_codes.find_one({"_id": "account-a"}), "_id": "account-b"})

    assert check_code(email_codes, "account-b", code) == WRONG
    assert check_code(email_codes, "account-a", code) == CONFIRMED
    assert check_code(email_codes, "account-a", code) == NO_CODE


# --- Asking for a new code ----------------------------------------------------------


def test_a_new_code_replaces_the_old_one(client, required, outbox):
    token = sign_up(client)["access_token"]
    old = outbox.last_code()

    assert resend(client, token).status_code == 204
    new = outbox.last_code()
    assert len(outbox.sent) == 2

    if old != new:
        assert confirm(client, token, old).status_code == 400
    assert confirm(client, token, new).status_code == 200


def test_new_codes_are_limited(client, required, outbox):
    token = sign_up(client)["access_token"]  # the first one counts
    for _ in range(config.EMAIL_CODE_SEND_LIMIT - 1):
        assert resend(client, token).status_code == 204

    response = resend(client, token)

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert len(outbox.sent) == config.EMAIL_CODE_SEND_LIMIT


def test_no_new_code_once_confirmed(client, required, outbox):
    token = sign_up(client)["access_token"]
    confirm(client, token, outbox.last_code())

    assert resend(client, token).status_code == 409
    assert len(outbox.sent) == 1


def test_no_code_for_accounts_from_before(client, outbox):
    token = sign_up(client)["access_token"]  # switched off: like an older account

    assert resend(client, token).status_code == 409


def test_a_new_code_when_email_isnt_set_up_says_so(client, required):
    token = sign_up(client)["access_token"]

    def not_set_up():
        raise EmailUnavailable("EMAIL_API_KEY or EMAIL_FROM is not set.")

    app.dependency_overrides[get_email_sender] = not_set_up

    assert resend(client, token).status_code == 503


# --- What an unconfirmed account can't do ---------------------------------------------


def test_an_unconfirmed_account_cant_start_a_voice_check(client, required, outbox):
    token = sign_up(client)["access_token"]

    response = client.post("/api/challenge", headers=auth(token))

    assert response.status_code == 403
    assert response.json()["detail"] == NOT_CONFIRMED


def test_an_unconfirmed_account_cant_send_a_voice_check(client, required, outbox):
    token = sign_up(client)["access_token"]

    response = client.post(
        "/api/verify",
        data={"attempt_id": str(ObjectId())},
        files={"audio": ("a.webm", b"x" * 2000, "audio/webm")},
        headers=auth(token),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == NOT_CONFIRMED


def test_an_unconfirmed_account_cant_set_up_voice_id(client, required, outbox):
    token = sign_up(client)["access_token"]

    status_now = client.get("/api/enroll", headers=auth(token)).json()
    sample = client.post(
        "/api/enroll/samples", files={"audio": ("a.webm", b"x" * 2000, "audio/webm")}, headers=auth(token)
    )

    assert status_now["can_enroll"] is False
    assert status_now["prompt"] is None
    assert sample.status_code == 403
    assert sample.json()["detail"] == NOT_CONFIRMED


def test_once_confirmed_the_signup_session_can_set_up_voice_id(client, required, outbox):
    token = sign_up(client)["access_token"]
    confirm(client, token, outbox.last_code())

    assert client.get("/api/enroll", headers=auth(token)).json()["can_enroll"] is True
    assert client.post("/api/challenge", headers=auth(token)).status_code == 201


def test_the_sign_in_that_confirms_can_set_up_voice_id(client, required, outbox):
    sign_up(client)  # the signup tab was closed before confirming
    confirming = log_in(client)
    other = log_in(client)

    confirm(client, confirming, outbox.last_code())

    assert client.get("/api/enroll", headers=auth(confirming)).json()["can_enroll"] is True
    assert client.get("/api/enroll", headers=auth(other)).json()["can_enroll"] is False


def test_older_accounts_keep_working(client, outbox, monkeypatch):
    token = sign_up(client)["access_token"]  # made while switched off
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)

    login = client.post("/api/auth/login", json=LOGIN).json()

    assert login["user"]["email_verified"] is True
    assert client.post("/api/challenge", headers=auth(token)).status_code == 201


# --- Abandoned accounts -----------------------------------------------------------------


def test_an_unconfirmed_account_doesnt_block_the_real_owner(client, required, outbox, users, email_codes):
    squatter = sign_up(client, {**SIGNUP, "full_name": "Not Sam", "password": "squatter-password"})

    owner = sign_up(client)

    assert users.count_documents({}) == 1
    assert owner["user"]["id"] != squatter["user"]["id"]
    assert users.find_one({})["full_name"] == "Sam Doe"
    # Only the owner's code is left; the squatter's was deleted with them.
    assert email_codes.count_documents({}) == 1
    assert email_codes.find_one({})["_id"] == owner["user"]["id"]
    # The squatter's sign-in no longer leads anywhere.
    assert resend(client, squatter["access_token"]).status_code == 401


def test_a_confirmed_address_still_gets_409(client, required, outbox):
    token = sign_up(client)["access_token"]
    confirm(client, token, outbox.last_code())

    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 409


def test_an_older_account_still_gets_409(client, required, outbox, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", False)
    sign_up(client)
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)

    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 409


# --- The enrollment window -------------------------------------------------------------


NOW = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def confirmed_account(minutes_ago, sid="s1"):
    return {
        "created_at": NOW - timedelta(days=2),
        "signup_session_enrollment": True,
        "email_verified": True,
        "email_verified_at": NOW - timedelta(minutes=minutes_ago),
        "email_verified_sid": sid,
    }


def test_an_unconfirmed_account_never_enrolls_even_in_the_signup_session():
    account = {"created_at": NOW, "signup_session_enrollment": True, "email_verified": False}

    assert may_enroll({"src": "signup", "sid": "s1"}, account, NOW) is False


@pytest.mark.parametrize(("minutes_ago", "allowed"), [(0, True), (30, True), (31, False)])
def test_the_confirming_session_has_the_usual_window(monkeypatch, minutes_ago, allowed):
    monkeypatch.setattr(config, "ENROLL_WINDOW_MINUTES", 30)

    assert may_enroll({"src": "login", "sid": "s1"}, confirmed_account(minutes_ago), NOW) is allowed


def test_only_the_confirming_session(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_WINDOW_MINUTES", 30)

    assert may_enroll({"src": "login", "sid": "s2"}, confirmed_account(1), NOW) is False
    assert may_enroll({"src": "login"}, confirmed_account(1, sid=None), NOW) is False
