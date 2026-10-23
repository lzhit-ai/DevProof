"""create core project task source and snapshot tables

Revision ID: 001_core_task_snapshot
Revises:
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_core_task_snapshot"
down_revision = None
branch_labels = None
depends_on = None


def uuid_column(name: str = "id") -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), primary_key=name == "id", nullable=False)


def upgrade() -> None:
    op.create_table(
        "users",
        uuid_column(),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "projects",
        uuid_column(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "project_members",
        uuid_column(),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('SUBMITTER', 'REVIEWER', 'ADMIN')", name="ck_project_members_role"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_table(
        "verification_tasks",
        uuid_column(),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("requirement_key", sa.String(length=100), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "requirement_key", name="uq_task_project_requirement"),
    )
    op.create_table(
        "verification_cycles",
        uuid_column(),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("business_status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("created_from_cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id"), nullable=True),
        sa.Column("active_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("business_status IN ('DRAFT', 'ANALYZING', 'DRAFT_READY', 'NEEDS_EVIDENCE', 'NEEDS_CONFIRMATION', 'PENDING_REVIEW', 'REJECTED', 'APPROVED', 'PUBLISHED')", name="ck_cycle_business_status"),
        sa.UniqueConstraint("task_id", "sequence_no", name="uq_cycle_task_sequence"),
    )
    op.create_table(
        "source_revisions",
        uuid_column(),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_role", sa.String(length=64), nullable=False),
        sa.Column("logical_name", sa.String(length=255), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="UPLOADED"),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("processing_status IN ('UPLOADED', 'PARSING', 'CHUNKING', 'INDEXING', 'READY', 'FAILED')", name="ck_source_processing_status"),
        sa.UniqueConstraint("project_id", "logical_name", "revision_no", name="uq_source_revision"),
    )
    op.create_table(
        "input_snapshots",
        uuid_column(),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=80), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("workflow_version", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="PREPARATION"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("snapshot_hash", name="uq_input_snapshot_hash"),
    )
    op.create_table(
        "input_snapshot_sources",
        uuid_column(),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id"), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("snapshot_id", "source_revision_id", name="uq_snapshot_source"),
    )
    op.create_table(
        "audit_events",
        uuid_column(),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("before_version", sa.Integer(), nullable=True),
        sa.Column("after_version", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "audit_events",
        "input_snapshot_sources",
        "input_snapshots",
        "source_revisions",
        "verification_cycles",
        "verification_tasks",
        "project_members",
        "projects",
        "users",
    ):
        op.drop_table(table)
