from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.collection import Collection

from audit import recent_events
from db import get_users_collection, get_voiceprints_collection
from schemas import ActivityEvent, ActivityResponse, MeResponse
from security import get_verified_user_id

router = APIRouter(prefix="/api", tags=["account"])


def _utc(moment: datetime | None) -> datetime | None:
    # MongoDB hands dates back without a time zone; they are UTC. Without
    # one, a browser would read them as local time and show the wrong hour.
    if moment is None or moment.tzinfo:
        return moment
    return moment.replace(tzinfo=UTC)


@router.get("/me", response_model=MeResponse)
def me(
    user_id: str = Depends(get_verified_user_id),
    users: Collection = Depends(get_users_collection),
    voiceprints: Collection = Depends(get_voiceprints_collection),
) -> MeResponse:
    """The account summary. Needs a voice-verified token (password and an
    approved voice check); a password alone gets 403."""
    user = users.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    if user is None:
        # The token is genuine but the account is gone.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    voiceprint = voiceprints.find_one({"_id": user_id}, {"created_at": 1})
    return MeResponse(
        full_name=user["full_name"],
        email=user["email"],
        created_at=_utc(user["created_at"]),
        enrolled_at=_utc(voiceprint["created_at"]) if voiceprint else None,
        previous_sign_in_at=_utc(user.get("previous_verified_at")),
    )


@router.get("/activity", response_model=ActivityResponse)
def activity(user_id: str = Depends(get_verified_user_id)) -> ActivityResponse:
    """The user's own security events from the last AUDIT_RETENTION_DAYS,
    newest first: what happened and when, never why. Needs a voice-verified
    token, like the account summary."""
    events = recent_events(user_id)
    return ActivityResponse(events=[ActivityEvent(kind=e["event"], at=_utc(e["at"])) for e in events])
