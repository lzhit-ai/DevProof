"""Stage the single GitHub source writer and record the executor of a sync run."""

from alembic import op
import sqlalchemy as sa

revision = "048_java_github_sources"
down_revision = "047_java_project_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('github-sources','PYTHON')")
    op.add_column("source_sync_runs",sa.Column("executor_owner",sa.String(16),nullable=False,server_default="PYTHON"))
    op.create_check_constraint("ck_source_sync_executor_owner","source_sync_runs","executor_owner IN ('PYTHON','JAVA')")
    op.execute("""CREATE FUNCTION devproof_guard_github_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='github-sources' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'GitHub sources are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["external_connections","source_sync_runs","external_resources","external_resource_revisions","delivery_items","delivery_item_source_links"]:
        op.execute(f"CREATE TRIGGER {table}_github_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_github_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='github-sources' AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand GitHub ownership back before removing guards'; END IF; END $$""")
    for table in ["external_connections","source_sync_runs","external_resources","external_resource_revisions","delivery_items","delivery_item_source_links"]:
        op.execute(f"DROP TRIGGER {table}_github_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_github_writer()")
    op.drop_constraint("ck_source_sync_executor_owner","source_sync_runs",type_="check")
    op.drop_column("source_sync_runs","executor_owner")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='github-sources'")
