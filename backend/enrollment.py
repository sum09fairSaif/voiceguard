from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.collection import Collection

import config
from content_check import ContentResult, check_every_word
from embedding import Embedding
from identity_check import cosine_similarity
from liveness_check import check_liveness
from passages import generate_passage
from voiceprints import decrypt_embedding, encrypt_embedding

# Why a sample was turned away. The router turns each into a message.
TOO_SHORT = "too_short"
TOO_LOUD = "too_loud"
INCONSISTENT = "inconsistent"
NOT_LIVE = "not_live"
WRONG_WORDS = "wrong_words"


def _current(user_id: str, now: datetime) -> dict:
    # MongoDB's clean-up runs only about once a minute, so expiry is checked
    # here too. Samples from another model can't be averaged with new ones.
    return {"_id": user_id, "model": config.EMBEDDING_MODEL, "expires_at": {"$gt": now}}


def accepted_samples(enrollments: Collection, user_id: str) -> list[list[float]]:
    """The user's accepted samples so far, decrypted."""
    record = enrollments.find_one(_current(user_id, datetime.now(UTC)))
    return [decrypt_embedding(sample) for sample in record["samples"]] if record else []


def count_samples(enrollments: Collection, user_id: str) -> int:
    """How many samples the user has given so far. Needs no key."""
    record = enrollments.find_one(_current(user_id, datetime.now(UTC)), {"samples": 1})
    return len(record["samples"]) if record else 0


def sample_problem(sample: Embedding, earlier: list[list[float]]) -> tuple[str | None, float | None]:
    """Return (problem, similarity). The problem is None if the sample is
    good enough to keep; the similarity is to the earlier samples, or None
    if it wasn't measured."""
    if sample.speech_seconds < config.ENROLL_MIN_SPEECH_SECONDS:
        return TOO_SHORT, None
    if sample.clipped_share > config.ENROLL_MAX_CLIPPED_SHARE:
        return TOO_LOUD, None
    # A voiceprint made from a recording or AI clone of someone would let
    # whoever made it pass as them from then on, so every sample has to
    # pass the same liveness check as a voice check.
    if not check_liveness(sample.liveness).passed:
        return NOT_LIVE, None
    if not earlier:
        return None, None
    # Compared with each earlier sample, not just their average: an
    # average can sit close to a new sample even when one of the samples
    # behind it is far off. The lowest similarity is the one that counts.
    similarity = min(cosine_similarity(take, sample.vector) for take in earlier)
    if similarity < config.ENROLL_CONSISTENCY_THRESHOLD:
        return INCONSISTENT, similarity
    return None, similarity


def issue_prompt(prompts: Collection, user_id: str) -> str:
    """A new sentence for the user's next sample, remembered so the sample
    can be checked against it. Only the newest ENROLL_PROMPTS_KEPT are kept."""
    now = datetime.now(UTC)
    passage = generate_passage()
    prompts.insert_one(
        {
            "user_id": user_id,
            "passage": passage,
            "created_at": now,
            "expires_at": now + timedelta(seconds=config.ENROLL_SESSION_TTL_SECONDS),
        }
    )
    older = prompts.find({"user_id": user_id}, {"_id": 1}).sort("created_at", -1).skip(config.ENROLL_PROMPTS_KEPT)
    prompts.delete_many({"_id": {"$in": [doc["_id"] for doc in older]}})
    return passage


def use_prompt(prompts: Collection, user_id: str, transcript: str) -> ContentResult:
    """Check what was heard against the user's current sentences. If it
    holds every word of one of them, in order, that sentence is used up
    (so one recording can't be sent again as another sample) and the
    result passes. Otherwise returns the closest result, which fails.
    Any of the newest few counts: the screen may have asked for a sentence
    more than once before showing one."""
    now = datetime.now(UTC)
    misses = []
    for prompt in prompts.find({"user_id": user_id, "expires_at": {"$gt": now}}).sort("created_at", -1):
        result = check_every_word(prompt["passage"], transcript)
        if not result.passed:
            misses.append(result)
        # Deleted in one step, so two requests can't both use one sentence.
        elif prompts.delete_one({"_id": prompt["_id"]}).deleted_count:
            return result
    if not misses:
        # No current sentence, or the one it matched was used a moment ago.
        return ContentResult(matched=0, total=0, passed=False)
    return max(misses, key=lambda result: result.matched / result.total)


def discard_prompts(prompts: Collection, user_id: str) -> None:
    prompts.delete_many({"user_id": user_id})


def add_sample(enrollments: Collection, user_id: str, embedding: list[float]) -> int:
    """Store one accepted sample, encrypted, and return how many the user
    has now. Each sample gives the user another ENROLL_SESSION_TTL_SECONDS."""
    now = datetime.now(UTC)
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
    record = enrollments.find_one_and_delete(_current(user_id, datetime.now(UTC)))
    return [decrypt_embedding(sample) for sample in record["samples"]] if record else None


def discard_samples(enrollments: Collection, user_id: str) -> None:
    enrollments.delete_one({"_id": user_id})
