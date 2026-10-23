"""persist append-only human delivery adjudications

Revision ID: 032_human_verification_decisions
Revises: 031_delivery_claim_confirmation
"""

import sqlalchemy as sa
from alembic import op


revision = "032_human_verification_decisions"
down_revision = "031_delivery_claim_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "human_verification_decisions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column(
            "result_id",
            sa.UUID(),
            sa.ForeignKey("verification_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=48), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "supersedes_decision_id",
            sa.UUID(),
            sa.ForeignKey("human_verification_decisions.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "decision IN ('CONFIRM_SUPPORT', 'CONFIRM_PARTIAL', 'CONFIRM_INSUFFICIENT', 'RETURN_FOR_EVIDENCE')",
            name="ck_human_verification_decision",
        ),
    )
    op.create_index(
        "ix_human_verification_decision_result_created",
        "human_verification_decisions",
        ["result_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_human_verification_decision_result_created", table_name="human_verification_decisions")
    op.drop_table("human_verification_decisions")
