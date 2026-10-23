"""add document full text retrieval index

Revision ID: 011_document_fts_index
Revises: 010_durable_job_heartbeat
Create Date: 2026-08-01
"""

from alembic import op


revision = "011_document_fts_index"
down_revision = "010_durable_job_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_document_chunks_fts ON document_chunks USING gin (to_tsvector('simple', content))")


def downgrade() -> None:
    op.execute("DROP INDEX ix_document_chunks_fts")
