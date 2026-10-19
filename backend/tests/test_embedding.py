import base64
import json

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
CALL_URL = "https://model-service.example/gradio_api/call/embed"


def finished(body, event="complete"):
    """What Gradio streams back once the job is done."""
    return httpx.Response(200, text=f"event: {event}\ndata: {json.dumps([body])}\n\n")


class FakeService:
    # Stands in for the Gradio app: answers the "start" POST with an event
    # id and the "result" GET with `result`, remembering every request.
    def __init__(self):
        self.result = finished({"embedding": [0.1, -0.2, 0.3], "speech_seconds": 2.4, "clipped_share": 0})
        self.start = httpx.Response(200, json={"event_id": "abc123"})
        self.error = None
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        if request.method == "POST" and str(request.url) == CALL_URL:
            return self.start
        if request.method == "GET" and str(request.url) == f"{CALL_URL}/abc123":
            return self.result
        return httpx.Response(404)


@pytest.fixture
def service(monkeypatch):
    fake = FakeService()
    real_client = httpx.Client
    monkeypatch.setattr(
        embedding.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs)
    )
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_HF_TOKEN", "")
    return fake


def test_returns_the_embedding_and_quality_measures(service):
    result = embed(URL, TOKEN, RECORDING, "attempt.webm")

    assert result.vector == [0.1, -0.2, 0.3]
    assert result.speech_seconds == 2.4
    assert result.clipped_share == 0.0


def test_older_service_without_quality_measures_is_fine(service):
    service.result = finished({"embedding": [0.1, -0.2, 0.3]})

    result = embed(URL, TOKEN, RECORDING, "attempt.webm")

    assert result.speech_seconds is None
    assert result.clipped_share is None


def test_sends_the_token_recording_and_extension(service):
    embed(URL, TOKEN, RECORDING, "attempt.webm")

    start = service.requests[0]
    sent = json.loads(start.content)["data"]
    assert sent == [TOKEN, base64.b64encode(RECORDING).decode(), ".webm"]
    # No Hugging Face token configured: no Authorization header.
    assert "authorization" not in start.headers


def test_hugging_face_token_is_sent_when_configured(service, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_SERVICE_HF_TOKEN", "hf_example")

    embed(URL, TOKEN, RECORDING, "attempt.webm")

    assert all(r.headers["authorization"] == "Bearer hf_example" for r in service.requests)


@pytest.mark.parametrize("error", ["not_audio", "unsupported_format", "too_large"])
def test_unreadable_audio_is_not_reported_as_an_outage(service, error):
    service.result = finished({"error": error})

    with pytest.raises(AudioNotUnderstood):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize("error", ["unauthorized", "service_token_not_set", "something_new"])
def test_refusals_are_reported_as_unavailable(service, error):
    service.result = finished({"error": error})

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


def test_failed_job_is_reported_as_unavailable(service):
    service.result = httpx.Response(200, text='event: error\ndata: {"error": null}\n\n')

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize("status_code", [401, 404, 500, 503])
def test_http_errors_are_reported_as_unavailable(service, status_code):
    service.start = httpx.Response(status_code)

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


def test_unreachable_service_is_reported_as_unavailable(service):
    service.error = httpx.ConnectTimeout("timed out")

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize(
    "start",
    [httpx.Response(200, text="not json"), httpx.Response(200, json={"no": "event id"})],
    ids=["not-json", "no-event-id"],
)
def test_unexpected_start_answer_is_reported_as_unavailable(service, start):
    service.start = start

    with pytest.raises(IdentityUnavailable):
        embed(URL, TOKEN, RECORDING, "attempt.webm")


@pytest.mark.parametrize(
    "result",
    [
        finished({"wrong": [0.1]}),
        finished({"embedding": "0.1"}),
        finished({"embedding": [0.1, "x"]}),
        finished(["not", "a", "dict"]),
        finished({"embedding": [0.1], "speech_seconds": "long"}),
        finished({"embedding": [0.1], "clipped_share": True}),
        httpx.Response(200, text="event: complete\ndata: not json\n\n"),
        httpx.Response(200, text="event: complete\ndata: [1, 2]\n\n"),
        httpx.Response(200, text=""),
    ],
    ids=[
        "missing",
        "not-a-list",
        "not-numbers",
        "not-an-object",
        "bad-speech-seconds",
        "bad-clipped-share",
        "data-not-json",
        "two-items",
        "empty-stream",
    ],
)
def test_unexpected_answer_is_reported_as_unavailable(service, result):
    service.result = result

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
    assert json.loads(service.requests[0].content)["data"][2] == ".ogg"
