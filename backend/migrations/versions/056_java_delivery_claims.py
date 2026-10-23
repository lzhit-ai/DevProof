"""Own editable claims and durable candidate extraction in the Java task center."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "056_java_delivery_claims"
down_revision = "055_java_delivery_associations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('delivery-claims','PYTHON')")
    op.create_table("delivery_claim_proposal_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("task_id", uuid, sa.ForeignKey("verification_tasks.id"), nullable=False),
        sa.Column("cycle_id", uuid, sa.ForeignKey("verification_cycles.id"), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("source_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_claim_proposal_status"),
        sa.CheckConstraint("input_hash='sha256:' || encode(sha256(convert_to(input_json,'UTF8')),'hex') AND jsonb_typeof(input_json::jsonb)='object' AND input_json::jsonb ? 'sourceManifest' AND input_json::jsonb->'sourceManifest'=source_manifest", name="ck_claim_proposal_input_hash"))
    op.create_index("uq_claim_proposal_active_cycle", "delivery_claim_proposal_runs", ["cycle_id"], unique=True, postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"))
    op.add_column("agent_tasks", sa.Column("claim_proposal_run_id", uuid, sa.ForeignKey("delivery_claim_proposal_runs.id")))
    op.drop_constraint("ck_agent_task_business_ref", "agent_tasks", type_="check")
    op.drop_constraint("ck_agent_task_run_kind", "agent_tasks", type_="check")
    op.create_check_constraint("ck_agent_task_business_ref", "agent_tasks", "num_nonnulls(analysis_run_id,planning_run_id,claim_proposal_run_id)=1")
    op.create_check_constraint("ck_agent_task_run_kind", "agent_tasks", "(task_kind='DELIVERY_VERIFY' AND analysis_run_id IS NOT NULL) OR (task_kind IN ('PLAN_DRAFT','PLAN_REFINE') AND planning_run_id IS NOT NULL) OR (task_kind='DELIVERY_CLAIM_PROPOSE' AND claim_proposal_run_id IS NOT NULL)")
    op.create_index("uq_agent_task_claim_proposal", "agent_tasks", ["claim_proposal_run_id"], unique=True, postgresql_where=sa.text("claim_proposal_run_id IS NOT NULL"))
    op.execute("""CREATE FUNCTION devproof_guard_delivery_claim_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='delivery-claims' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Delivery claims are owned by Java'; END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='delivery_claim_proposal_runs' AND TG_OP='UPDATE' THEN
          IF ROW(OLD.id,OLD.project_id,OLD.task_id,OLD.cycle_id,OLD.input_json,OLD.input_hash,OLD.source_manifest,OLD.created_by,OLD.created_at)
             IS DISTINCT FROM ROW(NEW.id,NEW.project_id,NEW.task_id,NEW.cycle_id,NEW.input_json,NEW.input_hash,NEW.source_manifest,NEW.created_by,NEW.created_at)
          THEN RAISE EXCEPTION 'Claim proposal inputs are immutable'; END IF;
        END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='delivery_claim_drafts' AND TG_OP IN ('INSERT','UPDATE') THEN
          IF EXISTS(SELECT 1 FROM input_snapshots WHERE cycle_id=NEW.cycle_id AND purpose='FORMAL')
          THEN RAISE EXCEPTION 'Claims cannot change after formal input freeze'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in ["delivery_claim_drafts", "delivery_claim_proposal_runs"]:
        op.execute(f"CREATE TRIGGER {table}_claim_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_delivery_claim_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='delivery-claims' AND owner='JAVA')
         OR EXISTS(SELECT 1 FROM delivery_claim_proposal_runs)
      THEN RAISE EXCEPTION 'Retain claim proposal history and hand ownership back before downgrade'; END IF;
    END $$""")
    for table in ["delivery_claim_drafts", "delivery_claim_proposal_runs"]:
        op.execute(f"DROP TRIGGER {table}_claim_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_delivery_claim_writer()")
    op.drop_index("uq_agent_task_claim_proposal", "agent_tasks")
    op.drop_constraint("ck_agent_task_run_kind", "agent_tasks", type_="check")
    op.drop_constraint("ck_agent_task_business_ref", "agent_tasks", type_="check")
    op.drop_column("agent_tasks", "claim_proposal_run_id")
    op.create_check_constraint("ck_agent_task_business_ref", "agent_tasks", "num_nonnulls(analysis_run_id,planning_run_id)=1")
    op.create_check_constraint("ck_agent_task_run_kind", "agent_tasks", "(task_kind='DELIVERY_VERIFY' AND analysis_run_id IS NOT NULL) OR (task_kind IN ('PLAN_DRAFT','PLAN_REFINE') AND planning_run_id IS NOT NULL)")
    op.drop_table("delivery_claim_proposal_runs")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='delivery-claims'")
