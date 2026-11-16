from dataclasses import dataclass

import config


@dataclass(frozen=True)
class LivenessResult:
    # The model service's liveness score: higher means more likely a live
    # person rather than a replay or AI voice. Not a probability. None if
    # the recording had no sound to judge.
    score: float | None
    passed: bool


def check_liveness(score: float | None) -> LivenessResult:
    """Is this recording a live person? Nothing to judge counts as a fail:
    a check that can't run must not let an attempt through."""
    return LivenessResult(score=score, passed=score is not None and score >= config.LIVENESS_THRESHOLD)
