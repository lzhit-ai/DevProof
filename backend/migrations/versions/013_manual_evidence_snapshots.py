"""add immutable manual evidence to formal input snapshots

Revision ID: 013_manual_evidence_snapshots
Revises: 012_qa_model_calls
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "013_manual_evidence_snapshots"
down_revision = "012_qa_model_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("logical_name", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "input_snapshot_manual_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manual_evidence.id"), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.UniqueConstraint("snapshot_id", "manual_evidence_id", name="uq_snapshot_manual_evidence"),
    )


def downgrade() -> None:
    op.drop_table("input_snapshot_manual_evidence")
    op.drop_table("manual_evidence")
