"""profile extensions: avatar, bio, last_login, watchlist

Revision ID: 003
Revises: 002
Create Date: 2026-04-18
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS avatar_url TEXT,
            ADD COLUMN IF NOT EXISTS bio VARCHAR(500),
            ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            movie_id BIGINT NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
            added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, movie_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_added_at ON watchlist(added_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS watchlist")
    op.execute(
        """
        ALTER TABLE users
            DROP COLUMN IF EXISTS last_login_at,
            DROP COLUMN IF EXISTS bio,
            DROP COLUMN IF EXISTS avatar_url
        """
    )
