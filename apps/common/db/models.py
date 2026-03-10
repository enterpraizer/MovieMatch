from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from apps.common.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    ratings: Mapped[list[UserRating]] = relationship("UserRating", back_populates="user")
    recommendation_requests: Mapped[list[RecommendationRequest]] = relationship(
        "RecommendationRequest",
        back_populates="user",
    )


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genres: Mapped[str | None] = mapped_column(String(500), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    ratings: Mapped[list[UserRating]] = relationship("UserRating", back_populates="movie")
    recommendation_results: Mapped[list[RecommendationResult]] = relationship(
        "RecommendationResult",
        back_populates="movie",
    )


class UserRating(Base):
    __tablename__ = "user_ratings"
    __table_args__ = (UniqueConstraint("user_id", "movie_id", name="uq_user_movie_rating"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="ratings")
    movie: Mapped[Movie] = relationship("Movie", back_populates="ratings")


class RecommendationRequest(Base):
    __tablename__ = "recommendation_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User | None] = relationship("User", back_populates="recommendation_requests")
    results: Mapped[list[RecommendationResult]] = relationship(
        "RecommendationResult",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class RecommendationResult(Base):
    __tablename__ = "recommendation_results"
    __table_args__ = (UniqueConstraint("request_id", "rank", name="uq_request_rank"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    request: Mapped[RecommendationRequest] = relationship("RecommendationRequest", back_populates="results")
    movie: Mapped[Movie] = relationship("Movie", back_populates="recommendation_results")

