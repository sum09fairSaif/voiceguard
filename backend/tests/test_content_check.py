import pytest

from content_check import check_content

PASSAGE = "quilt tiger ocean pebble winter planet"


def test_reading_the_passage_passes():
    result = check_content(PASSAGE, "quilt tiger ocean pebble winter planet")

    assert result.passed
    assert result.matched == 6
    assert result.score == 1.0


def test_capitals_and_punctuation_are_ignored():
    result = check_content(PASSAGE, "Quilt, tiger. Ocean! Pebble... winter -- planet?")

    assert result.passed
    assert result.matched == 6


def test_one_misheard_word_still_passes():
    result = check_content(PASSAGE, "quilt tiger ocean people winter planet")

    assert result.passed
    assert result.matched == 5


def test_two_misheard_words_fail():
    result = check_content(PASSAGE, "quilt tiger motion people winter planet")

    assert not result.passed
    assert result.matched == 4


def test_filler_words_around_the_passage_are_fine():
    result = check_content(PASSAGE, "Um, okay. Quilt tiger ocean pebble winter planet. Done.")

    assert result.passed


def test_words_in_the_wrong_order_fail():
    # An old recording cut up and rearranged shouldn't line up.
    result = check_content(PASSAGE, "planet winter pebble ocean tiger quilt")

    assert not result.passed
    assert result.matched == 1


@pytest.mark.parametrize("transcript", ["", "   ", "...", "hello there"])
def test_silence_or_unrelated_speech_fails(transcript):
    result = check_content(PASSAGE, transcript)

    assert not result.passed
    assert result.matched == 0
    assert result.score == 0.0


def test_empty_passage_never_passes():
    result = check_content("", "anything at all")

    assert not result.passed
    assert result.score == 0.0
