"""add policies and policy_evaluations tables

Revision ID: 5d6e7f8a9b0c
Revises: 4c5d6e7f8a9b
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "5d6e7f8a9b0c"
down_revision = "4c5d6e7f8a9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("active", sa.Boolean, default=True, nullable=False),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_policies_active", "policies", ["active"])

    op.create_table(
        "policy_evaluations",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("scan_id", sa.String, sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("policy_id", sa.String, sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("violations", JSONB, nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_policy_evaluations_scan_id", "policy_evaluations", ["scan_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_evaluations_scan_id", table_name="policy_evaluations")
    op.drop_table("policy_evaluations")
    op.drop_index("ix_policies_active", table_name="policies")
    op.drop_table("policies")
