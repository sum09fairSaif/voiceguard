from passages import WORDS, WORDS_PER_PASSAGE, generate_passage


def test_word_list_is_clean():
    assert len(WORDS) >= 100
    assert len(set(WORDS)) == len(WORDS)
    assert all(word.isalpha() and word.islower() for word in WORDS)


def test_passage_has_six_different_words_from_the_list():
    words = generate_passage().split(" ")

    assert len(words) == WORDS_PER_PASSAGE
    assert len(set(words)) == WORDS_PER_PASSAGE
    assert all(word in WORDS for word in words)


def test_passages_are_fresh_each_time():
    passages = {generate_passage() for _ in range(1000)}

    assert len(passages) == 1000
