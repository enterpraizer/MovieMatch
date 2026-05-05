"""email verification flag + tokens table

Revision ID: 004
Revises: 003
Create Date: 2026-04-18
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE"
    )
    # Backfill: every user that predates this migration is considered verified.
    # New registrations still default to FALSE.
    op.execute("UPDATE users SET email_verified = TRUE WHERE email_verified = FALSE")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_verif_user ON email_verification_tokens(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_verification_tokens")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
