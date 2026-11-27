"""Forgot password: the reset link by email, and setting a new password (#109)."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

import pytest

import config
from email_sender import EmailUnavailable, get_email_sender
from main import app
from password_reset import find_token, issue_token, reset_email, use_token
from sessions import is_revoked, revoke_all

REQUEST_URL = "/api/auth/password-reset"
CONFIRM_URL = "/api/auth/password-reset/confirm"
CHECK_URL = "/api/auth/password-reset/check"
EMAIL, OLD, NEW = "sam@example.com", "correct-horse-battery", "a-brand-new-long-passphrase"
SENT = "If there's an account with that email, we've sent it a link to reset the password."
NOT_USABLE = "This reset link has expired or has already been used. Please ask for a new one."


class Outbox:
    """Stands in for the email sender and keeps what would have gone."""

    def __init__(self):
        self.sent = []
        self.fail = False

    def __call__(self, to, subject, text, purpose):
        if self.fail:
            raise EmailUnavailable("The email provider refused the email: status=500 error=-.")
        self.sent.append({"to": to, "subject": subject, "text": text, "purpose": purpose})

    def token(self) -> str:
        # The token is after "#token=" at the end of the link's line.
        [line] = [line for line in self.sent[-1]["text"].splitlines() if "#token=" in line]
        return line.split("#token=", 1)[1]


@pytest.fixture
def outbox(client):
    box = Outbox()
    app.dependency_overrides[get_email_sender] = lambda: box
    return box


@pytest.fixture
def account(client):
    client.post("/api/auth/signup", json={"full_name": "Sam Doe", "email": EMAIL, "password": OLD})


def ask(client, email=EMAIL):
    return client.post(REQUEST_URL, json={"email": email})


def confirm(client, token, password=NEW):
    return client.post(CONFIRM_URL, json={"token": token, "password": password})


def login(client, password):
    return client.post("/api/auth/login", json={"email": EMAIL, "password": password})


# --- Asking for a link -------------------------------------------------------------


def test_an_account_gets_a_link_by_email(client, account, outbox):
    response = ask(client, "Sam@Example.com")

    assert response.status_code == 202
    assert response.json() == {"detail": SENT}
    [email] = outbox.sent
    assert email["to"] == EMAIL
    assert email["purpose"] == "password_reset"
    assert f"{config.PASSWORD_RESET_URL}#token=" in email["text"]
    assert f"expires in {config.PASSWORD_RESET_MINUTES} minutes" in email["text"]


def test_an_address_without_an_account_gets_the_same_answer_and_no_email(client, account, outbox, password_resets):
    response = ask(client, "nobody@example.com")

    assert response.status_code == 202
    assert response.json() == {"detail": SENT}
    assert outbox.sent == []
    assert password_resets.count_documents({}) == 0


def test_only_a_hash_of_the_token_is_stored(client, account, outbox, password_resets):
    ask(client)
    token = outbox.token()

    [stored] = password_resets.find()
    assert stored["_id"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(stored)


def test_the_token_is_long_and_random(client, account, outbox):
    ask(client)
    first = outbox.token()
    ask(client)

    assert len(first) >= 40
    assert outbox.token() != first


def test_the_link_keeps_the_token_out_of_requests_to_the_frontend():
    # After "#", browsers keep it to the page: it isn't sent to the server
    # or in Referer headers.
    _, text = reset_email("TOKEN")
    assert f"{config.PASSWORD_RESET_URL}#token=TOKEN" in text
    assert "?token=" not in text


def test_a_failed_email_still_gets_the_same_answer_and_is_logged_without_secrets(client, account, outbox, caplog):
    outbox.fail = True
    with caplog.at_level(logging.INFO):
        response = ask(client)

    assert response.status_code == 202
    assert response.json() == {"detail": SENT}
    assert "password_reset_not_sent" in caplog.text
    assert EMAIL not in caplog.text


def test_without_email_set_up_every_address_gets_the_same_503(client, account, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_API_KEY", "")

    for email in (EMAIL, "nobody@example.com"):
        assert ask(client, email).status_code == 503


def test_requests_are_limited_per_address_account_or_not(client, account, outbox, monkeypatch):
    monkeypatch.setattr(config, "PASSWORD_RESET_EMAIL_LIMIT", 2)

    for email in (EMAIL, "nobody@example.com"):
        assert [ask(client, email).status_code for _ in range(3)] == [202, 202, 429]
    assert len(outbox.sent) == 2
    # Another address isn't affected.
    assert ask(client, "other@example.com").status_code == 202


def test_the_limit_counters_dont_keep_addresses(client, account, outbox, rate_limits):
    ask(client)

    assert EMAIL not in str(list(rate_limits.find()))


def test_requests_from_everyone_together_are_capped(client, account, outbox, monkeypatch):
    monkeypatch.setattr(config, "PASSWORD_RESET_RATE_LIMIT", 3)

    codes = [ask(client, f"person{i}@example.com").status_code for i in range(4)]

    assert codes == [202, 202, 202, 429]


def test_nothing_secret_is_logged(client, account, outbox, caplog):
    with caplog.at_level(logging.INFO):
        ask(client)
        token = outbox.token()
        confirm(client, token)

    assert token not in caplog.text
    assert NEW not in caplog.text
    assert EMAIL not in caplog.text
    assert "password_reset_sent" in caplog.text
    assert "password_reset user=" in caplog.text


# --- Setting the new password ----------------------------------------------------------


def test_the_link_sets_a_new_password(client, account, outbox):
    ask(client)

    response = confirm(client, outbox.token())

    assert response.status_code == 204
    assert login(client, OLD).status_code == 401
    assert login(client, NEW).status_code == 200


def test_the_link_works_once(client, account, outbox):
    ask(client)
    token = outbox.token()
    confirm(client, token)

    again = confirm(client, token, "yet-another-long-passphrase")

    assert again.status_code == 400
    assert again.json()["detail"] == NOT_USABLE
    assert login(client, NEW).status_code == 200


def test_asking_again_makes_the_earlier_link_stop_working(client, account, outbox):
    ask(client)
    first = outbox.token()
    ask(client)

    assert confirm(client, first).status_code == 400
    assert confirm(client, outbox.token()).status_code == 204


def test_an_unknown_token_is_refused(client, account):
    response = confirm(client, "x" * 43)

    assert response.status_code == 400
    assert response.json()["detail"] == NOT_USABLE


def test_a_link_expires(password_resets):
    # Relative to now: the fake database also deletes expired links by itself.
    issued = datetime.now(UTC)
    token = issue_token(password_resets, "u1", now=issued)
    later = issued + timedelta(minutes=config.PASSWORD_RESET_MINUTES)

    assert find_token(password_resets, token, now=later - timedelta(seconds=1)) == "u1"
    assert find_token(password_resets, token, now=later) is None
    assert use_token(password_resets, token, now=later) is None


def test_using_a_link_uses_up_every_link_for_the_account(password_resets):
    first = issue_token(password_resets, "u1")
    # Two links at once can't normally exist; make one anyway.
    password_resets.insert_one(
        {"_id": "other", "user_id": "u1", "expires_at": datetime.now(UTC) + timedelta(minutes=5)}
    )
    issue_token(password_resets, "u2")

    assert use_token(password_resets, first) == "u1"
    assert password_resets.count_documents({"user_id": "u1"}) == 0
    assert password_resets.count_documents({"user_id": "u2"}) == 1


@pytest.mark.parametrize(
    "password, problem",
    [("zebrafishzebrafish", "password_repetitive"), ("samsamsamsamsam1", "password_personal")],
)
def test_the_new_password_follows_the_signup_rules(client, account, outbox, password, problem):
    ask(client)
    token = outbox.token()

    response = confirm(client, token, password)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["type"] == problem
    assert error["loc"] == ["body", "password"]
    # A refused password doesn't cost the user their link.
    assert confirm(client, token).status_code == 204


def test_a_short_password_is_refused(client, account, outbox):
    ask(client)

    assert confirm(client, outbox.token(), "short").status_code == 422


def test_a_reset_clears_the_sign_in_lockout(client, account, outbox):
    for _ in range(config.LOGIN_MAX_FAILURES):
        login(client, "wrong-password-again")
    assert login(client, OLD).status_code == 423

    ask(client)
    confirm(client, outbox.token())

    assert login(client, NEW).status_code == 200


def test_a_reset_clears_the_account_wide_lockout_too(client, account, outbox, login_failures, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_ACCOUNT_MAX_FAILURES", config.LOGIN_MAX_FAILURES)
    for _ in range(config.LOGIN_MAX_FAILURES):
        login(client, "wrong-password-again")
    assert login(client, OLD).status_code == 423

    ask(client)
    confirm(client, outbox.token())

    assert login_failures.count_documents({"locked_until": {"$exists": True}}) == 0
    assert login(client, NEW).status_code == 200


def test_a_reset_ends_every_session_the_account_had(client, account, outbox):
    sessions = [login(client, OLD).json()["access_token"] for _ in range(2)]
    for token in sessions:
        assert client.post("/api/challenge", headers={"Authorization": f"Bearer {token}"}).status_code == 201

    ask(client)
    confirm(client, outbox.token())

    for token in sessions:
        refused = client.post("/api/challenge", headers={"Authorization": f"Bearer {token}"})
        assert refused.status_code == 401
        assert refused.json()["detail"] == "This sign-in has ended. Please sign in again."


def test_if_sessions_cant_be_ended_the_password_and_link_stay_as_they_were(client, account, outbox):
    from pymongo.errors import ServerSelectionTimeoutError

    from sessions import revoked_sessions

    class Unreachable:
        def __getattr__(self, name):
            def unreachable(*args, **kwargs):
                raise ServerSelectionTimeoutError("database unreachable")

            return unreachable

    ask(client)
    token = outbox.token()
    real = app.dependency_overrides[revoked_sessions]
    app.dependency_overrides[revoked_sessions] = lambda: lambda: Unreachable()

    assert confirm(client, token).status_code == 503

    app.dependency_overrides[revoked_sessions] = real
    # Never a new password with the old sessions still working.
    assert login(client, OLD).status_code == 200
    # The link wasn't used up, so the user can just try again.
    assert confirm(client, token).status_code == 204
    assert login(client, NEW).status_code == 200


# --- Ending every session of an account -----------------------------------------------


def test_sessions_started_after_the_reset_are_unaffected(revoked):
    # Relative to now: the entry is kept for a day, and mongomock applies
    # the TTL index, so a fixed date would be deleted before the asserts.
    reset = datetime.now(UTC).replace(microsecond=500_000)
    revoke_all(revoked, "u1", now=reset)
    second = int(reset.timestamp())

    assert is_revoked(revoked, "s1", "u1", second - 60)
    # Token times are whole seconds: one from the reset's own second counts
    # as before it (the safe side).
    assert is_revoked(revoked, "s1", "u1", second)
    assert not is_revoked(revoked, "s1", "u1", second + 1)
    # Only that account.
    assert not is_revoked(revoked, "s1", "u2", second - 60)


def test_a_token_without_an_issue_time_counts_as_before(revoked):
    revoke_all(revoked, "u1")

    assert is_revoked(revoked, "s1", "u1", None)


def test_a_later_reset_moves_the_line_and_an_earlier_one_cant_move_it_back(revoked):
    noon = datetime.now(UTC) - timedelta(minutes=10)
    revoke_all(revoked, "u1", now=noon)
    revoke_all(revoked, "u1", now=noon + timedelta(minutes=5))
    revoke_all(revoked, "u1", now=noon + timedelta(minutes=1))

    assert is_revoked(revoked, "s1", "u1", noon.timestamp() + 240)


def test_a_signed_out_session_is_still_refused_with_the_account_given(revoked):
    from sessions import revoke

    revoke(revoked, "s1")

    assert is_revoked(revoked, "s1", "u1", datetime.now(UTC).timestamp())
    assert is_revoked(revoked, "s1")


# Checking a link when the reset screen opens, without using it up.


def check(client, token):
    return client.post(CHECK_URL, json={"token": token})


def test_a_fresh_link_checks_as_usable_and_still_works_afterwards(client, account, outbox):
    ask(client)
    token = outbox.token()

    assert check(client, token).status_code == 204
    assert check(client, token).status_code == 204
    assert confirm(client, token).status_code == 204


def test_a_used_link_checks_as_unusable(client, account, outbox):
    ask(client)
    token = outbox.token()
    confirm(client, token)

    response = check(client, token)

    assert response.status_code == 400
    assert response.json()["detail"] == NOT_USABLE


def test_an_older_link_checks_as_unusable_once_a_newer_one_is_sent(client, account, outbox):
    ask(client)
    first = outbox.token()
    ask(client)

    assert check(client, first).status_code == 400
    assert check(client, outbox.token()).status_code == 204


def test_an_unknown_or_expired_link_checks_as_unusable(client, account, outbox, password_resets):
    assert check(client, "x" * 43).status_code == 400

    ask(client)
    token = outbox.token()
    password_resets.update_many({}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}})
    assert check(client, token).status_code == 400


def test_a_link_for_a_deleted_account_checks_as_unusable(client, account, outbox, users):
    ask(client)
    token = outbox.token()
    users.delete_many({})

    assert check(client, token).status_code == 400


def test_checking_says_nothing_about_the_account(client, account, outbox):
    ask(client)

    response = check(client, outbox.token())

    assert response.status_code == 204
    assert response.content == b""


# Security events (#167): a reset nobody asked for is what a takeover looks like.


def recorded(audit_events, event):
    return list(audit_events.find({"event": event}))


def account_stand_in(users):
    from audit import hashed

    return hashed(str(users.find_one({"email": EMAIL})["_id"]))


def test_asking_for_a_link_is_recorded_under_the_account(client, account, outbox, users, audit_events):
    ask(client)

    [event] = recorded(audit_events, "password_reset_requested")
    assert event["user"] == account_stand_in(users)
    assert event["reason"] is None


def test_asking_for_an_address_without_an_account_is_recorded_without_one(client, account, outbox, audit_events):
    # Recorded either way, so both answers take the same time.
    ask(client, "nobody@example.com")

    [event] = recorded(audit_events, "password_reset_requested")
    assert event["user"] is None
    assert "nobody" not in str(event)


def test_setting_a_new_password_is_recorded(client, account, outbox, users, audit_events):
    ask(client)
    assert confirm(client, outbox.token()).status_code == 204

    [event] = recorded(audit_events, "password_reset")
    assert event["user"] == account_stand_in(users)


def test_a_refused_reset_isnt_recorded_as_one(client, account, outbox, audit_events):
    ask(client)
    assert confirm(client, "x" * 43).status_code == 400
    assert confirm(client, outbox.token(), password="short").status_code == 422

    assert recorded(audit_events, "password_reset") == []
