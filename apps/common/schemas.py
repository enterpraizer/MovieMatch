from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RecommendationMode(str, Enum):
    collaborative = "collaborative"
    nlp = "nlp"
    mood = "mood"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    details: dict[str, str] | None = None


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPayload(BaseModel):
    sub: str
    email: str
    type: str


class RecommendationRequest(BaseModel):
    user_id: Optional[int] = None
    query: Optional[str] = None
    image_url: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=50)


class MovieRecommendation(BaseModel):
    movie_id: int
    title: str
    score: float
    reason: str


class RecommendationResponse(BaseModel):
    mode: RecommendationMode
    recommendations: list[MovieRecommendation]
    trace_id: str
