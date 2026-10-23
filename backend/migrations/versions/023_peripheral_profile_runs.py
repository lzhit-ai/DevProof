"""persist dedicated non-delivery profile runs

Revision ID: 023_peripheral_profile_runs
Revises: 022_agent_change_link_candidates
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "023_peripheral_profile_runs"
down_revision = "022_agent_change_link_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "peripheral_profile_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessment_profile", sa.String(48), nullable=False),
        sa.Column("run_status", sa.String(32), nullable=False, server_default="SUCCEEDED"),
        sa.Column("input_manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("limitations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "assessment_profile IN ('PROJECT_STATUS_SUMMARY', 'SECURITY_BASELINE', 'QUALITY_TREND')",
            name="ck_peripheral_profile_run_profile",
        ),
        sa.CheckConstraint("run_status IN ('SUCCEEDED')", name="ck_peripheral_profile_run_status"),
    )
    op.create_index("ix_peripheral_profile_runs_project_created", "peripheral_profile_runs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_peripheral_profile_runs_project_created", table_name="peripheral_profile_runs")
    op.drop_table("peripheral_profile_runs")
