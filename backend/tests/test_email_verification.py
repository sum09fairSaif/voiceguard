"""Confirming the email address at signup (#110), without signup saying
whether an address already has an account (#111)."""

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
from routers.auth import CHECK_EMAIL, CODE_NOT_ACCEPTED
from security import create_access_token

SIGNUP = {"full_name": "Sam Doe", "email": "sam@example.com", "password": "correct-horse-battery"}
LOGIN = {"email": "sam@example.com", "password": "correct-horse-battery"}


class Outbox:
    """Stands in for the email sender and keeps what would have been sent."""

    def __init__(self):
        self.sent = []
        self.fail = False

    def __call__(self, to, subject, text, purpose):
        if self.fail:
            raise EmailUnavailable("The email provider refused the email: status=500 error=-.")
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
    return client.post("/api/auth/signup", json=body)


def confirm(client, code, email="sam@example.com"):
    return client.post("/api/auth/email/verify", json={"email": email, "code": code})


def resend(client, email="sam@example.com"):
    return client.post("/api/auth/email/code", json={"email": email})


def signed_up_and_confirmed(client, outbox):
    sign_up(client)
    return confirm(client, outbox.last_code()).json()


def unconfirmed_token(users):
    # The API never gives an unconfirmed account a sign-in any more (#111);
    # made directly, to check the routes still refuse one.
    return create_access_token(str(users.find_one({})["_id"]), source="signup")


def a_wrong_code(right):
    return "000000" if right != "000000" else "111111"


# --- Signup -----------------------------------------------------------------------


def test_while_switched_off_signup_is_as_before(client, outbox, users):
    response = sign_up(client)

    assert response.status_code == 201
    assert response.json()["user"]["email_verified"] is True
    assert response.json()["access_token"]
    assert outbox.sent == []
    stored = users.find_one({})
    assert "email_verified" not in stored
    assert "unverified_expires_at" not in stored


def test_while_switched_off_a_taken_address_still_gets_409(client, outbox):
    # Without confirmation, signup answers with a sign-in, so it can't hide this.
    sign_up(client)

    assert sign_up(client).status_code == 409


def test_a_new_account_starts_unverified_and_gets_a_code(client, required, outbox, users, email_codes):
    response = sign_up(client)

    assert response.status_code == 202
    assert response.json() == {"detail": CHECK_EMAIL}
    ((email,),) = [outbox.sent]
    assert email["to"] == "sam@example.com"
    assert email["purpose"] == "email_verification"
    code = outbox.last_code()
    # Only a hash is stored, never the code.
    (record,) = list(email_codes.find({}))
    assert code not in str(record)
    assert record["code_hash"] != code
    assert users.find_one({})["email_verified"] is False


def test_signup_gives_no_sign_in_until_the_address_is_confirmed(client, required, outbox):
    response = sign_up(client)

    assert "access_token" not in response.json()
    assert "user" not in response.json()
    assert "set-cookie" not in response.headers


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


def test_a_failed_email_still_gets_the_same_answer_and_is_logged(client, required, outbox, caplog):
    outbox.fail = True
    with caplog.at_level(logging.WARNING, logger="voiceguard.auth"):
        response = sign_up(client)

    assert response.status_code == 202
    assert response.json() == {"detail": CHECK_EMAIL}
    assert "email_code_not_sent" in caplog.text
    assert "sam@example.com" not in caplog.text


def test_with_email_not_set_up_every_signup_gets_the_same_503(client, required, users):
    # The default stand-in: email isn't set up, so nothing could ever confirm.
    assert sign_up(client).status_code == 503
    assert sign_up(client, {**SIGNUP, "email": "new@example.com"}).status_code == 503
    assert users.count_documents({}) == 0


def test_the_code_is_never_logged(client, required, outbox, caplog):
    with caplog.at_level(logging.DEBUG):
        sign_up(client)
        code = outbox.last_code()
        confirm(client, code)

    assert code not in caplog.text


# --- An address that already has an account (#111) ---------------------------------


