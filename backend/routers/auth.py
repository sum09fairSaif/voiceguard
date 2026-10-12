from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from db import get_users_collection
from schemas import SignupRequest, SignupResponse, UserPublic
from security import create_access_token, hash_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    users: Collection = Depends(get_users_collection),
) -> SignupResponse:
    user_id = ObjectId()
    # Make the token before saving, so a config problem never leaves
    # behind an account the user can't sign up for again.
    token = create_access_token(str(user_id))

    user = {
        "_id": user_id,
        "full_name": body.full_name,
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    return SignupResponse(
        user=UserPublic(
            id=str(user_id),
            full_name=user["full_name"],
            email=user["email"],
            created_at=user["created_at"],
        ),
        access_token=token,
    )
