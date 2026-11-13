import numpy as np
import pytest

from liveness import CROP_SAMPLES, TARGET_DBFS, TARGET_RATE, prepare


def tone(seconds, level=0.3, offset=0.0):
    t = np.arange(int(seconds * TARGET_RATE)) / TARGET_RATE
    return (level * np.sin(2 * np.pi * 200 * t) + offset).astype(np.float32)


def test_input_is_always_the_models_length():
    for seconds in [0.3, 2.0, 4.0, 9.0]:
        clip = prepare(tone(seconds))
        assert clip.shape == (CROP_SAMPLES,)
        assert clip.dtype == np.float32


def test_silence_at_the_ends_is_trimmed():
    # Two seconds of tone with a second of silence before it: the input
    # starts with the tone, as training clips did. At most one 25 ms frame
    # of the silence stays, the frame where the tone begins.
    samples = np.concatenate([np.zeros(TARGET_RATE, np.float32), tone(2.0)])

    clip = prepare(samples)

    assert np.abs(clip[:400]).max() > 0.01


def test_speech_is_brought_to_the_training_loudness():
    for level in [0.01, 0.3, 0.9]:
        clip = prepare(tone(5.0, level=level))
        dbfs = 20 * np.log10(np.sqrt(np.mean(clip**2)))
        assert abs(dbfs - TARGET_DBFS) < 0.5


def test_offset_from_zero_is_removed():
    clip = prepare(tone(5.0, offset=0.2))

    assert abs(clip.mean()) < 1e-3


def test_short_clips_are_repeated_to_fill_the_input():
    clip = prepare(tone(1.0))

    assert np.abs(clip[-1000:]).max() > 0.01


def test_silence_has_nothing_to_score():
    assert prepare(np.zeros(TARGET_RATE, np.float32)) is None


def test_the_real_model_loads_and_scores_repeatably():
    # Only where PyTorch is installed (the Space, or a local run): CI tests
    # the service without it.
    pytest.importorskip("torch")
    import liveness

    liveness.load_model()
    first = liveness.score(tone(3.0))

    assert isinstance(first, float) and np.isfinite(first)
    assert liveness.score(tone(3.0)) == first
    assert liveness.score(np.zeros(TARGET_RATE, np.float32)) is None
