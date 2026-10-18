from functools import lru_cache

import openai

import config

MODEL = "whisper-1"


class TranscriptionUnavailable(Exception):
    """Speech-to-text isn't set up or can't be reached right now."""


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
            model=MODEL,
            file=(filename, audio),
            language="en",
        )
    except openai.OpenAIError as exc:
        raise TranscriptionUnavailable("Speech-to-text request failed.") from exc
    return result.text
