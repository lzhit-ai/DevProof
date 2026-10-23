"""allow read only QA model call audit records

Revision ID: 012_qa_model_calls
Revises: 011_document_fts_index
Create Date: 2026-08-01
"""

from alembic import op


revision = "012_qa_model_calls"
down_revision = "011_document_fts_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("model_calls", "run_id", nullable=True)


def downgrade() -> None:
    op.alter_column("model_calls", "run_id", nullable=False)
