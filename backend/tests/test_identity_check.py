import pytest

import config
from identity_check import check_identity

VOICEPRINT = [0.2, -0.5, 0.1, 0.8]


def test_same_voice_passes():
    result = check_identity(VOICEPRINT, VOICEPRINT)

    assert result.score == pytest.approx(1.0)
    assert result.passed


def test_loudness_does_not_matter():
    # Cosine similarity compares direction, not size, so a louder or
    # quieter take of the same voice scores the same.
    result = check_identity(VOICEPRINT, [x * 3 for x in VOICEPRINT])

    assert result.score == pytest.approx(1.0)


def test_different_speaker_fails():
    other = [0.5, 0.2, 0.0, 0.0]  # at right angles to VOICEPRINT: score 0
    result = check_identity(VOICEPRINT, other)

    assert result.score == pytest.approx(0.0)
    assert not result.passed


def test_threshold_comes_from_settings(monkeypatch):
    close = [0.25, -0.45, 0.1, 0.8]
    assert check_identity(VOICEPRINT, close).passed

    monkeypatch.setattr(config, "IDENTITY_THRESHOLD", 0.999)
    assert not check_identity(VOICEPRINT, close).passed


def test_score_on_the_threshold_passes(monkeypatch):
    monkeypatch.setattr(config, "IDENTITY_THRESHOLD", 1.0)

    assert check_identity([1.0, 0.0], [1.0, 0.0]).passed


def test_silent_embedding_fails():
    assert not check_identity(VOICEPRINT, [0.0, 0.0, 0.0, 0.0]).passed


def test_embeddings_of_different_sizes_are_an_error():
    # A voiceprint from another model can't be compared.
    with pytest.raises(ValueError):
        check_identity(VOICEPRINT, [0.1, 0.2])
