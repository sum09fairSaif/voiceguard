import numpy as np
import pandas as pd
import pytest
import soundfile as sf

pytest.importorskip("torch")  # CI doesn't install it (see requirements-model.txt)

import audio
from augment import Augmenter
from training_data import ClipDataset, balanced_sampler, even_sample, sampling_weights


def manifest(counts):
    """Rows for {(source, label): number of clips}."""
    rows = [{"source": s, "label": lab, "path": f"{s}/{lab}/{i}.flac", "split": "train"}
            for (s, lab), n in counts.items() for i in range(n)]
    return pd.DataFrame(rows)


COUNTS = {("big", "spoof"): 900, ("big", "bonafide"): 100, ("small", "spoof"): 100, ("small", "bonafide"): 25}


def test_half_the_draws_are_real():
    df = manifest(COUNTS)
    w = sampling_weights(df)
    assert w.sum() == pytest.approx(1)
    assert w[df["label"] == "bonafide"].sum() == pytest.approx(0.5)


def test_datasets_count_by_the_square_root_of_their_size():
    df = manifest(COUNTS)
    w = sampling_weights(df)
    fake = df["label"] == "spoof"
    big, small = w[fake & (df["source"] == "big")].sum(), w[fake & (df["source"] == "small")].sum()
    assert big / small == pytest.approx(np.sqrt(900 / 100))
    # Every clip of one dataset and label is equally likely.
    assert len(np.unique(w[fake & (df["source"] == "big")].round(12))) == 1


def test_the_sampler_draws_about_half_real():
    df = manifest(COUNTS)
    drawn = df.loc[list(balanced_sampler(df, 20000, seed=0)), "label"]
    assert (drawn == "bonafide").mean() == pytest.approx(0.5, abs=0.02)


def test_even_sample_caps_each_group_and_repeats():
    df = manifest(COUNTS)
    a, b = even_sample(df, 50), even_sample(df, 50)
    assert a.groupby(["source", "label"]).size().to_dict() == {
        ("big", "bonafide"): 50, ("big", "spoof"): 50, ("small", "bonafide"): 25, ("small", "spoof"): 50}
    assert a.equals(b)


@pytest.fixture
def clips(tmp_path):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"path": ["a.flac", "b.flac"], "label": ["bonafide", "spoof"]})
    for path, seconds in zip(df["path"], [6.0, 2.0]):
        sf.write(str(tmp_path / path), (0.05 * rng.standard_normal(int(seconds * 16000))).astype(np.float32),
                 16000, subtype="PCM_16")
    return df, tmp_path


def test_clips_come_as_4_second_inputs_with_1_for_real(clips):
    df, root = clips
    data = ClipDataset(df, root)
    x0, y0 = data[0]
    x1, y1 = data[1]
    assert x0.shape == x1.shape == (audio.CROP_SAMPLES,)
    assert (y0, y1) == (1, 0)
    assert np.array_equal(data[0][0].numpy(), x0.numpy())  # scoring is repeatable


def test_training_clips_vary_each_time_theyre_drawn(clips):
    df, root = clips
    data = ClipDataset(df, root, Augmenter())
    first, second = data[0][0].numpy(), data[0][0].numpy()
    assert first.shape == (audio.CROP_SAMPLES,)
    assert not np.array_equal(first, second)
