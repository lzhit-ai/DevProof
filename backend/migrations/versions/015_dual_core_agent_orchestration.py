"""add dual core Agent capabilities and frozen orchestration snapshots

Revision ID: 015_dual_core_orchestration
Revises: 014_node_attempts_risks
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "015_dual_core_orchestration"
down_revision = "014_node_attempts_risks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Later revision IDs exceed the 32-character limit created by the initial schema.
    # Widen this Alembic-owned bookkeeping column before advancing the migration chain.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_table(
        "agent_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("tool_type", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.Text()),
        sa.Column("secret_ref", sa.String(160)),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "key", name="uq_agent_tool_project_key"),
        sa.CheckConstraint("tool_type IN ('DOCUMENT_RETRIEVAL', 'GIT_DIFF', 'CI_EVIDENCE', 'EVIDENCE_QUERY', 'HTTP_QUERY')", name="ck_agent_tool_type"),
    )
    op.create_table(
        "agent_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("core_scope", sa.String(24), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_default_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "key", name="uq_agent_capability_project_key"),
        sa.CheckConstraint("core_scope IN ('REQUIREMENT', 'DELIVERY', 'SHARED')", name="ck_agent_capability_core_scope"),
        sa.CheckConstraint("kind IN ('SYSTEM', 'CUSTOM')", name="ck_agent_capability_kind"),
    )
    op.create_table(
        "agent_capability_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_capabilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tool_bindings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parameter_schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("capability_id", "version_no", name="uq_agent_capability_version"),
    )
    op.create_table(
        "orchestration_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", "name", name="uq_orchestration_template_project_name"),
    )
    op.create_table(
        "orchestration_template_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orchestration_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_capability_versions.id"), nullable=False),
        sa.Column("core_scope", sa.String(24), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("template_id", "display_order", name="uq_orchestration_template_node_order"),
        sa.UniqueConstraint("template_id", "capability_version_id", name="uq_orchestration_template_capability"),
    )
    op.create_table(
        "task_orchestration_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_tasks.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orchestration_templates.id"), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("bound_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "analysis_run_orchestration_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orchestration_templates.id"), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("template_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("nodes_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("analysis_run_orchestration_snapshots")
    op.drop_table("task_orchestration_bindings")
    op.drop_table("orchestration_template_nodes")
    op.drop_table("orchestration_templates")
    op.drop_table("agent_capability_versions")
    op.drop_table("agent_capabilities")
    op.drop_table("agent_tools")
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
