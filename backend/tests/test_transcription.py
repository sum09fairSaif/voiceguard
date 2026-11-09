from types import SimpleNamespace

import httpx
import openai
import pytest

import config
from transcription import AudioNotUnderstood, TranscriptionUnavailable, get_openai_client, transcribe


class FakeTranscriptions:
    # Stands in for OpenAI, so tests never send audio over the network.
    def __init__(self, text="quilt tiger ocean", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def fake_client(transcriptions):
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))


@pytest.fixture(autouse=True)
def fresh_client_cache():
    get_openai_client.cache_clear()
    yield
    get_openai_client.cache_clear()


def test_returns_what_was_said():
    transcriptions = FakeTranscriptions(text="Quilt, tiger, ocean.")

    assert transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm") == "Quilt, tiger, ocean."


def test_sends_the_audio_to_whisper_in_english():
    transcriptions = FakeTranscriptions()

    transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")

    [call] = transcriptions.calls
    assert call["model"] == config.WHISPER_MODEL
    assert call["file"] == ("attempt.webm", b"audio-bytes")
    assert call["language"] == "en"


def test_never_hints_the_expected_words():
    transcriptions = FakeTranscriptions()

    transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")

    [call] = transcriptions.calls
    assert "prompt" not in call
    assert "keywords" not in call


def test_model_comes_from_settings(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_MODEL", "some-newer-model")
    transcriptions = FakeTranscriptions()

    transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")

    assert transcriptions.calls[0]["model"] == "some-newer-model"


def test_unreadable_audio_is_not_reported_as_an_outage():
    # OpenAI answers 400 when the file isn't valid audio: that's the
    # recording's fault, not a service problem.
    rejected = openai.BadRequestError(
        "Invalid file format.",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")),
        body=None,
    )
    transcriptions = FakeTranscriptions(error=rejected)

    with pytest.raises(AudioNotUnderstood):
        transcribe(fake_client(transcriptions), b"not really audio", "attempt.webm")


def test_outage_is_reported_as_unavailable():
    transcriptions = FakeTranscriptions(error=openai.OpenAIError("connection reset"))

    with pytest.raises(TranscriptionUnavailable):
        transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")


@pytest.mark.parametrize(
    "error_type, status, code",
    [
        (openai.RateLimitError, 429, "insufficient_quota"),
        (openai.AuthenticationError, 401, "invalid_api_key"),
        (openai.NotFoundError, 404, "model_not_found"),
    ],
    ids=["no-credit", "bad-key", "wrong-model"],
)
def test_outage_says_what_openai_answered(error_type, status, code):
    # These all look the same to the user, but need very different fixes.
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"))
    error = error_type("private detail from OpenAI", response=response, body={"code": code})

    with pytest.raises(TranscriptionUnavailable) as caught:
        transcribe(fake_client(FakeTranscriptions(error=error)), b"audio-bytes", "attempt.webm")

    assert caught.value.details == f"{error_type.__name__} status={status} code={code}"
    assert "private detail" not in str(caught.value)


def test_unreadable_audio_says_what_openai_answered():
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"))
    error = openai.BadRequestError("private detail", response=response, body={"code": "invalid_value"})

    with pytest.raises(AudioNotUnderstood) as caught:
        transcribe(fake_client(FakeTranscriptions(error=error)), b"audio-bytes", "attempt.webm")

    assert caught.value.details == "BadRequestError status=400 code=invalid_value"


def test_missing_api_key_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    with pytest.raises(TranscriptionUnavailable):
        get_openai_client()


def test_client_is_built_from_the_api_key(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-real")

    client = get_openai_client()

    assert client.api_key == "sk-test-not-real"
    assert get_openai_client() is client
