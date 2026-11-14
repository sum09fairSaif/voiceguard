from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("full_name")
    @classmethod
    def full_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank.")
        return value

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt only reads the first 72 bytes of a password.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password is too long (72 bytes at most).")
        return value


class UserPublic(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    created_at: datetime


class SignupResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    # No length or strength rules here: a wrong password, of any length,
    # gets the same "incorrect" answer.
    password: str = Field(min_length=1)


class LoginResponse(SignupResponse):
    """Same shape as signup: the account and a fresh token."""


class ChallengeResponse(BaseModel):
    attempt_id: str
    passage: str
    expires_at: datetime


class ContentScore(BaseModel):
    passed: bool
    score: float
    matched: int
    total: int


class VerifyResponse(BaseModel):
    # "approved" only when all three checks pass; "incomplete" when the
    # account has no voiceprint, so only the words could be checked.
    decision: Literal["approved", "rejected", "incomplete"]
    reason: str
    content: ContentScore
    # Pass or fail only. The similarity score stays on the server: handing
    # it back would let someone tune a voice clone until it scores high.
    identity: Literal["passed", "failed", "not_enrolled"]
    # Pass or fail only, for the same reason. "not_checked" when the account
    # has no voiceprint: liveness runs in the same model-service call.
    liveness: Literal["passed", "failed", "not_checked"]


class EnrollmentStatus(BaseModel):
    status: Literal["not_started", "in_progress", "enrolled"]
    samples_accepted: int
    samples_required: int
    # The sentence to read aloud for the next sample. The sample must hold
    # every word of it, in order. None once enrolled.
    prompt: str | None
