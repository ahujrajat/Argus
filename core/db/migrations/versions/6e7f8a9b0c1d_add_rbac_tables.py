"""add orgs, workspaces, org_members tables for RBAC

Revision ID: 6e7f8a9b0c1d
Revises: 5d6e7f8a9b0c
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "6e7f8a9b0c1d"
down_revision = "5d6e7f8a9b0c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orgs_slug", "orgs", ["slug"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspaces_org_id", "workspaces", ["org_id"])

    op.create_table(
        "org_members",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_org_members_org_id", "org_members", ["org_id"])
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_org_members_user_id", table_name="org_members")
    op.drop_index("ix_org_members_org_id", table_name="org_members")
    op.drop_table("org_members")
    op.drop_index("ix_workspaces_org_id", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index("ix_orgs_slug", table_name="orgs")
    op.drop_table("orgs")
