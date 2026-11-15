from datetime import UTC, datetime, timedelta

import pytest

import config
from transcription_budget import BudgetUsedUp, release_transcription, reserve_transcription

NOON = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def budget_of_two(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIPTION_DAILY_BUDGET", 2)


def count(rate_limits):
    return rate_limits.find_one({})["count"]


def test_reserves_up_to_the_budget_then_refuses(rate_limits):
    reserve_transcription(rate_limits, now=NOON)
    reserve_transcription(rate_limits, now=NOON)

    with pytest.raises(BudgetUsedUp) as refused:
        reserve_transcription(rate_limits, now=NOON)
    # Until midnight UTC, and the refused one isn't counted.
    assert refused.value.retry_after == 12 * 3600
    assert count(rate_limits) == 2


def test_requests_together_cant_pass_the_budget(rate_limits):
    # Each reservation is one atomic step: however many arrive, only the
    # budget's worth get through.
    allowed = 0
    for _ in range(10):
        try:
            reserve_transcription(rate_limits, now=NOON)
            allowed += 1
        except BudgetUsedUp:
            pass

    assert allowed == 2
    assert count(rate_limits) == 2


def test_a_released_slot_can_be_used_again(rate_limits):
    reserve_transcription(rate_limits, now=NOON)
    reserve_transcription(rate_limits, now=NOON)
    release_transcription(rate_limits, now=NOON)

    reserve_transcription(rate_limits, now=NOON)
    assert count(rate_limits) == 2


def test_release_never_goes_below_zero(rate_limits):
    reserve_transcription(rate_limits, now=NOON)
    release_transcription(rate_limits, now=NOON)
    release_transcription(rate_limits, now=NOON)

    assert count(rate_limits) == 0


def test_the_budget_starts_again_the_next_day(rate_limits):
    reserve_transcription(rate_limits, now=NOON)
    reserve_transcription(rate_limits, now=NOON)

    reserve_transcription(rate_limits, now=NOON + timedelta(hours=12, seconds=1))


def test_the_count_expires_on_its_own(rate_limits):
    reserve_transcription(rate_limits, now=NOON)

    record = rate_limits.find_one({})
    assert record["expires_at"].replace(tzinfo=UTC) > NOON + timedelta(days=1)
