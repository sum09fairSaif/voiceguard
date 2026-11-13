import importlib.util
import itertools
from pathlib import Path

import numpy as np
import pytest

from liveness import (
    BATCH,
    CROP_SAMPLES,
    MAX_WINDOWS,
    TARGET_DBFS,
    TARGET_RATE,
    WINDOW_HOP,
    lowest_score,
    prepare,
    window_starts,
)


def tone(seconds, level=0.3, offset=0.0, hz=200):
    t = np.arange(int(seconds * TARGET_RATE)) / TARGET_RATE
    return (level * np.sin(2 * np.pi * hz * t) + offset).astype(np.float32)


def test_input_is_always_windows_of_the_models_length():
    for seconds in [0.3, 2.0, 4.0, 9.0]:
        windows = prepare(tone(seconds))
        assert windows.ndim == 2 and windows.shape[1] == CROP_SAMPLES
        assert windows.dtype == np.float32


def test_windows_cover_all_of_the_speech_and_overlap():
    for seconds in [4.5, 6.0, 7.3, 12.0]:
        length = int(seconds * TARGET_RATE)
        starts = window_starts(length)
        assert starts[0] == 0
        assert starts[-1] + CROP_SAMPLES == length
        assert all(0 < b - a <= WINDOW_HOP for a, b in itertools.pairwise(starts))


def test_a_passage_is_a_few_windows():
    assert len(prepare(tone(4.0))) == 1
    assert len(prepare(tone(7.0))) == 3


def test_a_clone_after_a_live_start_is_caught():
    # Said live for the first 4.5 seconds (a low tone), then a clone for the
    # last 3 (a high tone). A stand-in model calls a window fake if any of it
    # is the high tone. The first window alone is all live; the lowest score
    # across the windows is what catches it.
    samples = np.concatenate([tone(4.5, hz=200), tone(3.0, hz=3000)])

    def score_batch(batch):
        # Zero crossings per 0.1 s stretch: the high tone crosses 15x as often.
        crossings = np.mean(np.abs(np.diff(np.sign(batch.reshape(len(batch), 40, -1)), axis=2)) > 0, axis=2)
        return np.where(crossings.max(axis=1) > 0.1, -1.0, 1.0)

    windows = prepare(samples)

    assert score_batch(windows[:1])[0] == 1.0
    assert lowest_score(windows, score_batch) == -1.0


def test_windows_are_scored_in_batches():
    sizes = []

    def score_batch(batch):
        sizes.append(len(batch))
        return np.arange(len(batch), dtype=np.float32)

    lowest_score(np.zeros((BATCH + 3, CROP_SAMPLES), np.float32), score_batch)

    assert sizes == [BATCH, 3]


def test_too_long_a_recording_isnt_scored():
    longest = (CROP_SAMPLES + (MAX_WINDOWS - 1) * WINDOW_HOP) / TARGET_RATE
    assert len(prepare(tone(longest))) == MAX_WINDOWS
    assert prepare(tone(longest + 0.5)) is None


def test_silence_at_the_ends_is_trimmed():
    # Two seconds of tone with a second of silence before it: the input
    # starts with the tone, as training clips did. At most one 25 ms frame
    # of the silence stays, the frame where the tone begins.
    samples = np.concatenate([np.zeros(TARGET_RATE, np.float32), tone(2.0)])

    windows = prepare(samples)

    assert np.abs(windows[0, :400]).max() > 0.01


def test_speech_is_brought_to_the_training_loudness():
    for level in [0.01, 0.3, 0.9]:
        windows = prepare(tone(5.0, level=level))
        dbfs = 20 * np.log10(np.sqrt(np.mean(windows**2)))
        assert abs(dbfs - TARGET_DBFS) < 0.5


def test_offset_from_zero_is_removed():
    windows = prepare(tone(5.0, offset=0.2))

    assert abs(windows.mean()) < 1e-3


def test_short_clips_are_repeated_to_fill_the_input():
    windows = prepare(tone(1.0))

    assert windows.shape == (1, CROP_SAMPLES)
    assert np.abs(windows[0, -1000:]).max() > 0.01


def test_silence_has_nothing_to_score():
    assert prepare(np.zeros(TARGET_RATE, np.float32)) is None


def training_audio():
    """ml/liveness/audio.py, the steps the model's training clips went through."""
    path = Path(__file__).resolve().parents[2] / "ml" / "liveness" / "audio.py"
    spec = importlib.util.spec_from_file_location("training_audio", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("seconds", [1.5, 4.0, 7.3])
def test_the_audio_is_prepared_exactly_as_in_training(seconds):
    # Speech-like bursts with silence at the ends and an offset from zero, so
    # every step (centring, trimming, loudness) has something to do.
    rng = np.random.default_rng(0)
    speech = rng.standard_normal(int(seconds * TARGET_RATE)).astype(np.float32)
    speech *= 0.1 + 0.4 * np.abs(np.sin(np.linspace(0, 12, len(speech)))).astype(np.float32)
    silence = np.zeros(TARGET_RATE // 2, np.float32)
    samples = np.concatenate([silence, speech, silence]) + np.float32(0.05)
    audio = training_audio()

    cleaned, _ = audio.clean(samples[:, None], TARGET_RATE)
    windows = prepare(samples)

    # Training's first window, as scored, is our first window...
    np.testing.assert_allclose(windows[0], audio.fix_length(cleaned), atol=1e-6)
    # ...and every window is a stretch of the same cleaned audio.
    if len(cleaned) >= CROP_SAMPLES:
        for window, start in zip(windows, window_starts(len(cleaned)), strict=True):
            np.testing.assert_allclose(window, cleaned[start : start + CROP_SAMPLES], atol=1e-6)


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
    # A longer recording is several windows, and gets one score.
    assert np.isfinite(liveness.score(tone(7.0)))
