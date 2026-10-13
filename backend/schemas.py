from datetime import datetime

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


class ChallengeResponse(BaseModel):
    attempt_id: str
    passage: str
    expires_at: datetime
