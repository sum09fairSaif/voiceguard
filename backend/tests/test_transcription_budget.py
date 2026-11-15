from datetime import UTC, datetime, timedelta

import pytest

import config
from transcription_budget import BudgetUsedUp, ensure_budget_left, spend_transcription

NOON = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def budget_of_two(monkeypatch):
    monkeypatch.setattr(config, "TRANSCRIPTION_DAILY_BUDGET", 2)


def test_allows_calls_up_to_the_budget(rate_limits):
    for _ in range(2):
        ensure_budget_left(rate_limits, now=NOON)
        spend_transcription(rate_limits, now=NOON)

    with pytest.raises(BudgetUsedUp) as refused:
        ensure_budget_left(rate_limits, now=NOON)
    # Until midnight UTC.
    assert refused.value.retry_after == 12 * 3600


def test_the_budget_starts_again_the_next_day(rate_limits):
    for _ in range(2):
        spend_transcription(rate_limits, now=NOON)

    ensure_budget_left(rate_limits, now=NOON + timedelta(hours=12, seconds=1))


def test_the_count_expires_on_its_own(rate_limits):
    spend_transcription(rate_limits, now=NOON)

    record = rate_limits.find_one({})
    assert record["expires_at"].replace(tzinfo=UTC) > NOON + timedelta(days=1)
