"""add node attempt observability and deterministic risk findings

Revision ID: 014_node_attempts_risks
Revises: 013_manual_evidence_snapshots
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "014_node_attempts_risks"
down_revision = "013_manual_evidence_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "node_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("analysis_run_id", "node_id", "attempt_no", name="uq_node_attempt"),
    )
    op.create_table(
        "risk_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_items.id"), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("finding_kind", sa.String(32), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "claim_id", "evidence_id", "category", name="uq_risk_finding"),
    )


def downgrade() -> None:
    op.drop_table("risk_findings")
    op.drop_table("node_attempts")
