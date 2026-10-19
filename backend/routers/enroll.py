import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pymongo.collection import Collection

import config
from audio_upload import read_recording
from db import get_enrollments_collection, get_rate_limits_collection, get_voiceprints_collection
from embedding import Embedder, Embedding, get_embedder
from enrollment import (
    INCONSISTENT,
    TOO_LOUD,
    TOO_SHORT,
    accepted_samples,
    add_sample,
    count_samples,
    discard_samples,
    sample_problem,
    take_samples,
)
from identity_check import IdentityUnavailable
from passages import generate_passage
from rate_limit import count_request
from schemas import EnrollmentStatus
from security import get_current_user_id
from transcription import AudioNotUnderstood
from voiceprints import build_voiceprint, has_voiceprint, save_voiceprint

router = APIRouter(prefix="/api/enroll", tags=["enroll"])

logger = logging.getLogger("voiceguard.enroll")

# What the user is told when a sample is turned away. Each says how to fix it.
RETRY_MESSAGES = {
    TOO_SHORT: "That recording was too short or too quiet. Please read the whole sentence clearly, "
    "close to your microphone.",
    TOO_LOUD: "That recording was too loud and sounds distorted. Please move a little further "
    "from your microphone and try again.",
    INCONSISTENT: "That recording doesn't sound like your earlier ones. Please record it again in the same "
    "quiet place. If this keeps happening, start over.",
}
UNREADABLE_MESSAGE = "We couldn't read that recording. Please record it again."


@router.get("", response_model=EnrollmentStatus)
def enrollment_status(
    user_id: str = Depends(get_current_user_id),
    voiceprints: Collection = Depends(get_voiceprints_collection),
    enrollments: Collection = Depends(get_enrollments_collection),
) -> EnrollmentStatus:
    return _status(voiceprints, enrollments, user_id)


@router.post("/samples", response_model=EnrollmentStatus)
def add_enrollment_sample(
    audio: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    voiceprints: Collection = Depends(get_voiceprints_collection),
    enrollments: Collection = Depends(get_enrollments_collection),
    embed: Embedder | None = Depends(get_embedder),
) -> EnrollmentStatus:
    count_request(rate_limits, "enroll", user_id, config.ENROLL_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

    # Replacing a voiceprint needs more than a password: otherwise anyone
    # who learned the password could swap in their own voice and pass the
    # voice check from then on.
    if has_voiceprint(voiceprints, user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your voice is already enrolled.")

    recording, extension = read_recording(audio)
    # Checked before the model-service call, so a misconfigured server
    # fails straight away instead of after the user has recorded.
    if embed is None:
        raise IdentityUnavailable("EMBEDDING_SERVICE_URL or EMBEDDING_SERVICE_TOKEN is not set.")
    if not config.VOICEPRINT_KEY:
        raise IdentityUnavailable("VOICEPRINT_KEY is not set.")

    earlier = accepted_samples(enrollments, user_id)
    try:
        sample = embed(recording, f"sample.{extension}")
    except AudioNotUnderstood:
        _log(user_id, "unreadable", None, None)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=UNREADABLE_MESSAGE)
    # The recording isn't needed past this point and is never stored.
    del recording

    if sample.speech_seconds is None or sample.clipped_share is None:
        raise IdentityUnavailable("The model service is too old to measure recording quality.")
    if earlier and len(earlier[0]) != len(sample.vector):
        raise IdentityUnavailable("The embedding doesn't match the earlier samples' model.")

    problem, similarity = sample_problem(sample, earlier)
    _log(user_id, problem or "accepted", sample, similarity)
    if problem is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=RETRY_MESSAGES[problem])

    if add_sample(enrollments, user_id, sample.vector) >= config.ENROLL_SAMPLES_REQUIRED:
        samples = take_samples(enrollments, user_id)
        # None if a request arriving at the same moment already finished.
        if samples is not None:
            save_voiceprint(voiceprints, user_id, build_voiceprint(samples))
            logger.info("enrolled user=%s samples=%d", user_id, len(samples))
    return _status(voiceprints, enrollments, user_id)


@router.delete("/samples", response_model=EnrollmentStatus)
def start_over(
    user_id: str = Depends(get_current_user_id),
    voiceprints: Collection = Depends(get_voiceprints_collection),
    enrollments: Collection = Depends(get_enrollments_collection),
) -> EnrollmentStatus:
    """Throw away the samples given so far. Leaves a finished voiceprint alone."""
    discard_samples(enrollments, user_id)
    return _status(voiceprints, enrollments, user_id)


def _status(voiceprints: Collection, enrollments: Collection, user_id: str) -> EnrollmentStatus:
    required = config.ENROLL_SAMPLES_REQUIRED
    if has_voiceprint(voiceprints, user_id):
        return EnrollmentStatus(status="enrolled", samples_accepted=required, samples_required=required, prompt=None)
    accepted = count_samples(enrollments, user_id)
    return EnrollmentStatus(
        status="in_progress" if accepted else "not_started",
        samples_accepted=accepted,
        samples_required=required,
        prompt=generate_passage(),
    )


def _log(user_id: str, outcome: str, sample: Embedding | None, similarity: float | None) -> None:
    # One line per sample, to tune the limits from real recordings. Never
    # the audio or the voice numbers.
    logger.info(
        "enroll_sample user=%s outcome=%s speech_seconds=%s clipped_share=%s similarity=%s",
        user_id,
        outcome,
        "-" if sample is None else f"{sample.speech_seconds:.2f}",
        "-" if sample is None else f"{sample.clipped_share:.4f}",
        "-" if similarity is None else f"{similarity:.3f}",
    )
