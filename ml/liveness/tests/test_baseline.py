import numpy as np
import pandas as pd
import pytest

pytest.importorskip("torch")  # CI doesn't install it (see requirements-model.txt)

from score_baseline import eer, summarise  # noqa: E402


def test_eer_is_zero_when_real_and_fake_are_apart():
    rate, threshold = eer(np.array([2.0, 3.0]), np.array([-1.0, 0.0]))
    assert rate == 0
    assert 0 <= threshold < 2


def test_eer_is_half_when_the_scores_say_nothing():
    rng = np.random.default_rng(0)
    rate, _ = eer(rng.normal(size=20000), rng.normal(size=20000))
    assert rate == pytest.approx(0.5, abs=0.02)


def test_eer_finds_where_the_two_errors_meet():
    # Threshold at 1: one of four real clips rejected, one of four fakes accepted.
    rate, _ = eer(np.array([1.0, 5.0, 6.0, 7.0]), np.array([-3.0, -2.0, -1.0, 2.0]))
    assert rate == pytest.approx(0.25)


def test_a_source_without_fakes_reports_real_clips_rejected():
    scores = pd.DataFrame({
        "model": "m", "audio": "raw",
        "source": ["a", "a", "a", "a", "real_only", "real_only"],
        "label": ["bonafide", "bonafide", "spoof", "spoof", "bonafide", "bonafide"],
        "score": [2.0, 3.0, -1.0, 0.0, 5.0, -5.0],
    })
    table = summarise(scores)
    assert table.loc["a", ("m", "raw")] == 0
    assert table.loc["real_only (real rejected)", ("m", "raw")] == 50
