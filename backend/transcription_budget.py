"""A daily budget for speech-to-text, which is paid for from prepaid credit.

A slot is reserved in one database step before a passage is used up, so
requests arriving together can't all slip past the budget, and a refused
check never costs the user their passage. If the request then fails before
the paid call (e.g. the passage was already used), the slot is given back.
"""

from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
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


def reserve_transcription(rate_limits: Collection, now: datetime | None = None) -> None:
    """Take one slot of today's budget, or raise BudgetUsedUp if none is left."""
    now = now or datetime.now(UTC)
    key, tomorrow = _today(now)
    record = rate_limits.find_one_and_update(
        {"_id": key},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": tomorrow + timedelta(days=1)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if record["count"] > config.TRANSCRIPTION_DAILY_BUDGET:
        # Over by this one: give it back, so the count stays at the budget.
        rate_limits.update_one({"_id": key}, {"$inc": {"count": -1}})
        raise BudgetUsedUp(retry_after=max(1, int((tomorrow - now).total_seconds())))


def release_transcription(rate_limits: Collection, now: datetime | None = None) -> None:
    """Give back a reserved slot when the request fails before the paid call."""
    key, _ = _today(now or datetime.now(UTC))
    rate_limits.update_one({"_id": key, "count": {"$gt": 0}}, {"$inc": {"count": -1}})
