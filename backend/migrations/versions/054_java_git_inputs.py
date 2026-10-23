"""Stage repository registration and immutable Git capture ownership."""
from alembic import op

revision = "054_java_git_inputs"
down_revision = "053_java_evidence_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('git-inputs','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_git_input_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='git-inputs' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Git inputs are owned by Java'; END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='git_snapshots' AND TG_OP='UPDATE' THEN RAISE EXCEPTION 'Git snapshots are immutable'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in ["git_repositories", "git_snapshots"]:
        op.execute(f"CREATE TRIGGER {table}_git_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_git_input_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='git-inputs' AND owner='JAVA') THEN
      RAISE EXCEPTION 'Hand Git input ownership back before removing guards'; END IF; END $$""")
    for table in ["git_repositories", "git_snapshots"]:
        op.execute(f"DROP TRIGGER {table}_git_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_git_input_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='git-inputs'")
