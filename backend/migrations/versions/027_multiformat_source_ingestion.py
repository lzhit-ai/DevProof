"""add multi-format source extraction and durable ingestion jobs

Revision ID: 027_multiformat_source_ingestion
Revises: 026_retrieval_index_build_runs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027_multiformat_source_ingestion"
down_revision = "026_retrieval_index_build_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_source_processing_status", "source_revisions", type_="check")
    op.create_check_constraint(
        "ck_source_processing_status", "source_revisions",
        "processing_status IN ('UPLOADED', 'PARSING', 'OCR_CHECKING', 'CHUNKING', 'INDEXING', 'READY', 'FAILED')",
    )
    op.add_column("source_revisions", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.execute("UPDATE source_revisions SET original_filename = logical_name WHERE original_filename IS NULL")
    op.alter_column("source_revisions", "original_filename", nullable=False)
    op.add_column("source_revisions", sa.Column("extracted_artifact_uri", sa.Text(), nullable=True))
    op.add_column("source_revisions", sa.Column("extraction_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("source_revisions", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.create_table(
        "source_ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_revision_id", name="uq_source_ingestion_job_source"),
        sa.CheckConstraint("job_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_source_ingestion_job_status"),
    )


def downgrade() -> None:
    op.drop_table("source_ingestion_jobs")
    op.drop_column("source_revisions", "ocr_confidence")
    op.drop_column("source_revisions", "extraction_metadata")
    op.drop_column("source_revisions", "extracted_artifact_uri")
    op.drop_column("source_revisions", "original_filename")
    op.drop_constraint("ck_source_processing_status", "source_revisions", type_="check")
    op.create_check_constraint(
        "ck_source_processing_status", "source_revisions",
        "processing_status IN ('UPLOADED', 'PARSING', 'CHUNKING', 'INDEXING', 'READY', 'FAILED')",
    )
