"""upgrade knowledge folders to standalone knowledge bases with project mounts

Revision ID: 036_knowledge_bases
Revises: 035_source_sync_worker
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "036_knowledge_bases"
down_revision = "035_source_sync_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create knowledge_bases (standalone knowledge library entity).
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_knowledge_bases_project_id", "knowledge_bases", ["project_id"])

    # 2. Migrate existing knowledge_folders rows into knowledge_bases.
    op.execute(
        """
        INSERT INTO knowledge_bases (id, project_id, name, created_by, created_at, updated_at)
        SELECT id, project_id, name, created_by, created_at, updated_at
        FROM knowledge_folders
        """
    )

    # 3. Create project_knowledge_bases mount table.
    op.create_table(
        "project_knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "knowledge_base_id", name="uq_project_knowledge_base"),
    )
    op.create_index("ix_project_knowledge_bases_project_id", "project_knowledge_bases", ["project_id"])
    op.create_index("ix_project_knowledge_bases_kb_id", "project_knowledge_bases", ["knowledge_base_id"])

    # 4. Auto-mount each migrated knowledge base to its owning (project) project.
    op.execute(
        """
        INSERT INTO project_knowledge_bases (id, project_id, knowledge_base_id, created_by, created_at, updated_at)
        SELECT gen_random_uuid(), project_id, id, created_by, created_at, updated_at
        FROM knowledge_bases
        """
    )

    # 5. source_revisions.folder_id -> knowledge_base_id.
    op.add_column("source_revisions", sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True))
    op.execute(
        """
        UPDATE source_revisions SET knowledge_base_id = folder_id WHERE folder_id IS NOT NULL
        """
    )
    op.create_index("ix_source_revisions_knowledge_base_id", "source_revisions", ["knowledge_base_id"])

    # 6. Drop legacy knowledge_folders (and its folder_id column on source_revisions).
    #    Drop the folder_id FK constraint on source_revisions first so the table
    #    can be dropped without the dependent constraint blocking it.
    op.drop_constraint("source_revisions_folder_id_fkey", "source_revisions", type_="foreignkey")
    op.drop_index("ix_knowledge_folders_project_id", table_name="knowledge_folders")
    op.drop_index("ix_knowledge_folders_parent_folder_id", table_name="knowledge_folders")
    op.drop_table("knowledge_folders")
    op.drop_index("ix_source_revisions_folder_id", table_name="source_revisions")
    op.drop_column("source_revisions", "folder_id")


def downgrade() -> None:
    op.add_column("source_revisions", sa.Column("folder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_source_revisions_folder_id", "source_revisions", ["folder_id"])
    op.execute("UPDATE source_revisions SET folder_id = knowledge_base_id WHERE knowledge_base_id IS NOT NULL")
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
    op.execute("INSERT INTO knowledge_folders (id, project_id, name, created_by, created_at, updated_at) SELECT id, project_id, name, created_by, created_at, updated_at FROM knowledge_bases")
    op.drop_index("ix_source_revisions_knowledge_base_id", table_name="source_revisions")
    op.drop_column("source_revisions", "knowledge_base_id")
    op.drop_table("project_knowledge_bases")
    op.drop_index("ix_knowledge_bases_project_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
