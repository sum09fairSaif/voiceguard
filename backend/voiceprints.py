import json
import math
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from pymongo.collection import Collection

import config
from identity_check import IdentityUnavailable


def _cipher() -> Fernet:
    if not config.VOICEPRINT_KEY:
        raise IdentityUnavailable("VOICEPRINT_KEY is not set.")
    return Fernet(config.VOICEPRINT_KEY)


def build_voiceprint(embeddings: list[list[float]]) -> list[float]:
    """Combine the embeddings of several recordings into one voiceprint:
    the average of each scaled to length 1, so no take counts more for
    being louder."""
    if not embeddings:
        raise ValueError("At least one recording is needed.")
    scaled = []
    for embedding in embeddings:
        length = math.sqrt(sum(x * x for x in embedding))
        if not length:
            raise ValueError("A recording had no voice in it.")
        scaled.append([x / length for x in embedding])
    return [sum(values) / len(scaled) for values in zip(*scaled, strict=True)]


def save_voiceprint(voiceprints: Collection, user_id: str, embedding: list[float]) -> None:
    """Store a user's voiceprint, encrypted, replacing any earlier one.
    Enrollment will call this; for now only tests and the dev script do."""
    encrypted = _cipher().encrypt(json.dumps(embedding).encode())
    voiceprints.replace_one(
        {"_id": user_id},
        {
            "_id": user_id,
            "voiceprint": encrypted,
            # A voiceprint only compares with embeddings from the same model.
            "model": config.EMBEDDING_MODEL,
            "created_at": datetime.now(timezone.utc),
        },
        upsert=True,
    )


def load_voiceprint(voiceprints: Collection, user_id: str) -> list[float] | None:
    """Return the user's decrypted voiceprint, or None if they haven't
    enrolled (or enrolled with a different model, so must enroll again)."""
    record = voiceprints.find_one({"_id": user_id})
    if record is None or record.get("model") != config.EMBEDDING_MODEL:
        return None
    try:
        return json.loads(_cipher().decrypt(record["voiceprint"]))
    except InvalidToken as exc:
        # Wrong or rotated key: a server problem, not the user's fault.
        raise IdentityUnavailable("The voiceprint couldn't be decrypted.") from exc
