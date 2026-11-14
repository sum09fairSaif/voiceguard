import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pymongo.collection import Collection

import config
from audio_upload import read_recording
from challenges import use_challenge
from content_check import check_content
from db import get_challenges_collection, get_rate_limits_collection, get_voiceprints_collection
from decision import decide
from embedding import Embedder, get_embedder
from identity_check import IdentityResult, IdentityUnavailable, check_identity
from liveness_check import LivenessResult, check_liveness
from rate_limit import count_request
from schemas import ContentScore, VerifyResponse
from security import get_current_user_id
from transcription import Transcriber, get_transcriber, transcribe_and_log
from voiceprints import load_voiceprint

router = APIRouter(prefix="/api", tags=["verify"])

logger = logging.getLogger("voiceguard.verify")


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

    recording, extension = read_recording(audio)

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

    transcript = transcribe_and_log(transcribe, recording, f"attempt.{extension}", user_id, attempt_id, logger)
    content = check_content(passage, transcript)
    identity = liveness = None
    if voiceprint is not None:
        # One model-service call gives both the voice embedding and the
        # liveness score.
        embedding = embed(recording, f"attempt.{extension}")
        if embedding.liveness_model is None:
            raise IdentityUnavailable("The model service is too old to check liveness.")
        try:
            identity = check_identity(voiceprint, embedding.vector)
        except ValueError as exc:
            # Sizes differ: the service is running a different model.
            raise IdentityUnavailable("The embedding doesn't match the voiceprint's model.") from exc
        liveness = check_liveness(embedding.liveness)
        # The scores stay on the server (see VerifyResponse); log them so
        # the thresholds can be tuned from real attempts.
        logger.info(
            "identity user=%s attempt=%s score=%.3f passed=%s", user_id, attempt_id, identity.score, identity.passed
        )
        logger.info(
            "liveness user=%s attempt=%s model=%s score=%s passed=%s",
            user_id,
            attempt_id,
            embedding.liveness_model,
            "-" if liveness.score is None else f"{liveness.score:.3f}",
            liveness.passed,
        )
    result = decide(content, identity, liveness)
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
        liveness=_liveness_status(liveness),
    )


def _identity_status(identity: IdentityResult | None) -> str:
    if identity is None:
        return "not_enrolled"
    return "passed" if identity.passed else "failed"


def _liveness_status(liveness: LivenessResult | None) -> str:
    if liveness is None:
        return "not_checked"
    return "passed" if liveness.passed else "failed"