def test_an_address_with_an_account_gets_the_same_answer(client, required, outbox):
    first = sign_up(client)
    confirm(client, outbox.last_code())

    again = sign_up(client, {**SIGNUP, "full_name": "Someone Else", "password": "a-different-long-password"})

    assert again.status_code == first.status_code == 202
    assert again.json() == first.json()
    assert again.headers.get("set-cookie") == first.headers.get("set-cookie")


def test_its_owner_gets_a_notice_instead_of_a_code(client, required, outbox, users, email_codes):
    signed_up_and_confirmed(client, outbox)
    outbox.sent.clear()

    sign_up(client, {**SIGNUP, "password": "a-different-long-password"})

    ((notice,),) = [outbox.sent]
    assert notice["to"] == "sam@example.com"
    assert notice["purpose"] == "account_exists"
    assert "already have one" in notice["text"]
    assert not re.search(r"\b\d{6}\b", notice["text"])
    # The account is untouched, and no code waits for it.
    assert users.count_documents({}) == 1
    assert users.find_one({})["email_verified"] is True
    assert email_codes.count_documents({}) == 0


def test_an_older_account_gets_the_notice_too(client, outbox, users, monkeypatch):
    sign_up(client)  # made while switched off
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)

    response = sign_up(client, {**SIGNUP, "password": "a-different-long-password"})

    assert response.status_code == 202
    assert [email["purpose"] for email in outbox.sent] == ["account_exists"]
    assert users.count_documents({}) == 1


def test_the_notice_is_logged_without_the_address(client, required, outbox, caplog):
    signed_up_and_confirmed(client, outbox)
    with caplog.at_level(logging.DEBUG, logger="voiceguard.auth"):
        sign_up(client)

    assert "account_exists_notice_sent" in caplog.text
    assert "sam@example.com" not in caplog.text


def test_the_answer_comes_before_any_account_work(client, required, outbox, monkeypatch):
    # Timing: what differs between the two cases runs after the answer.
    # Only rate limits and the password hash run before, the same for both.
    import routers.auth as auth_routes

    seen = []
    monkeypatch.setattr(auth_routes, "_finish_signup", lambda *args: seen.append(args[4]))

    response = sign_up(client)

    assert response.status_code == 202
    assert seen == ["sam@example.com"]


def test_signing_in_to_an_unconfirmed_account_is_like_a_wrong_password(client, required, outbox):
    # Otherwise: sign up with an address and a password of your own, then
    # sign in with them; success would mean the address was free.
    sign_up(client)

    right_password = client.post("/api/auth/login", json=LOGIN)
    wrong_password = client.post("/api/auth/login", json={**LOGIN, "password": "not-the-password"})

    assert right_password.status_code == wrong_password.status_code == 401
    assert right_password.json() == wrong_password.json()


def test_an_unconfirmed_account_is_locked_like_any_other(client, required, outbox):
    sign_up(client)
    for _ in range(config.LOGIN_MAX_FAILURES):
        client.post("/api/auth/login", json=LOGIN)

    assert client.post("/api/auth/login", json=LOGIN).status_code == 423


# --- Confirming -------------------------------------------------------------------


def test_the_right_code_confirms_the_address_and_signs_in(client, required, outbox, users, email_codes):
    sign_up(client)

    response = confirm(client, outbox.last_code())

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email_verified"] is True
    assert body["user"]["email"] == "sam@example.com"
    assert body["access_token"]
    assert "set-cookie" in response.headers
    stored = users.find_one({})
    assert stored["email_verified"] is True
    # Kept for good: the field the deletion runs on is gone.
    assert "unverified_expires_at" not in stored
    assert email_codes.count_documents({}) == 0


def test_the_address_is_matched_whatever_its_case(client, required, outbox):
    sign_up(client)

    assert confirm(client, outbox.last_code(), email="Sam@Example.com").status_code == 200


def test_spaces_in_the_code_are_fine(client, required, outbox):
    sign_up(client)
    code = outbox.last_code()

    assert confirm(client, f" {code[:3]} {code[3:]} ").status_code == 200


