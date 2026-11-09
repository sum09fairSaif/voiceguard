import numpy as np
import pytest
import soundfile as sf
from conftest import write_tone

import validate
from validate import check_clip, read_audio


def libsndfile_fails(monkeypatch):
    """Make soundfile fail the way libsndfile 1.2.2 does on half of ASVspoof 2019 PA."""

    def broken_read(*args, **kwargs):
        raise sf.LibsndfileError(1, "Error reading file: ")

    monkeypatch.setattr(validate.sf, "read", broken_read)


def test_reads_a_normal_file_with_soundfile(tmp_path):
    path = tmp_path / "tone.flac"
    write_tone(path, seconds=1.0)

    samples, rate = read_audio(path)

    assert rate == 16000
    assert samples.shape == (16000, 1)
    assert samples.dtype == np.float32


def test_flac_soundfile_cant_read_is_decoded_with_miniaudio(tmp_path, monkeypatch):
    path = tmp_path / "tone.flac"
    write_tone(path, seconds=1.0)
    expected, _ = sf.read(str(path), dtype="float32", always_2d=True)
    libsndfile_fails(monkeypatch)

    samples, rate = read_audio(path)

    assert rate == 16000
    assert samples.shape == expected.shape
    assert samples.dtype == np.float32
    # Same 16-bit samples, so the same values to within float rounding.
    assert np.abs(samples - expected).max() < 1e-6


def test_other_formats_soundfile_cant_read_still_fail(tmp_path, monkeypatch):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=1.0)
    libsndfile_fails(monkeypatch)

    with pytest.raises(RuntimeError):
        read_audio(path)


def test_flac_neither_decoder_can_read_fails(tmp_path):
    path = tmp_path / "broken.flac"
    path.write_bytes(b"fLaC" + b"\x00" * 100)

    with pytest.raises(RuntimeError):
        read_audio(path)


def test_check_clip_accepts_a_flac_only_miniaudio_can_read(tmp_path, monkeypatch):
    path = tmp_path / "tone.flac"
    write_tone(path, seconds=2.0)
    libsndfile_fails(monkeypatch)

    assert check_clip(path) == ""
