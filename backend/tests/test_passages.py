import re

import pytest

from content_check import check_content
from passages import (
    ACTIONS,
    CREATURE_WORDS,
    CREATURES,
    KEY_WORDS_PER_PASSAGE,
    NEAR_WORDS,
    PLACES,
    THING_WORDS,
    THINGS,
    UNCHECKED_WORDS,
    generate_passage,
)

KEY_LISTS = [CREATURE_WORDS, CREATURES, ACTIONS, THING_WORDS, THINGS, PLACES]
SENTENCE = re.compile(r"The (\w+) (\w+) (\w+) the (\w+) (\w+) (\w+) the (\w+)\.")


@pytest.mark.parametrize("words", [*KEY_LISTS, NEAR_WORDS])
def test_word_lists_are_clean(words):
    assert len(set(words)) == len(words)
    assert all(word.isalpha() and word.islower() for word in words)


def test_no_word_is_in_two_lists():
    # Otherwise a word could stand for two different slots.
    everything = [word for words in [*KEY_LISTS, NEAR_WORDS] for word in words]
    assert len(set(everything)) == len(everything)


def test_key_words_are_never_left_unchecked():
    assert not UNCHECKED_WORDS & {word for words in KEY_LISTS for word in words}


def test_passage_is_a_sentence_with_one_word_from_each_list():
    passage = generate_passage()

    match = SENTENCE.fullmatch(passage)
    assert match, passage
    creature_word, creature, action, thing_word, thing, near, place = match.groups()
    assert creature_word in CREATURE_WORDS
    assert creature in CREATURES
    assert action in ACTIONS
    assert thing_word in THING_WORDS
    assert thing in THINGS
    assert near in NEAR_WORDS
    assert place in PLACES


def test_there_are_billions_of_possible_passages():
    combinations = len(NEAR_WORDS)
    for words in KEY_LISTS:
        combinations *= len(words)
    assert combinations > 1_000_000_000


def test_passages_are_fresh_each_time():
    passages = {generate_passage() for _ in range(1000)}

    assert len(passages) == 1000


def test_reading_a_passage_checks_exactly_its_key_words():
    passage = generate_passage()

    result = check_content(passage, passage)

    assert result.passed
    assert result.matched == result.total == KEY_WORDS_PER_PASSAGE
