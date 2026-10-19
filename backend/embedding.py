import base64
import json
import os
from dataclasses import dataclass
from functools import partial
from typing import Callable

import httpx

import config
from identity_check import IdentityUnavailable
from transcription import AudioNotUnderstood


@dataclass(frozen=True)
class Embedding:
    # The numbers describing the voice.
    vector: list[float]
    # How the recording sounded, for turning away poor enrollment samples.
    # None if the model service is too old to report them.
    speech_seconds: float | None
    clipped_share: float | None


# Takes the recording and a filename (whose extension tells the model
# service the format) and returns the voice embedding.
Embedder = Callable[[bytes, str], Embedding]


def embed(url: str, token: str, audio: bytes, filename: str) -> Embedding:
    """Ask the model service for the speaker embedding of this recording.
    The audio is sent as-is and never saved, here or by the service.

    The service is a Gradio app (Hugging Face's free GPU hardware only runs
    Gradio apps), so this uses Gradio's HTTP API: one request starts the
    job and returns an id, a second one waits for the result."""
    call_url = f"{url.rstrip('/')}/gradio_api/call/embed"
    # The recording travels as base64 text so Gradio never saves it as an
    # uploaded file. Only the extension of the filename is sent.
    data = [token, base64.b64encode(audio).decode("ascii"), os.path.splitext(filename)[1]]
    # Optional: lets the Space count GPU time against our Hugging Face
    # account rather than as anonymous use, which gets very little.
    headers = {}
    if config.EMBEDDING_SERVICE_HF_TOKEN:
        headers["Authorization"] = f"Bearer {config.EMBEDDING_SERVICE_HF_TOKEN}"
    try:
        # A sleeping free-tier service can take a while to wake up.
        with httpx.Client(headers=headers, timeout=60) as client:
            started = client.post(call_url, json={"data": data})
            started.raise_for_status()
            finished = client.get(f"{call_url}/{started.json()['event_id']}")
            finished.raise_for_status()
    except httpx.HTTPError as exc:
        raise IdentityUnavailable("The model service can't be reached.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise IdentityUnavailable("The model service sent an unexpected answer.") from exc

    body = _result(finished.text)
    error = body.get("error")
    if error in ("not_audio", "unsupported_format", "too_large"):
        # The service is fine; the file itself is broken or not really audio.
        raise AudioNotUnderstood("The model service couldn't read the recording.")
    if error is not None:
        # e.g. "unauthorized": the tokens don't match. A server problem.
        raise IdentityUnavailable(f"The model service refused the request: {error}.")
    embedding = body.get("embedding")
    if not isinstance(embedding, list) or not all(_is_number(x) for x in embedding):
        raise IdentityUnavailable("The model service sent an unexpected answer.")
    return Embedding(
        vector=embedding,
        speech_seconds=_optional_number(body, "speech_seconds"),
        clipped_share=_optional_number(body, "clipped_share"),
    )


def _result(stream: str) -> dict:
    """Read the endpoint's answer from Gradio's event stream, which ends
    with "event: complete" and a "data:" line holding a one-item list."""
    event = data = None
    for line in stream.splitlines():
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = line[len("data:"):].strip()
    if event != "complete" or data is None:
        raise IdentityUnavailable(f"The model service failed (event {event!r}).")
    try:
        [body] = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise IdentityUnavailable("The model service sent an unexpected answer.") from exc
    if not isinstance(body, dict):
        raise IdentityUnavailable("The model service sent an unexpected answer.")
    return body


def _is_number(value: object) -> bool:
    # bool counts as an int in Python, but true/false isn't a measurement.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _optional_number(body: dict, key: str) -> float | None:
    value = body.get(key)
    if value is None:
        return None
    if not _is_number(value):
        raise IdentityUnavailable("The model service sent an unexpected answer.")
    return float(value)


def get_embedder() -> Embedder | None:
    # None when the model service isn't configured. That's only a problem
    # for users who have a voiceprint to compare against.
    if not config.EMBEDDING_SERVICE_URL or not config.EMBEDDING_SERVICE_TOKEN:
        return None
    return partial(embed, config.EMBEDDING_SERVICE_URL, config.EMBEDDING_SERVICE_TOKEN)
