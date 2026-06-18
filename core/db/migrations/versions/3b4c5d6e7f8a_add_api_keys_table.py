"""add api_keys table

Revision ID: 3b4c5d6e7f8a
Revises: 2a1b3c4d5e6f
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "3b4c5d6e7f8a"
down_revision = "2a1b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("key_hash", sa.String, nullable=False, unique=True),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean, default=False, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
