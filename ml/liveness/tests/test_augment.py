import numpy as np
import pytest
import soundfile as sf

import audio
import augment


def speech(seconds=4.0, seed=0):
    """A voice-like signal: a pitched tone switching on and off, plus a little noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * audio.TARGET_RATE)) / audio.TARGET_RATE
    voiced = np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    return (0.05 * voiced + 0.002 * rng.standard_normal(len(t))).astype(np.float32)


def snr_db(clean, other):
    return 10 * np.log10(np.sum(clean**2) / np.sum((clean - other) ** 2))


def active_dbfs(samples):
    levels = audio.frame_levels(samples)
    active = levels[levels >= levels.max() * 10 ** (-audio.ACTIVE_DB / 20)]
    return 20 * np.log10(np.sqrt(np.mean(active**2)))


@pytest.mark.parametrize("opus_share", [1.0, 0.0])  # Opus, then MP3
def test_compression_keeps_the_length_and_the_timing(monkeypatch, opus_share):
    monkeypatch.setattr(augment, "OPUS_SHARE", opus_share)
    clean = speech()
    out = augment.compress(clean, np.random.default_rng(1))
    assert out.shape == clean.shape and out.dtype == np.float32
    assert not np.array_equal(out, clean)
    # Opus lines up exactly; MP3's encoder delay shifts it a little.
    best_lag = max(range(-2000, 2001, 50), key=lambda lag: np.dot(np.roll(out, -lag), clean))
    assert abs(best_lag) <= (0 if opus_share else 1200)


def test_low_bitrate_opus_changes_the_sound_more(monkeypatch):
    monkeypatch.setattr(augment, "OPUS_SHARE", 1.0)
    clean = speech()
    monkeypatch.setattr(augment, "OPUS_LEVELS", (0.6, 0.6))
    high = augment.compress(clean, np.random.default_rng(0))
    monkeypatch.setattr(augment, "OPUS_LEVELS", (1.0, 1.0))
    low = augment.compress(clean, np.random.default_rng(0))
    assert snr_db(clean, high) > snr_db(clean, low) + 5


def test_a_room_with_no_echo_leaves_the_clip_alone():
    clean = speech()
    rir = np.zeros(800, dtype=np.float32)
    rir[100] = 0.3  # just the direct sound, a little late and quiet
    assert np.allclose(augment.reverberate(clean, rir), clean, atol=1e-5)


def test_reverb_keeps_the_length_and_adds_a_tail():
    clean = speech()
    rir = (np.exp(-np.arange(4000) / 800) * np.random.default_rng(0).standard_normal(4000)).astype(np.float32)
    rir[0] = 5.0
    out = augment.reverberate(clean, rir)
    assert out.shape == clean.shape
    assert snr_db(clean, out) < 30


def test_noise_goes_in_at_the_asked_level():
    clean = speech()
    noise = np.random.default_rng(0).standard_normal(5000).astype(np.float32)  # shorter: gets repeated
    out = augment.add_noise(clean, noise, 10.0)
    assert out.shape == clean.shape
    assert snr_db(clean, out) == pytest.approx(10.0, abs=0.1)


def test_augmented_clips_come_back_at_the_usual_level():
    clean = speech()
    aug = augment.Augmenter()
    for seed in range(10):
        out = aug(clean, np.random.default_rng(seed))
        assert out.shape == clean.shape
        assert active_dbfs(out) == pytest.approx(audio.TARGET_DBFS, abs=0.5)
        assert np.abs(out).max() <= audio.MAX_PEAK + 1e-6


def test_mp3_works_at_its_lowest_bitrate(monkeypatch):
    monkeypatch.setattr(augment, "OPUS_SHARE", 0.0)
    monkeypatch.setattr(augment, "MP3_LEVELS", (augment.MP3_LEVELS[1],) * 2)
    clean = speech()
    assert not np.array_equal(augment.compress(clean, np.random.default_rng(0)), clean)


def test_a_failing_codec_leaves_the_clip_unchanged(monkeypatch):
    # The MP3 encoder fails at level 1.0, as it did once in training.
    monkeypatch.setattr(augment, "OPUS_SHARE", 0.0)
    monkeypatch.setattr(augment, "MP3_LEVELS", (1.0, 1.0))
    clean = speech()
    assert np.array_equal(augment.compress(clean, np.random.default_rng(0)), clean)


def test_without_noise_files_only_compression_happens():
    aug = augment.Augmenter()
    assert aug.rirs == [] and aug.noises == []


@pytest.fixture
def noise_dir(tmp_path):
    root = tmp_path / "RIRS_NOISES"
    rng = np.random.default_rng(0)
    files = {
        "simulated_rirs/smallroom/Room001/Room001-00001.wav": 1,
        "pointsource_noises/noise-free-sound-0001.wav": 1,
        "real_rirs_isotropic_noises/RVB2014_type1_rir_largeroom1_near_angla.wav": 8,
        "real_rirs_isotropic_noises/RVB2014_type1_noise_largeroom1_1.wav": 8,
    }
    for name, channels in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        data = (0.1 * rng.standard_normal((8000, channels))).astype(np.float32)
        data[0] = 1.0
        sf.write(str(root / name), data, audio.TARGET_RATE)
    return root


def test_echoes_and_noises_are_told_apart(noise_dir):
    aug = augment.Augmenter(noise_dir)
    assert sorted(p.name for p in aug.rirs) == ["RVB2014_type1_rir_largeroom1_near_angla.wav", "Room001-00001.wav"]
    assert sorted(p.name for p in aug.noises) == ["RVB2014_type1_noise_largeroom1_1.wav", "noise-free-sound-0001.wav"]


def test_every_effect_can_be_applied(noise_dir, monkeypatch):
    for name in ["REVERB_CHANCE", "NOISE_CHANCE", "CODEC_CHANCE"]:
        monkeypatch.setattr(augment, name, 1.0)
    clean = speech()
    out = augment.Augmenter(noise_dir)(clean, np.random.default_rng(0))
    assert out.shape == clean.shape
    assert snr_db(clean / np.abs(clean).max(), out / np.abs(out).max()) < 20


def test_a_missing_noise_folder_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        augment.Augmenter(tmp_path / "nothing")
