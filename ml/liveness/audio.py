"""The audio steps every clip goes through, so all clips look alike to the model.

Kept apart from the batch script (preprocess.py) so the live check can run a
user's recording through exactly the same steps as the training data.

Order matters: resampling comes first so every later measurement means the
same thing for every clip. The DC offset goes next, so it can't pass for sound
when the silence is trimmed, and the silence is trimmed before loudness is
measured so that it can't affect the level.
"""

import numpy as np
import soxr

TARGET_RATE = 16000
CROP_SAMPLES = 64600  # AASIST's input: about 4 seconds at 16 kHz

FRAME_SECONDS = 0.025
HOP_SECONDS = 0.010
# Frames this far below the loudest frame count as silence. At 40, background
# noise in some datasets passed as sound and their silence stayed; 30 trims all
# of them alike and removes at most 0.3% of a clip's energy.
TRIM_DB = 30
ACTIVE_DB = 30  # frames within this of the loudest are speech, for measuring loudness
TARGET_DBFS = -26  # loudness of the speech, a common level for speech processing
MAX_PEAK = 0.95  # never scale a clip so far that it would clip
# Raise this when the steps change in a way the numbers above don't show, so
# preprocess.py refuses to mix old and new clips.
STEPS_VERSION = 2


def to_mono_16k(samples: np.ndarray, rate: int) -> np.ndarray:
    """Average the channels of a (frames, channels) array and resample."""
    mono = samples.mean(axis=1, dtype=np.float32)
    if rate == TARGET_RATE:
        return mono
    return soxr.resample(mono, rate, TARGET_RATE, quality="HQ")


def remove_dc(samples: np.ndarray) -> np.ndarray:
    """Centre the wave on zero. Fakes tend to sit slightly off centre, which
    says how they were made rather than anything about the voice."""
    return samples - samples.mean()


def frame_levels(samples: np.ndarray) -> np.ndarray:
    """The RMS level of each short frame of a 16 kHz clip."""
    frame = int(FRAME_SECONDS * TARGET_RATE)
    hop = int(HOP_SECONDS * TARGET_RATE)
    energy = np.concatenate(([0.0], np.cumsum(samples.astype(np.float64) ** 2)))
    starts = np.arange(0, max(len(samples) - frame + 1, 1), hop)
    ends = np.minimum(starts + frame, len(samples))
    return np.sqrt((energy[ends] - energy[starts]) / np.maximum(ends - starts, 1))


def speech_bounds(samples: np.ndarray) -> tuple[int, int]:
    """Where speech starts and ends.

    No padding is left: real clips have silence to keep and many fakes
    don't, so padding would bring back the difference trimming removes.
    Only the ends are trimmed. Pauses inside the speech stay, since how a
    voice pauses can itself be evidence. A silent clip returns (0, 0).
    """
    levels = frame_levels(samples)
    loudest = levels.max(initial=0.0)
    if loudest == 0:
        return 0, 0
    speech = np.flatnonzero(levels >= loudest * 10 ** (-TRIM_DB / 20))
    hop = int(HOP_SECONDS * TARGET_RATE)
    frame = int(FRAME_SECONDS * TARGET_RATE)
    return int(speech[0]) * hop, min(int(speech[-1]) * hop + frame, len(samples))


def normalize_gain(samples: np.ndarray) -> float:
    """The gain that brings the speech to TARGET_DBFS without clipping."""
    levels = frame_levels(samples)
    active = levels[levels >= levels.max() * 10 ** (-ACTIVE_DB / 20)]
    level = float(np.sqrt(np.mean(active**2)))
    return min(10 ** (TARGET_DBFS / 20) / level, MAX_PEAK / float(np.abs(samples).max()))


def clean(samples: np.ndarray, rate: int) -> tuple[np.ndarray, dict]:
    """Run one clip through every step.

    Returns the audio and what was done to it. The audio is empty if the
    clip had no signal.
    """
    mono = remove_dc(to_mono_16k(samples, rate))
    start, end = speech_bounds(mono)
    if end == start:
        return mono[:0], {"lead_trim_s": 0.0, "tail_trim_s": 0.0, "gain_db": 0.0}
    trimmed = remove_dc(mono[start:end])  # cutting the ends moves the centre slightly
    gain = normalize_gain(trimmed)
    return trimmed * gain, {
        "lead_trim_s": start / TARGET_RATE,
        "tail_trim_s": (len(mono) - end) / TARGET_RATE,
        "gain_db": 20 * float(np.log10(gain)),
    }


def fix_length(samples: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """Make a clip exactly CROP_SAMPLES long, the way AASIST expects it.

    Short clips are repeated. Long ones take a random window when given a
    random generator (training, so each pass sees different audio), and the
    start of the clip otherwise (scoring, so results are repeatable). This
    runs when clips are loaded, not in preprocess.py, so that training can
    use all of a long clip.
    """
    if len(samples) < CROP_SAMPLES:
        repeats = CROP_SAMPLES // len(samples) + 1
        return np.tile(samples, repeats)[:CROP_SAMPLES]
    start = 0 if rng is None else int(rng.integers(0, len(samples) - CROP_SAMPLES + 1))
    return samples[start : start + CROP_SAMPLES]
