"""add external test and build evidence snapshots

Revision ID: 009_external_test_build_evidence
Revises: 008_command_idempotency
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "009_external_test_build_evidence"
down_revision = "008_command_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("external_evidence", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False), sa.Column("evidence_type", sa.String(16), nullable=False), sa.Column("logical_name", sa.String(255), nullable=False), sa.Column("commit_sha", sa.String(64), nullable=False), sa.Column("content_hash", sa.String(80), nullable=False), sa.Column("artifact_uri", sa.Text(), nullable=False), sa.Column("exit_code", sa.Integer()), sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.CheckConstraint("evidence_type IN ('TEST', 'BUILD')", name="ck_external_evidence_type"))
    op.create_table("input_snapshot_external_evidence", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False), sa.Column("external_evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_evidence.id"), nullable=False), sa.Column("content_hash", sa.String(80), nullable=False), sa.Column("commit_sha", sa.String(64), nullable=False), sa.UniqueConstraint("snapshot_id", "external_evidence_id", name="uq_snapshot_external_evidence"))


def downgrade() -> None:
    op.drop_table("input_snapshot_external_evidence")
    op.drop_table("external_evidence")
