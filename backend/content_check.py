import re
from dataclasses import dataclass

import config
from passages import UNCHECKED_WORDS


@dataclass(frozen=True)
class ContentResult:
    # Key words only: "the", "near" and the like aren't counted on either side.
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


def _all_words(text: str) -> list[str]:
    # Capitals and punctuation can differ between the passage and what
    # speech-to-text writes, so compare bare lowercase words only.
    return re.findall(r"[a-z]+", text.lower())


def _words(text: str) -> list[str]:
    # Capitals and punctuation can differ between the passage and what
    # speech-to-text writes, so compare bare lowercase words only. Small
    # words like "the" are left out: speech-to-text drops or swaps them
    # easily, and they say nothing about whether the passage was read.
    return [word for word in _all_words(text) if word not in UNCHECKED_WORDS]


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


def check_every_word(passage: str, transcript: str) -> ContentResult:
    """The stricter check for enrollment samples: every word of the
    passage, small words included, heard in the passage's order. A voice
    sample is only as good as the speech in it, so a part-read sentence
    isn't kept. A few extra words (a stumble, a word said twice) are
    allowed, up to ENROLL_MAX_EXTRA_WORDS."""
    expected = _all_words(passage)
    heard = _all_words(transcript)
    matched = _in_order_matches(expected, heard)
    extra = len(heard) - matched
    passed = bool(expected) and matched == len(expected) and extra <= config.ENROLL_MAX_EXTRA_WORDS
    return ContentResult(matched=matched, total=len(expected), passed=passed, extra=extra)
