"""Random changes to training clips, so the model can't rely on how a dataset
was recorded and still works on what VoiceGuard's users send.

Used by training only, on real and fake clips alike, with the same chances:
an effect applied to one class only would itself become a cue. Each clip may
get, in this order (the order sound meets them on the way to us):

1. a room's echo (reverb), from a recorded or simulated room;
2. background noise, 5 to 25 dB below the speech;
3. lossy compression: Opus, what browsers record in, or MP3, what Common
   Voice and many fakes come in. Without this, "sounds like MP3" alone would
   tell Common Voice's real clips from the fakes.

The echoes and noises come from OpenSLR's RIRS_NOISES (`python download.py
rirs_noises`). Without them, only compression is applied.
"""

import io
from pathlib import Path

import numpy as np
import soundfile as sf

import audio

REVERB_CHANCE = 0.25
NOISE_CHANCE = 0.3
CODEC_CHANCE = 0.5
OPUS_SHARE = 0.6  # of compressed clips; the rest are MP3
SNR_DB = (5.0, 25.0)
# soundfile's compression levels: 0.6-1.0 is about 110 kbps down to 7 kbps for
# Opus; 0.3-0.99 is about 120 down to 16 kbps for MP3. The MP3 encoder fails
# at 0.9999 and above, so its range stops at 0.99.
OPUS_LEVELS = (0.6, 1.0)
MP3_LEVELS = (0.3, 0.99)


def fit(samples: np.ndarray, length: int) -> np.ndarray:
    """Cut or zero-pad to length. Codecs can add a few samples at the end."""
    if len(samples) >= length:
        return samples[:length]
    return np.pad(samples, (0, length - len(samples)))


def compress(samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Encode and decode with Opus or MP3 at a random bitrate. If the codec
    fails, the clip is returned unchanged rather than stopping training."""
    buffer = io.BytesIO()
    try:
        if rng.random() < OPUS_SHARE:
            sf.write(buffer, samples, audio.TARGET_RATE, format="OGG", subtype="OPUS",
                     compression_level=rng.uniform(*OPUS_LEVELS))
        else:
            sf.write(buffer, samples, audio.TARGET_RATE, format="MP3", subtype="MPEG_LAYER_III",
                     compression_level=rng.uniform(*MP3_LEVELS),
                     bitrate_mode="VARIABLE" if rng.random() < 0.5 else "CONSTANT")
        buffer.seek(0)
        decoded, _ = sf.read(buffer, dtype="float32")
    except sf.LibsndfileError:
        return samples
    return fit(decoded, len(samples))


def fft_convolve(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[:n]


def reverberate(samples: np.ndarray, rir: np.ndarray) -> np.ndarray:
    """Play the clip in a room. Lined up on the direct sound, so the speech
    doesn't move, and scaled so the room doesn't change the level much."""
    rir = rir[int(np.argmax(np.abs(rir))):]
    rir = rir / (np.sqrt(np.sum(rir**2)) + 1e-9)
    return fft_convolve(samples, rir)[: len(samples)].astype(np.float32)


def add_noise(samples: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Mix noise in at snr_db below the clip, repeating the noise if it's short."""
    noise = np.resize(noise, len(samples))
    speech_power = np.mean(samples**2)
    noise_power = np.mean(noise**2)
    if noise_power == 0 or speech_power == 0:
        return samples
    scale = np.sqrt(speech_power / (noise_power * 10 ** (snr_db / 10)))
    return (samples + scale * noise).astype(np.float32)


def read_random_part(path: Path, frames: int, rng: np.random.Generator) -> np.ndarray:
    """A random stretch of up to frames samples from one random channel."""
    info = sf.info(str(path))
    start = int(rng.integers(0, max(info.frames - frames, 0) + 1))
    data, rate = sf.read(str(path), start=start, frames=frames, dtype="float32", always_2d=True)
    channel = data[:, int(rng.integers(0, data.shape[1]))]
    return audio.to_mono_16k(channel[:, None], rate)


class Augmenter:
    """Picks and applies the random changes. Safe to send to DataLoader workers."""

    def __init__(self, noise_dir: Path | None = None):
        self.rirs: list[Path] = []
        self.noises: list[Path] = []
        if noise_dir is not None:
            root = Path(noise_dir)
            self.rirs = sorted((root / "simulated_rirs").rglob("*.wav"))
            self.noises = sorted((root / "pointsource_noises").rglob("*.wav"))
            # Recorded rooms: the same folder holds their echoes and their noise.
            for path in sorted((root / "real_rirs_isotropic_noises").glob("*.wav")):
                (self.noises if "noise" in path.name else self.rirs).append(path)
            if not self.rirs or not self.noises:
                raise FileNotFoundError(f"no room echoes or noises in {root}; run `python download.py rirs_noises`")

    def __call__(self, samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        out = samples.astype(np.float32)
        if self.rirs and rng.random() < REVERB_CHANCE:
            rir = read_random_part(self.rirs[int(rng.integers(len(self.rirs)))], audio.TARGET_RATE, rng)
            out = reverberate(out, rir)
        if self.noises and rng.random() < NOISE_CHANCE:
            noise = read_random_part(self.noises[int(rng.integers(len(self.noises)))], len(out), rng)
            out = add_noise(out, noise, rng.uniform(*SNR_DB))
        if rng.random() < CODEC_CHANCE:
            out = compress(out, rng)
        if not np.any(out):
            return samples.astype(np.float32)
        # Back to the level every clip has after preprocessing.
        return (out * audio.normalize_gain(out)).astype(np.float32)
