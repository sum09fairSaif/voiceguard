from content_check import ContentResult
from decision import decide
from identity_check import IdentityResult
from liveness_check import LivenessResult

RIGHT_WORDS = ContentResult(matched=6, total=6, passed=True)
WRONG_WORDS = ContentResult(matched=2, total=6, passed=False)
SAME_VOICE = IdentityResult(score=0.8, passed=True)
OTHER_VOICE = IdentityResult(score=0.05, passed=False)
LIVE = LivenessResult(score=2.0, passed=True)
SPOOFED = LivenessResult(score=-3.0, passed=False)
NOTHING_TO_JUDGE = LivenessResult(score=None, passed=False)


def test_right_words_voice_and_live_person_are_approved():
    result = decide(RIGHT_WORDS, SAME_VOICE, LIVE)

    assert result.decision == "approved"


def test_failed_liveness_rejects_even_the_right_voice():
    # The veto: a replay or AI clone of the user can pass the voice match.
    result = decide(RIGHT_WORDS, SAME_VOICE, SPOOFED)

    assert result.decision == "rejected"
    assert result.reason == "The recording didn't sound like a live voice."


def test_liveness_that_couldnt_judge_rejects():
    assert decide(RIGHT_WORDS, SAME_VOICE, NOTHING_TO_JUDGE).decision == "rejected"


def test_a_different_voice_is_rejected():
    result = decide(RIGHT_WORDS, OTHER_VOICE, LIVE)

    assert result.decision == "rejected"
    assert result.reason == "The voice didn't match this account."


def test_right_words_without_a_voiceprint_are_not_approved():
    result = decide(RIGHT_WORDS, None, None)

    assert result.decision == "incomplete"
    assert "no voiceprint" in result.reason


def test_missing_liveness_result_is_never_approved():
    assert decide(RIGHT_WORDS, SAME_VOICE, None).decision == "incomplete"


def test_wrong_words_are_rejected_with_a_reason():
    for identity in (SAME_VOICE, OTHER_VOICE, None):
        for liveness in (LIVE, SPOOFED, None):
            result = decide(WRONG_WORDS, identity, liveness)

            assert result.decision == "rejected"
            assert result.reason == "The words didn't match the passage."


# --- The deciding check, as recorded in the security log (#167) ----------------


def test_each_result_names_the_check_that_decided_it():
    assert decide(RIGHT_WORDS, SAME_VOICE, LIVE).check is None
    assert decide(WRONG_WORDS, OTHER_VOICE, SPOOFED).check == "words"
    assert decide(RIGHT_WORDS, SAME_VOICE, SPOOFED).check == "liveness"
    assert decide(RIGHT_WORDS, OTHER_VOICE, LIVE).check == "voice"
    assert decide(RIGHT_WORDS, None, None).check == "not_enrolled"
    assert decide(RIGHT_WORDS, SAME_VOICE, None).check == "liveness_not_checked"


def test_when_voice_and_liveness_both_fail_liveness_decides():
    # The deepfake case: the reason shown and the check recorded agree.
    result = decide(RIGHT_WORDS, OTHER_VOICE, SPOOFED)

    assert result.reason == "The recording didn't sound like a live voice."
    assert result.check == "liveness"
