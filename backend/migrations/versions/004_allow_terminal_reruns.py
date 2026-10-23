"""allow terminal reruns while preventing duplicate active runs

Revision ID: 004_allow_terminal_reruns
Revises: 003_analysis_jobs
Create Date: 2026-08-01
"""

from alembic import op

revision = "004_allow_terminal_reruns"
down_revision = "003_analysis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_active_run_config", "analysis_runs", type_="unique")
    op.execute("CREATE UNIQUE INDEX uq_active_run_config ON analysis_runs (snapshot_id, analysis_config_hash) WHERE run_status IN ('QUEUED', 'RUNNING')")


def downgrade() -> None:
    op.execute("DROP INDEX uq_active_run_config")
    op.create_unique_constraint("uq_active_run_config", "analysis_runs", ["snapshot_id", "analysis_config_hash"])
