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
"""

import os

import numpy as np

# The weights file and a name for it, reported with every score so the
# backend's logs say which model made it.
LIVENESS_MODEL = "aasist-first-try"
WEIGHTS = os.getenv(
    "LIVENESS_WEIGHTS", os.path.join(os.path.dirname(__file__), "weights", "liveness-first-try.pth")
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


def prepare(samples: np.ndarray) -> np.ndarray | None:
    """16 kHz mono samples as the model's input: centred, silence trimmed
    off both ends, speech brought to -26 dBFS, then the first CROP_SAMPLES
    (short clips repeated to fill them). None if there's no sound at all."""
    mono = _remove_dc(samples.astype(np.float32))
    start, end = _speech_bounds(mono)
    if end == start:
        return None
    trimmed = _remove_dc(mono[start:end])
    clip = (trimmed * _normalize_gain(trimmed)).astype(np.float32)
    if len(clip) < CROP_SAMPLES:
        clip = np.tile(clip, CROP_SAMPLES // len(clip) + 1)
    return clip[:CROP_SAMPLES]


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
    """The liveness score for 16 kHz mono samples, or None if there's no
    sound to judge. Few weights but a lot of arithmetic: about 3 seconds
    on a CPU, a few milliseconds on a GPU."""
    import torch

    clip = prepare(samples)
    if clip is None:
        return None
    if next(_model.parameters()).device.type != device:
        _model.to(device)
    with torch.inference_mode():
        _, logits = _model(torch.from_numpy(clip).unsqueeze(0).to(device))
    return float(logits[0, 1])
