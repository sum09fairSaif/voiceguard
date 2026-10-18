import re
from dataclasses import dataclass

import config


@dataclass(frozen=True)
class ContentResult:
    matched: int
    total: int
    passed: bool
    # Words heard that aren't part of the passage.
    extra: int = 0

    @property
    def score(self) -> float:
        if not self.total:
            return 0.0
        # Extra words beyond the allowance count against the score.
        padding = max(0, self.extra - config.CONTENT_MAX_EXTRA_WORDS)
        return self.matched / (self.total + padding)


def _words(text: str) -> list[str]:
    # Speech-to-text adds capitals and punctuation ("Tulip, river.") that
    # the passage doesn't have, so compare bare lowercase words only.
    return re.findall(r"[a-z]+", text.lower())


def _in_order_matches(expected: list[str], heard: list[str]) -> int:
    """Count how many expected words were heard in the right order
    (longest common subsequence). Saying the words shuffled doesn't add
    up to a match; reading out a long list of words is caught by the
    extra-words limit in check_content."""
    previous = [0] * (len(heard) + 1)
    for word in expected:
        current = [0] * (len(heard) + 1)
        for j, heard_word in enumerate(heard, start=1):
            if word == heard_word:
                current[j] = previous[j - 1] + 1
            else:
                current[j] = max(previous[j], current[j - 1])
        previous = current
    return previous[-1]


def check_content(passage: str, transcript: str) -> ContentResult:
    expected = _words(passage)
    heard = _words(transcript)
    matched = _in_order_matches(expected, heard)
    extra = len(heard) - matched
    passed = (
        bool(expected)
        and matched >= len(expected) - config.CONTENT_MAX_MISSED_WORDS
        and extra <= config.CONTENT_MAX_EXTRA_WORDS
    )
    return ContentResult(matched=matched, total=len(expected), passed=passed, extra=extra)
