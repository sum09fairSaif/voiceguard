import pytest

import config
from liveness_check import check_liveness


@pytest.fixture(autouse=True)
def threshold(monkeypatch):
    monkeypatch.setattr(config, "LIVENESS_THRESHOLD", -0.5)


def test_score_above_the_threshold_passes():
    result = check_liveness(1.0)

    assert result.passed
    assert result.score == 1.0


def test_score_at_the_threshold_passes():
    assert check_liveness(-0.5).passed


def test_score_below_the_threshold_fails():
    assert not check_liveness(-0.6).passed


def test_no_score_fails():
    result = check_liveness(None)

    assert not result.passed
    assert result.score is None
