from datetime import datetime, timedelta, timezone

from login_lockout import clear_failures, record_failure, seconds_locked

# A day ahead: the test database deletes records whose expiry has already
# passed in real time, so the times used here must still be in the future.
NOW = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
MAX, WINDOW, LOCKOUT = 3, 900, 1800


def fail(login_failures, email="sam@example.com", now=NOW):
    return record_failure(login_failures, email, MAX, WINDOW, LOCKOUT, now=now)


def test_failures_under_the_limit_do_not_lock(login_failures):
    assert fail(login_failures) == 0
    assert fail(login_failures) == 0
    assert seconds_locked(login_failures, "sam@example.com", now=NOW) == 0


def test_reaching_the_limit_locks_for_the_lockout_time(login_failures):
    fail(login_failures)
    fail(login_failures)

    assert fail(login_failures) == LOCKOUT
    assert seconds_locked(login_failures, "sam@example.com", now=NOW) == LOCKOUT
    assert seconds_locked(login_failures, "sam@example.com", now=NOW + timedelta(minutes=10)) == 20 * 60


def test_lock_ends_after_the_lockout_time(login_failures):
    for _ in range(MAX):
        fail(login_failures)

    assert seconds_locked(login_failures, "sam@example.com", now=NOW + timedelta(seconds=LOCKOUT)) == 0


def test_failures_spread_beyond_the_window_do_not_lock(login_failures):
    fail(login_failures)
    fail(login_failures)

    # The first window has ended, so this starts a new count of one.
    assert fail(login_failures, now=NOW + timedelta(seconds=WINDOW)) == 0
    assert login_failures.find_one()["failures"] == 1


def test_email_case_does_not_matter(login_failures):
    fail(login_failures, email="Sam@Example.com")
    fail(login_failures, email="SAM@example.com")

    assert fail(login_failures, email="sam@example.com") == LOCKOUT


def test_each_email_has_its_own_count(login_failures):
    fail(login_failures, email="sam@example.com")
    fail(login_failures, email="sam@example.com")

    assert fail(login_failures, email="alex@example.com") == 0


def test_clearing_forgets_earlier_failures(login_failures):
    fail(login_failures)
    fail(login_failures)
    clear_failures(login_failures, "sam@example.com")

    assert fail(login_failures) == 0


def test_email_is_not_stored(login_failures):
    fail(login_failures, email="sam@example.com")

    record = login_failures.find_one()
    assert "sam@example.com" not in str(record)


def test_record_is_kept_until_the_lockout_ends(login_failures):
    for _ in range(MAX):
        fail(login_failures)

    record = login_failures.find_one()
    assert record["expires_at"].replace(tzinfo=timezone.utc) == NOW + timedelta(seconds=LOCKOUT)
    assert login_failures.index_information()["expires_at_1"]["expireAfterSeconds"] == 0
