"""add retry availability to durable jobs

Revision ID: 010_durable_job_heartbeat
Revises: 009_external_test_build_evidence
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa


revision = "010_durable_job_heartbeat"
down_revision = "009_external_test_build_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")))
    op.create_index("ix_analysis_jobs_available", "analysis_jobs", ["job_status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_available", table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "available_at")
