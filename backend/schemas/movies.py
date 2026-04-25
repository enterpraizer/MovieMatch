from pydantic import BaseModel


class GenreResponse(BaseModel):
    id: int
    name: str
    slug: str


class PersonResponse(BaseModel):
    id: int
    name: str
    profile_path: str | None = None


class CreditResponse(BaseModel):
    person: PersonResponse
    role: str
    character_name: str | None = None
    order_index: int | None = None


class MovieResponse(BaseModel):
    id: int
    title: str
    year: int | None = None
    avg_rating: float | None = None
    rating_count: int = 0
    genres: list[str] = []
    poster_url: str | None = None


class MovieDetailResponse(MovieResponse):
    description: str | None = None
    runtime_minutes: int | None = None
    credits: list[CreditResponse] = []
    imdb_id: str | None = None


class MovieListResponse(BaseModel):
    items: list[MovieResponse]
    next_cursor: int | None = None
    total: int | None = None
