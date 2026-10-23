"""Freeze explicit confirmed-plan acceptance bindings before verification."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "042_plan_verification_bindings"
down_revision = "041_repository_aware_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("cycle_plan_selections",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("cycle_id", uuid, sa.ForeignKey("verification_cycles.id"), nullable=False),
        sa.Column("plan_version_id", uuid, sa.ForeignKey("plan_versions.id"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("plan_content_hash", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("cycle_id", "sequence_no", name="uq_cycle_plan_sequence"),
        sa.UniqueConstraint("id", "cycle_id", name="uq_cycle_plan_identity"),
        sa.UniqueConstraint("id", "plan_version_id", "plan_content_hash", "content_hash", name="uq_cycle_plan_baseline"))
    op.create_table("cycle_plan_selection_current",
        sa.Column("cycle_id", uuid, sa.ForeignKey("verification_cycles.id"), primary_key=True),
        sa.Column("selection_id", uuid, nullable=False),
        sa.ForeignKeyConstraint(["selection_id", "cycle_id"], ["cycle_plan_selections.id", "cycle_plan_selections.cycle_id"]))
    op.create_table("input_snapshot_plans",
        sa.Column("snapshot_id", uuid, sa.ForeignKey("input_snapshots.id"), primary_key=True),
        sa.Column("selection_id", uuid, nullable=False),
        sa.Column("plan_version_id", uuid, nullable=False),
        sa.Column("plan_content_hash", sa.String(80), nullable=False),
        sa.Column("selection_hash", sa.String(80), nullable=False),
        sa.ForeignKeyConstraint(["selection_id", "plan_version_id", "plan_content_hash", "selection_hash"],
            ["cycle_plan_selections.id", "cycle_plan_selections.plan_version_id", "cycle_plan_selections.plan_content_hash", "cycle_plan_selections.content_hash"]))
    op.add_column("analysis_runs", sa.Column("plan_version_id", uuid, sa.ForeignKey("plan_versions.id")))
    op.add_column("analysis_runs", sa.Column("plan_baseline_hash", sa.String(80)))
    op.create_check_constraint("ck_run_plan_baseline_pair", "analysis_runs", "(plan_version_id IS NULL) = (plan_baseline_hash IS NULL)")
    op.execute("""CREATE FUNCTION devproof_immutable_plan_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Plan verification baseline is immutable'; END; $$""")
    for table in ["cycle_plan_selections", "input_snapshot_plans"]:
        op.execute(f"""CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_immutable_plan_binding()""")
    op.execute("""CREATE FUNCTION devproof_guard_plan_selection() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE cycle uuid;
        BEGIN
          IF TG_OP='DELETE' THEN cycle:=OLD.cycle_id; ELSE cycle:=NEW.cycle_id; END IF;
          IF TG_OP='UPDATE' AND OLD.cycle_id<>NEW.cycle_id THEN RAISE EXCEPTION 'Selection cycle is immutable'; END IF;
          PERFORM id FROM verification_cycles WHERE id=cycle FOR UPDATE;
          IF EXISTS(SELECT 1 FROM input_snapshots WHERE cycle_id=cycle AND purpose='FORMAL') THEN
            RAISE EXCEPTION 'Formal input has already frozen the plan selection';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER current_plan_selection_guard BEFORE INSERT OR UPDATE OR DELETE ON cycle_plan_selection_current
        FOR EACH ROW EXECUTE FUNCTION devproof_guard_plan_selection()""")
    op.execute("""CREATE FUNCTION devproof_guard_snapshot_plan() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS(SELECT 1 FROM input_snapshots s JOIN cycle_plan_selections p ON p.cycle_id=s.cycle_id
            JOIN cycle_plan_selection_current c ON c.cycle_id=s.cycle_id AND c.selection_id=p.id
            WHERE s.id=NEW.snapshot_id AND s.purpose='FORMAL' AND p.id=NEW.selection_id) THEN
            RAISE EXCEPTION 'Plan selection must belong to the formal snapshot cycle';
          END IF;
          IF EXISTS(SELECT 1 FROM analysis_runs WHERE snapshot_id=NEW.snapshot_id) THEN
            RAISE EXCEPTION 'Cannot attach a plan after analysis has started';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER snapshot_plan_scope BEFORE INSERT ON input_snapshot_plans
        FOR EACH ROW EXECUTE FUNCTION devproof_guard_snapshot_plan()""")
    op.execute("""CREATE FUNCTION devproof_guard_run_plan() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE baseline input_snapshot_plans%ROWTYPE;
        BEGIN
          SELECT * INTO baseline FROM input_snapshot_plans WHERE snapshot_id=NEW.snapshot_id;
          IF NEW.plan_version_id IS DISTINCT FROM baseline.plan_version_id
            OR NEW.plan_baseline_hash IS DISTINCT FROM baseline.selection_hash THEN
              RAISE EXCEPTION 'Analysis plan must match its frozen input baseline';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER analysis_run_plan_scope BEFORE INSERT OR UPDATE OF snapshot_id,plan_version_id,plan_baseline_hash ON analysis_runs
        FOR EACH ROW EXECUTE FUNCTION devproof_guard_run_plan()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER analysis_run_plan_scope ON analysis_runs")
    op.execute("DROP FUNCTION devproof_guard_run_plan()")
    op.drop_constraint("ck_run_plan_baseline_pair", "analysis_runs", type_="check")
    op.drop_column("analysis_runs", "plan_baseline_hash")
    op.drop_column("analysis_runs", "plan_version_id")
    op.drop_table("input_snapshot_plans")
    op.execute("DROP FUNCTION devproof_guard_snapshot_plan()")
    op.drop_table("cycle_plan_selection_current")
    op.execute("DROP FUNCTION devproof_guard_plan_selection()")
    op.drop_table("cycle_plan_selections")
    op.execute("DROP FUNCTION devproof_immutable_plan_binding()")
