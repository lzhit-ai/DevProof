"""Persist immutable run-scoped supplemental code context.

Revision ID: 037_run_context_artifacts
Revises: 036_knowledge_bases
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "037_run_context_artifacts"
down_revision = "036_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_run_context_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_objects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "round_no", name="uq_run_context_artifact_round"),
    )


def downgrade() -> None:
    op.drop_table("analysis_run_context_artifacts")
