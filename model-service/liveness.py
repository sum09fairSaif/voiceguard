"""Liveness check: does a recording sound like a live person, rather than a
replay or an AI-made voice?

The model is AASIST (aasist.py, copied unchanged from the ASVspoof 5
baseline), fine-tuned in ml/liveness/ on real and fake speech. Its score is
the model's "real" output: higher means more likely a live person. It isn't
a probability; the backend compares it with a threshold chosen from test
results (see ml/liveness/README.md).

The model only gives meaningful scores on audio prepared exactly the way its
training clips were, so prepare() repeats ml/liveness/audio.py's steps. Keep
the two in step: a change there needs the same change here, and retraining.

The model hears about 4 seconds at a time and a passage takes longer, so the
whole recording is scored in overlapping 4-second windows and the lowest
score counts. Scoring only the start would let someone say the first words
themselves and play a recording or clone for the rest.
"""

import os

import numpy as np

# The weights file and a name for it, reported with every score so the
# backend's logs say which model made it.
LIVENESS_MODEL = "aasist-first-try"
# LIVENESS_WEIGHTS can point elsewhere, e.g. a Space variable. Spaces and line
# breaks around it are dropped: a value pasted into the Space's settings
# with a trailing newline otherwise names a file that doesn't exist.
WEIGHTS = os.getenv("LIVENESS_WEIGHTS", "").strip() or os.path.join(
    os.path.dirname(__file__), "weights", "liveness-first-try.pth"
)

# From ml/liveness/audio.py (STEPS_VERSION 2). The input arrives already
# 16 kHz mono from ffmpeg, so its resampling step isn't needed here.
TARGET_RATE = 16000
CROP_SAMPLES = 64600  # AASIST's input: about 4 seconds
FRAME_SECONDS = 0.025
HOP_SECONDS = 0.010
TRIM_DB = 30
ACTIVE_DB = 30
TARGET_DBFS = -26
MAX_PEAK = 0.95

# Each window starts 2 seconds after the last, so they overlap by half, and
# the last one ends where the speech does: the first and last 4 seconds are
# always scored whole, and any 6 seconds hold at least one whole window.
WINDOW_HOP = 2 * TARGET_RATE
# A passage is about 5-8 seconds of speech: 2-3 windows. Over this many
# (about a minute) isn't scored, so a long upload can't run past the
# backend's timeout or the GPU's time limit; with no score, the check fails.
MAX_WINDOWS = 30
# Windows sent through the model at once.
BATCH = 8

# The AASIST settings the checkpoint was trained with (ml/liveness/score_baseline.py).
MODEL_CONFIG = {
    "architecture": "AASIST", "nb_samp": CROP_SAMPLES, "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]], "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5], "temperatures": [2.0, 2.0, 100.0, 100.0],
}

# The loaded model, set once by load_model().
_model = None


def _remove_dc(samples: np.ndarray) -> np.ndarray:
    return samples - samples.mean()


def _frame_levels(samples: np.ndarray) -> np.ndarray:
    frame = int(FRAME_SECONDS * TARGET_RATE)
    hop = int(HOP_SECONDS * TARGET_RATE)
    energy = np.concatenate(([0.0], np.cumsum(samples.astype(np.float64) ** 2)))
    starts = np.arange(0, max(len(samples) - frame + 1, 1), hop)
    ends = np.minimum(starts + frame, len(samples))
    return np.sqrt((energy[ends] - energy[starts]) / np.maximum(ends - starts, 1))


def _speech_bounds(samples: np.ndarray) -> tuple[int, int]:
    levels = _frame_levels(samples)
    loudest = levels.max(initial=0.0)
    if loudest == 0:
        return 0, 0
    speech = np.flatnonzero(levels >= loudest * 10 ** (-TRIM_DB / 20))
    hop = int(HOP_SECONDS * TARGET_RATE)
    frame = int(FRAME_SECONDS * TARGET_RATE)
    return int(speech[0]) * hop, min(int(speech[-1]) * hop + frame, len(samples))


def _normalize_gain(samples: np.ndarray) -> float:
    levels = _frame_levels(samples)
    active = levels[levels >= levels.max() * 10 ** (-ACTIVE_DB / 20)]
    level = float(np.sqrt(np.mean(active**2)))
    return min(10 ** (TARGET_DBFS / 20) / level, MAX_PEAK / float(np.abs(samples).max()))


def window_starts(length: int) -> list[int]:
    """Where each window starts in speech `length` samples long (at least
    CROP_SAMPLES): every WINDOW_HOP, plus one ending exactly at the end."""
    starts = list(range(0, length - CROP_SAMPLES + 1, WINDOW_HOP))
    if starts[-1] != length - CROP_SAMPLES:
        starts.append(length - CROP_SAMPLES)
    return starts


def prepare(samples: np.ndarray) -> np.ndarray | None:
    """16 kHz mono samples as the model's input: centred, silence trimmed
    off both ends, speech brought to -26 dBFS, then cut into overlapping
    windows of CROP_SAMPLES covering all of it, as a (windows, CROP_SAMPLES)
    array. Speech shorter than one window is repeated to fill it, as in
    training. None if there's no sound at all, or more than MAX_WINDOWS."""
    mono = _remove_dc(samples.astype(np.float32))
    start, end = _speech_bounds(mono)
    if end == start:
        return None
    trimmed = _remove_dc(mono[start:end])
    clip = (trimmed * _normalize_gain(trimmed)).astype(np.float32)
    if len(clip) < CROP_SAMPLES:
        clip = np.tile(clip, CROP_SAMPLES // len(clip) + 1)[:CROP_SAMPLES]
    starts = window_starts(len(clip))
    if len(starts) > MAX_WINDOWS:
        return None
    return np.stack([clip[s : s + CROP_SAMPLES] for s in starts])


def lowest_score(windows: np.ndarray, score_batch) -> float:
    """The recording's score: its least live-sounding window. `score_batch`
    takes up to BATCH windows and returns one score per window."""
    scores = [score_batch(windows[i : i + BATCH]) for i in range(0, len(windows), BATCH)]
    return float(np.min(np.concatenate(scores)))


def load_model() -> None:
    """Load the model on the CPU. ZeroGPU only allows the GPU inside a
    @spaces.GPU function, so score() moves it there when asked."""
    global _model
    # Imported here so tests can run without PyTorch installed.
    import torch

    from aasist import Model

    model = Model(MODEL_CONFIG)
    # weights_only stops the file running code when it's loaded.
    model.load_state_dict(torch.load(WEIGHTS, map_location="cpu", weights_only=True))
    _model = model.eval()


def score(samples: np.ndarray, device: str = "cpu") -> float | None:
    """The liveness score for 16 kHz mono samples: the lowest of its
    windows' scores. None if there's no sound to judge, or too much. Few
    weights but a lot of arithmetic: about 3 seconds a window on a CPU, a
    few milliseconds on a GPU."""
    import torch

    windows = prepare(samples)
    if windows is None:
        return None
    if next(_model.parameters()).device.type != device:
        _model.to(device)

    def score_batch(batch: np.ndarray) -> np.ndarray:
        with torch.inference_mode():
            _, logits = _model(torch.from_numpy(batch).to(device))
        return logits[:, 1].float().cpu().numpy()

    return lowest_score(windows, score_batch)
