"""add worker lease fields to source sync runs for async consumption

Revision ID: 035_source_sync_worker
Revises: 034_knowledge_folders
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "035_source_sync_worker"
down_revision = "034_knowledge_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_sync_runs", sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("source_sync_runs", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("source_sync_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source_sync_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source_sync_runs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")))
    op.add_column("source_sync_runs", sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("source_sync_runs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("source_sync_runs", sa.Column("last_error_code", sa.String(length=64), nullable=True))
    op.add_column("source_sync_runs", sa.Column("last_error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_sync_runs", "last_error_message")
    op.drop_column("source_sync_runs", "last_error_code")
    op.drop_column("source_sync_runs", "max_attempts")
    op.drop_column("source_sync_runs", "attempt_no")
    op.drop_column("source_sync_runs", "available_at")
    op.drop_column("source_sync_runs", "heartbeat_at")
    op.drop_column("source_sync_runs", "lease_expires_at")
    op.drop_column("source_sync_runs", "lease_owner")
    op.drop_column("source_sync_runs", "requested_by")