def test_a_code_works_only_once(client, required, outbox):
    sign_up(client)
    code = outbox.last_code()
    confirm(client, code)

    response = confirm(client, code)

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_NOT_ACCEPTED


def test_a_wrong_code_is_refused(client, required, outbox, users):
    sign_up(client)

    response = confirm(client, a_wrong_code(outbox.last_code()))

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_NOT_ACCEPTED
    assert users.find_one({})["email_verified"] is False


def test_too_many_wrong_tries_use_the_code_up(client, required, outbox):
    sign_up(client)
    code = outbox.last_code()
    for _ in range(config.EMAIL_CODE_MAX_TRIES):
        confirm(client, a_wrong_code(code))

    assert confirm(client, code).status_code == 400


def test_an_expired_code_is_refused(client, required, outbox, email_codes):
    sign_up(client)
    email_codes.update_one({}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}})

    assert confirm(client, outbox.last_code()).status_code == 400


def test_every_failure_gets_the_same_answer(client, required, outbox):
    # A wrong code for an account waiting for one, and any code for an
    # address with no such account, look the same.
    sign_up(client)
    wrong = confirm(client, a_wrong_code(outbox.last_code()))
    no_account = confirm(client, "123456", email="nobody@example.com")

    assert wrong.status_code == no_account.status_code == 400
    assert wrong.json() == no_account.json()


def test_a_confirmed_address_cant_be_confirmed_again(client, required, outbox):
    signed_up_and_confirmed(client, outbox)

    response = confirm(client, "123456")

    assert response.status_code == 400
    assert response.json()["detail"] == CODE_NOT_ACCEPTED


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "١٢٣٤٥٦"])
def test_a_code_must_be_six_digits(client, required, outbox, code):
    sign_up(client)

    assert confirm(client, code).status_code == 422


