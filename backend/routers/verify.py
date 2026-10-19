import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pymongo.collection import Collection

import config
from challenges import use_challenge
from content_check import check_content
from db import get_challenges_collection, get_rate_limits_collection
from decision import decide
from rate_limit import count_request
from schemas import ContentScore, VerifyResponse
from security import get_current_user_id
from transcription import AudioNotUnderstood, Transcriber, TranscriptionUnavailable, get_transcriber

router = APIRouter(prefix="/api", tags=["verify"])

logger = logging.getLogger("voiceguard.verify")

# Reading six words is a few seconds of compressed audio, around 100 KB.
# 1 MB is plenty, and uploads that size stay in memory instead of being
# written to a temporary file.
MAX_AUDIO_BYTES = 1024 * 1024

# What browsers record in, mapped to the file extension Whisper uses to
# recognise the format. The uploaded filename is never trusted or used.
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


@router.post("/verify", response_model=VerifyResponse)
def verify(
    audio: UploadFile = File(...),
    attempt_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
    challenges: Collection = Depends(get_challenges_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    transcribe: Transcriber = Depends(get_transcriber),
) -> VerifyResponse:
    # Checked before the passage is used up, so a refused request doesn't
    # cost the user their passage.
    count_request(rate_limits, "verify", user_id, config.VERIFY_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

    # Browsers send e.g. "audio/webm;codecs=opus", so drop the parameters.
    media_type = (audio.content_type or "").split(";")[0].strip().lower()
    extension = AUDIO_TYPES.get(media_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Please send the recording as audio (webm, ogg, mp4, mp3 or wav).",
        )

    recording = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(recording) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The recording is too long. Please read just the passage.",
        )
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The recording is empty. Please try again.",
        )

    # Use up the attempt before transcribing, so a passage can never be
    # checked twice, even if transcription fails part-way.
    passage = use_challenge(challenges, attempt_id, user_id)
    if passage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This passage has expired or was already used. Please get a new one.",
        )

    transcript = _transcribe_and_log(transcribe, recording, extension, user_id, attempt_id)
    content = check_content(passage, transcript)
    result = decide(content)
    return VerifyResponse(
        decision=result.decision,
        reason=result.reason,
        content=ContentScore(
            passed=content.passed,
            score=content.score,
            matched=content.matched,
            total=content.total,
        ),
    )


def _transcribe_and_log(
    transcribe: Transcriber, recording: bytes, extension: str, user_id: str, attempt_id: str
) -> str:
    """Transcribe the recording and log one line per paid speech-to-text
    call, so spend can be traced to a user. Never logs the audio, the
    passage or what was heard."""
    started = time.monotonic()
    outcome = "error"
    try:
        transcript = transcribe(recording, f"attempt.{extension}")
        outcome = "ok"
        return transcript
    except AudioNotUnderstood:
        outcome = "unreadable"
        raise
    except TranscriptionUnavailable:
        outcome = "unavailable"
        raise
    finally:
        logger.info(
            "transcription user=%s attempt=%s model=%s format=%s bytes=%d outcome=%s seconds=%.2f",
            user_id,
            attempt_id,
            config.WHISPER_MODEL,
            extension,
            len(recording),
            outcome,
            time.monotonic() - started,
        )
