from dataclasses import dataclass

from content_check import ContentResult


@dataclass(frozen=True)
class Decision:
    decision: str  # "approved", "rejected" or "incomplete"
    reason: str


def decide(content: ContentResult) -> Decision:
    # Every check that ran must pass. Identity (#16) and liveness (#17) aren't
    # built yet. When they are, a failed liveness check must reject on its
    # own, whatever the other scores say.
    if not content.passed:
        return Decision("rejected", "The words didn't match the passage.")
    # Reading the words proves the recording is fresh, not who is speaking.
    # Until identity and liveness run, a correct reading can't approve access.
    return Decision(
        "incomplete",
        "The passage was read correctly, but the identity and liveness checks aren't built yet.",
    )