def test_confirming_is_limited_per_client(client, required, outbox, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_CODE_CLIENT_LIMIT", 2)
    headers = {"CF-Connecting-IP": "203.0.113.7"}
    for _ in range(2):
        client.post("/api/auth/email/verify", json={"email": "a@example.com", "code": "123456"}, headers=headers)

    response = client.post(
        "/api/auth/email/verify", json={"email": "b@example.com", "code": "123456"}, headers=headers
    )

    assert response.status_code == 429


def test_a_code_belongs_to_one_account(email_codes, monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret")
    code = issue_code(email_codes, "account-a")
    email_codes.insert_one({**email_codes.find_one({"_id": "account-a"}), "_id": "account-b"})

    assert check_code(email_codes, "account-b", code) == WRONG
    assert check_code(email_codes, "account-a", code) == CONFIRMED
    assert check_code(email_codes, "account-a", code) == NO_CODE


# --- Asking for a new code ----------------------------------------------------------


def test_a_new_code_replaces_the_old_one(client, required, outbox):
    sign_up(client)
    old = outbox.last_code()

    response = resend(client)

    assert response.status_code == 202
    assert response.json() == {"detail": CHECK_EMAIL}
    new = outbox.last_code()
    assert len(outbox.sent) == 2
    if old != new:
        assert confirm(client, old).status_code == 400
    assert confirm(client, new).status_code == 200


def test_asking_for_an_address_without_an_unconfirmed_account_sends_nothing(client, required, outbox):
    signed_up_and_confirmed(client, outbox)
    sent_before = len(outbox.sent)

    confirmed = resend(client)
    unknown = resend(client, "nobody@example.com")

    assert confirmed.status_code == unknown.status_code == 202
    assert confirmed.json() == unknown.json() == {"detail": CHECK_EMAIL}
    assert len(outbox.sent) == sent_before


def test_emails_to_one_address_are_limited_account_or_not(client, required, outbox):
    sign_up(client)  # the first code counts
    for _ in range(config.EMAIL_CODE_SEND_LIMIT - 1):
        assert resend(client).status_code == 202

    refused = resend(client)

    assert refused.status_code == 429
    assert "Retry-After" in refused.headers
    assert len(outbox.sent) == config.EMAIL_CODE_SEND_LIMIT
    # An address without an account is counted the same way.
    for _ in range(config.EMAIL_CODE_SEND_LIMIT):
        assert resend(client, "nobody@example.com").status_code == 202
    assert resend(client, "nobody@example.com").status_code == 429


def test_the_limit_counts_addresses_hashed(client, required, outbox, rate_limits):
    resend(client, "nobody@example.com")

    assert "nobody@example.com" not in str(list(rate_limits.find({})))


def test_a_new_code_when_email_isnt_set_up_says_so_for_everyone(client, required):
    assert resend(client).status_code == 503
    assert resend(client, "nobody@example.com").status_code == 503


# --- What an unconfirmed account can't do ---------------------------------------------


def test_an_unconfirmed_account_cant_start_a_voice_check(client, required, outbox, users):
    sign_up(client)

    response = client.post("/api/challenge", headers=auth(unconfirmed_token(users)))

    assert response.status_code == 403
    assert response.json()["detail"] == NOT_CONFIRMED


def test_an_unconfirmed_account_cant_send_a_voice_check(client, required, outbox, users):
    sign_up(client)

    response = client.post(
        "/api/verify",
        data={"attempt_id": str(ObjectId())},
        files={"audio": ("a.webm", b"x" * 2000, "audio/webm")},
        headers=auth(unconfirmed_token(users)),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == NOT_CONFIRMED


def test_an_unconfirmed_account_cant_set_up_voice_id(client, required, outbox, users):
    sign_up(client)
    token = unconfirmed_token(users)

    status_now = client.get("/api/enroll", headers=auth(token)).json()
    sample = client.post(
        "/api/enroll/samples", files={"audio": ("a.webm", b"x" * 2000, "audio/webm")}, headers=auth(token)
    )

    assert status_now["can_enroll"] is False
    assert status_now["prompt"] is None
    assert sample.status_code == 403
    assert sample.json()["detail"] == NOT_CONFIRMED


def test_the_session_started_by_confirming_can_set_up_voice_id(client, required, outbox):
    token = signed_up_and_confirmed(client, outbox)["access_token"]

    assert client.get("/api/enroll", headers=auth(token)).json()["can_enroll"] is True
    assert client.post("/api/challenge", headers=auth(token)).status_code == 201


def test_a_later_sign_in_can_use_the_account_but_not_set_up_voice_id(client, required, outbox):
    signed_up_and_confirmed(client, outbox)

    later = client.post("/api/auth/login", json=LOGIN)

    assert later.status_code == 200
    token = later.json()["access_token"]
    assert client.get("/api/enroll", headers=auth(token)).json()["can_enroll"] is False


def test_older_accounts_keep_working(client, outbox, monkeypatch):
    token = sign_up(client).json()["access_token"]  # made while switched off
    monkeypatch.setattr(config, "EMAIL_VERIFICATION_REQUIRED", True)

    login = client.post("/api/auth/login", json=LOGIN).json()

    assert login["user"]["email_verified"] is True
    assert client.post("/api/challenge", headers=auth(token)).status_code == 201


# --- Abandoned accounts -----------------------------------------------------------------


def test_an_unconfirmed_account_doesnt_block_the_real_owner(client, required, outbox, users, email_codes):
    sign_up(client, {**SIGNUP, "full_name": "Not Sam", "password": "squatter-password"})
    squatter_id = str(users.find_one({})["_id"])

    sign_up(client)

    assert users.count_documents({}) == 1
    owner = users.find_one({})
    assert owner["full_name"] == "Sam Doe"
    assert str(owner["_id"]) != squatter_id
    # Only the owner's code is left; the squatter's was deleted with them.
    assert email_codes.count_documents({}) == 1
    assert email_codes.find_one({})["_id"] == str(owner["_id"])
    # The owner gets a code, not a notice: the address had no real account.
    assert outbox.sent[-1]["purpose"] == "email_verification"
    assert confirm(client, outbox.last_code()).status_code == 200


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
