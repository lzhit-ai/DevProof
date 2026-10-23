"""Stage Java source ingestion and derived-index ownership with fenced durable jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "051_java_knowledge_sources"
down_revision = "050_java_knowledge_bases"
branch_labels = None
depends_on = None
_TABLES = ["source_revisions","source_ingestion_jobs","document_chunks","project_retrieval_indexes","retrieval_index_build_runs"]


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('knowledge-sources','PYTHON')")
    op.add_column("source_revisions",sa.Column("normalized_text_hash",sa.String(80)))
    for table in ["source_ingestion_jobs","retrieval_index_build_runs"]:
        op.add_column(table,sa.Column("executor_owner",sa.String(16),nullable=False,server_default="PYTHON"))
        op.add_column(table,sa.Column("compute_configuration",postgresql.JSONB()))
        op.add_column(table,sa.Column("configuration_hash",sa.String(80)))
        op.create_check_constraint(f"ck_{table}_executor",table,"executor_owner IN ('PYTHON','JAVA')")
        op.create_check_constraint(f"ck_{table}_configuration",table,"(compute_configuration IS NULL)=(configuration_hash IS NULL)")
    for column in ["lease_owner","last_error_code"]:
        op.add_column("retrieval_index_build_runs",sa.Column(column,sa.String(160 if column=="lease_owner" else 64)))
    for column in ["lease_expires_at","heartbeat_at","available_at"]:
        op.add_column("retrieval_index_build_runs",sa.Column(column,sa.DateTime(timezone=True)))
    op.add_column("retrieval_index_build_runs",sa.Column("attempt_no",sa.Integer(),nullable=False,server_default="0"))
    op.add_column("retrieval_index_build_runs",sa.Column("max_attempts",sa.Integer(),nullable=False,server_default="3"))
    op.add_column("retrieval_index_build_runs",sa.Column("input_manifest",postgresql.JSONB()))
    op.execute("""CREATE FUNCTION devproof_guard_knowledge_source_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Knowledge sources are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    for table in _TABLES:
        op.execute(f"CREATE TRIGGER {table}_source_writer BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_guard_knowledge_source_writer()")
    op.execute("""CREATE FUNCTION devproof_preserve_ready_source() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF (SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE)<>'JAVA' THEN RETURN NEW; END IF;
      IF ROW(OLD.project_id,OLD.source_role,OLD.logical_name,OLD.revision_no,OLD.content_hash,OLD.artifact_uri,OLD.original_filename,OLD.media_type,OLD.knowledge_base_id,OLD.force_ocr)
          IS DISTINCT FROM ROW(NEW.project_id,NEW.source_role,NEW.logical_name,NEW.revision_no,NEW.content_hash,NEW.artifact_uri,NEW.original_filename,NEW.media_type,NEW.knowledge_base_id,NEW.force_ocr)
      THEN RAISE EXCEPTION 'Source version identity is immutable'; END IF;
      IF OLD.processing_status='READY' AND ROW(OLD.processing_status,OLD.extracted_artifact_uri,OLD.normalized_text_hash,OLD.extraction_metadata,OLD.parser_version,OLD.ocr_confidence)
          IS DISTINCT FROM ROW(NEW.processing_status,NEW.extracted_artifact_uri,NEW.normalized_text_hash,NEW.extraction_metadata,NEW.parser_version,NEW.ocr_confidence)
      THEN RAISE EXCEPTION 'Ready source content is immutable'; END IF;
      RETURN NEW; END; $$""")
    op.execute("CREATE TRIGGER source_revision_identity BEFORE UPDATE ON source_revisions FOR EACH ROW EXECUTE FUNCTION devproof_preserve_ready_source()")
    op.execute("""CREATE FUNCTION devproof_preserve_source_compute_config() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.configuration_hash IS NOT NULL AND ROW(OLD.configuration_hash,OLD.compute_configuration) IS DISTINCT FROM ROW(NEW.configuration_hash,NEW.compute_configuration)
      THEN RAISE EXCEPTION 'Compute job configuration is immutable'; END IF;
      IF TG_TABLE_NAME='source_ingestion_jobs' THEN
        IF ROW(OLD.source_revision_id,OLD.requested_by) IS DISTINCT FROM ROW(NEW.source_revision_id,NEW.requested_by)
        THEN RAISE EXCEPTION 'Source ingestion identity is immutable'; END IF;
      ELSE
        IF ROW(OLD.project_id,OLD.target_index_version,OLD.created_by,OLD.input_manifest) IS DISTINCT FROM ROW(NEW.project_id,NEW.target_index_version,NEW.created_by,NEW.input_manifest)
        THEN RAISE EXCEPTION 'Index build input is immutable'; END IF;
      END IF; RETURN NEW; END; $$""")
    for table in ["source_ingestion_jobs","retrieval_index_build_runs"]:
        op.execute(f"CREATE TRIGGER {table}_compute_config BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION devproof_preserve_source_compute_config()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='knowledge-sources' AND owner='JAVA') THEN
      RAISE EXCEPTION 'Hand source ownership back before removing guards'; END IF; END $$""")
    for table in ["source_ingestion_jobs","retrieval_index_build_runs"]:
        op.execute(f"DROP TRIGGER {table}_compute_config ON {table}")
    op.execute("DROP FUNCTION devproof_preserve_source_compute_config()")
    op.execute("DROP TRIGGER source_revision_identity ON source_revisions")
    op.execute("DROP FUNCTION devproof_preserve_ready_source()")
    for table in _TABLES:op.execute(f"DROP TRIGGER {table}_source_writer ON {table}")
    op.execute("DROP FUNCTION devproof_guard_knowledge_source_writer()")
    for column in ["input_manifest","max_attempts","attempt_no","available_at","heartbeat_at","lease_expires_at","last_error_code","lease_owner"]:
        op.drop_column("retrieval_index_build_runs",column)
    for table in ["source_ingestion_jobs","retrieval_index_build_runs"]:
        op.drop_constraint(f"ck_{table}_configuration",table,type_="check")
        op.drop_constraint(f"ck_{table}_executor",table,type_="check")
        for column in ["configuration_hash","compute_configuration","executor_owner"]:op.drop_column(table,column)
    op.drop_column("source_revisions","normalized_text_hash")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='knowledge-sources'")
