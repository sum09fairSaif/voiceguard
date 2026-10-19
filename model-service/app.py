"""VoiceGuard model service: turns a recording into a speaker embedding.

Runs separately from the backend (as a Hugging Face Space) because the
voice model needs PyTorch, which is too big for the backend's host. The
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
FFMPEG = os.getenv("FFMPEG_BINARY", "ffmpeg")

# Takes 16 kHz mono samples and returns the embedding.
Encoder = Callable[[np.ndarray], list[float]]


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model: str


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


def decode_audio(audio: bytes, suffix: str) -> np.ndarray:
    """Decode any common audio format to 16 kHz mono float samples.
    Raises ValueError if it isn't readable audio."""
    # A temporary file rather than a pipe, because some formats (m4a, mp4)
    # keep their index at the end of the file, which ffmpeg can't read
    # from a pipe.
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(audio)
        result = subprocess.run(
            [FFMPEG, "-nostdin", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
            capture_output=True,
            timeout=30,
        )
    finally:
        os.remove(path)
    if result.returncode != 0:
        raise ValueError("Not readable audio.")
    samples = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        raise ValueError("Too short.")
    return samples


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
        # Only the extension is used, as a hint for the format.
        suffix = os.path.splitext(audio.filename or "")[1][:8]
        try:
            samples = decode_audio(data, suffix)
        except (ValueError, subprocess.TimeoutExpired):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't read the recording as audio.")
        return EmbeddingResponse(embedding=request.app.state.encode(samples), model=MODEL_SOURCE)

    return app


app = create_app()
