"""Java-owned execution tasks and independent planning runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "040_agent_task_center"
down_revision = "039_published_report_bodies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    stamp = lambda name: sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    op.create_table("planning_input_snapshots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False), stamp("created_at"))
    op.create_table("planning_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("snapshot_id", uuid, sa.ForeignKey("planning_input_snapshots.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), stamp("created_at"))
    op.create_table("agent_tasks",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("analysis_run_id", uuid, sa.ForeignKey("analysis_runs.id")),
        sa.Column("planning_run_id", uuid, sa.ForeignKey("planning_runs.id")),
        sa.Column("task_kind", sa.String(48), nullable=False),
        sa.Column("executor_version", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("current_attempt_id", uuid),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_hash", sa.String(80)),
        sa.Column("accepted_json", sa.Text()),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        stamp("available_at"), stamp("created_at"),
        sa.CheckConstraint("num_nonnulls(analysis_run_id,planning_run_id)=1", name="ck_agent_task_business_ref"),
        sa.CheckConstraint("(task_kind='DELIVERY_VERIFY' AND analysis_run_id IS NOT NULL) OR (task_kind IN ('PLAN_DRAFT','PLAN_REFINE') AND planning_run_id IS NOT NULL)", name="ck_agent_task_run_kind"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_agent_task_status"),
        sa.CheckConstraint("max_attempts>0 AND attempt_no>=0 AND fencing_token>=0", name="ck_agent_task_attempts"))
    op.create_index("ix_agent_task_queue", "agent_tasks", ["status", "available_at", "created_at"])
    op.create_index("uq_agent_task_analysis", "agent_tasks", ["analysis_run_id"], unique=True, postgresql_where=sa.text("analysis_run_id IS NOT NULL"))
    op.create_index("uq_agent_task_planning", "agent_tasks", ["planning_run_id"], unique=True, postgresql_where=sa.text("planning_run_id IS NOT NULL"))
    op.create_table("agent_task_attempts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("task_id", uuid, sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("worker_id", sa.String(160), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        stamp("heartbeat_at"), stamp("created_at"),
        sa.UniqueConstraint("id", "task_id", name="uq_attempt_task"),
        sa.UniqueConstraint("task_id", "fencing_token", name="uq_task_fencing"))
    op.create_table("agent_task_events",
        sa.Column("task_id", uuid, nullable=False),
        sa.Column("attempt_id", uuid, nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("event_json", sa.Text(), nullable=False), stamp("received_at"),
        sa.PrimaryKeyConstraint("task_id", "attempt_id", "event_seq"),
        sa.ForeignKeyConstraint(["attempt_id", "task_id"], ["agent_task_attempts.id", "agent_task_attempts.task_id"]))


def downgrade() -> None:
    for table in ["agent_task_events", "agent_task_attempts", "agent_tasks", "planning_runs", "planning_input_snapshots"]:
        op.drop_table(table)
