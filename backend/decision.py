from dataclasses import dataclass

from content_check import ContentResult
from identity_check import IdentityResult
from liveness_check import LivenessResult


@dataclass(frozen=True)
class Decision:
    decision: str  # "approved", "rejected" or "incomplete"
    reason: str


def decide(content: ContentResult, identity: IdentityResult | None, liveness: LivenessResult | None) -> Decision:
    """Approved only when all three checks ran and passed. `identity` and
    `liveness` are None when the user has no voiceprint yet: both run in
    the same model-service call, which is skipped without one."""
    if not content.passed:
        return Decision("rejected", "The words didn't match the passage.")
    # The veto: a recording or AI clone of the user's own voice can pass the
    # identity check, so a failed liveness check rejects whatever the voice
    # match says.
    if liveness is not None and not liveness.passed:
        return Decision("rejected", "The recording didn't sound like a live voice.")
    if identity is not None and not identity.passed:
        return Decision("rejected", "The voice didn't match this account.")
    if identity is None:
        return Decision(
            "incomplete",
            "The passage was read correctly, but this account has no voiceprint yet.",
        )
    if liveness is None:
        # Not reached from /api/verify, which checks both together; kept so
        # a missing liveness result can never end in an approval.
        return Decision("incomplete", "The passage and the voice matched, but liveness wasn't checked.")
    return Decision("approved", "The passage, the voice and liveness all checked out.")
