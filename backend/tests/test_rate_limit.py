from datetime import datetime, timedelta, timezone

import pytest

from rate_limit import RateLimited, count_request

# 20 past the hour, a day ahead: the test database deletes counters whose
# window has already ended, so the window must still be open in real time.
NEXT_DAY_HOUR = (datetime.now(timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
NOW = NEXT_DAY_HOUR + timedelta(minutes=20)
HOUR = 3600


def hit(rate_limits, user_id="user-1", action="verify", limit=3, now=NOW):
    count_request(rate_limits, action, user_id, limit, HOUR, now=now)


def test_requests_up_to_the_limit_are_allowed(rate_limits):
    for _ in range(3):
        hit(rate_limits)


def test_one_over_the_limit_is_refused_with_the_wait(rate_limits):
    for _ in range(3):
        hit(rate_limits)

    with pytest.raises(RateLimited) as refused:
        hit(rate_limits)

    # 40 minutes until the window ends on the hour.
    assert refused.value.retry_after == 40 * 60


def test_each_user_has_their_own_count(rate_limits):
    for _ in range(3):
        hit(rate_limits, user_id="user-1")

    hit(rate_limits, user_id="user-2")


def test_each_action_has_its_own_count(rate_limits):
    for _ in range(3):
        hit(rate_limits, action="verify")

    hit(rate_limits, action="challenge")


def test_the_count_starts_again_in_the_next_window(rate_limits):
    for _ in range(3):
        hit(rate_limits)

    hit(rate_limits, now=NOW + timedelta(minutes=40))


def test_counter_is_deleted_when_its_window_ends(rate_limits):
    hit(rate_limits)

    counter = rate_limits.find_one()
    assert counter["expires_at"].replace(tzinfo=timezone.utc) == NEXT_DAY_HOUR + timedelta(hours=1)
    assert rate_limits.index_information()["expires_at_1"]["expireAfterSeconds"] == 0
