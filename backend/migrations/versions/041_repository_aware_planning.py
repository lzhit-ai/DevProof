"""Repository-aware ideas, clarification and human-confirmed plan versions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041_repository_aware_planning"
down_revision = "040_agent_task_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    def created():
        return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    op.create_table("repository_snapshots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("repository_id", uuid, sa.ForeignKey("git_repositories.id"), nullable=False),
        sa.Column("target_sha", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False), created())
    op.create_table("ideas",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False), created())
    op.create_table("idea_revisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("idea_id", uuid, sa.ForeignKey("ideas.id"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False), created(),
        sa.UniqueConstraint("idea_id", "revision_no", name="uq_idea_revision"))
    op.add_column("planning_input_snapshots", sa.Column("repository_snapshot_id", uuid, sa.ForeignKey("repository_snapshots.id")))
    op.add_column("planning_runs", sa.Column("idea_revision_id", uuid, sa.ForeignKey("idea_revisions.id")))
    op.add_column("planning_runs", sa.Column("request_key", sa.String(200)))
    op.add_column("planning_runs", sa.Column("request_hash", sa.String(80)))
    op.create_unique_constraint("uq_planning_request", "planning_runs", ["project_id", "created_by", "request_key"])
    op.create_index("uq_active_planning_revision", "planning_runs", ["idea_revision_id"], unique=True,
                    postgresql_where=sa.text("status IN ('QUEUED','RUNNING') AND idea_revision_id IS NOT NULL"))
    op.create_table("planning_questions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("planning_run_id", uuid, sa.ForeignKey("planning_runs.id"), nullable=False),
        sa.Column("question_key", sa.String(100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("answered_by", uuid, sa.ForeignKey("users.id")),
        sa.Column("answered_at", sa.DateTime(timezone=True)), created(),
        sa.UniqueConstraint("planning_run_id", "question_key", name="uq_planning_question"))
    op.create_table("plan_versions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("idea_revision_id", uuid, sa.ForeignKey("idea_revisions.id"), nullable=False),
        sa.Column("planning_run_id", uuid, sa.ForeignKey("planning_runs.id"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_plan_id", uuid, sa.ForeignKey("plan_versions.id")),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by", uuid, sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)), created(),
        sa.UniqueConstraint("idea_revision_id", "sequence_no", name="uq_plan_revision_sequence"),
        sa.CheckConstraint("status IN ('DRAFT','CONFIRMED','SUPERSEDED')", name="ck_plan_status"))
    op.execute("""CREATE FUNCTION devproof_immutable_repository_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Repository snapshot is immutable'; END; $$""")
    op.execute("""CREATE TRIGGER repository_snapshot_immutable BEFORE UPDATE OR DELETE ON repository_snapshots
        FOR EACH ROW EXECUTE FUNCTION devproof_immutable_repository_snapshot()""")
    op.execute("""CREATE FUNCTION devproof_confirmed_plan_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status IN ('CONFIRMED','SUPERSEDED') THEN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Confirmed plan is immutable'; END IF;
            IF NEW.status NOT IN ('CONFIRMED','SUPERSEDED') THEN RAISE EXCEPTION 'Confirmed plan cannot return to draft'; END IF;
            IF ROW(OLD.id,OLD.body_json,OLD.content_hash,OLD.idea_revision_id,OLD.planning_run_id,OLD.version,OLD.confirmed_by,OLD.confirmed_at,OLD.sequence_no,OLD.parent_plan_id,OLD.created_by,OLD.created_at)
                IS DISTINCT FROM ROW(NEW.id,NEW.body_json,NEW.content_hash,NEW.idea_revision_id,NEW.planning_run_id,NEW.version,NEW.confirmed_by,NEW.confirmed_at,NEW.sequence_no,NEW.parent_plan_id,NEW.created_by,NEW.created_at)
              THEN RAISE EXCEPTION 'Confirmed plan content is immutable'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER confirmed_plan_immutable BEFORE UPDATE OR DELETE ON plan_versions
        FOR EACH ROW EXECUTE FUNCTION devproof_confirmed_plan_immutable()""")


def downgrade() -> None:
    for table in ["plan_versions", "planning_questions"]:
        op.drop_table(table)
    op.execute("DROP FUNCTION devproof_confirmed_plan_immutable()")
    op.drop_index("uq_active_planning_revision", table_name="planning_runs")
    op.drop_constraint("uq_planning_request", "planning_runs", type_="unique")
    op.drop_column("planning_runs", "request_hash")
    op.drop_column("planning_runs", "request_key")
    op.drop_column("planning_runs", "idea_revision_id")
    op.drop_column("planning_input_snapshots", "repository_snapshot_id")
    for table in ["idea_revisions", "ideas", "repository_snapshots"]:
        op.drop_table(table)
    op.execute("DROP FUNCTION devproof_immutable_repository_snapshot()")
