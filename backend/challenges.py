from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.collection import Collection

import config
from passages import generate_passage


def create_challenge(challenges: Collection, user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    challenge = {
        "_id": ObjectId(),
        "user_id": user_id,
        "passage": generate_passage(),
        "created_at": now,
        "expires_at": now + timedelta(seconds=config.CHALLENGE_TTL_SECONDS),
        "used": False,
    }
    challenges.insert_one(challenge)
    return challenge


def use_challenge(challenges: Collection, attempt_id: str, user_id: str) -> str | None:
    """Return the expected passage and mark the attempt used, or None if the
    attempt doesn't exist, belongs to someone else, has expired or was used."""
    if not ObjectId.is_valid(attempt_id):
        return None
    now = datetime.now(timezone.utc)
    # Find and mark used in one step, so two requests can't both use it.
    challenge = challenges.find_one_and_update(
        {
            "_id": ObjectId(attempt_id),
            "user_id": user_id,
            "used": False,
            "expires_at": {"$gt": now},
        },
        {"$set": {"used": True, "used_at": now}},
    )
    return challenge["passage"] if challenge else None
