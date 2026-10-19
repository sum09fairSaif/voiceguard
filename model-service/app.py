"""VoiceGuard model service: turns a recording into a speaker embedding.

Runs separately from the backend, as a free Hugging Face Space on ZeroGPU,
because the voice model needs PyTorch, which is too big for the backend's
host. ZeroGPU only works for Gradio apps, so this is one: a Gradio app with
a single API endpoint, `embed`, and no UI.

The backend sends a recording (as base64 text, so Gradio never saves it as
an uploaded file) and gets back a list of numbers describing the voice.
Recordings are never stored: each one lives in a temporary file only while
it is decoded, then is deleted.
"""

import base64
import binascii
import logging
import os
import secrets
import subprocess
import tempfile
from typing import Any, Callable

try:
    # Hugging Face's ZeroGPU package. It must be imported before anything
    # loads PyTorch, and only exists on the Space; locally and in CI the
    # model simply runs on the CPU.
    import spaces
except ImportError:
    spaces = None

import numpy as np

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = os.getenv("MODEL_DIR", "pretrained_models/spkrec-ecapa-voxceleb")
SAMPLE_RATE = 16000  # what the model was trained on
MAX_AUDIO_BYTES = 1024 * 1024  # same cap as the backend
MAX_BASE64_CHARS = (MAX_AUDIO_BYTES + 2) // 3 * 4
MIN_SECONDS = 0.5  # shorter than this isn't enough voice to describe
# Recording-quality measures, reported back so the backend can turn away
# poor enrollment samples. The backend decides the limits; these only say
# how the audio is measured.
FRAME_SECONDS = 0.03  # loudness is measured in 30 ms slices
SPEECH_LEVEL = 0.01  # a slice louder than this (about -40 dBFS) counts as sound
CLIPPED_LEVEL = 0.99  # a sample this close to full scale was cut off (too loud)
FFMPEG = os.getenv("FFMPEG_BINARY", "ffmpeg")

# The formats browsers record in, by file extension, mapped to the ffmpeg
# demuxer that reads each. Anything else is refused. Naming the demuxer
# stops ffmpeg guessing the format from the contents, so an upload can't
# pass itself off as a playlist (HLS, concat) that makes ffmpeg open other
# files or URLs.
FORMATS = {
    ".webm": "webm",
    ".ogg": "ogg",
    ".mp4": "mp4",
    ".m4a": "m4a",
    ".mp3": "mp3",
    ".wav": "wav",
}

# Takes 16 kHz mono samples and returns the embedding.
Encoder = Callable[[np.ndarray], list[float]]

logger = logging.getLogger("model-service")

# The loaded model, set once by load_encoder().
_model = None


def load_encoder() -> Encoder:
    global _model
    # Imported here so tests can run without PyTorch installed.
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    # Loaded on the CPU: ZeroGPU only allows the GPU inside a @spaces.GPU
    # function, and loading onto "cuda" would touch it at startup.
    _model = EncoderClassifier.from_hparams(
        source=MODEL_SOURCE,
        savedir=MODEL_DIR,
        run_opts={"device": "cpu"},
        # Copy rather than symlink the downloaded files: Windows only allows
        # symlinks for admins, and this keeps local runs working there.
        local_strategy=LocalStrategy.COPY,
    )
    _model.eval()
    return encode


def _embed(samples: np.ndarray, device: str) -> list[float]:
    import torch

    if _model.device != device:
        _model.mods.to(device)
        _model.device = device
    with torch.no_grad():
        embedding = _model.encode_batch(torch.from_numpy(samples).unsqueeze(0))
    return embedding.squeeze().cpu().tolist()


def _embed_on_gpu(samples: np.ndarray) -> list[float]:
    return _embed(samples, "cuda")


if spaces is not None:
    # ZeroGPU attaches a GPU only while a function marked like this runs,
    # and refuses to start a Space that has none. One call takes well under
    # a second; the limit is generous so a slow start isn't cut off.
    _embed_on_gpu = spaces.GPU(duration=20)(_embed_on_gpu)


def encode(samples: np.ndarray) -> list[float]:
    """Return the embedding, on ZeroGPU's GPU when there is one."""
    if spaces is not None:
        try:
            return _embed_on_gpu(samples)
        except Exception:
            # Out of GPU quota, or no GPU free right now. The model is small
            # enough that the CPU still answers in about half a second.
            logger.warning("GPU unavailable, embedding on the CPU instead.", exc_info=True)
    return _embed(samples, "cpu")


