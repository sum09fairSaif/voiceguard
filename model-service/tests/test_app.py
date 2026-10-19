import os
import subprocess
import tempfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app as service
from app import FFMPEG, MAX_AUDIO_BYTES, SAMPLE_RATE, create_app

TOKEN = "test-service-token"


def make_audio(seconds=1.0, fmt="wav", codec="pcm_s16le"):
    """A tone made by ffmpeg, so the tests need no audio files."""
    result = subprocess.run(
        [FFMPEG, "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
         "-ar", "48000", "-c:a", codec, "-f", fmt, "-"],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


class FakeEncoder:
    # Stands in for the model: remembers the samples it was given.
    def __init__(self):
        self.calls = []

    def __call__(self, samples):
        self.calls.append(samples)
        return [0.1, -0.2, 0.3]


@pytest.fixture
def encoder():
    return FakeEncoder()


@pytest.fixture
def client(encoder, monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", TOKEN)
    with TestClient(create_app(load=lambda: encoder)) as test_client:
        yield test_client


def send(client, audio, filename="attempt.wav", token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post("/embed", headers=headers, files={"audio": (filename, audio)})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "model": "speechbrain/spkrec-ecapa-voxceleb"}


def test_recording_becomes_an_embedding(client, encoder):
    response = send(client, make_audio(seconds=1.0))

    assert response.status_code == 200
    assert response.json() == {"embedding": [0.1, -0.2, 0.3], "model": "speechbrain/spkrec-ecapa-voxceleb"}
    # Decoded to one second of 16 kHz mono before reaching the model.
    [samples] = encoder.calls
    assert samples.dtype == np.float32
    assert abs(len(samples) - SAMPLE_RATE) < 200


# Browsers record webm or ogg (Opus) or mp4 (AAC); m4a has its index at the
# end, which is why the service decodes from a file rather than a pipe.
@pytest.mark.parametrize(
    "fmt, codec, filename",
    [("webm", "libopus", "attempt.webm"), ("ogg", "libopus", "attempt.ogg"), ("ipod", "aac", "attempt.m4a")],
    ids=["webm", "ogg", "m4a"],
)
def test_browser_formats_are_decoded(client, encoder, fmt, codec, filename):
    if fmt == "ipod":
        # mp4 can't be written to a pipe either, so make it via a file.
        handle, path = tempfile.mkstemp(suffix=".m4a")
        os.close(handle)
        try:
            subprocess.run(
                [FFMPEG, "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1",
                 "-c:a", codec, path],
                check=True,
            )
            with open(path, "rb") as file:
                audio = file.read()
        finally:
            os.remove(path)
    else:
        audio = make_audio(fmt=fmt, codec=codec)

    assert send(client, audio, filename).status_code == 200
    assert abs(len(encoder.calls[0]) - SAMPLE_RATE) < 1000


def test_recording_is_not_kept(client, monkeypatch):
    made = []
    real_mkstemp = tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        handle, path = real_mkstemp(*args, **kwargs)
        made.append(path)
        return handle, path

    monkeypatch.setattr(service.tempfile, "mkstemp", recording_mkstemp)
    send(client, make_audio())
    send(client, b"not audio at all")

    assert len(made) == 2
    assert not any(os.path.exists(path) for path in made)


def test_not_audio_is_refused(client, encoder):
    response = send(client, b"definitely not audio", "attempt.webm")

    assert response.status_code == 422
    assert encoder.calls == []


def test_too_short_is_refused(client, encoder):
    assert send(client, make_audio(seconds=0.2)).status_code == 422
    assert encoder.calls == []


def test_too_large_is_refused(client, encoder):
    assert send(client, b"\0" * (MAX_AUDIO_BYTES + 1)).status_code == 413
    assert encoder.calls == []


@pytest.mark.parametrize("token", [None, "wrong-token", ""], ids=["missing", "wrong", "empty"])
def test_wrong_token_is_refused(client, encoder, token):
    assert send(client, make_audio(), token=token).status_code == 401
    assert encoder.calls == []


def test_service_without_a_token_refuses_everything(client, encoder, monkeypatch):
    monkeypatch.delenv("SERVICE_TOKEN")

    assert send(client, make_audio()).status_code == 503
    assert encoder.calls == []
