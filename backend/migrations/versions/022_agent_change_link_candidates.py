"""persist controlled Agent change-link proposal runs

Revision ID: 022_agent_change_link_candidates
Revises: 021_agent_tool_execution_evidence_boundary
Create Date: 2026-08-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "022_agent_change_link_candidates"
down_revision = "021_agent_tool_execution_evidence_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_change_proposal_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input_manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("rules_version", sa.String(64), nullable=False),
        sa.Column("candidate_target_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("delivery_change_links", sa.Column("agent_proposal_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_delivery_change_link_agent_proposal_run",
        "delivery_change_links",
        "agent_change_proposal_runs",
        ["agent_proposal_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_delivery_change_link_agent_proposal_run", "delivery_change_links", type_="foreignkey")
    op.drop_column("delivery_change_links", "agent_proposal_run_id")
    op.drop_table("agent_change_proposal_runs")
