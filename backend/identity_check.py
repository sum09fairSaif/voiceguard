import math
from dataclasses import dataclass

import config


class IdentityUnavailable(Exception):
    """The identity check isn't set up or can't be reached right now."""


@dataclass(frozen=True)
class IdentityResult:
    # Cosine similarity between the attempt and the voiceprint: about 1.0
    # for the same voice, around 0 for unrelated voices.
    score: float
    passed: bool


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Embeddings differ in size ({len(a)} vs {len(b)}).")
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if not norms:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / norms


def check_identity(voiceprint: list[float], attempt: list[float]) -> IdentityResult:
    """Compare the voice in this attempt to the user's enrolled voiceprint."""
    score = _cosine(voiceprint, attempt)
    return IdentityResult(score=score, passed=score >= config.IDENTITY_THRESHOLD)
