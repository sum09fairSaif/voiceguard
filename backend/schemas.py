from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from password_policy import MIN_LENGTH, password_problem

# Why a password was refused, sent as the error's "type" so the screen can
# say it in its own words (NIST: say why).
PASSWORD_PROBLEMS = {
    "common": "This password is too common or has appeared in a data breach.",
    "personal": "This password is too close to your email or the app's name.",
    "repetitive": "This password repeats the same characters or words.",
    "sequential": "This password is a simple sequence, like letters or keys in order.",
}


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # NIST SP 800-63B-4: at least 15 when the password is one factor; no
    # rules about which kinds of character it must contain.
    password: str = Field(min_length=MIN_LENGTH)

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

    @field_validator("password")
    @classmethod
    def password_not_known_bad(cls, value: str, info: ValidationInfo) -> str:
        # The email is checked before the password, so it's here if valid.
        problem = password_problem(value, str(info.data.get("email") or ""))
        if problem:
            raise PydanticCustomError(f"password_{problem}", PASSWORD_PROBLEMS[problem])
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
    # Rejected checks the user has left before voice checks lock. Back to
    # the maximum after an approval; not lowered by an "incomplete".
    attempts_left: int
    # True when this rejection used up the last attempt: voice checks are
    # now locked, and the user should be offered the email code (#20).
    fallback_required: bool
    # Only when approved: a short-lived voice-verified token, the only kind
    # that opens the account (GET /api/me). None otherwise.
    access_token: str | None = None


class MeResponse(BaseModel):
    """The account summary, for a voice-verified session only."""

    full_name: str
    email: EmailStr
    created_at: datetime
    # When the voiceprint was recorded; None if the account hasn't enrolled.
    enrolled_at: datetime | None
    # The voice-verified sign-in before this one, so the user can spot one
    # that wasn't them; None on the first.
    previous_sign_in_at: datetime | None


class EnrollmentStatus(BaseModel):
    status: Literal["not_started", "in_progress", "enrolled"]
    samples_accepted: int
    samples_required: int
    # The sentence to read aloud for the next sample. The sample must hold
    # every word of it, in order. None once enrolled, or when this session
    # may not enroll (can_enroll is false).
    prompt: str | None
    # Whether this session may add samples: only the signup session, or
    # during the one-off grace period (see enrollment_window.py).
    can_enroll: bool
