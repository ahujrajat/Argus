"""add suppression_rules and scheduled_scans tables

Revision ID: 4c5d6e7f8a9b
Revises: 3b4c5d6e7f8a
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "4c5d6e7f8a9b"
down_revision = "3b4c5d6e7f8a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suppression_rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("pattern_type", sa.String, nullable=False),
        sa.Column("pattern", sa.String, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suppression_rules_pattern_type", "suppression_rules", ["pattern_type"])

    op.create_table(
        "scheduled_scans",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("cron_expr", sa.String, nullable=False),
        sa.Column("pipeline_config_name", sa.String, nullable=False),
        sa.Column("target_ref", sa.String, nullable=False),
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_suppression_rules_pattern_type", table_name="suppression_rules")
    op.drop_table("suppression_rules")
    op.drop_table("scheduled_scans")
