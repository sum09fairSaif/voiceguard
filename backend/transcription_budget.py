"""A daily budget for speech-to-text, which is paid for from prepaid credit.

Checked before a passage is used up, so a refused check never costs the user
their passage, and counted only once a real paid call is about to be made, so
requests that fail earlier (bad passage, bad audio) don't use the budget.
Requests arriving at the same moment can overshoot it by a few; that's fine
for capping spend.
"""

from datetime import UTC, datetime, timedelta

from pymongo.collection import Collection

import config


class BudgetUsedUp(Exception):
    """Today's speech-to-text budget is spent: try again after midnight UTC."""

    def __init__(self, retry_after: int):
        super().__init__(f"Transcription budget used up, retry in {retry_after}s.")
        self.retry_after = retry_after


def _today(now: datetime) -> tuple[str, datetime]:
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"transcription-budget:{start.date().isoformat()}", start + timedelta(days=1)


def ensure_budget_left(rate_limits: Collection, now: datetime | None = None) -> None:
    """Raise BudgetUsedUp if today's budget is already spent."""
    now = now or datetime.now(UTC)
    key, tomorrow = _today(now)
    record = rate_limits.find_one({"_id": key})
    if record and record["count"] >= config.TRANSCRIPTION_DAILY_BUDGET:
        raise BudgetUsedUp(retry_after=max(1, int((tomorrow - now).total_seconds())))


def spend_transcription(rate_limits: Collection, now: datetime | None = None) -> None:
    """Count one paid speech-to-text call against today's budget."""
    now = now or datetime.now(UTC)
    key, tomorrow = _today(now)
    rate_limits.update_one(
        {"_id": key},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": tomorrow + timedelta(days=1)}},
        upsert=True,
    )
