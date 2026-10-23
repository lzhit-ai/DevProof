"""create formal snapshot analysis run and durable job tables

Revision ID: 003_analysis_jobs
Revises: 002_evidence_and_git
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_analysis_jobs"
down_revision = "002_evidence_and_git"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("input_snapshot_git", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("git_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("git_snapshots.id"), nullable=False), sa.Column("diff_hash", sa.String(80), nullable=False))
    op.create_table("analysis_runs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False), sa.Column("analysis_config_hash", sa.String(80), nullable=False), sa.Column("run_status", sa.String(32), nullable=False), sa.Column("manifest_hash", sa.String(80), nullable=False), sa.Column("checkpoint_ns", sa.String(128), nullable=False, unique=True), sa.Column("cancel_requested_at", sa.DateTime(timezone=True)), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.UniqueConstraint("snapshot_id", "analysis_config_hash", name="uq_active_run_config"))
    op.create_table("analysis_run_manifests", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("workflow_version", sa.String(64), nullable=False), sa.Column("rule_set_version", sa.String(64), nullable=False), sa.Column("prompt_set_version", sa.String(64), nullable=False), sa.Column("generation_model", sa.String(128), nullable=False), sa.Column("embedding_model", sa.String(128), nullable=False), sa.Column("schema_version", sa.String(64), nullable=False), sa.Column("degradation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_table("analysis_jobs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True), sa.Column("job_status", sa.String(32), nullable=False), sa.Column("lease_owner", sa.String(128)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)), sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"), sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"), sa.Column("last_error_code", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_table("run_events", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("node_id", sa.String(64)), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("payload_redacted", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("correlation_id", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))


def downgrade() -> None:
    for table in ("run_events", "analysis_jobs", "analysis_run_manifests", "analysis_runs", "input_snapshot_git"):
        op.drop_table(table)
