from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision: str = "2a1b3c4d5e6f"
down_revision: str | None = "1c040f64f366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_configs",
        sa.Column("is_factory", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("pipeline_configs", "is_factory")
