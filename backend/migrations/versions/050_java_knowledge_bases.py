"""Stage knowledge-base and mount membership ownership."""
from alembic import op

revision = "050_java_knowledge_bases"
down_revision = "049_retrieval_version_capacity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('knowledge-bases','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_knowledge_base_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='knowledge-bases' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Knowledge bases are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["knowledge_bases","project_knowledge_bases"]:
        op.execute(f"CREATE TRIGGER {table}_java_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_knowledge_base_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='knowledge-bases' AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand knowledge-base ownership back before removing guards'; END IF; END $$""")
    for table in ["knowledge_bases","project_knowledge_bases"]:
        op.execute(f"DROP TRIGGER {table}_java_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_knowledge_base_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='knowledge-bases'")
