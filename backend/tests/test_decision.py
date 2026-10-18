from content_check import ContentResult
from decision import decide


def test_matching_words_are_approved():
    result = decide(ContentResult(matched=6, total=6, passed=True))

    assert result.decision == "approved"


def test_wrong_words_are_rejected_with_a_reason():
    result = decide(ContentResult(matched=2, total=6, passed=False))

    assert result.decision == "rejected"
    assert result.reason == "The words didn't match the passage."
