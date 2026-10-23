"""Keep project history while removing deleted projects from active use."""

from alembic import op
import sqlalchemy as sa


revision = "038_project_soft_delete"
down_revision = "037_run_context_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "deleted_at")
