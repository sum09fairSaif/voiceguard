import re
from dataclasses import dataclass

# Speech-to-text sometimes mishears one word, so allow a single miss.
MAX_MISSED_WORDS = 1


@dataclass(frozen=True)
class ContentResult:
    matched: int
    total: int
    passed: bool

    @property
    def score(self) -> float:
        return self.matched / self.total if self.total else 0.0


def _words(text: str) -> list[str]:
    # Speech-to-text adds capitals and punctuation ("Tulip, river.") that
    # the passage doesn't have, so compare bare lowercase words only.
    return re.findall(r"[a-z]+", text.lower())


def _in_order_matches(expected: list[str], heard: list[str]) -> int:
    """Count how many expected words were heard in the right order
    (longest common subsequence). Saying the words shuffled, or reading
    out a long list of words, doesn't add up to a match."""
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
    matched = _in_order_matches(expected, _words(transcript))
    passed = bool(expected) and matched >= len(expected) - MAX_MISSED_WORDS
    return ContentResult(matched=matched, total=len(expected), passed=passed)
