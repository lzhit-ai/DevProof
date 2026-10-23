"""add SHA-bound security scan evidence and immutable baselines

Revision ID: 020_security_baseline
Revises: 019_project_health_summary
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "020_security_baseline"
down_revision = "019_project_health_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_scan_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("git_repositories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_sha", sa.String(64), nullable=False),
        sa.Column("scan_type", sa.String(24), nullable=False),
        sa.Column("scanner_name", sa.String(160), nullable=False),
        sa.Column("scanner_version", sa.String(160), nullable=False),
        sa.Column("rule_set_version", sa.String(160), nullable=False),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("imported_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scan_type IN ('SAST', 'DEPENDENCY', 'SECRET', 'CONFIG', 'CI')", name="ck_security_scan_artifact_type"),
    )
    op.create_table(
        "security_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_scan_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("locator", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("finding_status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("status_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("status_updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("status_updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scan_artifact_id", "fingerprint", name="uq_security_finding_artifact_fingerprint"),
        sa.CheckConstraint("severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_security_finding_severity"),
        sa.CheckConstraint("finding_status IN ('OPEN', 'ACCEPTED_RISK', 'REMEDIATION_CLAIMED')", name="ck_security_finding_status"),
    )
    op.create_table(
        "security_baseline_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("git_repositories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_sha", sa.String(64), nullable=False),
        sa.Column("input_manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("snapshot_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "security_baseline_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("security_baseline_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record_no", sa.String(96), nullable=False, unique=True),
        sa.Column("record_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("confirmation_reason", sa.Text(), nullable=False),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("baseline_snapshot_id", name="uq_security_baseline_record_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("security_baseline_records")
    op.drop_table("security_baseline_snapshots")
    op.drop_table("security_findings")
    op.drop_table("security_scan_artifacts")
