"""persist project-scoped active retrieval indexes

Revision ID: 025_project_retrieval_indexes
Revises: 024_source_sync_pagination_cursor
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "025_project_retrieval_indexes"
down_revision = "024_source_sync_pagination_cursor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_retrieval_indexes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index_version", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="HISTORICAL"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "index_version", name="uq_project_retrieval_index_version"),
        sa.CheckConstraint("status IN ('ACTIVE', 'HISTORICAL')", name="ck_project_retrieval_index_status"),
    )
    op.create_index("ix_project_retrieval_indexes_project_status", "project_retrieval_indexes", ["project_id", "status"])
    op.create_index(
        "uq_project_retrieval_active_index",
        "project_retrieval_indexes",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_retrieval_active_index", table_name="project_retrieval_indexes")
    op.drop_index("ix_project_retrieval_indexes_project_status", table_name="project_retrieval_indexes")
    op.drop_table("project_retrieval_indexes")
