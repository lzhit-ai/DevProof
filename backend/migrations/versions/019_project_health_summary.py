"""add immutable project health snapshots and personal summary records

Revision ID: 019_project_health_summary
Revises: 018_delivery_change_links
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "019_project_health_summary"
down_revision = "018_delivery_change_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_health_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("snapshot_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "project_summary_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("health_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_health_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("draft_status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("period_type IN ('DAILY', 'WEEKLY', 'ITERATION')", name="ck_project_summary_draft_period_type"),
        sa.CheckConstraint("draft_status IN ('DRAFT', 'PUBLISHED')", name="ck_project_summary_draft_status"),
    )
    op.create_table(
        "project_summary_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("health_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_health_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("summary_draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_summary_drafts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record_no", sa.String(96), nullable=False, unique=True),
        sa.Column("record_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("confirmation_type", sa.String(32), nullable=False, server_default="PERSONAL_CONFIRMED"),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("summary_draft_id", name="uq_project_summary_record_draft"),
        sa.CheckConstraint("confirmation_type IN ('PERSONAL_CONFIRMED')", name="ck_project_summary_record_confirmation_type"),
    )


def downgrade() -> None:
    op.drop_table("project_summary_records")
    op.drop_table("project_summary_drafts")
    op.drop_table("project_health_snapshots")
