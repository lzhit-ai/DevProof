"""require every verification task to belong to a delivery item

Revision ID: 030_require_task_delivery_item
Revises: 029_standard_verification_challenge
"""

import sqlalchemy as sa
from alembic import op


revision = "030_require_task_delivery_item"
down_revision = "029_standard_verification_challenge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM verification_tasks WHERE delivery_item_id IS NULL")
    op.alter_column("verification_tasks", "delivery_item_id", existing_type=sa.UUID(), nullable=False)


def downgrade() -> None:
    op.alter_column("verification_tasks", "delivery_item_id", existing_type=sa.UUID(), nullable=True)
