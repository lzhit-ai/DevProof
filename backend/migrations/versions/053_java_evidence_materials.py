"""Stage append-only human and external evidence material ownership."""
from alembic import op

revision = "053_java_evidence_materials"
down_revision = "052_java_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('evidence-materials','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_evidence_material_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-materials' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Evidence materials are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP='UPDATE' THEN RAISE EXCEPTION 'Evidence materials are immutable'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in ["manual_evidence","external_evidence"]:
        op.execute(f"CREATE TRIGGER {table}_material_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_evidence_material_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='evidence-materials' AND owner='JAVA') THEN
      RAISE EXCEPTION 'Hand evidence material ownership back before removing guards'; END IF; END $$""")
    for table in ["manual_evidence","external_evidence"]:op.execute(f"DROP TRIGGER {table}_material_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_evidence_material_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='evidence-materials'")
