"""add knowledge folder hierarchy for project knowledge bases

Revision ID: 034_knowledge_folders
Revises: 033_embedding_dimension_configurable
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "034_knowledge_folders"
down_revision = "033_embedding_dimension_configurable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_folder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_knowledge_folders_project_id", "knowledge_folders", ["project_id"])
    op.create_index("ix_knowledge_folders_parent_folder_id", "knowledge_folders", ["parent_folder_id"])
    # Persist the per-file OCR intent so the asynchronous worker can honour it.
    op.add_column("source_revisions", sa.Column("force_ocr", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("source_revisions", sa.Column("folder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_source_revisions_folder_id", "source_revisions", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_source_revisions_folder_id", table_name="source_revisions")
    op.drop_column("source_revisions", "folder_id")
    op.drop_column("source_revisions", "force_ocr")
    op.drop_index("ix_knowledge_folders_parent_folder_id", table_name="knowledge_folders")
    op.drop_index("ix_knowledge_folders_project_id", table_name="knowledge_folders")
    op.drop_table("knowledge_folders")
