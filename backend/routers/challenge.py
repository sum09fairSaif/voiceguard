from fastapi import APIRouter, Depends, status
from pymongo.collection import Collection

import config
from challenges import create_challenge
from db import get_challenges_collection, get_rate_limits_collection, get_voice_failures_collection
from rate_limit import count_request
from schemas import ChallengeResponse
from security import get_current_user_id
from voice_attempts import ensure_not_locked

router = APIRouter(prefix="/api", tags=["challenge"])


@router.post("/challenge", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def new_challenge(
    user_id: str = Depends(get_current_user_id),
    challenges: Collection = Depends(get_challenges_collection),
    rate_limits: Collection = Depends(get_rate_limits_collection),
    voice_failures: Collection = Depends(get_voice_failures_collection),
) -> ChallengeResponse:
    # After too many failed voice checks, no new passages until the lockout ends.
    ensure_not_locked(voice_failures, user_id)
    count_request(
        rate_limits, "challenge", user_id, config.CHALLENGE_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS
    )
    challenge = create_challenge(challenges, user_id)
    return ChallengeResponse(
        attempt_id=str(challenge["_id"]),
        passage=challenge["passage"],
        expires_at=challenge["expires_at"],
    )
