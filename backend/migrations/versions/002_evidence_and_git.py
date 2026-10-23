"""create evidence document and git snapshot tables

Revision ID: 002_evidence_and_git
Revises: 001_core_task_snapshot
Create Date: 2026-08-01
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_evidence_and_git"
down_revision = "001_core_task_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=80), nullable=False),
        sa.Column("locator", postgresql.JSONB(), nullable=False),
        sa.Column("index_version", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.UniqueConstraint("source_revision_id", "chunk_index", "index_version", name="uq_document_chunk_version"),
    )
    op.execute("CREATE INDEX ix_document_chunks_content_fts ON document_chunks USING gin (to_tsvector('simple', content))")
    op.create_table(
        "git_repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_url_hash", sa.String(length=80), nullable=False),
        sa.Column("display_url", sa.Text(), nullable=False),
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "canonical_url_hash", name="uq_project_git_repository"),
    )
    op.create_table(
        "git_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("git_repositories.id"), nullable=False),
        sa.Column("selected_base_ref", sa.String(length=255), nullable=False),
        sa.Column("selected_target_ref", sa.String(length=255), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=False),
        sa.Column("target_sha", sa.String(length=64), nullable=False),
        sa.Column("merge_base_sha", sa.String(length=64), nullable=False),
        sa.Column("diff_mode", sa.String(length=16), nullable=False),
        sa.Column("include_paths", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("exclude_paths", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("diff_hash", sa.String(length=80), nullable=False),
        sa.Column("coverage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_key", sa.String(length=128), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("authority_level", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id"), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "claim_key", name="uq_claim_run_key"),
    )
    op.create_table(
        "evidence_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_kind", sa.String(length=32), nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id"), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("excerpt_safe", sa.Text(), nullable=False),
        sa.Column("locator", postgresql.JSONB(), nullable=False),
        sa.Column("locator_precision", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("requires_human_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("locator_precision IN ('EXACT', 'APPROXIMATE', 'UNAVAILABLE')", name="ck_evidence_locator_precision"),
    )
    op.create_table(
        "claim_evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("produced_by", sa.String(length=32), nullable=False),
        sa.Column("requires_human_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("relation IN ('SUPPORTS', 'CONTRADICTS', 'CONTEXT_ONLY')", name="ck_claim_evidence_relation"),
        sa.UniqueConstraint("claim_id", "evidence_id", "relation", name="uq_claim_evidence_relation"),
    )
    op.create_table(
        "verification_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("requires_human_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("produced_by", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("analysis_run_id", "claim_id", name="uq_result_run_claim"),
    )
    op.create_table(
        "analysis_coverages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_ref", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    for table in ("analysis_coverages", "verification_results", "claim_evidence_links", "evidence_items", "claims", "git_snapshots", "git_repositories", "document_chunks"):
        op.drop_table(table)
