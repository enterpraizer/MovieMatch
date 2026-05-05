import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    avatar_url: str | None = None
    bio: str | None = None
    email_verified: bool = True
    created_at: str
    last_login_at: str | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class DeleteAccountRequest(BaseModel):
    password: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class VerifyEmailResponse(BaseModel):
    email: str
    already_verified: bool = False


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class GenreCount(BaseModel):
    slug: str
    name: str
    count: int


class UserStatsResponse(BaseModel):
    total_ratings: int
    avg_rating: float | None
    first_rated_at: str | None
    last_rated_at: str | None
    top_genres: list[GenreCount]
    score_distribution: dict[str, int]
