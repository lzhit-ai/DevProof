"""Stage project/member and task/cycle management ownership."""

from alembic import op

revision = "047_java_project_tasks"
down_revision = "046_java_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('projects','PYTHON'),('task-management','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_management_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key=TG_ARGV[0] FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Management aggregate is owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table,aggregate in [("projects","projects"),("project_members","projects"),("verification_tasks","task-management"),("verification_cycles","task-management")]:
        op.execute(f"CREATE TRIGGER {table}_management_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_management_writer('{aggregate}')")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key IN ('projects','task-management') AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand management ownership back before removing guards'; END IF; END $$""")
    for table in ["projects","project_members","verification_tasks","verification_cycles"]:
        op.execute(f"DROP TRIGGER {table}_management_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_management_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key IN ('projects','task-management')")
