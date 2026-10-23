"""separate temporary Agent tool results from formal evidence

Revision ID: 021_agent_tool_execution_evidence_boundary
Revises: 020_security_baseline
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "021_agent_tool_execution_evidence_boundary"
down_revision = "020_security_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_key", sa.String(96), nullable=False),
        sa.Column("tool_key", sa.String(96), nullable=False),
        sa.Column("tool_type", sa.String(32), nullable=False, server_default="HTTP_QUERY"),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("excerpt_safe", sa.Text(), nullable=False),
        sa.Column("locator", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="SUCCEEDED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("analysis_run_id", "capability_key", "tool_key", name="uq_agent_tool_execution_run_tool"),
        sa.CheckConstraint("tool_type = 'HTTP_QUERY'", name="ck_agent_tool_execution_type"),
        sa.CheckConstraint("status IN ('SUCCEEDED')", name="ck_agent_tool_execution_status"),
    )
    op.add_column("manual_evidence", sa.Column("origin_type", sa.String(32), nullable=False, server_default="MANUAL"))
    op.add_column("manual_evidence", sa.Column("origin_locator", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("manual_evidence", sa.Column("source_tool_execution_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_manual_evidence_tool_execution",
        "manual_evidence",
        "agent_tool_executions",
        ["source_tool_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_manual_evidence_tool_execution", "manual_evidence", ["source_tool_execution_id"])


def downgrade() -> None:
    op.drop_constraint("uq_manual_evidence_tool_execution", "manual_evidence", type_="unique")
    op.drop_constraint("fk_manual_evidence_tool_execution", "manual_evidence", type_="foreignkey")
    op.drop_column("manual_evidence", "source_tool_execution_id")
    op.drop_column("manual_evidence", "origin_locator")
    op.drop_column("manual_evidence", "origin_type")
    op.drop_table("agent_tool_executions")
