import httpx
import pytest

import config
import embedding
from embedding import embed, get_embedder
from identity_check import IdentityUnavailable
from transcription import AudioNotUnderstood

URL = "https://model-service.example/"
TOKEN = "service-token"
RECORDING = b"pretend this is a few seconds of speech"


class FakeService:
    # Stands in for httpx.post: answers with the given response and
    # remembers what it was sent.
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def service(monkeypatch):
    fake = FakeService(httpx.Response(200, json={"embedding": [0.1, -0.2, 0.3]}))
    monkeypatch.setattr(embedding.httpx, "post", fake)
    return fake


def test_returns_the_embedding(service):
    result = embed(URL, TOKEN, RECORDING, "attempt.webm")

    assert result.vector == [0.1, -0.2, 0.3]
    # An older model service doesn't measure quality; that's not an error.
    assert result.speech_seconds is None
    assert result.clipped_share is None


def test_returns_the_quality_measures(service):
    service.response = httpx.Response(
        200, json={"embedding": [0.1, -0.2, 0.3], "speech_seconds": 2.4, "clipped_share": 0}
    )

    result = embed(URL, TOKEN, RECORDING, "attempt.webm")

    assert result.speech_seconds == 2.4
    assert result.clipped_share == 0.0


def test_sends_the_recording_with_the_service_token(service):
    embed(URL, TOKEN, RECORDING, "attempt.webm")

    [(url, kwargs)] = service.calls
    assert url == "https://model-service.example/embed"
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs["files"] == {"audio": ("attempt.webm", RECORDING)}


def test_unreadable_audio_is_not_reported_as_an_outage(service):
    service.response = httpx.Response(422, json={"detail": "not audio"})

    with pytest.raises(AudioNotUnderstood):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize("status_code", [401, 500, 503])
def test_service_errors_are_reported_as_unavailable(service, status_code):
    service.response = httpx.Response(status_code)

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


def test_unreachable_service_is_reported_as_unavailable(service):
    service.error = httpx.ConnectTimeout("timed out")

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize(
    "body",
    [
        {"wrong": [0.1]},
        {"embedding": "0.1"},
        {"embedding": [0.1, "x"]},
        ["not", "a", "dict"],
        {"embedding": [0.1], "speech_seconds": "long"},
        {"embedding": [0.1], "clipped_share": True},
    ],
    ids=["missing", "not-a-list", "not-numbers", "not-an-object", "bad-speech-seconds", "bad-clipped-share"],
)
def test_unexpected_answer_is_reported_as_unavailable(service, body):
    service.response = httpx.Response(200, json=body)

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


def test_no_embedder_when_the_service_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_URL", "")
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_TOKEN", TOKEN)
    assert get_embedder() is None

    monkeypatch.setattr(config, "EMBEDDING_SERVICE_URL", URL)
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_TOKEN", "")
    assert get_embedder() is None


def test_embedder_uses_the_configured_service(service, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_URL", URL)
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_TOKEN", TOKEN)

    assert get_embedder()(RECORDING, "attempt.ogg").vector == [0.1, -0.2, 0.3]
    assert service.calls[0][1]["files"]["audio"][0] == "attempt.ogg"
