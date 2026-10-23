"""Stage the Java delivery writer and attempt-scoped model audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "045_verification_execution"
down_revision = "044_snapshot_business_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('verification','PYTHON')")
    op.add_column("analysis_runs",sa.Column("executor_owner",sa.String(16),nullable=False,server_default="PYTHON"))
    op.add_column("model_calls",sa.Column("usage",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.create_check_constraint("ck_analysis_executor_owner","analysis_runs","executor_owner IN ('PYTHON','JAVA')")
    op.add_column("model_calls",sa.Column("agent_task_attempt_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("agent_task_attempts.id")))
    op.execute("""CREATE FUNCTION devproof_guard_verification_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text; run uuid; profile text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='verification' FOR SHARE;
          IF expected='JAVA' THEN
            writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
            IF TG_TABLE_NAME='analysis_runs' THEN
              IF TG_OP='DELETE' THEN profile:=OLD.assessment_profile; ELSE profile:=NEW.assessment_profile; END IF;
            ELSIF TG_TABLE_NAME='evidence_items' THEN profile:='DELIVERY_VERIFICATION';
            ELSIF TG_TABLE_NAME='claim_evidence_links' THEN
              IF TG_OP='DELETE' THEN SELECT analysis_run_id INTO run FROM claims WHERE id=OLD.claim_id;
              ELSE SELECT analysis_run_id INTO run FROM claims WHERE id=NEW.claim_id; END IF;
            ELSIF TG_TABLE_NAME IN ('analysis_run_manifests','analysis_run_orchestration_snapshots','model_calls','run_events') THEN
              IF TG_OP='DELETE' THEN run:=OLD.run_id; ELSE run:=NEW.run_id; END IF;
            ELSE
              IF TG_OP='DELETE' THEN run:=OLD.analysis_run_id; ELSE run:=NEW.analysis_run_id; END IF;
            END IF;
            IF profile IS NULL AND run IS NOT NULL THEN SELECT assessment_profile INTO profile FROM analysis_runs WHERE id=run; END IF;
            IF profile='DELIVERY_VERIFICATION' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Delivery verification is owned by Java'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["analysis_runs","claims","evidence_items","claim_evidence_links","verification_results","code_review_findings",
                  "code_review_finding_challenges","risk_findings","analysis_coverages","node_attempts","analysis_run_manifests",
                  "analysis_run_orchestration_snapshots","analysis_run_context_artifacts","model_calls","run_events","agent_tool_executions"]:
        op.execute(f"""CREATE TRIGGER {table}_verification_writer BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_guard_verification_writer()""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='verification' AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand verification ownership back before removing guards'; END IF; END $$""")
    for table in ["analysis_runs","claims","evidence_items","claim_evidence_links","verification_results","code_review_findings",
                  "code_review_finding_challenges","risk_findings","analysis_coverages","node_attempts","analysis_run_manifests",
                  "analysis_run_orchestration_snapshots","analysis_run_context_artifacts","model_calls","run_events","agent_tool_executions"]:
        op.execute(f"DROP TRIGGER {table}_verification_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_verification_writer()")
    op.drop_column("model_calls","agent_task_attempt_id")
    op.drop_column("model_calls","usage")
    op.drop_constraint("ck_analysis_executor_owner","analysis_runs",type_="check")
    op.drop_column("analysis_runs","executor_owner")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='verification'")
