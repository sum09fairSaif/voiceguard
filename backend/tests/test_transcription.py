from types import SimpleNamespace

import openai
import pytest

import config
from transcription import MODEL, TranscriptionUnavailable, get_openai_client, transcribe


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
    assert call["model"] == MODEL
    assert call["file"] == ("attempt.webm", b"audio-bytes")
    assert call["language"] == "en"


def test_never_hints_the_expected_words():
    transcriptions = FakeTranscriptions()

    transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")

    [call] = transcriptions.calls
    assert "prompt" not in call
    assert "keywords" not in call


def test_outage_is_reported_as_unavailable():
    transcriptions = FakeTranscriptions(error=openai.OpenAIError("connection reset"))

    with pytest.raises(TranscriptionUnavailable):
        transcribe(fake_client(transcriptions), b"audio-bytes", "attempt.webm")


def test_missing_api_key_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    with pytest.raises(TranscriptionUnavailable):
        get_openai_client()


def test_client_is_built_from_the_api_key(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-not-real")

    client = get_openai_client()

    assert client.api_key == "sk-test-not-real"
    assert get_openai_client() is client
