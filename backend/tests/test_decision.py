from content_check import ContentResult
from decision import decide


def test_matching_words_alone_are_not_approved():
    # Reading the right words doesn't prove who is speaking.
    result = decide(ContentResult(matched=6, total=6, passed=True))

    assert result.decision == "incomplete"
    assert "identity and liveness" in result.reason


def test_wrong_words_are_rejected_with_a_reason():
    result = decide(ContentResult(matched=2, total=6, passed=False))

    assert result.decision == "rejected"
    assert result.reason == "The words didn't match the passage."
