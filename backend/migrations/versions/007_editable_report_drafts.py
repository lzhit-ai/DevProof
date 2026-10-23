"""add editable report draft note

Revision ID: 007_editable_report_drafts
Revises: 006_model_call_audit
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa


revision = "007_editable_report_drafts"
down_revision = "006_model_call_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_versions", sa.Column("editorial_note", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("report_versions", "editorial_note")
