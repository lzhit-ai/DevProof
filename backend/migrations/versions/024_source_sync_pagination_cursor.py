"""persist source-sync pagination progress

Revision ID: 024_source_sync_pagination_cursor
Revises: 023_peripheral_profile_runs
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "024_source_sync_pagination_cursor"
down_revision = "023_peripheral_profile_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_sync_runs",
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_sync_runs",
        sa.Column(
            "continuation_cursor",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("source_sync_runs", "continuation_cursor")
    op.drop_column("source_sync_runs", "page_count")
