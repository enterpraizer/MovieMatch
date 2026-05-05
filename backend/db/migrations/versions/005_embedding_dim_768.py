"""widen movies.embedding from vector(384) to vector(768)

Motivation: switching NLP retrieval model to `intfloat/multilingual-e5-base`
(768 dim) for stronger semantic matching, especially cross-lingual queries.

Upgrade path:
  1. Drop the HNSW index (tied to the old dimensionality).
  2. NULL every row's embedding — pgvector can't cast across dim sizes.
  3. ALTER the column type to vector(768).
  4. The HNSW index is NOT recreated here — it's rebuilt post-reindex by the
     sibling script `scripts/sql/recreate_embedding_index.sql`, so that the
     HNSW build happens over a fully-populated column instead of NULLs.

Revision ID: 005
Revises: 004
Create Date: 2026-04-18
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_movies_embedding")
    op.execute("UPDATE movies SET embedding = NULL, embedding_updated_at = NULL")
    op.execute("ALTER TABLE movies ALTER COLUMN embedding TYPE vector(768)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_movies_embedding")
    op.execute("UPDATE movies SET embedding = NULL, embedding_updated_at = NULL")
    op.execute("ALTER TABLE movies ALTER COLUMN embedding TYPE vector(384)")
    op.execute(
        "CREATE INDEX idx_movies_embedding ON movies "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
    )
