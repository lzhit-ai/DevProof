"""create report approval and immutable publication tables

Revision ID: 005_reports_and_approval
Revises: 004_allow_terminal_reruns
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_reports_and_approval"
down_revision = "004_allow_terminal_reruns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("report_versions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence_no", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("parent_report_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_versions.id")), sa.Column("content_hash", sa.String(80), nullable=False), sa.Column("snapshot_hash", sa.String(80), nullable=False), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False), sa.Column("submitted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")), sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("cycle_id", "sequence_no", name="uq_report_cycle_sequence"))
    op.create_table("report_items", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("report_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_results.id"), nullable=False), sa.Column("display_order", sa.Integer(), nullable=False), sa.Column("result_snapshot", postgresql.JSONB(), nullable=False), sa.Column("citation_snapshot", postgresql.JSONB(), nullable=False), sa.Column("disposition", sa.Text()), sa.UniqueConstraint("report_version_id", "display_order", name="uq_report_item_order"))
    op.create_table("approval_actions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("report_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("action", sa.String(32), nullable=False), sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("report_hash", sa.String(80), nullable=False), sa.Column("snapshot_hash", sa.String(80), nullable=False), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_table("published_records", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_tasks.id"), nullable=False), sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id"), nullable=False), sa.Column("report_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_versions.id"), nullable=False), sa.Column("record_no", sa.String(64), nullable=False, unique=True), sa.Column("record_hash", sa.String(80), nullable=False, unique=True), sa.Column("published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("report_version_id", name="uq_published_report"))


def downgrade() -> None:
    for table in ("published_records", "approval_actions", "report_items", "report_versions"):
        op.drop_table(table)
