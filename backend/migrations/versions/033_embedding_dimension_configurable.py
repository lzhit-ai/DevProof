"""make the embedding vector column dimension configurable

Revision ID: 033_embedding_dimension_configurable
Revises: 032_human_verification_decisions
"""

import os

from alembic import op


revision = "033_embedding_dimension_configurable"
down_revision = "032_human_verification_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dimension = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))
    # pgvector cannot convert stored vectors across a changed dimension, so existing
    # vectors must be cleared; rerun rebuild_project_retrieval_index afterwards to
    # re-embed derivation index chunks at the configured dimension.
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding DROP NOT NULL")
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute(
        f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({dimension}) "
        f"USING embedding::vector({dimension})"
    )


def downgrade() -> None:
    op.execute("UPDATE document_chunks SET embedding = NULL")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)")
