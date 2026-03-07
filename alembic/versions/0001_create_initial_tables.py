"""create initial tables

Revision ID: 0001_create_initial_tables
Revises: None
Create Date: 2026-02-23 16:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_create_initial_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("genres", sa.String(length=500), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_movies_title", "movies", ["title"], unique=False)

    op.create_table(
        "user_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "movie_id", name="uq_user_movie_rating"),
    )
    op.create_index("ix_user_ratings_user_id", "user_ratings", ["user_id"], unique=False)
    op.create_index("ix_user_ratings_movie_id", "user_ratings", ["movie_id"], unique=False)

    op.create_table(
        "recommendation_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_recommendation_requests_user_id", "recommendation_requests", ["user_id"], unique=False)
    op.create_index("ix_recommendation_requests_mode", "recommendation_requests", ["mode"], unique=False)

    op.create_table(
        "recommendation_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Integer(),
            sa.ForeignKey("recommendation_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movie_id", sa.Integer(), sa.ForeignKey("movies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("request_id", "rank", name="uq_request_rank"),
    )
    op.create_index("ix_recommendation_results_request_id", "recommendation_results", ["request_id"], unique=False)
    op.create_index("ix_recommendation_results_movie_id", "recommendation_results", ["movie_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recommendation_results_movie_id", table_name="recommendation_results")
    op.drop_index("ix_recommendation_results_request_id", table_name="recommendation_results")
    op.drop_table("recommendation_results")

    op.drop_index("ix_recommendation_requests_mode", table_name="recommendation_requests")
    op.drop_index("ix_recommendation_requests_user_id", table_name="recommendation_requests")
    op.drop_table("recommendation_requests")

    op.drop_index("ix_user_ratings_movie_id", table_name="user_ratings")
    op.drop_index("ix_user_ratings_user_id", table_name="user_ratings")
    op.drop_table("user_ratings")

    op.drop_index("ix_movies_title", table_name="movies")
    op.drop_table("movies")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

