import logging
import time
from collections.abc import Callable
from functools import lru_cache, partial

import openai

import config

# Takes the recording and a filename (whose extension tells Whisper the
# format) and returns what was said.
Transcriber = Callable[[bytes, str], str]


class TranscriptionError(Exception):
    """`details` says what OpenAI answered, for the logs. It never holds the
    audio, the transcript or OpenAI's message text."""

    def __init__(self, message: str, details: str = "-"):
        super().__init__(message)
        self.details = details


class TranscriptionUnavailable(TranscriptionError):
    """Speech-to-text isn't set up or can't be reached right now."""


class AudioNotUnderstood(TranscriptionError):
    """Speech-to-text received the recording but couldn't read it as audio."""


@lru_cache
def get_openai_client() -> openai.OpenAI:
    if not config.OPENAI_API_KEY:
        raise TranscriptionUnavailable("OPENAI_API_KEY is not set.")
    # Fail fast rather than leave the user staring at "checking..." for minutes.
    return openai.OpenAI(api_key=config.OPENAI_API_KEY, timeout=20, max_retries=1)


def _describe(exc: openai.OpenAIError) -> str:
    # e.g. "RateLimitError status=429 code=insufficient_quota": enough to tell
    # no credit from a bad key, a wrong model or an outage.
    status = getattr(exc, "status_code", None) or "-"
    code = getattr(exc, "code", None) or "-"
    return f"{type(exc).__name__} status={status} code={code}"


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
        details = _describe(exc)
        raise AudioNotUnderstood("Speech-to-text couldn't read the recording.", details) from exc
    except openai.OpenAIError as exc:
        details = _describe(exc)
        raise TranscriptionUnavailable(f"Speech-to-text request failed: {details}.", details) from exc
    return result.text


def get_transcriber() -> Transcriber:
    # Raises before the request does anything else if the key is missing, so
    # a misconfigured server doesn't use up the user's passage.
    return partial(transcribe, get_openai_client())


def transcribe_and_log(
    transcribe: Transcriber,
    recording: bytes,
    filename: str,
    user_id: str,
    attempt_id: str,
    logger: logging.Logger,
) -> str:
    """Transcribe the recording and log one line per paid speech-to-text
    call, so spend can be traced to a user. Never logs the audio, the
    passage or what was heard."""
    started = time.monotonic()
    outcome = "error"
    error = "-"
    try:
        transcript = transcribe(recording, filename)
        outcome = "ok"
        return transcript
    except AudioNotUnderstood as exc:
        outcome = "unreadable"
        error = exc.details
        raise
    except TranscriptionUnavailable as exc:
        outcome = "unavailable"
        error = exc.details
        raise
    finally:
        logger.info(
            "transcription user=%s attempt=%s model=%s format=%s bytes=%d outcome=%s seconds=%.2f error=%s",
            user_id,
            attempt_id,
            config.WHISPER_MODEL,
            filename.rsplit(".", 1)[-1],
            len(recording),
            outcome,
            time.monotonic() - started,
            error,
        )
