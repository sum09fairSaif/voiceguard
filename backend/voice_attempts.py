"""Failed voice checks, and the lockout after too many.

Only a rejected check counts: the words, the voice or liveness failed.
An approved check clears the count. Not being enrolled yet, or the check
not running at all (an outage, audio that couldn't be read), says nothing
about who is speaking, so it doesn't count.

After VOICE_MAX_FAILURES rejections within VOICE_FAILURE_WINDOW_SECONDS,
voice checks are locked for VOICE_LOCKOUT_SECONDS: no new passages, no
checks. That's the point where the user is meant to fall back to an email
code (#20); until that exists, they wait out the lockout.
"""

from pymongo.collection import Collection

import config
from login_lockout import clear_failures, failure_count, record_failure, seconds_locked


class VoiceLockedOut(Exception):
    """Too many failed voice checks: none allowed for retry_after seconds."""

    def __init__(self, retry_after: int):
        super().__init__(f"Voice checks locked, retry in {retry_after}s.")
        self.retry_after = retry_after


def ensure_not_locked(voice_failures: Collection, user_id: str) -> None:
    """Raise VoiceLockedOut if this user's voice checks are locked."""
    locked = seconds_locked(voice_failures, user_id)
    if locked:
        raise VoiceLockedOut(locked)


def record_outcome(voice_failures: Collection, user_id: str, decision: str) -> int:
    """Count this check's decision and return how many failed checks the
    user has left before the lockout (0 means it has just started)."""
    if decision == "approved":
        clear_failures(voice_failures, user_id)
        return config.VOICE_MAX_FAILURES
    if decision == "rejected":
        locked = record_failure(
            voice_failures,
            user_id,
            config.VOICE_MAX_FAILURES,
            config.VOICE_FAILURE_WINDOW_SECONDS,
            config.VOICE_LOCKOUT_SECONDS,
        )
        if locked:
            return 0
    return max(0, config.VOICE_MAX_FAILURES - failure_count(voice_failures, user_id))
