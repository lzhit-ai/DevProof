"""persist replayable delivery code-review inputs and findings

Revision ID: 028_delivery_code_review_core
Revises: 027_multiformat_source_ingestion
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "028_delivery_code_review_core"
down_revision = "027_multiformat_source_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "kind", "content_hash", name="uq_artifact_project_kind_hash"),
    )
    op.add_column("git_snapshots", sa.Column("effective_base_sha", sa.String(length=64), nullable=True))
    op.add_column("git_snapshots", sa.Column("capture_version", sa.String(length=64), nullable=True))
    op.add_column("git_snapshots", sa.Column("diff_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_objects.id"), nullable=True))
    op.add_column("git_snapshots", sa.Column("code_change_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_objects.id"), nullable=True))
    op.add_column("analysis_coverages", sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_table(
        "code_review_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_items.id"), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fingerprint", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("finding_kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("trigger_scenario", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("produced_by", sa.String(length=32), nullable=False),
        sa.Column("requires_human_confirmation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("analysis_run_id", "fingerprint", name="uq_code_review_finding_run_fingerprint"),
    )


def downgrade() -> None:
    op.drop_table("code_review_findings")
    op.drop_column("analysis_coverages", "details")
    op.drop_column("git_snapshots", "code_change_artifact_id")
    op.drop_column("git_snapshots", "diff_artifact_id")
    op.drop_column("git_snapshots", "capture_version")
    op.drop_column("git_snapshots", "effective_base_sha")
    op.drop_table("artifact_objects")
