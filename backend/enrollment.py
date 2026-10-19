from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from pymongo.collection import Collection

import config
from embedding import Embedding
from identity_check import cosine_similarity
from voiceprints import build_voiceprint, decrypt_embedding, encrypt_embedding

# Why a sample was turned away. The router turns each into a message.
TOO_SHORT = "too_short"
TOO_LOUD = "too_loud"
INCONSISTENT = "inconsistent"


def _current(user_id: str, now: datetime) -> dict:
    # MongoDB's clean-up runs only about once a minute, so expiry is checked
    # here too. Samples from another model can't be averaged with new ones.
    return {"_id": user_id, "model": config.EMBEDDING_MODEL, "expires_at": {"$gt": now}}


def accepted_samples(enrollments: Collection, user_id: str) -> list[list[float]]:
    """The user's accepted samples so far, decrypted."""
    record = enrollments.find_one(_current(user_id, datetime.now(timezone.utc)))
    return [decrypt_embedding(sample) for sample in record["samples"]] if record else []


def count_samples(enrollments: Collection, user_id: str) -> int:
    """How many samples the user has given so far. Needs no key."""
    record = enrollments.find_one(_current(user_id, datetime.now(timezone.utc)), {"samples": 1})
    return len(record["samples"]) if record else 0


def sample_problem(sample: Embedding, earlier: list[list[float]]) -> tuple[str | None, float | None]:
    """Return (problem, similarity). The problem is None if the sample is
    good enough to keep; the similarity is to the earlier samples, or None
    if it wasn't measured."""
    if sample.speech_seconds < config.ENROLL_MIN_SPEECH_SECONDS:
        return TOO_SHORT, None
    if sample.clipped_share > config.ENROLL_MAX_CLIPPED_SHARE:
        return TOO_LOUD, None
    if not earlier:
        return None, None
    similarity = cosine_similarity(build_voiceprint(earlier), sample.vector)
    if similarity < config.ENROLL_CONSISTENCY_THRESHOLD:
        return INCONSISTENT, similarity
    return None, similarity


def add_sample(enrollments: Collection, user_id: str, embedding: list[float]) -> int:
    """Store one accepted sample, encrypted, and return how many the user
    has now. Each sample gives the user another ENROLL_SESSION_TTL_SECONDS."""
    now = datetime.now(timezone.utc)
    # Clear out an expired or other-model enrollment first, so its samples
    # aren't mixed in with this one.
    enrollments.delete_many({"_id": user_id, "$nor": [_current(user_id, now)]})
    record = enrollments.find_one_and_update(
        {"_id": user_id},
        {
            "$push": {"samples": encrypt_embedding(embedding)},
            "$set": {"expires_at": now + timedelta(seconds=config.ENROLL_SESSION_TTL_SECONDS)},
            "$setOnInsert": {"model": config.EMBEDDING_MODEL, "started_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return len(record["samples"])


def take_samples(enrollments: Collection, user_id: str) -> list[list[float]] | None:
    """Remove the user's samples and return them, decrypted. Done in one
    step, so if two requests finish at once only one builds the voiceprint."""
    record = enrollments.find_one_and_delete(_current(user_id, datetime.now(timezone.utc)))
    return [decrypt_embedding(sample) for sample in record["samples"]] if record else None


def discard_samples(enrollments: Collection, user_id: str) -> None:
    enrollments.delete_one({"_id": user_id})
