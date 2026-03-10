from __future__ import annotations

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from apps.common.db.models import Movie, RecommendationRequest, RecommendationResult, UserRating
from apps.common.schemas import MovieRecommendation, RecommendationMode, RecommendationRequest as RecommendationPayload


def _base_rating_query() -> Select[tuple[int, float]]:
    return (
        select(UserRating.movie_id, func.avg(UserRating.rating).label("avg_rating"))
        .group_by(UserRating.movie_id)
        .subquery()
    )


def _collaborative_recommendations(db: Session, payload: RecommendationPayload) -> list[MovieRecommendation]:
    ratings_sq = _base_rating_query()
    rated_movie_ids: set[int] = set()
    if payload.user_id is not None:
        rated_movie_ids = set(
            db.scalars(select(UserRating.movie_id).where(UserRating.user_id == payload.user_id)).all()
        )

    stmt = (
        select(Movie.id, Movie.title, ratings_sq.c.avg_rating)
        .join(ratings_sq, ratings_sq.c.movie_id == Movie.id)
        .where(~Movie.id.in_(rated_movie_ids) if rated_movie_ids else True)
        .order_by(ratings_sq.c.avg_rating.desc(), Movie.id.asc())
        .limit(payload.top_k)
    )
    rows = db.execute(stmt).all()
    if not rows:
        # Fallback for sparse/small samples: allow already-rated movies.
        rows = db.execute(
            select(Movie.id, Movie.title, ratings_sq.c.avg_rating)
            .join(ratings_sq, ratings_sq.c.movie_id == Movie.id)
            .order_by(ratings_sq.c.avg_rating.desc(), Movie.id.asc())
            .limit(payload.top_k)
        ).all()
    return [
        MovieRecommendation(
            movie_id=row.id,
            title=row.title,
            score=round(float(row.avg_rating), 3),
            reason="Collaborative score from user ratings",
        )
        for row in rows
    ]


def _nlp_recommendations(db: Session, payload: RecommendationPayload) -> list[MovieRecommendation]:
    ratings_sq = _base_rating_query()
    query = (payload.query or "").strip()

    if not query:
        return _collaborative_recommendations(db, payload)

    pattern = f"%{query.lower()}%"
    stmt = (
        select(
            Movie.id,
            Movie.title,
            ratings_sq.c.avg_rating,
            case(
                (func.lower(Movie.title).like(pattern), 1),
                (func.lower(func.coalesce(Movie.overview, "")).like(pattern), 1),
                else_=0,
            ).label("text_match"),
        )
        .join(ratings_sq, ratings_sq.c.movie_id == Movie.id, isouter=True)
        .where(
            func.lower(Movie.title).like(pattern) | func.lower(func.coalesce(Movie.overview, "")).like(pattern)
        )
        .order_by(
            func.coalesce(ratings_sq.c.avg_rating, 0).desc(),
            Movie.id.asc(),
        )
        .limit(payload.top_k)
    )
    rows = db.execute(stmt).all()
    if not rows:
        return _collaborative_recommendations(db, payload)
    return [
        MovieRecommendation(
            movie_id=row.id,
            title=row.title,
            score=round(float(row.avg_rating or 0), 3),
            reason=f"NLP text match for query '{query}'",
        )
        for row in rows
    ]


def _mood_recommendations(db: Session, payload: RecommendationPayload) -> list[MovieRecommendation]:
    ratings_sq = _base_rating_query()
    mood = (payload.query or "neutral").strip().lower()
    mood_to_genres = {
        "happy": ["Comedy", "Adventure", "Animation", "Family", "Romance"],
        "sad": ["Drama", "Romance"],
        "angry": ["Action", "Thriller", "Crime"],
        "fear": ["Horror", "Thriller", "Mystery"],
        "neutral": ["Drama", "Adventure", "Comedy"],
    }
    genres = mood_to_genres.get(mood, mood_to_genres["neutral"])

    conditions = [func.lower(func.coalesce(Movie.genres, "")).like(f"%{g.lower()}%") for g in genres]
    stmt = (
        select(Movie.id, Movie.title, ratings_sq.c.avg_rating)
        .join(ratings_sq, ratings_sq.c.movie_id == Movie.id, isouter=True)
        .where(or_(*conditions))
        .order_by(func.coalesce(ratings_sq.c.avg_rating, 0).desc(), Movie.id.asc())
        .limit(payload.top_k)
    )
    rows = db.execute(stmt).all()
    if not rows:
        return _collaborative_recommendations(db, payload)
    return [
        MovieRecommendation(
            movie_id=row.id,
            title=row.title,
            score=round(float(row.avg_rating or 0), 3),
            reason=f"Mood-to-genre match for '{mood}'",
        )
        for row in rows
    ]


def build_recommendations(db: Session, mode: RecommendationMode, payload: RecommendationPayload) -> list[MovieRecommendation]:
    if mode == RecommendationMode.collaborative:
        return _collaborative_recommendations(db, payload)
    if mode == RecommendationMode.nlp:
        return _nlp_recommendations(db, payload)
    if mode == RecommendationMode.mood:
        return _mood_recommendations(db, payload)
    return []


def persist_recommendation_result(
    db: Session,
    mode: RecommendationMode,
    payload: RecommendationPayload,
    recommendations: list[MovieRecommendation],
) -> None:
    request_row = RecommendationRequest(
        user_id=payload.user_id,
        mode=mode.value,
        payload=payload.model_dump(),
        status="completed",
    )
    db.add(request_row)
    db.flush()

    for idx, rec in enumerate(recommendations, start=1):
        db.add(
            RecommendationResult(
                request_id=request_row.id,
                movie_id=rec.movie_id,
                score=rec.score,
                rank=idx,
                explanation={"reason": rec.reason},
            )
        )
