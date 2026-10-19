from dataclasses import dataclass

from content_check import ContentResult
from identity_check import IdentityResult


@dataclass(frozen=True)
class Decision:
    decision: str  # "approved", "rejected" or "incomplete"
    reason: str


def decide(content: ContentResult, identity: IdentityResult | None) -> Decision:
    # Every check that ran must pass. `identity` is None when the user has
    # no voiceprint yet. Liveness (#17) isn't built yet. When it is, a
    # failed liveness check must reject on its own, whatever the other
    # scores say.
    if not content.passed:
        return Decision("rejected", "The words didn't match the passage.")
    if identity is not None and not identity.passed:
        return Decision("rejected", "The voice didn't match this account.")
    # Until liveness runs, a recording or AI clone of the user could pass
    # both checks, so nothing can be approved yet.
    if identity is None:
        return Decision(
            "incomplete",
            "The passage was read correctly, but this account has no voiceprint yet "
            "and the liveness check isn't built yet.",
        )
    return Decision(
        "incomplete",
        "The passage and the voice matched, but the liveness check isn't built yet.",
    )
