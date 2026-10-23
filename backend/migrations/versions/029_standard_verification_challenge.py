"""persist standard-verification finding challenges

Revision ID: 029_standard_verification_challenge
Revises: 028_delivery_code_review_core
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "029_standard_verification_challenge"
down_revision = "028_delivery_code_review_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "code_review_finding_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_review_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(length=80), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_call_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("analysis_run_id", "finding_id", name="uq_code_review_challenge_run_finding"),
    )
    op.create_index("ix_code_review_challenge_run_fingerprint", "code_review_finding_challenges", ["analysis_run_id", "fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_code_review_challenge_run_fingerprint", table_name="code_review_finding_challenges")
    op.drop_table("code_review_finding_challenges")
