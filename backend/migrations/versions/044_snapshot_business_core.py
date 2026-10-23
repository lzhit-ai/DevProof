"""Persist replayable Java snapshot bodies; stage input ownership for P4 cutover."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "044_snapshot_business_core"
down_revision = "043_java_report_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('verification-inputs','PYTHON')")
    op.create_unique_constraint("uq_snapshot_body_identity", "input_snapshots", ["id", "snapshot_hash"])
    op.create_table("input_snapshot_bodies",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["snapshot_id", "content_hash"], ["input_snapshots.id", "input_snapshots.snapshot_hash"]))
    op.execute("""CREATE FUNCTION devproof_guard_input_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='verification-inputs' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS NULL OR expected<>writer THEN RAISE EXCEPTION 'Verification input is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["input_snapshots", "input_snapshot_bodies", "input_snapshot_claims", "input_snapshot_sources",
                  "input_snapshot_git", "input_snapshot_external_evidence", "input_snapshot_manual_evidence", "input_snapshot_plans"]:
        op.execute(f"""CREATE TRIGGER {table}_writer_guard BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_guard_input_writer()""")
    op.execute("""CREATE FUNCTION devproof_validate_snapshot_body() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE snapshot input_snapshots%ROWTYPE; body jsonb;
        BEGIN
          SELECT * INTO snapshot FROM input_snapshots WHERE id=NEW.snapshot_id;
          body:=NEW.body_json::jsonb;
          IF NEW.schema_version<>'verification-input-v2' OR body->>'schemaVersion' IS DISTINCT FROM NEW.schema_version
            OR body->>'cycleId' IS DISTINCT FROM snapshot.cycle_id::text
            OR body->>'purpose' IS DISTINCT FROM snapshot.purpose THEN
              RAISE EXCEPTION 'Frozen input body does not match its snapshot';
          END IF;
          IF EXISTS(SELECT 1 FROM analysis_runs WHERE snapshot_id=NEW.snapshot_id) THEN
            RAISE EXCEPTION 'Cannot attach a new body after analysis has started';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER snapshot_body_scope BEFORE INSERT ON input_snapshot_bodies
        FOR EACH ROW EXECUTE FUNCTION devproof_validate_snapshot_body()""")
    op.execute("""CREATE FUNCTION devproof_immutable_snapshot_body() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Frozen snapshot body is immutable'; END; $$""")
    op.execute("""CREATE TRIGGER snapshot_body_immutable BEFORE UPDATE OR DELETE ON input_snapshot_bodies
        FOR EACH ROW EXECUTE FUNCTION devproof_immutable_snapshot_body()""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='verification-inputs' AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand input ownership back before removing writer guards'; END IF; END $$""")
    for table in ["input_snapshots", "input_snapshot_bodies", "input_snapshot_claims", "input_snapshot_sources",
                  "input_snapshot_git", "input_snapshot_external_evidence", "input_snapshot_manual_evidence", "input_snapshot_plans"]:
        op.execute(f"DROP TRIGGER {table}_writer_guard ON {table}")
    op.execute("DROP FUNCTION devproof_guard_input_writer()")
    op.drop_table("input_snapshot_bodies")
    op.execute("DROP FUNCTION devproof_immutable_snapshot_body()")
    op.execute("DROP FUNCTION devproof_validate_snapshot_body()")
    op.drop_constraint("uq_snapshot_body_identity", "input_snapshots", type_="unique")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='verification-inputs'")
