from datetime import UTC, datetime, timedelta

import pytest

import config
from enrollment_window import may_enroll

CUT_OFF = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)
SIGNUP = {"src": "signup"}
LOGIN = {"src": "login"}


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_WINDOW_MINUTES", 30)
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", CUT_OFF)


def account(created):
    return {"created_at": created}


AFTER = CUT_OFF + timedelta(days=1)


@pytest.mark.parametrize(
    ("minutes_after_creation", "allowed"),
    [(0, True), (29, True), (30, True), (31, False), (600, False)],
)
def test_the_signup_window(minutes_after_creation, allowed):
    created = AFTER
    now = created + timedelta(minutes=minutes_after_creation)

    assert may_enroll(SIGNUP, account(created), now) is allowed


def test_a_sign_in_token_never_opens_the_window_after_the_cut_off():
    assert may_enroll(LOGIN, account(AFTER), AFTER + timedelta(minutes=1)) is False


def test_grace_covers_older_accounts_until_the_cut_off():
    older = CUT_OFF - timedelta(days=20)

    assert may_enroll(LOGIN, account(older), CUT_OFF - timedelta(seconds=1)) is True
    assert may_enroll(LOGIN, account(older), CUT_OFF) is False


def test_no_grace_when_turned_off(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_GRACE_UNTIL", None)

    assert may_enroll(LOGIN, account(CUT_OFF - timedelta(days=20)), CUT_OFF - timedelta(days=1)) is False


def test_dates_from_the_database_without_a_zone_are_utc():
    naive = datetime(2026, 11, 20, 12, 0)

    assert may_enroll(SIGNUP, account(naive), datetime(2026, 11, 20, 12, 10, tzinfo=UTC)) is True


def test_fails_closed_without_an_account():
    assert may_enroll(SIGNUP, None, AFTER) is False
    assert may_enroll(SIGNUP, {}, AFTER) is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-16T05:00:00Z", CUT_OFF),
        ("2026-11-16T00:00:00-05:00", CUT_OFF),
        ("2026-11-16T05:00:00", CUT_OFF),
        ("", None),
        ("   ", None),
    ],
)
def test_the_cut_off_setting(value, expected):
    assert config.grace_until(value) == expected

