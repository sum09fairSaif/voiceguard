import base64
import os
import subprocess
import tempfile

import numpy as np
import pytest

import app as service
from app import FFMPEG, MAX_AUDIO_BYTES, SAMPLE_RATE, embed_recording

TOKEN = "test-service-token"


def make_audio(seconds=1.0, fmt="wav", codec="pcm_s16le", source=None):
    """A tone made by ffmpeg, so the tests need no audio files."""
    source = source or f"sine=frequency=220:duration={seconds}"
    result = subprocess.run(
        [FFMPEG, "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", source,
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
    # The request handler behind the Gradio `embed` endpoint, with a stand-in
    # model. Gradio itself only passes the three strings through.
    monkeypatch.setenv("SERVICE_TOKEN", TOKEN)
    return lambda token, audio_base64, extension: embed_recording(token, audio_base64, extension, encoder)


def send(client, audio, filename="attempt.wav", token=TOKEN):
    return client(token, base64.b64encode(audio).decode(), os.path.splitext(filename)[1])


def error(body):
    return body.get("error")


def test_recording_becomes_an_embedding(client, encoder):
    body = send(client, make_audio(seconds=1.0))

    assert error(body) is None
    assert body["embedding"] == [0.1, -0.2, 0.3]
    assert body["model"] == "speechbrain/spkrec-ecapa-voxceleb"
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

    assert error(send(client, audio, filename)) is None
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
    assert error(send(client, b"definitely not audio", "attempt.webm")) == "not_audio"
    assert encoder.calls == []


def test_too_short_is_refused(client, encoder):
    assert error(send(client, make_audio(seconds=0.2))) == "not_audio"
    assert encoder.calls == []


def test_too_large_is_refused(client, encoder):
    assert error(send(client, b"\0" * (MAX_AUDIO_BYTES + 1))) == "too_large"
    assert encoder.calls == []


@pytest.mark.parametrize("token", ["wrong-token", "", TOKEN + "x"], ids=["wrong", "empty", "longer"])
def test_wrong_token_is_refused(client, encoder, token):
    assert error(send(client, make_audio(), token=token)) == "unauthorized"
    assert encoder.calls == []


def test_service_without_a_token_refuses_everything(client, encoder, monkeypatch):
    monkeypatch.delenv("SERVICE_TOKEN")

    assert error(send(client, make_audio())) == "service_token_not_set"
    assert encoder.calls == []


@pytest.mark.parametrize("filename", ["attempt.m3u8", "attempt.txt", "attempt", "attempt.webm.exe"])
def test_other_formats_are_refused(client, encoder, filename):
    assert error(send(client, make_audio(), filename)) == "unsupported_format"
    assert encoder.calls == []


def test_playlist_disguised_as_audio_is_not_followed(client, encoder, tmp_path):
    # An HLS playlist pointing at real audio. If ffmpeg guessed the format
    # from the contents, it would open the other file and succeed.
    real = tmp_path / "real.wav"
    real.write_bytes(make_audio())
    playlist = f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1.0,\n{real.as_posix()}\n#EXT-X-ENDLIST\n".encode()

    for filename in ("attempt.webm", "attempt.wav", "attempt.mp3"):
        assert error(send(client, playlist, filename)) == "not_audio"
    assert encoder.calls == []


def test_mp3_is_decoded(client, encoder):
    assert error(send(client, make_audio(fmt="mp3", codec="libmp3lame"), "attempt.mp3")) is None


def test_text_that_is_not_base64_is_refused(client, encoder):
    assert error(client(TOKEN, "this is not base64!", ".wav")) == "not_audio"
    assert encoder.calls == []


# --- Recording quality, for enrollment ----------------------------------------


def test_a_clear_recording_is_all_speech_and_not_clipped(client):
    body = send(client, make_audio(seconds=1.0))

    assert body["speech_seconds"] == pytest.approx(1.0, abs=0.05)
    assert body["clipped_share"] == 0.0


def test_silence_has_no_speech(client):
    silence = make_audio(source="sine=frequency=220:duration=1,volume=0")

    assert send(client, silence)["speech_seconds"] == 0.0


def test_half_silence_counts_only_the_sound(client):
    half = make_audio(source="sine=frequency=220:duration=1,apad=pad_dur=1")

    assert send(client, half)["speech_seconds"] == pytest.approx(1.0, abs=0.05)


def test_a_too_loud_recording_is_clipped(client):
    loud = make_audio(source="sine=frequency=220:duration=1,volume=20")

    assert send(client, loud)["clipped_share"] > 0.5


# --- ZeroGPU ------------------------------------------------------------------


def test_without_zerogpu_the_model_runs_on_the_cpu(monkeypatch):
    monkeypatch.setattr(service, "spaces", None)
    monkeypatch.setattr(service, "_embed", lambda samples, device: [device])

    assert service.encode(np.zeros(16000, dtype=np.float32)) == ["cpu"]


def test_on_zerogpu_the_model_runs_on_the_gpu(monkeypatch):
    monkeypatch.setattr(service, "spaces", object())
    monkeypatch.setattr(service, "_embed_on_gpu", lambda samples: ["cuda"])

    assert service.encode(np.zeros(16000, dtype=np.float32)) == ["cuda"]


def test_falls_back_to_the_cpu_when_no_gpu_is_free(monkeypatch):
    def no_gpu(samples):
        raise RuntimeError("ZeroGPU quota exceeded")

    monkeypatch.setattr(service, "spaces", object())
    monkeypatch.setattr(service, "_embed_on_gpu", no_gpu)
    monkeypatch.setattr(service, "_embed", lambda samples, device: [device])

    assert service.encode(np.zeros(16000, dtype=np.float32)) == ["cpu"]
