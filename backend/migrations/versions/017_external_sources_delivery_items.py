"""add read-only external source mirrors and delivery items

Revision ID: 017_external_sources_delivery_items
Revises: 016_assessment_profiles
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "017_external_sources_delivery_items"
down_revision = "016_assessment_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("repository_slug", sa.String(255), nullable=False),
        sa.Column("api_base_url", sa.Text(), nullable=False, server_default="https://api.github.com"),
        sa.Column("secret_ref", sa.String(160)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "provider", "repository_slug", name="uq_external_connection_project_provider_repo"),
        sa.CheckConstraint("provider IN ('GITHUB')", name="ck_external_connection_provider"),
    )
    op.create_table(
        "source_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'PARTIALLY_SUCCEEDED', 'FAILED')", name="ck_source_sync_run_status"),
    )
    op.create_table(
        "external_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("external_key", sa.String(160), nullable=False),
        sa.Column("logical_key", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("connection_id", "resource_type", "external_key", name="uq_external_resource_connection_type_key"),
        sa.CheckConstraint("resource_type IN ('ISSUE', 'PULL_REQUEST', 'MILESTONE')", name="ck_external_resource_type"),
    )
    op.create_table(
        "external_resource_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("web_url", sa.Text(), nullable=False),
        sa.Column("milestone_key", sa.String(160)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("resource_id", "revision_no", name="uq_external_resource_revision"),
    )
    op.create_table(
        "delivery_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_key", sa.String(320), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("planning_status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="NOT_ASSESSED"),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "external_key", name="uq_delivery_item_project_external_key"),
        sa.CheckConstraint("planning_status IN ('OPEN', 'IN_PROGRESS', 'DECLARED_DONE', 'CANCELLED')", name="ck_delivery_item_planning_status"),
        sa.CheckConstraint("verification_status IN ('NOT_ASSESSED', 'PARTIALLY_SUPPORTED', 'CONFIRMED', 'CONFLICT', 'INSUFFICIENT_EVIDENCE')", name="ck_delivery_item_verification_status"),
    )
    op.create_table(
        "delivery_item_source_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("delivery_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_resource_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_resource_revisions.id", ondelete="RESTRICT")),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_revisions.id", ondelete="RESTRICT")),
        sa.Column("link_role", sa.String(32), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("link_role IN ('PRIMARY', 'ACCEPTANCE', 'DESIGN', 'PLAN')", name="ck_delivery_item_source_link_role"),
        sa.CheckConstraint("(external_resource_revision_id IS NOT NULL AND source_revision_id IS NULL) OR (external_resource_revision_id IS NULL AND source_revision_id IS NOT NULL)", name="ck_delivery_item_source_link_exactly_one_source"),
    )


def downgrade() -> None:
    op.drop_table("delivery_item_source_links")
    op.drop_table("delivery_items")
    op.drop_table("external_resource_revisions")
    op.drop_table("external_resources")
    op.drop_table("source_sync_runs")
    op.drop_table("external_connections")
