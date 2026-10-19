from content_check import ContentResult
from decision import decide
from identity_check import IdentityResult

RIGHT_WORDS = ContentResult(matched=6, total=6, passed=True)
WRONG_WORDS = ContentResult(matched=2, total=6, passed=False)
SAME_VOICE = IdentityResult(score=0.8, passed=True)
OTHER_VOICE = IdentityResult(score=0.05, passed=False)


def test_right_words_and_voice_are_not_yet_approved():
    # Without the liveness check, a recording or clone of the user could
    # pass both checks.
    result = decide(RIGHT_WORDS, SAME_VOICE)

    assert result.decision == "incomplete"
    assert result.reason == "The passage and the voice matched, but the liveness check isn't built yet."


def test_right_words_without_a_voiceprint_are_not_approved():
    result = decide(RIGHT_WORDS, None)

    assert result.decision == "incomplete"
    assert "no voiceprint" in result.reason


def test_a_different_voice_is_rejected():
    result = decide(RIGHT_WORDS, OTHER_VOICE)

    assert result.decision == "rejected"
    assert result.reason == "The voice didn't match this account."


def test_wrong_words_are_rejected_with_a_reason():
    for identity in (SAME_VOICE, OTHER_VOICE, None):
        result = decide(WRONG_WORDS, identity)

        assert result.decision == "rejected"
        assert result.reason == "The words didn't match the passage."
