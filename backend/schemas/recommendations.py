from pydantic import BaseModel, Field, field_validator


class RatingInput(BaseModel):
    movie_id: int = Field(..., gt=0)
    score: float = Field(..., ge=0.5, le=5.0)

    @field_validator("score")
    @classmethod
    def validate_step(cls, v: float) -> float:
        if (v * 2) % 1 != 0:
            raise ValueError("Score must be in 0.5 steps (e.g. 0.5, 1.0, 1.5 ...)")
        return v


class RecommendFilters(BaseModel):
    year_from: int | None = None
    year_to: int | None = None
    genres: list[str] | None = None
    min_rating: float | None = None


class CollaborativeRequest(BaseModel):
    ratings: list[RatingInput] = Field(default_factory=list, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    exclude_seen: bool = True
    filters: RecommendFilters | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=200)
    filters: RecommendFilters | None = None


class MovieRecommendation(BaseModel):
    movie_id: int
    title: str
    year: int | None = None
    genres: list[str] = []
    avg_rating: float | None = None
    poster_url: str | None = None
    score: float | None = None
    reason: str


class RecommendResponse(BaseModel):
    items: list[MovieRecommendation]
    model_version: str
    latency_ms: int
    request_id: str
    cached: bool = False
    emotion: str | None = None
    emotion_confidence: float | None = None
    emotion_message: str | None = None
