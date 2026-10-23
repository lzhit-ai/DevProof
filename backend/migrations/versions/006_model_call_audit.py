"""add model call audit records

Revision ID: 006_model_call_audit
Revises: 005_reports_and_approval
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_model_call_audit"
down_revision = "005_reports_and_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("allowed_evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_model_calls_run_id", "model_calls", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_model_calls_run_id", table_name="model_calls")
    op.drop_table("model_calls")
