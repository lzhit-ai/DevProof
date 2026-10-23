"""persist retrieval-index rebuild observability

Revision ID: 026_retrieval_index_build_runs
Revises: 025_project_retrieval_indexes
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "026_retrieval_index_build_runs"
down_revision = "025_project_retrieval_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retrieval_index_build_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_index_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reindexed_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reindexed_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.String(length=500)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_retrieval_index_build_run_status"),
    )
    op.create_index("ix_retrieval_index_build_runs_project_started", "retrieval_index_build_runs", ["project_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_index_build_runs_project_started", table_name="retrieval_index_build_runs")
    op.drop_table("retrieval_index_build_runs")
