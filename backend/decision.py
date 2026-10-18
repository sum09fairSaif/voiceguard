from dataclasses import dataclass

from content_check import ContentResult


@dataclass(frozen=True)
class Decision:
    decision: str  # "approved" or "rejected"
    reason: str


def decide(content: ContentResult) -> Decision:
    # Every check that ran must pass. Identity (#16) and liveness (#17) aren't
    # built yet. When they are, a failed liveness check must reject on its
    # own, whatever the other scores say.
    if not content.passed:
        return Decision("rejected", "The words didn't match the passage.")
    return Decision("approved", "The passage was read correctly.")
