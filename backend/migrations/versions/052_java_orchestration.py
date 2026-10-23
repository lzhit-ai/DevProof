"""Stage orchestration ownership and preserve the exact bytes of new frozen configurations."""
from alembic import op
import sqlalchemy as sa

revision = "052_java_orchestration"
down_revision = "051_java_knowledge_sources"
branch_labels = None
depends_on = None
_TABLES = ["agent_tools","agent_capabilities","agent_capability_versions","orchestration_templates","orchestration_template_nodes","task_orchestration_bindings"]


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('orchestration','PYTHON')")
    op.add_column("analysis_run_orchestration_snapshots",sa.Column("raw_body",sa.Text()))
    op.create_check_constraint("ck_orchestration_raw_body","analysis_run_orchestration_snapshots",
        "raw_body IS NULL OR (raw_body::jsonb=jsonb_build_object('template',template_snapshot,'nodes',nodes_snapshot) "
        "AND content_hash='sha256:'||encode(sha256(convert_to(raw_body,'UTF8')),'hex'))")
    op.execute("""CREATE FUNCTION devproof_guard_orchestration_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='orchestration' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Orchestration is owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
        END; $$""")
    for table in _TABLES:
        op.execute(f"CREATE TRIGGER {table}_orchestration_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_orchestration_writer()")
    op.execute("""CREATE FUNCTION devproof_preserve_capability_version() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Capability versions are immutable'; END IF; RETURN OLD;
      END; $$""")
    op.execute("CREATE TRIGGER capability_version_immutable BEFORE UPDATE ON agent_capability_versions FOR EACH ROW EXECUTE FUNCTION devproof_preserve_capability_version()")
    op.execute("""CREATE FUNCTION devproof_preserve_orchestration_body() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Run orchestration snapshots are immutable'; END IF; RETURN OLD;
      END; $$""")
    op.execute("CREATE TRIGGER run_orchestration_immutable BEFORE UPDATE ON analysis_run_orchestration_snapshots FOR EACH ROW EXECUTE FUNCTION devproof_preserve_orchestration_body()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='orchestration' AND owner='JAVA') THEN
      RAISE EXCEPTION 'Hand orchestration ownership back before removing guards'; END IF; END $$""")
    op.execute("DROP TRIGGER run_orchestration_immutable ON analysis_run_orchestration_snapshots")
    op.execute("DROP FUNCTION devproof_preserve_orchestration_body()")
    op.execute("DROP TRIGGER capability_version_immutable ON agent_capability_versions")
    op.execute("DROP FUNCTION devproof_preserve_capability_version()")
    for table in _TABLES:op.execute(f"DROP TRIGGER {table}_orchestration_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_orchestration_writer()")
    op.drop_constraint("ck_orchestration_raw_body","analysis_run_orchestration_snapshots",type_="check")
    op.drop_column("analysis_run_orchestration_snapshots","raw_body")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='orchestration'")