def decode_audio(audio: bytes, demuxer: str) -> np.ndarray:
    """Decode a recording to 16 kHz mono float samples. `demuxer` must be
    one of FORMATS' values. Raises ValueError if it isn't readable audio."""
    if demuxer not in FORMATS.values():
        raise ValueError("Unsupported format.")
    # A temporary file rather than a pipe, because some formats (m4a, mp4)
    # keep their index at the end of the file, which ffmpeg can't read
    # from a pipe. Its name is made here, never taken from the upload.
    handle, path = tempfile.mkstemp(suffix=".audio")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(audio)
        # A list of arguments with no shell, so nothing in them is run as a
        # command. Every argument is a constant, the server-made temp path,
        # or a demuxer name checked against FORMATS above.
        command = [
            FFMPEG, "-nostdin", "-loglevel", "error",
            "-protocol_whitelist", "file",  # never open URLs
            "-f", demuxer, "-i", path,
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
        ]
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit, python.lang.security.audit.dangerous-subprocess-use-tainted-env-args
        result = subprocess.run(command, capture_output=True, timeout=30)
    finally:
        os.remove(path)
    if result.returncode != 0:
        raise ValueError("Not readable audio.")
    samples = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        raise ValueError("Too short.")
    return samples


def measure_quality(samples: np.ndarray) -> tuple[float, float]:
    """Return (speech_seconds, clipped_share) for 16 kHz mono samples."""
    frame = int(FRAME_SECONDS * SAMPLE_RATE)
    frames = samples[: len(samples) // frame * frame].reshape(-1, frame)
    loud = np.sqrt(np.mean(frames**2, axis=1)) >= SPEECH_LEVEL
    clipped = np.mean(np.abs(samples) >= CLIPPED_LEVEL) if len(samples) else 0.0
    return float(np.sum(loud) * FRAME_SECONDS), float(clipped)


def embed_recording(token: str, audio_base64: str, extension: str, encode: Encoder) -> dict[str, Any]:
    """Handle one request. Returns the embedding and quality measures, or
    {"error": ...} naming what was wrong. Errors are answers rather than
    exceptions so the backend can tell a bad recording from an outage."""
    expected = os.getenv("SERVICE_TOKEN", "")
    if not expected:
        # Refuse to run open to the world.
        return {"error": "service_token_not_set"}
    if not secrets.compare_digest(token.encode(), expected.encode()):
        return {"error": "unauthorized"}
    demuxer = FORMATS.get(extension.lower())
    if demuxer is None:
        return {"error": "unsupported_format"}
    # Checked before decoding, so a huge request isn't decoded at all, and
    # after, because base64 rounds up to whole groups of 3 bytes.
    if len(audio_base64) > MAX_BASE64_CHARS:
        return {"error": "too_large"}
    try:
        audio = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return {"error": "not_audio"}
    if len(audio) > MAX_AUDIO_BYTES:
        return {"error": "too_large"}
    try:
        samples = decode_audio(audio, demuxer)
    except (ValueError, subprocess.TimeoutExpired):
        return {"error": "not_audio"}
    speech_seconds, clipped_share = measure_quality(samples)
    return {
        "embedding": encode(samples),
        "model": MODEL_SOURCE,
        # Seconds of the recording loud enough to be voice rather than silence.
        "speech_seconds": speech_seconds,
        # Share of samples cut off at full volume, 0 to 1. High means distorted.
        "clipped_share": clipped_share,
    }


def build_demo(encode: Encoder):
    """The Gradio app: one API endpoint, `embed`, called by the backend
    over Gradio's HTTP API (POST /gradio_api/call/embed)."""
    import gradio as gr

    def embed(token: str, audio_base64: str, extension: str) -> dict:
        return embed_recording(token, audio_base64, extension, encode)

    with gr.Blocks(title="VoiceGuard model service") as demo:
        gr.Markdown("VoiceGuard model service. API only, for the VoiceGuard backend.")
        gr.api(embed, api_name="embed", concurrency_limit=2)
    return demo


if __name__ == "__main__":
    # The model loads before launch, so ZeroGPU sees the @spaces.GPU
    # function when it checks at startup.
    demo = build_demo(load_encoder())
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")), show_error=False)
