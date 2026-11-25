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


def fits_bcrypt(password: str) -> str:
    # bcrypt only reads the first 72 bytes of a password.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password is too long (72 bytes at most).")
    return password


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
        return fits_bcrypt(value)

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
    # False until the code we emailed is entered (#110). Until then the
    # account can't set up Voice ID or run voice checks. Accounts made
    # before verification existed, or while it's switched off, are true.
    email_verified: bool = True
    # The stand-in the browser's analytics identifies this person by (#170):
    # the same keyed hash the server's security events use (audit.hashed),
    # so the two can be linked without either showing the account id.
    analytics_id: str


class SignupResponse(BaseModel):
    user: UserPublic
    # The token is set as an HttpOnly cookie. It's also here only while
    # TOKEN_IN_RESPONSE_BODY is on (until the frontend uses the cookie).
    access_token: str | None = None
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    # No length or strength rules here: a wrong password, of any length,
    # gets the same "incorrect" answer.
    password: str = Field(min_length=1)


class LoginResponse(SignupResponse):
    """Same shape as signup: the account and a fresh token."""


class SignupAccepted(BaseModel):
    """Signup's answer while email confirmation is on (#111): the same
    whether or not the address already has an account."""

    detail: str


class EmailAddressRequest(BaseModel):
    """Asking for a new confirmation code (#111): by address, not sign-in."""

    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    # From the emailed link (43 characters today; some room for change).
    token: str = Field(min_length=20, max_length=200)
    # Same rules as signup. The checks that need the account's email
    # (password_policy) run in the endpoint, which knows whose link it is.
    password: str = Field(min_length=MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        return fits_bcrypt(value)


class EmailCodeRequest(BaseModel):
    """Confirming the address with the emailed code. Starts the session."""

    email: EmailStr
    # Six digits; spaces the user may type between them are dropped.
    code: str = Field(min_length=1, max_length=20)

    @field_validator("code")
    @classmethod
    def six_digits(cls, value: str) -> str:
        value = "".join(value.split())
        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValueError("The code is 6 digits.")
        return value


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
    # Says which check failed while VERIFY_CHECK_DETAILS is on; a general
    # message that names no check while it's off (#112).
    reason: str
    # content, identity and liveness are None while VERIFY_CHECK_DETAILS is
    # off (#112): telling an attacker which check failed helps them tune a
    # replay or voice clone. The server log still has them.
    content: ContentScore | None
    # Pass or fail only. The similarity score stays on the server: handing
    # it back would let someone tune a voice clone until it scores high.
    identity: Literal["passed", "failed", "not_enrolled"] | None
    # Pass or fail only, for the same reason. "not_checked" when the account
    # has no voiceprint: liveness runs in the same model-service call.
    liveness: Literal["passed", "failed", "not_checked"] | None
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


# The security events a user is shown of their own (audit.SHOWN_TO_USER).
ActivityKind = Literal[
    "signup",
    "email_verified",
    "login_succeeded",
    "login_failed",
    "login_locked",
    "logout",
    "enrolled",
    "voice_check_approved",
    "voice_check_rejected",
    "voice_check_incomplete",
    "voice_checks_paused",
]


class ActivityEvent(BaseModel):
    kind: ActivityKind
    at: datetime


class ActivityResponse(BaseModel):
    """A user's own security events, newest first: what happened and when,
    never why (a voice check's reason would say which check failed)."""

    events: list[ActivityEvent]


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
