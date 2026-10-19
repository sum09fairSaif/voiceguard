"""VoiceGuard model service: turns a recording into a speaker embedding.

Runs separately from the backend (as a free Hugging Face Space, started
with `python app.py`) because the voice model needs PyTorch, which is too
big for the backend's host. The
backend sends a recording and gets back a list of numbers describing the
voice. Recordings are never stored: each one lives in a temporary file only
while it is decoded, then is deleted.
"""

import os
import secrets
import subprocess
import tempfile
from contextlib import asynccontextmanager
from typing import Callable

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = os.getenv("MODEL_DIR", "pretrained_models/spkrec-ecapa-voxceleb")
SAMPLE_RATE = 16000  # what the model was trained on
MAX_AUDIO_BYTES = 1024 * 1024  # same cap as the backend
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


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model: str
    # Seconds of the recording loud enough to be voice rather than silence.
    speech_seconds: float
    # Share of samples cut off at full volume, 0 to 1. High means distorted.
    clipped_share: float


def load_encoder() -> Encoder:
    # Imported here so tests can run without PyTorch installed.
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    model = EncoderClassifier.from_hparams(
        source=MODEL_SOURCE,
        savedir=MODEL_DIR,
        run_opts={"device": "cpu"},
        # Copy rather than symlink the downloaded files: Windows only allows
        # symlinks for admins, and this keeps local runs working there.
        local_strategy=LocalStrategy.COPY,
    )
    model.eval()

    def encode(samples: np.ndarray) -> list[float]:
        with torch.no_grad():
            embedding = model.encode_batch(torch.from_numpy(samples).unsqueeze(0))
        return embedding.squeeze().tolist()

    return encode


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


def require_token(authorization: str = Header(default="")) -> None:
    expected = os.getenv("SERVICE_TOKEN", "")
    if not expected:
        # Refuse to run open to the world.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SERVICE_TOKEN is not set.")
    if not secrets.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong or missing service token.")


def create_app(load: Callable[[], Encoder] = load_encoder) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the model once at startup, not on every request.
        app.state.encode = load()
        yield

    app = FastAPI(title="VoiceGuard model service", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok", "model": MODEL_SOURCE}

    @app.post("/embed", response_model=EmbeddingResponse, dependencies=[Depends(require_token)])
    def embed(request: Request, audio: UploadFile = File(...)) -> EmbeddingResponse:
        data = audio.file.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Recording is too large.")
        # Only the extension is used, to pick the format.
        demuxer = FORMATS.get(os.path.splitext(audio.filename or "")[1].lower())
        if demuxer is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send webm, ogg, mp4, m4a, mp3 or wav audio.")
        try:
            samples = decode_audio(data, demuxer)
        except (ValueError, subprocess.TimeoutExpired):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't read the recording as audio.")
        speech_seconds, clipped_share = measure_quality(samples)
        return EmbeddingResponse(
            embedding=request.app.state.encode(samples),
            model=MODEL_SOURCE,
            speech_seconds=speech_seconds,
            clipped_share=clipped_share,
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Hugging Face Spaces serve whatever listens on port 7860.
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
