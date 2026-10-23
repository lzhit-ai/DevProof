"""Own evidence-question inputs, informational answers and their model-call audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "057_java_evidence_questions"
down_revision = "056_java_delivery_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('evidence-questions','PYTHON')")
    op.create_table("evidence_question_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("snapshot_id", uuid, sa.ForeignKey("input_snapshots.id"), nullable=False),
        sa.Column("created_by", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(80), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_evidence_question_status"),
        sa.CheckConstraint("input_hash='sha256:' || encode(sha256(convert_to(input_json,'UTF8')),'hex') AND jsonb_typeof(input_json::jsonb)='object'", name="ck_evidence_question_input_hash"))
    op.add_column("agent_tasks", sa.Column("question_run_id", uuid, sa.ForeignKey("evidence_question_runs.id")))
    op.drop_constraint("ck_agent_task_business_ref", "agent_tasks", type_="check")
    op.drop_constraint("ck_agent_task_run_kind", "agent_tasks", type_="check")
    op.create_check_constraint("ck_agent_task_business_ref", "agent_tasks", "num_nonnulls(analysis_run_id,planning_run_id,claim_proposal_run_id,question_run_id)=1")
    op.create_check_constraint("ck_agent_task_run_kind", "agent_tasks", "(task_kind='DELIVERY_VERIFY' AND analysis_run_id IS NOT NULL) OR (task_kind IN ('PLAN_DRAFT','PLAN_REFINE') AND planning_run_id IS NOT NULL) OR (task_kind='DELIVERY_CLAIM_PROPOSE' AND claim_proposal_run_id IS NOT NULL) OR (task_kind='EVIDENCE_QUESTION' AND question_run_id IS NOT NULL)")
    op.create_index("uq_agent_task_evidence_question", "agent_tasks", ["question_run_id"], unique=True, postgresql_where=sa.text("question_run_id IS NOT NULL"))
    op.execute("""CREATE FUNCTION devproof_guard_evidence_question_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Evidence questions are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP='UPDATE' THEN
          IF ROW(OLD.id,OLD.project_id,OLD.snapshot_id,OLD.created_by,OLD.input_json,OLD.input_hash,OLD.created_at)
             IS DISTINCT FROM ROW(NEW.id,NEW.project_id,NEW.snapshot_id,NEW.created_by,NEW.input_json,NEW.input_hash,NEW.created_at)
          THEN RAISE EXCEPTION 'Question inputs are immutable'; END IF;
          IF OLD.status IN ('SUCCEEDED','FAILED','CANCELLED') THEN RAISE EXCEPTION 'Terminal question runs are immutable'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    op.execute("CREATE TRIGGER evidence_question_runs_question_writer BEFORE INSERT OR UPDATE OR DELETE ON evidence_question_runs FOR EACH ROW EXECUTE FUNCTION devproof_guard_evidence_question_writer()")
    op.execute("""CREATE FUNCTION devproof_guard_question_model_call_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        IF TG_OP='INSERT' THEN IF NEW.operation<>'EVIDENCE_QA' THEN RETURN NEW; END IF;
        ELSIF TG_OP='UPDATE' THEN IF OLD.operation<>'EVIDENCE_QA' AND NEW.operation<>'EVIDENCE_QA' THEN RETURN NEW; END IF;
        ELSE IF OLD.operation<>'EVIDENCE_QA' THEN RETURN OLD; END IF; END IF;
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Question model-call audit is owned by Java'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    op.execute("CREATE TRIGGER model_calls_question_writer BEFORE INSERT OR UPDATE OR DELETE ON model_calls FOR EACH ROW EXECUTE FUNCTION devproof_guard_question_model_call_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='evidence-questions' AND owner='JAVA') OR EXISTS(SELECT 1 FROM evidence_question_runs)
      THEN RAISE EXCEPTION 'Retain question history and hand ownership back before downgrade'; END IF;
    END $$""")
    op.execute("DROP TRIGGER model_calls_question_writer ON model_calls")
    op.execute("DROP FUNCTION devproof_guard_question_model_call_writer()")
    op.execute("DROP TRIGGER evidence_question_runs_question_writer ON evidence_question_runs")
    op.execute("DROP FUNCTION devproof_guard_evidence_question_writer()")
    op.drop_index("uq_agent_task_evidence_question", "agent_tasks")
    op.drop_constraint("ck_agent_task_run_kind", "agent_tasks", type_="check")
    op.drop_constraint("ck_agent_task_business_ref", "agent_tasks", type_="check")
    op.drop_column("agent_tasks", "question_run_id")
    op.create_check_constraint("ck_agent_task_business_ref", "agent_tasks", "num_nonnulls(analysis_run_id,planning_run_id,claim_proposal_run_id)=1")
    op.create_check_constraint("ck_agent_task_run_kind", "agent_tasks", "(task_kind='DELIVERY_VERIFY' AND analysis_run_id IS NOT NULL) OR (task_kind IN ('PLAN_DRAFT','PLAN_REFINE') AND planning_run_id IS NOT NULL) OR (task_kind='DELIVERY_CLAIM_PROPOSE' AND claim_proposal_run_id IS NOT NULL)")
    op.drop_table("evidence_question_runs")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='evidence-questions'")
