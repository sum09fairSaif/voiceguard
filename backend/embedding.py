from functools import partial
from typing import Callable

import httpx

import config
from identity_check import IdentityUnavailable
from transcription import AudioNotUnderstood

# Takes the recording and a filename (whose extension tells the model
# service the format) and returns the voice embedding.
Embedder = Callable[[bytes, str], list[float]]


def embed(url: str, token: str, audio: bytes, filename: str) -> list[float]:
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
        embedding = response.json()["embedding"]
    except (ValueError, KeyError, TypeError) as exc:
        raise IdentityUnavailable("The model service sent an unexpected answer.") from exc
    if not isinstance(embedding, list) or not all(isinstance(x, (int, float)) for x in embedding):
        raise IdentityUnavailable("The model service sent an unexpected answer.")
    return embedding


def get_embedder() -> Embedder | None:
    # None when the model service isn't configured. That's only a problem
    # for users who have a voiceprint to compare against.
    if not config.EMBEDDING_SERVICE_URL or not config.EMBEDDING_SERVICE_TOKEN:
        return None
    return partial(embed, config.EMBEDDING_SERVICE_URL, config.EMBEDDING_SERVICE_TOKEN)
