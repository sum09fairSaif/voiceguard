import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pymongo.collection import Collection

import config
from challenges import use_challenge
from content_check import check_content
from db import get_challenges_collection, get_rate_limits_collection, get_voiceprints_collection
from decision import decide
from embedding import Embedder, get_embedder
from identity_check import IdentityResult, IdentityUnavailable, check_identity
from rate_limit import count_request
from schemas import ContentScore, VerifyResponse
from security import get_current_user_id
from voiceprints import load_voiceprint
from transcription import AudioNotUnderstood, Transcriber, TranscriptionUnavailable, get_transcriber

router = APIRouter(prefix="/api", tags=["verify"])

logger = logging.getLogger("voiceguard.verify")

# Reading six words is a few seconds of compressed audio, around 100 KB.
# 1 MB is plenty, and uploads that size stay in memory instead of being
# written to a temporary file.
MAX_AUDIO_BYTES = 1024 * 1024

# What browsers record in, mapped to the file extension Whisper and the
# model service use to recognise the format. The uploaded filename is never trusted or used.
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
    voiceprints: Collection = Depends(get_voiceprints_collection),
    transcribe: Transcriber = Depends(get_transcriber),
    embed: Embedder | None = Depends(get_embedder),
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

    # None if the user hasn't enrolled. Checked before the passage is used
    # up, so a misconfigured server doesn't cost the user their passage.
    voiceprint = load_voiceprint(voiceprints, user_id)
    if voiceprint is not None and embed is None:
        raise IdentityUnavailable("EMBEDDING_SERVICE_URL or EMBEDDING_SERVICE_TOKEN is not set.")

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
    identity = None
    if voiceprint is not None:
        try:
            identity = check_identity(voiceprint, embed(recording, f"attempt.{extension}"))
        except ValueError as exc:
            # Sizes differ: the service is running a different model.
            raise IdentityUnavailable("The embedding doesn't match the voiceprint's model.") from exc
        # The score stays on the server (see VerifyResponse); log it so the
        # threshold can be tuned from real attempts.
        logger.info(
            "identity user=%s attempt=%s score=%.3f passed=%s", user_id, attempt_id, identity.score, identity.passed
        )
    result = decide(content, identity)
    return VerifyResponse(
        decision=result.decision,
        reason=result.reason,
        content=ContentScore(
            passed=content.passed,
            score=content.score,
            matched=content.matched,
            total=content.total,
        ),
        identity=_identity_status(identity),
    )


def _identity_status(identity: IdentityResult | None) -> str:
    if identity is None:
        return "not_enrolled"
    return "passed" if identity.passed else "failed"


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
