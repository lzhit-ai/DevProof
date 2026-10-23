"""add durable command idempotency records

Revision ID: 008_command_idempotency
Revises: 007_editable_report_drafts
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_command_idempotency"
down_revision = "007_editable_report_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_hash", sa.String(80), nullable=False),
        sa.Column("request_method", sa.String(10), nullable=False),
        sa.Column("request_path", sa.String(1000), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(80), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("principal_hash", "request_method", "request_path", "idempotency_key", name="uq_idempotency_request"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
