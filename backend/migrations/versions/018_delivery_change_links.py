"""link delivery items to verification tasks PRs and frozen Git snapshots

Revision ID: 018_delivery_change_links
Revises: 017_external_sources_delivery_items
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "018_delivery_change_links"
down_revision = "017_external_sources_delivery_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "verification_tasks",
        sa.Column("delivery_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_items.id", ondelete="RESTRICT")),
    )
    op.create_index("ix_verification_tasks_delivery_item_id", "verification_tasks", ["delivery_item_id"])
    op.create_table(
        "delivery_change_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pull_request_resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_resources.id", ondelete="RESTRICT")),
        sa.Column("git_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("git_snapshots.id", ondelete="RESTRICT")),
        sa.Column("link_status", sa.String(24), nullable=False),
        sa.Column("link_source", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("link_status IN ('CANDIDATE', 'CONFIRMED')", name="ck_delivery_change_link_status"),
        sa.CheckConstraint("link_source IN ('PLATFORM', 'USER', 'AGENT')", name="ck_delivery_change_link_source"),
        sa.CheckConstraint("(pull_request_resource_id IS NOT NULL AND git_snapshot_id IS NULL) OR (pull_request_resource_id IS NULL AND git_snapshot_id IS NOT NULL)", name="ck_delivery_change_link_exactly_one_target"),
        sa.UniqueConstraint("delivery_item_id", "pull_request_resource_id", name="uq_delivery_change_link_item_pr"),
        sa.UniqueConstraint("delivery_item_id", "git_snapshot_id", name="uq_delivery_change_link_item_git_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("delivery_change_links")
    op.drop_index("ix_verification_tasks_delivery_item_id", table_name="verification_tasks")
    op.drop_column("verification_tasks", "delivery_item_id")
