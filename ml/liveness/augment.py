"""Random changes to training clips, so the model can't rely on how a dataset
was recorded and still works on what VoiceGuard's users send.

Used by training only, on real and fake clips alike, with the same chances:
an effect applied to one class only would itself become a cue. Each clip may
get, in this order (the order sound meets them on the way to us):

1. RawBoost (only with Augmenter(rawboost=True)): the distortions of cheap
   microphones, speakers and phone lines, made up at random for each clip. A
   replay passes through a speaker and a second microphone, so this teaches
   the model that "sounds like a different device" isn't "sounds fake";
2. a room's echo (reverb), from a recorded or simulated room;
3. background noise, 5 to 25 dB below the speech;
4. lossy compression: Opus, what browsers record in, or MP3, what Common
   Voice and many fakes come in. Without this, "sounds like MP3" alone would
   tell Common Voice's real clips from the fakes.

The echoes and noises come from OpenSLR's RIRS_NOISES (`python download.py
rirs_noises`). Without them, only RawBoost and compression are applied.
"""

import io
from pathlib import Path

import numpy as np
import soundfile as sf

import audio

RAWBOOST_CHANCE = 0.5
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


# RawBoost (Tak et al., "RawBoost: A Raw Data Boosting and Augmentation Method
# applied to Automatic Speaker Verification Anti-Spoofing", ICASSP 2022), the
# augmentation the XLS-R + AASIST paper trained with. Rewritten here in numpy
# from the paper and its MIT-licensed code (github.com/TakHemlata/RawBoost-
# antispoofing), with that code's default settings, so training needs no
# scipy. Each clip gets one of: device-like filtering and distortion (LnL),
# crackle on a few samples (ISD), filtered background hiss (SSI), or LnL then
# ISD, the combination the paper found best on ASVspoof 2019 LA.
RB_BANDS = 5  # notch filters per random filter
RB_FREQ = (20.0, 8000.0)  # Hz, where a notch can sit
RB_WIDTH = (100.0, 1000.0)  # Hz, how wide it is
RB_TAPS = (10, 100)  # filter length per notch
RB_GAIN_DB = (0.0, 0.0)
RB_NONLINEAR_BIAS_DB = (5.0, 20.0)  # how much quieter the distorted copies are
RB_ORDERS = 5  # the signal, its square, cube, ...: harmonic distortion
RB_ISD_SHARE = 10.0  # up to this % of samples get a crackle
RB_ISD_GAIN = 2.0
RB_SSI_SNR_DB = (10.0, 40.0)


def _lowpass(taps: int, cutoff_hz: float) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    fc = cutoff_hz / audio.TARGET_RATE
    return 2 * fc * np.sinc(2 * fc * n)


def notch_filter(rng: np.random.Generator, gain_db: tuple[float, float] = RB_GAIN_DB) -> np.ndarray:
    """A random FIR filter: RB_BANDS band-stop (Hamming-window) filters in a
    row, scaled so its loudest frequency has a random gain."""
    nyquist = audio.TARGET_RATE / 2
    b = np.ones(1)
    for _ in range(RB_BANDS):
        centre, width = rng.uniform(*RB_FREQ), rng.uniform(*RB_WIDTH)
        taps = int(rng.integers(RB_TAPS[0], RB_TAPS[1] + 1)) | 1  # odd, as a band-stop filter needs
        low, high = max(centre - width / 2, 1e-3), min(centre + width / 2, nyquist - 1e-3)
        band_pass = _lowpass(taps, high) - _lowpass(taps, low)
        band_stop = -band_pass
        band_stop[taps // 2] += 1.0
        b = np.convolve(band_stop * np.hamming(taps), b)
    peak = np.abs(np.fft.rfft(b, 1024)).max()
    # Not rng.uniform: the distortion terms' range runs from -5 down to -20 dB.
    gain = gain_db[0] + (gain_db[1] - gain_db[0]) * rng.random()
    return (10 ** (gain / 20) * b / peak).astype(np.float64)


def _zero_phase(samples: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Filter forwards and backwards, as RawBoost's filtfilt does, so the
    speech doesn't move in time."""
    both = np.convolve(b, b[::-1])
    full = fft_convolve(samples, both)
    start = (len(both) - 1) // 2
    return full[start : start + len(samples)]


def _peak_limit(samples: np.ndarray) -> np.ndarray:
    peak = np.abs(samples).max()
    return samples / peak if peak > 1 else samples


def rb_device(samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """LnL: the clip through a random filter, plus quieter, differently
    filtered copies of its square, cube and so on, the harmonics a cheap
    speaker or microphone adds."""
    x = samples.astype(np.float64)
    out = np.zeros_like(x)
    gain = RB_GAIN_DB
    for order in range(1, RB_ORDERS + 1):
        if order == 2:
            gain = (RB_GAIN_DB[0] - RB_NONLINEAR_BIAS_DB[0], RB_GAIN_DB[1] - RB_NONLINEAR_BIAS_DB[1])
        out += _zero_phase(x**order, notch_filter(rng, gain))
    return _peak_limit(out - out.mean())


def rb_crackle(samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """ISD: up to RB_ISD_SHARE % of samples, chosen at random, pushed by up to
    RB_ISD_GAIN times their own value: clicks and crackle that follow the speech."""
    x = samples.astype(np.float64).copy()
    count = int(len(x) * rng.uniform(0, RB_ISD_SHARE) / 100)
    where = rng.permutation(len(x))[:count]
    factor = (2 * rng.random(count) - 1) * (2 * rng.random(count) - 1)
    x[where] += RB_ISD_GAIN * x[where] * factor
    return _peak_limit(x)


def rb_hiss(samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """SSI: white noise through a random filter, 10 to 40 dB below the clip."""
    x = samples.astype(np.float64)
    noise = fft_convolve(rng.standard_normal(len(x)), notch_filter(rng))[: len(x)]
    norm = np.linalg.norm(noise)
    if norm == 0 or not np.any(x):
        return x
    noise *= np.linalg.norm(x) / norm / 10 ** (rng.uniform(*RB_SSI_SNR_DB) / 20)
    return x + noise


def rawboost(samples: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One of RawBoost's distortions, chosen at random, same length out."""
    choice = int(rng.integers(4))
    if choice == 0:
        out = rb_device(samples, rng)
    elif choice == 1:
        out = rb_crackle(samples, rng)
    elif choice == 2:
        out = rb_hiss(samples, rng)
    else:
        out = rb_crackle(rb_device(samples, rng), rng)
    return out.astype(np.float32)


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

    def __init__(self, noise_dir: Path | None = None, rawboost: bool = False):
        self.rawboost = rawboost
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
        if self.rawboost and rng.random() < RAWBOOST_CHANCE:
            out = rawboost(out, rng)
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
