import math
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.collection import Collection


class RateLimited(Exception):
    """The user has made too many requests of this kind for now."""

    def __init__(self, retry_after: int):
        super().__init__(f"Rate limited, retry in {retry_after}s.")
        self.retry_after = retry_after


def count_request(
    rate_limits: Collection,
    action: str,
    user_id: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> None:
    """Count one request and raise RateLimited if the user is over `limit`
    for the current window. Windows are fixed blocks of time (e.g. each
    clock hour), so a user can make up to 2 x limit requests either side
    of a window edge; that's fine for capping cost."""
    now = now or datetime.now(timezone.utc)
    window_start = math.floor(now.timestamp() / window_seconds) * window_seconds
    window_end = datetime.fromtimestamp(window_start + window_seconds, timezone.utc)
    # Add one and read the new count in a single step, so requests arriving
    # at the same moment can't all slip under the limit.
    counter = rate_limits.find_one_and_update(
        {"_id": f"{action}:{user_id}:{window_start}"},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": window_end}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if counter["count"] > limit:
        raise RateLimited(retry_after=max(1, math.ceil((window_end - now).total_seconds())))
