"""Hand project-health snapshots and personally confirmed summaries to Java."""
from alembic import op

revision = "058_java_project_status"
down_revision = "057_java_evidence_questions"
branch_labels = None
depends_on = None

TABLES = ("project_health_snapshots", "project_summary_drafts", "project_summary_records")


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('project-status','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_project_status_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='project-status' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Project status is owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP<>'INSERT' THEN
          IF TG_TABLE_NAME<>'project_summary_drafts' OR TG_OP='DELETE' THEN RAISE EXCEPTION 'Project-status snapshots and records are immutable'; END IF;
          IF OLD.draft_status<>'DRAFT' OR NEW.draft_status<>'PUBLISHED'
            OR (to_jsonb(OLD)-ARRAY['draft_status','updated_at']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['draft_status','updated_at'])
          THEN RAISE EXCEPTION 'Summary publication cannot rewrite its identity or frozen content'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_status_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_project_status_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='project-status' AND owner='JAVA')
      THEN RAISE EXCEPTION 'Hand project-status ownership back before downgrade'; END IF;
    END $$""")
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_status_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_project_status_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='project-status'")
