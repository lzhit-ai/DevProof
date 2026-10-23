"""Stage delivery association ownership and preserve confirmed links and proposal inputs."""
from alembic import op

revision = "055_java_delivery_associations"
down_revision = "054_java_git_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('delivery-associations','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_delivery_association_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='delivery-associations' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Delivery associations are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP='UPDATE' THEN
          IF TG_TABLE_NAME='agent_change_proposal_runs' THEN RAISE EXCEPTION 'Association proposal runs are immutable'; END IF;
          IF OLD.link_status='CONFIRMED' OR NEW.link_status<>'CONFIRMED' THEN RAISE EXCEPTION 'Only candidate confirmation is allowed'; END IF;
          IF ROW(OLD.id,OLD.delivery_item_id,OLD.pull_request_resource_id,OLD.git_snapshot_id,OLD.agent_proposal_run_id,OLD.created_by,OLD.created_at)
             IS DISTINCT FROM ROW(NEW.id,NEW.delivery_item_id,NEW.pull_request_resource_id,NEW.git_snapshot_id,NEW.agent_proposal_run_id,NEW.created_by,NEW.created_at)
          THEN RAISE EXCEPTION 'Association identity and proposal provenance are immutable'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in ["delivery_change_links", "agent_change_proposal_runs"]:
        op.execute(f"CREATE TRIGGER {table}_association_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_delivery_association_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='delivery-associations' AND owner='JAVA') THEN
      RAISE EXCEPTION 'Hand association ownership back before removing guards'; END IF; END $$""")
    for table in ["delivery_change_links", "agent_change_proposal_runs"]:
        op.execute(f"DROP TRIGGER {table}_association_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_delivery_association_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='delivery-associations'")
