from fastapi import APIRouter, Depends, status
from pymongo.collection import Collection

from challenges import create_challenge
from db import get_challenges_collection
from schemas import ChallengeResponse
from security import get_current_user_id

router = APIRouter(prefix="/api", tags=["challenge"])


@router.post("/challenge", response_model=ChallengeResponse, status_code=status.HTTP_201_CREATED)
def new_challenge(
    user_id: str = Depends(get_current_user_id),
    challenges: Collection = Depends(get_challenges_collection),
) -> ChallengeResponse:
    challenge = create_challenge(challenges, user_id)
    return ChallengeResponse(
        attempt_id=str(challenge["_id"]),
        passage=challenge["passage"],
        expires_at=challenge["expires_at"],
    )
