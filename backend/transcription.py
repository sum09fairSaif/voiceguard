from functools import lru_cache, partial
from typing import Callable

import openai

import config

# Takes the recording and a filename (whose extension tells Whisper the
# format) and returns what was said.
Transcriber = Callable[[bytes, str], str]


class TranscriptionUnavailable(Exception):
    """Speech-to-text isn't set up or can't be reached right now."""


class AudioNotUnderstood(Exception):
    """Speech-to-text received the recording but couldn't read it as audio."""


@lru_cache
def get_openai_client() -> openai.OpenAI:
    if not config.OPENAI_API_KEY:
        raise TranscriptionUnavailable("OPENAI_API_KEY is not set.")
    # Fail fast rather than leave the user staring at "checking..." for minutes.
    return openai.OpenAI(api_key=config.OPENAI_API_KEY, timeout=20, max_retries=1)


def transcribe(client: openai.OpenAI, audio: bytes, filename: str) -> str:
    """Return what was said in the recording. The audio is sent as-is and
    never saved."""
    try:
        # Don't pass the passage as a `prompt` or `keywords` hint: that would
        # nudge the transcript towards the expected words and let a wrong
        # recording pass the content check.
        result = client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=(filename, audio),
            language="en",
        )
    except openai.BadRequestError as exc:
        # The service is fine; the file itself is broken or not really audio.
        raise AudioNotUnderstood("Speech-to-text couldn't read the recording.") from exc
    except openai.OpenAIError as exc:
        raise TranscriptionUnavailable("Speech-to-text request failed.") from exc
    return result.text


def get_transcriber() -> Transcriber:
    # Raises before the request does anything else if the key is missing, so
    # a misconfigured server doesn't use up the user's passage.
    return partial(transcribe, get_openai_client())
