"""Own SHA-bound imported security facts and deterministic peripheral projections."""
from alembic import op

revision = "059_java_security_profiles"
down_revision = "058_java_project_status"
branch_labels = None
depends_on = None

TABLES = ("security_scan_artifacts", "security_findings", "security_baseline_snapshots", "security_baseline_records", "peripheral_profile_runs")


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('security-baselines','PYTHON'),('peripheral-profiles','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_security_profile_writer() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE expected text; writer text; aggregate text;
      BEGIN
        aggregate:=CASE WHEN TG_TABLE_NAME='peripheral_profile_runs' THEN 'peripheral-profiles' ELSE 'security-baselines' END;
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key=aggregate FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Security/profile facts are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP<>'INSERT' THEN
          IF TG_TABLE_NAME<>'security_findings' OR TG_OP='DELETE' THEN RAISE EXCEPTION 'Imported scanner inputs, baselines, records and projections are immutable'; END IF;
          IF (to_jsonb(OLD)-ARRAY['finding_status','status_reason','status_updated_by','status_updated_at','updated_at'])
             IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['finding_status','status_reason','status_updated_by','status_updated_at','updated_at'])
          THEN RAISE EXCEPTION 'Finding disposition cannot rewrite imported scanner facts'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$""")
    for table in TABLES:
        op.execute(f"CREATE TRIGGER {table}_security_profile_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_security_profile_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key IN ('security-baselines','peripheral-profiles') AND owner='JAVA')
      THEN RAISE EXCEPTION 'Hand security/profile ownership back before downgrade'; END IF;
    END $$""")
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_security_profile_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_security_profile_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key IN ('security-baselines','peripheral-profiles')")
