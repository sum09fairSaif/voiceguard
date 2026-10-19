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
    The audio is sent as-is and never saved, here or by the service."""
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/embed",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": (filename, audio)},
            # A sleeping free-tier service can take a while to wake up.
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise IdentityUnavailable("The model service can't be reached.") from exc
    if response.status_code == 422:
        # The service is fine; the file itself is broken or not really audio.
        raise AudioNotUnderstood("The model service couldn't read the recording.")
    if response.status_code != 200:
        raise IdentityUnavailable(f"The model service answered {response.status_code}.")
    try:
        body = response.json()
        embedding = body["embedding"]
    except (ValueError, KeyError, TypeError) as exc:
        raise IdentityUnavailable("The model service sent an unexpected answer.") from exc
    if not isinstance(embedding, list) or not all(_is_number(x) for x in embedding):
        raise IdentityUnavailable("The model service sent an unexpected answer.")
    return Embedding(
        vector=embedding,
        speech_seconds=_optional_number(body, "speech_seconds"),
        clipped_share=_optional_number(body, "clipped_share"),
    )


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
