"""Coordinate the single report writer and durable automatic draft requests."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "043_java_report_ownership"
down_revision = "042_plan_verification_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table("business_write_owners",
        sa.Column("aggregate_key", sa.String(64), primary_key=True),
        sa.Column("owner", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("owner IN ('PYTHON','JAVA')", name="ck_business_write_owner"))
    # This is deployment ownership configuration, not a business seed.
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('reports','PYTHON')")
    op.create_table("report_generation_jobs",
        sa.Column("run_id", uuid, sa.ForeignKey("analysis_runs.id"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("report_id", uuid, sa.ForeignKey("report_versions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING','SUCCEEDED','FAILED')", name="ck_report_generation_job"))
    op.create_index("ix_report_generation_pending", "report_generation_jobs", ["available_at"],
                    postgresql_where=sa.text("status='PENDING'"))
    op.execute("""CREATE FUNCTION devproof_guard_report_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='reports' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS NULL OR expected<>writer THEN RAISE EXCEPTION 'Report aggregate is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["report_versions", "report_items", "approval_actions", "published_records", "published_report_bodies", "human_verification_decisions"]:
        op.execute(f"""CREATE TRIGGER {table}_writer_guard BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_guard_report_writer()""")
    op.execute("""CREATE FUNCTION devproof_append_only_report_fact() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Published records and human/approval decisions are append-only'; END; $$""")
    for table in ["approval_actions", "published_records", "human_verification_decisions"]:
        op.execute(f"""CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_append_only_report_fact()""")
    op.execute("""CREATE FUNCTION devproof_guard_published_report() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE cycle uuid;
        BEGIN
          IF TG_TABLE_NAME='report_versions' THEN
            IF TG_OP='DELETE' THEN cycle:=OLD.cycle_id; ELSE cycle:=NEW.cycle_id; END IF;
            IF TG_OP<>'INSERT' THEN
              IF OLD.status='PUBLISHED' THEN RAISE EXCEPTION 'Published report is immutable'; END IF;
              IF TG_OP='UPDATE' AND NEW.cycle_id<>OLD.cycle_id THEN RAISE EXCEPTION 'Report cycle is immutable'; END IF;
            END IF;
          ELSE
            IF TG_OP='UPDATE' AND NEW.report_version_id<>OLD.report_version_id THEN RAISE EXCEPTION 'Report item parent is immutable'; END IF;
            IF TG_OP='DELETE' THEN SELECT cycle_id INTO cycle FROM report_versions WHERE id=OLD.report_version_id;
            ELSE SELECT cycle_id INTO cycle FROM report_versions WHERE id=NEW.report_version_id; END IF;
          END IF;
          IF EXISTS(SELECT 1 FROM verification_cycles WHERE id=cycle AND business_status='PUBLISHED') THEN
            RAISE EXCEPTION 'Published cycle reports are immutable';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in ["report_versions", "report_items"]:
        op.execute(f"""CREATE TRIGGER {table}_publication_guard BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION devproof_guard_published_report()""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE owner='JAVA') THEN
        RAISE EXCEPTION 'Explicitly hand ownership back before removing writer guards'; END IF; END $$""")
    for table in ["report_versions", "report_items"]:
        op.execute(f"DROP TRIGGER {table}_publication_guard ON {table}")
    op.execute("DROP FUNCTION devproof_guard_published_report()")
    for table in ["approval_actions", "published_records", "human_verification_decisions"]:
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION devproof_append_only_report_fact()")
    for table in ["report_versions", "report_items", "approval_actions", "published_records", "published_report_bodies", "human_verification_decisions"]:
        op.execute(f"DROP TRIGGER {table}_writer_guard ON {table}")
    op.execute("DROP FUNCTION devproof_guard_report_writer()")
    op.drop_table("report_generation_jobs")
    op.drop_table("business_write_owners")
