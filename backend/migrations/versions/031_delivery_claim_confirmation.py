"""freeze confirmed delivery claims with formal snapshots

Revision ID: 031_delivery_claim_confirmation
Revises: 030_require_task_delivery_item
"""

import sqlalchemy as sa
from alembic import op


revision = "031_delivery_claim_confirmation"
down_revision = "030_require_task_delivery_item"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_claim_drafts",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("cycle_id", sa.UUID(), sa.ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_key", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("claim_status", sa.String(length=16), nullable=False, server_default="CANDIDATE"),
        sa.Column("source_manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("cycle_id", "claim_key", name="uq_delivery_claim_draft_cycle_key"),
        sa.CheckConstraint("origin IN ('MODEL', 'HUMAN')", name="ck_delivery_claim_draft_origin"),
        sa.CheckConstraint("claim_status IN ('CANDIDATE', 'CONFIRMED', 'DISCARDED')", name="ck_delivery_claim_draft_status"),
    )
    op.create_table(
        "input_snapshot_claims",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("snapshot_id", sa.UUID(), sa.ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_claim_draft_id", sa.UUID(), sa.ForeignKey("delivery_claim_drafts.id"), nullable=False),
        sa.Column("claim_key", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("source_manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("snapshot_id", "claim_key", name="uq_input_snapshot_claim_key"),
    )


def downgrade() -> None:
    op.drop_table("input_snapshot_claims")
    op.drop_table("delivery_claim_drafts")
