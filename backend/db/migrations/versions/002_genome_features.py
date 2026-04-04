"""add genome features

Revision ID: 002
Revises: 001
Create Date: 2026-04-17
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE movies ADD COLUMN genome_scores REAL[]")
    op.execute("CREATE INDEX idx_movies_has_genome ON movies ((genome_scores IS NOT NULL))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_movies_has_genome")
    op.execute("ALTER TABLE movies DROP COLUMN IF EXISTS genome_scores")
