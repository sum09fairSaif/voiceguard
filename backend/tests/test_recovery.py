"""Recording a new Voice ID after the voice check keeps failing (#20):
asking for the emailed code, and confirming it."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

import config
import switches
from audit import hashed
from email_sender import EmailUnavailable, get_email_sender
from main import app
from recovery import in_recovery_session
from security import create_access_token
from voice_attempts import record_outcome
from voiceprints import save_voiceprint

CODE_URL = "/api/recovery/code"
VERIFY_URL = "/api/recovery/verify"
EMAIL = "sam@example.com"


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
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def account(users):
    user_id = ObjectId()
    users.insert_one({"_id": user_id, "full_name": "Sam Doe", "email": EMAIL})
    return str(user_id)


@pytest.fixture
def enrolled(voiceprints, account):
    save_voiceprint(voiceprints, account, [0.1] * 192)


@pytest.fixture
def paused(voice_failures, account):
    for _ in range(config.VOICE_MAX_FAILURES):
        record_outcome(voice_failures, account, "rejected")


def session(user_id, sid="session-1"):
    return {"Authorization": f"Bearer {create_access_token(user_id, session_id=sid)}"}


def ask(client, user_id, sid="session-1"):
    return client.post(CODE_URL, headers=session(user_id, sid))


def confirm(client, user_id, code, sid="session-1"):
    return client.post(VERIFY_URL, json={"code": code}, headers=session(user_id, sid))


# --- Asking for a code ---------------------------------------------------------


def test_a_paused_account_gets_a_code_at_its_own_address(client, outbox, account, enrolled, paused, audit_events):
    response = ask(client, account)

    assert response.status_code == 202
    [email] = outbox.sent
    assert email["to"] == EMAIL
    assert email["purpose"] == "voice_recovery"
    assert re.search(r"\b\d{6}\b", email["text"])
    [event] = list(audit_events.find({"event": "recovery_code_sent"}))
    assert event["user"] == hashed(account)


def test_only_a_hash_of_the_code_is_kept(client, outbox, account, enrolled, paused, recovery_codes):
    ask(client, account)

    record = recovery_codes.find_one({"_id": account})
    assert outbox.last_code() not in str(record)


def test_no_code_while_voice_checks_arent_paused(client, outbox, account, enrolled):
    response = ask(client, account)

    assert response.status_code == 409
    assert outbox.sent == []


def test_no_code_without_a_voice_id_to_replace(client, outbox, account, paused):
    response = ask(client, account)

    assert response.status_code == 409
    assert outbox.sent == []


def test_asking_needs_a_sign_in(client, outbox):
    assert client.post(CODE_URL).status_code == 401
    assert outbox.sent == []


def test_an_unconfirmed_email_address_gets_no_code(client, outbox, account, enrolled, paused, users):
    users.update_one({"_id": ObjectId(account)}, {"$set": {"email_verified": False}})

    assert ask(client, account).status_code == 403
    assert outbox.sent == []


def test_asking_is_limited_per_account(client, outbox, account, enrolled, paused):
    for _ in range(config.EMAIL_CODE_SEND_LIMIT):
        assert ask(client, account).status_code == 202

    assert ask(client, account).status_code == 429
    assert len(outbox.sent) == config.EMAIL_CODE_SEND_LIMIT


def test_a_newer_code_replaces_the_older_one(client, outbox, account, enrolled, paused):
    ask(client, account)
    first = outbox.last_code()
    ask(client, account)
    second = outbox.last_code()

    if first != second:
        assert confirm(client, account, first).status_code == 400
    assert confirm(client, account, second).status_code == 200


def test_email_trouble_is_a_503(client, outbox, account, enrolled, paused):
    outbox.fail = True

    assert ask(client, account).status_code == 503


def test_asking_pauses_with_enrollment(client, outbox, account, enrolled, paused, switch_store):
    switches.set_switch(switch_store, "enrollment", False, by="tester", reason="test")
    switches._cache.clear()

    response = ask(client, account)

    assert response.status_code == 503
    assert response.json()["paused"] == "enrollment"
    assert outbox.sent == []


# --- Confirming the code -------------------------------------------------------


def test_the_code_lets_this_session_record_a_new_voice_id(
    client, outbox, account, enrolled, paused, users, audit_events
):
    ask(client, account)

    response = confirm(client, account, outbox.last_code())

    assert response.status_code == 200
    assert response.json() == {"enroll_minutes": config.ENROLL_WINDOW_MINUTES}
    user = users.find_one({"_id": ObjectId(account)})
    assert in_recovery_session({"sid": "session-1"}, user)
    assert list(audit_events.find({"event": "recovery_confirmed"}))


def test_the_grant_belongs_to_the_session_that_confirmed(client, outbox, account, enrolled, paused, users):
    ask(client, account)
    confirm(client, account, outbox.last_code())

    user = users.find_one({"_id": ObjectId(account)})
    assert not in_recovery_session({"sid": "another-session"}, user)
    assert not in_recovery_session({}, user)


def test_the_grant_runs_out(account, users):
    granted = datetime.now(UTC) - timedelta(minutes=config.ENROLL_WINDOW_MINUTES, seconds=1)
    user = {"recovery_sid": "s1", "recovery_at": granted}

    assert not in_recovery_session({"sid": "s1"}, user)
    assert in_recovery_session({"sid": "s1"}, {**user, "recovery_at": datetime.now(UTC)})
    # A time in the future (clock trouble) never opens it.
    assert not in_recovery_session({"sid": "s1"}, {**user, "recovery_at": datetime.now(UTC) + timedelta(minutes=5)})
    assert not in_recovery_session({"sid": "s1"}, None)


def test_a_wrong_code_is_refused(client, outbox, account, enrolled, paused, users):
    ask(client, account)
    code = outbox.last_code()
    wrong = f"{(int(code) + 1) % 10**6:06d}"

    response = confirm(client, account, wrong)

    assert response.status_code == 400
    assert "recovery_sid" not in users.find_one({"_id": ObjectId(account)})


def test_a_code_works_once(client, outbox, account, enrolled, paused):
    ask(client, account)
    code = outbox.last_code()

    assert confirm(client, account, code).status_code == 200
    assert confirm(client, account, code).status_code == 400


def test_an_expired_code_is_refused(client, outbox, account, enrolled, paused, recovery_codes):
    ask(client, account)
    recovery_codes.update_many({}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}})

    assert confirm(client, account, outbox.last_code()).status_code == 400


def test_too_many_wrong_tries_use_the_code_up(client, outbox, account, enrolled, paused):
    ask(client, account)
    code = outbox.last_code()
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    for _ in range(config.EMAIL_CODE_MAX_TRIES):
        confirm(client, account, wrong)

    assert confirm(client, account, code).status_code == 400


def test_a_signup_code_isnt_a_recovery_code(client, outbox, account, enrolled, paused, email_codes):
    from email_verification import issue_code

    signup_code = issue_code(email_codes, account)

    assert confirm(client, account, signup_code).status_code == 400


def test_another_accounts_code_is_refused(client, outbox, account, enrolled, paused, users):
    ask(client, account)
    code = outbox.last_code()
    other = str(users.insert_one({"full_name": "Alex Roe", "email": "alex@example.com"}).inserted_id)

    assert confirm(client, other, code).status_code == 400


def test_confirming_clears_samples_left_from_before(client, outbox, account, enrolled, paused, enrollments):
    enrollments.insert_one({"_id": account, "samples": [b"old"]})
    ask(client, account)

    confirm(client, account, outbox.last_code())

    assert enrollments.find_one({"_id": account}) is None


def test_confirming_pauses_with_enrollment(client, outbox, account, enrolled, paused, switch_store):
    ask(client, account)
    switches.set_switch(switch_store, "enrollment", False, by="tester", reason="test")
    switches._cache.clear()

    response = confirm(client, account, outbox.last_code())

    assert response.status_code == 503
    switches.set_switch(switch_store, "enrollment", True, by="tester", reason="test")
    switches._cache.clear()
    # The paused try didn't use the code up.
    assert confirm(client, account, outbox.last_code()).status_code == 200


def test_the_code_is_never_logged(client, outbox, account, enrolled, paused, caplog):
    with caplog.at_level("DEBUG"):
        ask(client, account)
        code = outbox.last_code()
        confirm(client, account, code)

    assert code not in caplog.text
