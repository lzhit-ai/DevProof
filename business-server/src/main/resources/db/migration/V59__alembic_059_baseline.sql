-- Structural baseline exported from the reviewed Alembic 059 database.
-- Contains schema and writer metadata only; no business rows.
--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: devproof_append_only_report_fact(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_append_only_report_fact() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'Published records and human/approval decisions are append-only'; END; $$;


--
-- Name: devproof_confirmed_plan_immutable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_confirmed_plan_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF OLD.status IN ('CONFIRMED','SUPERSEDED') THEN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Confirmed plan is immutable'; END IF;
            IF NEW.status NOT IN ('CONFIRMED','SUPERSEDED') THEN RAISE EXCEPTION 'Confirmed plan cannot return to draft'; END IF;
            IF ROW(OLD.id,OLD.body_json,OLD.content_hash,OLD.idea_revision_id,OLD.planning_run_id,OLD.version,OLD.confirmed_by,OLD.confirmed_at,OLD.sequence_no,OLD.parent_plan_id,OLD.created_by,OLD.created_at)
                IS DISTINCT FROM ROW(NEW.id,NEW.body_json,NEW.content_hash,NEW.idea_revision_id,NEW.planning_run_id,NEW.version,NEW.confirmed_by,NEW.confirmed_at,NEW.sequence_no,NEW.parent_plan_id,NEW.created_by,NEW.created_at)
              THEN RAISE EXCEPTION 'Confirmed plan content is immutable'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_delivery_association_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_delivery_association_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
      END; $$;


--
-- Name: devproof_guard_delivery_claim_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_delivery_claim_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='delivery-claims' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Delivery claims are owned by Java'; END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='delivery_claim_proposal_runs' AND TG_OP='UPDATE' THEN
          IF ROW(OLD.id,OLD.project_id,OLD.task_id,OLD.cycle_id,OLD.input_json,OLD.input_hash,OLD.source_manifest,OLD.created_by,OLD.created_at)
             IS DISTINCT FROM ROW(NEW.id,NEW.project_id,NEW.task_id,NEW.cycle_id,NEW.input_json,NEW.input_hash,NEW.source_manifest,NEW.created_by,NEW.created_at)
          THEN RAISE EXCEPTION 'Claim proposal inputs are immutable'; END IF;
        END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='delivery_claim_drafts' AND TG_OP IN ('INSERT','UPDATE') THEN
          IF EXISTS(SELECT 1 FROM input_snapshots WHERE cycle_id=NEW.cycle_id AND purpose='FORMAL')
          THEN RAISE EXCEPTION 'Claims cannot change after formal input freeze'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_evidence_material_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_evidence_material_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-materials' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Evidence materials are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP='UPDATE' THEN RAISE EXCEPTION 'Evidence materials are immutable'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_evidence_question_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_evidence_question_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Evidence questions are owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP='UPDATE' THEN
          IF ROW(OLD.id,OLD.project_id,OLD.snapshot_id,OLD.created_by,OLD.input_json,OLD.input_hash,OLD.created_at)
             IS DISTINCT FROM ROW(NEW.id,NEW.project_id,NEW.snapshot_id,NEW.created_by,NEW.input_json,NEW.input_hash,NEW.created_at)
          THEN RAISE EXCEPTION 'Question inputs are immutable'; END IF;
          IF OLD.status IN ('SUCCEEDED','FAILED','CANCELLED') THEN RAISE EXCEPTION 'Terminal question runs are immutable'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_git_input_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_git_input_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='git-inputs' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Git inputs are owned by Java'; END IF;
        IF expected='JAVA' AND TG_TABLE_NAME='git_snapshots' AND TG_OP='UPDATE' THEN RAISE EXCEPTION 'Git snapshots are immutable'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_github_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_github_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='github-sources' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'GitHub sources are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_identity_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_identity_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='identity' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS DISTINCT FROM writer THEN RAISE EXCEPTION 'Identity aggregate is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_input_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_input_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='verification-inputs' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS NULL OR expected<>writer THEN RAISE EXCEPTION 'Verification input is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_knowledge_base_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_knowledge_base_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='knowledge-bases' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Knowledge bases are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_knowledge_source_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_knowledge_source_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Knowledge sources are owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_management_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_management_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key=TG_ARGV[0] FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Management aggregate is owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_orchestration_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_orchestration_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='orchestration' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Orchestration is owned by Java'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_plan_selection(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_plan_selection() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE cycle uuid;
        BEGIN
          IF TG_OP='DELETE' THEN cycle:=OLD.cycle_id; ELSE cycle:=NEW.cycle_id; END IF;
          IF TG_OP='UPDATE' AND OLD.cycle_id<>NEW.cycle_id THEN RAISE EXCEPTION 'Selection cycle is immutable'; END IF;
          PERFORM id FROM verification_cycles WHERE id=cycle FOR UPDATE;
          IF EXISTS(SELECT 1 FROM input_snapshots WHERE cycle_id=cycle AND purpose='FORMAL') THEN
            RAISE EXCEPTION 'Formal input has already frozen the plan selection';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_project_status_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_project_status_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='project-status' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Project status is owned by Java'; END IF;
        IF expected='JAVA' AND TG_OP<>'INSERT' THEN
          IF TG_TABLE_NAME<>'project_summary_drafts' OR TG_OP='DELETE' THEN RAISE EXCEPTION 'Project-status snapshots and records are immutable'; END IF;
          IF OLD.draft_status<>'DRAFT' OR NEW.draft_status<>'PUBLISHED'
            OR (to_jsonb(OLD)-ARRAY['draft_status','updated_at']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['draft_status','updated_at'])
          THEN RAISE EXCEPTION 'Summary publication cannot rewrite its identity or frozen content'; END IF;
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_published_report(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_published_report() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
        END; $$;


--
-- Name: devproof_guard_question_model_call_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_question_model_call_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
      DECLARE expected text; writer text;
      BEGIN
        IF TG_OP='INSERT' THEN IF NEW.operation<>'EVIDENCE_QA' THEN RETURN NEW; END IF;
        ELSIF TG_OP='UPDATE' THEN IF OLD.operation<>'EVIDENCE_QA' AND NEW.operation<>'EVIDENCE_QA' THEN RETURN NEW; END IF;
        ELSE IF OLD.operation<>'EVIDENCE_QA' THEN RETURN OLD; END IF; END IF;
        SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR SHARE;
        writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
        IF expected='JAVA' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Question model-call audit is owned by Java'; END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
      END; $$;


--
-- Name: devproof_guard_report_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_report_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='reports' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS NULL OR expected<>writer THEN RAISE EXCEPTION 'Report aggregate is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_run_plan(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_run_plan() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE baseline input_snapshot_plans%ROWTYPE;
        BEGIN
          SELECT * INTO baseline FROM input_snapshot_plans WHERE snapshot_id=NEW.snapshot_id;
          IF NEW.plan_version_id IS DISTINCT FROM baseline.plan_version_id
            OR NEW.plan_baseline_hash IS DISTINCT FROM baseline.selection_hash THEN
              RAISE EXCEPTION 'Analysis plan must match its frozen input baseline';
          END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_security_profile_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_security_profile_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
      END; $$;


--
-- Name: devproof_guard_snapshot_plan(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_snapshot_plan() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF NOT EXISTS(SELECT 1 FROM input_snapshots s JOIN cycle_plan_selections p ON p.cycle_id=s.cycle_id
            JOIN cycle_plan_selection_current c ON c.cycle_id=s.cycle_id AND c.selection_id=p.id
            WHERE s.id=NEW.snapshot_id AND s.purpose='FORMAL' AND p.id=NEW.selection_id) THEN
            RAISE EXCEPTION 'Plan selection must belong to the formal snapshot cycle';
          END IF;
          IF EXISTS(SELECT 1 FROM analysis_runs WHERE snapshot_id=NEW.snapshot_id) THEN
            RAISE EXCEPTION 'Cannot attach a plan after analysis has started';
          END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_guard_verification_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_guard_verification_writer() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE expected text; writer text; run uuid; profile text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='verification' FOR SHARE;
          IF expected='JAVA' THEN
            writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
            IF TG_TABLE_NAME='analysis_runs' THEN
              IF TG_OP='DELETE' THEN profile:=OLD.assessment_profile; ELSE profile:=NEW.assessment_profile; END IF;
            ELSIF TG_TABLE_NAME='evidence_items' THEN profile:='DELIVERY_VERIFICATION';
            ELSIF TG_TABLE_NAME='claim_evidence_links' THEN
              IF TG_OP='DELETE' THEN SELECT analysis_run_id INTO run FROM claims WHERE id=OLD.claim_id;
              ELSE SELECT analysis_run_id INTO run FROM claims WHERE id=NEW.claim_id; END IF;
            ELSIF TG_TABLE_NAME IN ('analysis_run_manifests','analysis_run_orchestration_snapshots','model_calls','run_events') THEN
              IF TG_OP='DELETE' THEN run:=OLD.run_id; ELSE run:=NEW.run_id; END IF;
            ELSE
              IF TG_OP='DELETE' THEN run:=OLD.analysis_run_id; ELSE run:=NEW.analysis_run_id; END IF;
            END IF;
            IF profile IS NULL AND run IS NOT NULL THEN SELECT assessment_profile INTO profile FROM analysis_runs WHERE id=run; END IF;
            IF profile='DELIVERY_VERIFICATION' AND writer<>'JAVA' THEN RAISE EXCEPTION 'Delivery verification is owned by Java'; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$;


--
-- Name: devproof_immutable_plan_binding(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_immutable_plan_binding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'Plan verification baseline is immutable'; END; $$;


--
-- Name: devproof_immutable_repository_snapshot(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_immutable_repository_snapshot() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'Repository snapshot is immutable'; END; $$;


--
-- Name: devproof_immutable_snapshot_body(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_immutable_snapshot_body() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'Frozen snapshot body is immutable'; END; $$;


--
-- Name: devproof_preserve_capability_version(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_preserve_capability_version() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN
      IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Capability versions are immutable'; END IF; RETURN OLD;
      END; $$;


--
-- Name: devproof_preserve_orchestration_body(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_preserve_orchestration_body() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN
      IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Run orchestration snapshots are immutable'; END IF; RETURN OLD;
      END; $$;


--
-- Name: devproof_preserve_ready_source(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_preserve_ready_source() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN
      IF (SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE)<>'JAVA' THEN RETURN NEW; END IF;
      IF ROW(OLD.project_id,OLD.source_role,OLD.logical_name,OLD.revision_no,OLD.content_hash,OLD.artifact_uri,OLD.original_filename,OLD.media_type,OLD.knowledge_base_id,OLD.force_ocr)
          IS DISTINCT FROM ROW(NEW.project_id,NEW.source_role,NEW.logical_name,NEW.revision_no,NEW.content_hash,NEW.artifact_uri,NEW.original_filename,NEW.media_type,NEW.knowledge_base_id,NEW.force_ocr)
      THEN RAISE EXCEPTION 'Source version identity is immutable'; END IF;
      IF OLD.processing_status='READY' AND ROW(OLD.processing_status,OLD.extracted_artifact_uri,OLD.normalized_text_hash,OLD.extraction_metadata,OLD.parser_version,OLD.ocr_confidence)
          IS DISTINCT FROM ROW(NEW.processing_status,NEW.extracted_artifact_uri,NEW.normalized_text_hash,NEW.extraction_metadata,NEW.parser_version,NEW.ocr_confidence)
      THEN RAISE EXCEPTION 'Ready source content is immutable'; END IF;
      RETURN NEW; END; $$;


--
-- Name: devproof_preserve_source_compute_config(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_preserve_source_compute_config() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN
      IF OLD.configuration_hash IS NOT NULL AND ROW(OLD.configuration_hash,OLD.compute_configuration) IS DISTINCT FROM ROW(NEW.configuration_hash,NEW.compute_configuration)
      THEN RAISE EXCEPTION 'Compute job configuration is immutable'; END IF;
      IF TG_TABLE_NAME='source_ingestion_jobs' THEN
        IF ROW(OLD.source_revision_id,OLD.requested_by) IS DISTINCT FROM ROW(NEW.source_revision_id,NEW.requested_by)
        THEN RAISE EXCEPTION 'Source ingestion identity is immutable'; END IF;
      ELSE
        IF ROW(OLD.project_id,OLD.target_index_version,OLD.created_by,OLD.input_manifest) IS DISTINCT FROM ROW(NEW.project_id,NEW.target_index_version,NEW.created_by,NEW.input_manifest)
        THEN RAISE EXCEPTION 'Index build input is immutable'; END IF;
      END IF; RETURN NEW; END; $$;


--
-- Name: devproof_reject_body_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_reject_body_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN RAISE EXCEPTION 'Published report body is immutable'; END;
        $$;


--
-- Name: devproof_validate_snapshot_body(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.devproof_validate_snapshot_body() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
        END; $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_capabilities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_capabilities (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    key character varying(96) NOT NULL,
    name character varying(160) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    core_scope character varying(24) NOT NULL,
    kind character varying(16) NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    is_default_enabled boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_agent_capability_core_scope CHECK (((core_scope)::text = ANY ((ARRAY['REQUIREMENT'::character varying, 'DELIVERY'::character varying, 'SHARED'::character varying])::text[]))),
    CONSTRAINT ck_agent_capability_kind CHECK (((kind)::text = ANY ((ARRAY['SYSTEM'::character varying, 'CUSTOM'::character varying])::text[])))
);


--
-- Name: agent_capability_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_capability_versions (
    id uuid NOT NULL,
    capability_id uuid NOT NULL,
    version_no integer NOT NULL,
    prompt_template text DEFAULT ''::text NOT NULL,
    input_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    tool_bindings jsonb DEFAULT '[]'::jsonb NOT NULL,
    parameter_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    content_hash character varying(80) NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_change_proposal_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_change_proposal_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    delivery_item_id uuid NOT NULL,
    input_manifest jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_hash character varying(80) NOT NULL,
    rules_version character varying(64) NOT NULL,
    candidate_target_count integer DEFAULT 0 NOT NULL,
    created_candidate_count integer DEFAULT 0 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_task_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_task_attempts (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    worker_id character varying(160) NOT NULL,
    fencing_token bigint NOT NULL,
    status character varying(32) NOT NULL,
    lease_expires_at timestamp with time zone NOT NULL,
    heartbeat_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_task_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_task_events (
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    event_seq bigint NOT NULL,
    event_json text NOT NULL,
    received_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: agent_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_tasks (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    created_by uuid NOT NULL,
    analysis_run_id uuid,
    planning_run_id uuid,
    task_kind character varying(48) NOT NULL,
    executor_version character varying(64) NOT NULL,
    payload_json text NOT NULL,
    status character varying(32) DEFAULT 'QUEUED'::character varying NOT NULL,
    attempt_no integer DEFAULT 0 NOT NULL,
    fencing_token bigint DEFAULT '0'::bigint NOT NULL,
    current_attempt_id uuid,
    max_attempts integer NOT NULL,
    cancel_requested_at timestamp with time zone,
    accepted_hash character varying(80),
    accepted_json text,
    last_error_code character varying(100),
    finished_at timestamp with time zone,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    claim_proposal_run_id uuid,
    question_run_id uuid,
    CONSTRAINT ck_agent_task_attempts CHECK (((max_attempts > 0) AND (attempt_no >= 0) AND (fencing_token >= 0))),
    CONSTRAINT ck_agent_task_business_ref CHECK ((num_nonnulls(analysis_run_id, planning_run_id, claim_proposal_run_id, question_run_id) = 1)),
    CONSTRAINT ck_agent_task_run_kind CHECK (((((task_kind)::text = 'DELIVERY_VERIFY'::text) AND (analysis_run_id IS NOT NULL)) OR (((task_kind)::text = ANY ((ARRAY['PLAN_DRAFT'::character varying, 'PLAN_REFINE'::character varying])::text[])) AND (planning_run_id IS NOT NULL)) OR (((task_kind)::text = 'DELIVERY_CLAIM_PROPOSE'::text) AND (claim_proposal_run_id IS NOT NULL)) OR (((task_kind)::text = 'EVIDENCE_QUESTION'::text) AND (question_run_id IS NOT NULL)))),
    CONSTRAINT ck_agent_task_status CHECK (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: agent_tool_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_tool_executions (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    input_snapshot_id uuid NOT NULL,
    capability_key character varying(96) NOT NULL,
    tool_key character varying(96) NOT NULL,
    tool_type character varying(32) DEFAULT 'HTTP_QUERY'::character varying NOT NULL,
    content_hash character varying(80) NOT NULL,
    artifact_uri text NOT NULL,
    excerpt_safe text NOT NULL,
    locator jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'SUCCEEDED'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_agent_tool_execution_status CHECK (((status)::text = 'SUCCEEDED'::text)),
    CONSTRAINT ck_agent_tool_execution_type CHECK (((tool_type)::text = 'HTTP_QUERY'::text))
);


--
-- Name: agent_tools; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_tools (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    key character varying(96) NOT NULL,
    name character varying(160) NOT NULL,
    tool_type character varying(32) NOT NULL,
    endpoint_url text,
    secret_ref character varying(160),
    input_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_agent_tool_type CHECK (((tool_type)::text = ANY ((ARRAY['DOCUMENT_RETRIEVAL'::character varying, 'GIT_DIFF'::character varying, 'CI_EVIDENCE'::character varying, 'EVIDENCE_QUERY'::character varying, 'HTTP_QUERY'::character varying])::text[])))
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(64) NOT NULL
);


--
-- Name: analysis_coverages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_coverages (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    scope_kind character varying(32) NOT NULL,
    scope_ref text NOT NULL,
    state character varying(32) NOT NULL,
    reason_code character varying(64),
    details jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: analysis_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_jobs (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    job_status character varying(32) NOT NULL,
    lease_owner character varying(128),
    lease_expires_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    attempt_no integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_error_code character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    available_at timestamp with time zone DEFAULT now()
);


--
-- Name: analysis_run_context_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_run_context_artifacts (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    round_no integer NOT NULL,
    request_hash character varying(80) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: analysis_run_manifests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_run_manifests (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    workflow_version character varying(64) NOT NULL,
    rule_set_version character varying(64) NOT NULL,
    prompt_set_version character varying(64) NOT NULL,
    generation_model character varying(128) NOT NULL,
    embedding_model character varying(128) NOT NULL,
    schema_version character varying(64) NOT NULL,
    degradation jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: analysis_run_orchestration_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_run_orchestration_snapshots (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    template_id uuid NOT NULL,
    template_version integer NOT NULL,
    content_hash character varying(80) NOT NULL,
    template_snapshot jsonb NOT NULL,
    nodes_snapshot jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    assessment_profile character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    raw_body text,
    CONSTRAINT ck_orchestration_raw_body CHECK (((raw_body IS NULL) OR (((raw_body)::jsonb = jsonb_build_object('template', template_snapshot, 'nodes', nodes_snapshot)) AND ((content_hash)::text = ('sha256:'::text || encode(sha256(convert_to(raw_body, 'UTF8'::name)), 'hex'::text)))))),
    CONSTRAINT ck_run_orchestration_snapshots_assessment_profile CHECK (((assessment_profile)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[])))
);


--
-- Name: analysis_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_runs (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    analysis_config_hash character varying(80) NOT NULL,
    run_status character varying(32) NOT NULL,
    manifest_hash character varying(80) NOT NULL,
    checkpoint_ns character varying(128) NOT NULL,
    cancel_requested_at timestamp with time zone,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    assessment_profile character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    plan_version_id uuid,
    plan_baseline_hash character varying(80),
    executor_owner character varying(16) DEFAULT 'PYTHON'::character varying NOT NULL,
    CONSTRAINT ck_analysis_executor_owner CHECK (((executor_owner)::text = ANY ((ARRAY['PYTHON'::character varying, 'JAVA'::character varying])::text[]))),
    CONSTRAINT ck_analysis_runs_assessment_profile CHECK (((assessment_profile)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[]))),
    CONSTRAINT ck_run_plan_baseline_pair CHECK (((plan_version_id IS NULL) = (plan_baseline_hash IS NULL)))
);


--
-- Name: approval_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_actions (
    id uuid NOT NULL,
    report_version_id uuid NOT NULL,
    action character varying(32) NOT NULL,
    actor_id uuid NOT NULL,
    reason text NOT NULL,
    report_hash character varying(80) NOT NULL,
    snapshot_hash character varying(80) NOT NULL,
    run_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: artifact_objects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artifact_objects (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    kind character varying(64) NOT NULL,
    content_hash character varying(80) NOT NULL,
    byte_size integer NOT NULL,
    media_type character varying(128) NOT NULL,
    schema_version character varying(64) NOT NULL,
    storage_uri text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    aggregate_type character varying(64) NOT NULL,
    aggregate_id uuid NOT NULL,
    action character varying(100) NOT NULL,
    before_version integer,
    after_version integer,
    correlation_id character varying(64) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: business_write_owners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.business_write_owners (
    aggregate_key character varying(64) NOT NULL,
    owner character varying(16) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_business_write_owner CHECK (((owner)::text = ANY ((ARRAY['PYTHON'::character varying, 'JAVA'::character varying])::text[])))
);


--
-- Name: claim_evidence_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claim_evidence_links (
    id uuid NOT NULL,
    claim_id uuid NOT NULL,
    evidence_id uuid NOT NULL,
    relation character varying(32) NOT NULL,
    reason text NOT NULL,
    confidence double precision NOT NULL,
    produced_by character varying(32) NOT NULL,
    requires_human_confirmation boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_claim_evidence_relation CHECK (((relation)::text = ANY ((ARRAY['SUPPORTS'::character varying, 'CONTRADICTS'::character varying, 'CONTEXT_ONLY'::character varying])::text[])))
);


--
-- Name: claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claims (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    claim_key character varying(128) NOT NULL,
    claim_type character varying(64) NOT NULL,
    text text NOT NULL,
    authority_level integer NOT NULL,
    source_revision_id uuid,
    version_no integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: code_review_finding_challenges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_review_finding_challenges (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    finding_id uuid NOT NULL,
    fingerprint character varying(80) NOT NULL,
    verdict character varying(32) NOT NULL,
    reason text NOT NULL,
    evidence_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    model_call_id uuid,
    schema_version character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: code_review_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.code_review_findings (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    evidence_id uuid NOT NULL,
    claim_id uuid,
    fingerprint character varying(80) NOT NULL,
    severity character varying(16) NOT NULL,
    finding_kind character varying(32) NOT NULL,
    title character varying(240) NOT NULL,
    problem text NOT NULL,
    trigger_scenario text NOT NULL,
    recommendation text NOT NULL,
    confidence double precision NOT NULL,
    produced_by character varying(32) NOT NULL,
    requires_human_confirmation boolean DEFAULT true NOT NULL,
    schema_version character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cycle_plan_selection_current; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cycle_plan_selection_current (
    cycle_id uuid NOT NULL,
    selection_id uuid NOT NULL
);


--
-- Name: cycle_plan_selections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cycle_plan_selections (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    plan_version_id uuid NOT NULL,
    sequence_no integer NOT NULL,
    plan_content_hash character varying(80) NOT NULL,
    content_hash character varying(80) NOT NULL,
    body_json text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: delivery_change_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.delivery_change_links (
    id uuid NOT NULL,
    delivery_item_id uuid NOT NULL,
    pull_request_resource_id uuid,
    git_snapshot_id uuid,
    link_status character varying(24) NOT NULL,
    link_source character varying(24) NOT NULL,
    confidence double precision,
    reason text DEFAULT ''::text NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamp with time zone,
    agent_proposal_run_id uuid,
    CONSTRAINT ck_delivery_change_link_exactly_one_target CHECK ((((pull_request_resource_id IS NOT NULL) AND (git_snapshot_id IS NULL)) OR ((pull_request_resource_id IS NULL) AND (git_snapshot_id IS NOT NULL)))),
    CONSTRAINT ck_delivery_change_link_source CHECK (((link_source)::text = ANY ((ARRAY['PLATFORM'::character varying, 'USER'::character varying, 'AGENT'::character varying])::text[]))),
    CONSTRAINT ck_delivery_change_link_status CHECK (((link_status)::text = ANY ((ARRAY['CANDIDATE'::character varying, 'CONFIRMED'::character varying])::text[])))
);


--
-- Name: delivery_claim_drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.delivery_claim_drafts (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    claim_key character varying(128) NOT NULL,
    text text NOT NULL,
    rationale text DEFAULT ''::text NOT NULL,
    origin character varying(16) NOT NULL,
    claim_status character varying(16) DEFAULT 'CANDIDATE'::character varying NOT NULL,
    source_manifest json DEFAULT '{}'::json NOT NULL,
    created_by uuid NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_delivery_claim_draft_origin CHECK (((origin)::text = ANY ((ARRAY['MODEL'::character varying, 'HUMAN'::character varying])::text[]))),
    CONSTRAINT ck_delivery_claim_draft_status CHECK (((claim_status)::text = ANY ((ARRAY['CANDIDATE'::character varying, 'CONFIRMED'::character varying, 'DISCARDED'::character varying])::text[])))
);


--
-- Name: delivery_claim_proposal_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.delivery_claim_proposal_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    task_id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    input_json text NOT NULL,
    input_hash character varying(80) NOT NULL,
    source_manifest jsonb NOT NULL,
    status character varying(32) NOT NULL,
    last_error_code character varying(100),
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_claim_proposal_input_hash CHECK ((((input_hash)::text = ('sha256:'::text || encode(sha256(convert_to(input_json, 'UTF8'::name)), 'hex'::text))) AND (jsonb_typeof((input_json)::jsonb) = 'object'::text) AND ((input_json)::jsonb ? 'sourceManifest'::text) AND (((input_json)::jsonb -> 'sourceManifest'::text) = source_manifest))),
    CONSTRAINT ck_claim_proposal_status CHECK (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: delivery_item_source_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.delivery_item_source_links (
    id uuid NOT NULL,
    delivery_item_id uuid NOT NULL,
    external_resource_revision_id uuid,
    source_revision_id uuid,
    link_role character varying(32) NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_delivery_item_source_link_exactly_one_source CHECK ((((external_resource_revision_id IS NOT NULL) AND (source_revision_id IS NULL)) OR ((external_resource_revision_id IS NULL) AND (source_revision_id IS NOT NULL)))),
    CONSTRAINT ck_delivery_item_source_link_role CHECK (((link_role)::text = ANY ((ARRAY['PRIMARY'::character varying, 'ACCEPTANCE'::character varying, 'DESIGN'::character varying, 'PLAN'::character varying])::text[])))
);


--
-- Name: delivery_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.delivery_items (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    external_resource_id uuid NOT NULL,
    external_key character varying(320) NOT NULL,
    title text NOT NULL,
    planning_status character varying(32) DEFAULT 'OPEN'::character varying NOT NULL,
    verification_status character varying(32) DEFAULT 'NOT_ASSESSED'::character varying NOT NULL,
    source_updated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_delivery_item_planning_status CHECK (((planning_status)::text = ANY ((ARRAY['OPEN'::character varying, 'IN_PROGRESS'::character varying, 'DECLARED_DONE'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT ck_delivery_item_verification_status CHECK (((verification_status)::text = ANY ((ARRAY['NOT_ASSESSED'::character varying, 'PARTIALLY_SUPPORTED'::character varying, 'CONFIRMED'::character varying, 'CONFLICT'::character varying, 'INSUFFICIENT_EVIDENCE'::character varying])::text[])))
);


--
-- Name: document_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_chunks (
    id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    text_hash character varying(80) NOT NULL,
    locator jsonb NOT NULL,
    index_version character varying(512) NOT NULL,
    embedding public.vector(768)
);


--
-- Name: evidence_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence_items (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    source_type character varying(32) NOT NULL,
    evidence_kind character varying(32) NOT NULL,
    source_revision_id uuid,
    commit_sha character varying(64),
    content_hash character varying(80) NOT NULL,
    excerpt_safe text NOT NULL,
    locator jsonb NOT NULL,
    locator_precision character varying(16) NOT NULL,
    captured_at timestamp with time zone DEFAULT now() NOT NULL,
    extractor_version character varying(64) NOT NULL,
    requires_human_confirmation boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_evidence_locator_precision CHECK (((locator_precision)::text = ANY ((ARRAY['EXACT'::character varying, 'APPROXIMATE'::character varying, 'UNAVAILABLE'::character varying])::text[])))
);


--
-- Name: evidence_question_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evidence_question_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    created_by uuid NOT NULL,
    input_json text NOT NULL,
    input_hash character varying(80) NOT NULL,
    result_json text,
    status character varying(32) NOT NULL,
    last_error_code character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_evidence_question_input_hash CHECK ((((input_hash)::text = ('sha256:'::text || encode(sha256(convert_to(input_json, 'UTF8'::name)), 'hex'::text))) AND (jsonb_typeof((input_json)::jsonb) = 'object'::text))),
    CONSTRAINT ck_evidence_question_status CHECK (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: external_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_connections (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    provider character varying(32) NOT NULL,
    name character varying(160) NOT NULL,
    repository_slug character varying(255) NOT NULL,
    api_base_url text DEFAULT 'https://api.github.com'::text NOT NULL,
    secret_ref character varying(160),
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_external_connection_provider CHECK (((provider)::text = 'GITHUB'::text))
);


--
-- Name: external_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_evidence (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    evidence_type character varying(16) NOT NULL,
    logical_name character varying(255) NOT NULL,
    commit_sha character varying(64) NOT NULL,
    content_hash character varying(80) NOT NULL,
    artifact_uri text NOT NULL,
    exit_code integer,
    submitted_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_external_evidence_type CHECK (((evidence_type)::text = ANY ((ARRAY['TEST'::character varying, 'BUILD'::character varying])::text[])))
);


--
-- Name: external_resource_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_resource_revisions (
    id uuid NOT NULL,
    resource_id uuid NOT NULL,
    revision_no integer NOT NULL,
    content_hash character varying(80) NOT NULL,
    title text NOT NULL,
    body text DEFAULT ''::text NOT NULL,
    state character varying(64) NOT NULL,
    web_url text NOT NULL,
    milestone_key character varying(160),
    source_updated_at timestamp with time zone,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: external_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_resources (
    id uuid NOT NULL,
    connection_id uuid NOT NULL,
    resource_type character varying(32) NOT NULL,
    external_key character varying(160) NOT NULL,
    logical_key character varying(320) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_external_resource_type CHECK (((resource_type)::text = ANY ((ARRAY['ISSUE'::character varying, 'PULL_REQUEST'::character varying, 'MILESTONE'::character varying])::text[])))
);


--
-- Name: git_repositories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.git_repositories (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    canonical_url_hash character varying(80) NOT NULL,
    display_url text NOT NULL,
    credential_ref character varying(255),
    read_only boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: git_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.git_snapshots (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    selected_base_ref character varying(255) NOT NULL,
    selected_target_ref character varying(255) NOT NULL,
    base_sha character varying(64) NOT NULL,
    target_sha character varying(64) NOT NULL,
    merge_base_sha character varying(64) NOT NULL,
    diff_mode character varying(16) NOT NULL,
    include_paths jsonb DEFAULT '[]'::jsonb NOT NULL,
    exclude_paths jsonb DEFAULT '[]'::jsonb NOT NULL,
    diff_hash character varying(80) NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    effective_base_sha character varying(64),
    capture_version character varying(64),
    diff_artifact_id uuid,
    code_change_artifact_id uuid
);


--
-- Name: human_verification_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.human_verification_decisions (
    id uuid NOT NULL,
    result_id uuid NOT NULL,
    decision character varying(48) NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    actor_id uuid NOT NULL,
    supersedes_decision_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_human_verification_decision CHECK (((decision)::text = ANY ((ARRAY['CONFIRM_SUPPORT'::character varying, 'CONFIRM_PARTIAL'::character varying, 'CONFIRM_INSUFFICIENT'::character varying, 'RETURN_FOR_EVIDENCE'::character varying])::text[])))
);


--
-- Name: idea_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idea_revisions (
    id uuid NOT NULL,
    idea_id uuid NOT NULL,
    revision_no integer NOT NULL,
    content text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ideas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ideas (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    title character varying(300) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: idempotency_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_records (
    id uuid NOT NULL,
    principal_hash character varying(80) NOT NULL,
    request_method character varying(10) NOT NULL,
    request_path character varying(1000) NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    request_hash character varying(80) NOT NULL,
    state character varying(32) DEFAULT 'IN_PROGRESS'::character varying NOT NULL,
    response_status integer,
    response_body jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: input_snapshot_bodies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_bodies (
    snapshot_id uuid NOT NULL,
    schema_version character varying(64) NOT NULL,
    content_hash character varying(80) NOT NULL,
    body_json text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: input_snapshot_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_claims (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    delivery_claim_draft_id uuid NOT NULL,
    claim_key character varying(128) NOT NULL,
    text text NOT NULL,
    origin character varying(16) NOT NULL,
    source_manifest json DEFAULT '{}'::json NOT NULL,
    content_hash character varying(80) NOT NULL
);


--
-- Name: input_snapshot_external_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_external_evidence (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    external_evidence_id uuid NOT NULL,
    content_hash character varying(80) NOT NULL,
    commit_sha character varying(64) NOT NULL
);


--
-- Name: input_snapshot_git; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_git (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    git_snapshot_id uuid NOT NULL,
    diff_hash character varying(80) NOT NULL
);


--
-- Name: input_snapshot_manual_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_manual_evidence (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    manual_evidence_id uuid NOT NULL,
    content_hash character varying(80) NOT NULL
);


--
-- Name: input_snapshot_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_plans (
    snapshot_id uuid NOT NULL,
    selection_id uuid NOT NULL,
    plan_version_id uuid NOT NULL,
    plan_content_hash character varying(80) NOT NULL,
    selection_hash character varying(80) NOT NULL
);


--
-- Name: input_snapshot_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshot_sources (
    id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    content_hash character varying(80) NOT NULL,
    parser_version character varying(64) NOT NULL
);


--
-- Name: input_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.input_snapshots (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    snapshot_hash character varying(80) NOT NULL,
    policy_version character varying(64) NOT NULL,
    workflow_version character varying(64) NOT NULL,
    created_by uuid NOT NULL,
    purpose character varying(32) DEFAULT 'PREPARATION'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    assessment_profile character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    CONSTRAINT ck_input_snapshots_assessment_profile CHECK (((assessment_profile)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[])))
);


--
-- Name: knowledge_bases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_bases (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: manual_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manual_evidence (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    logical_name character varying(255) NOT NULL,
    content_hash character varying(80) NOT NULL,
    artifact_uri text NOT NULL,
    submitted_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    origin_type character varying(32) DEFAULT 'MANUAL'::character varying NOT NULL,
    origin_locator jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_tool_execution_id uuid
);


--
-- Name: model_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_calls (
    id uuid NOT NULL,
    run_id uuid,
    provider character varying(64) NOT NULL,
    model character varying(128) NOT NULL,
    operation character varying(64) NOT NULL,
    prompt_version character varying(64) NOT NULL,
    schema_version character varying(64) NOT NULL,
    allowed_evidence_ids jsonb NOT NULL,
    status character varying(32) NOT NULL,
    latency_ms integer,
    attempts integer DEFAULT 1 NOT NULL,
    error_code character varying(64),
    error_summary character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    usage jsonb DEFAULT '{}'::jsonb NOT NULL,
    agent_task_attempt_id uuid
);


--
-- Name: node_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_attempts (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    node_id character varying(64) NOT NULL,
    attempt_no integer NOT NULL,
    status character varying(32) NOT NULL,
    error_code character varying(64),
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone
);


--
-- Name: orchestration_template_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestration_template_nodes (
    id uuid NOT NULL,
    template_id uuid NOT NULL,
    capability_version_id uuid NOT NULL,
    core_scope character varying(24) NOT NULL,
    display_order integer NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    parameters jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: orchestration_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestration_templates (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    name character varying(160) NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    assessment_profile character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    CONSTRAINT ck_orchestration_templates_assessment_profile CHECK (((assessment_profile)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[])))
);


--
-- Name: peripheral_profile_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.peripheral_profile_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    assessment_profile character varying(48) NOT NULL,
    run_status character varying(32) DEFAULT 'SUCCEEDED'::character varying NOT NULL,
    input_manifest jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_hash character varying(80) NOT NULL,
    output jsonb DEFAULT '{}'::jsonb NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    limitations jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_peripheral_profile_run_profile CHECK (((assessment_profile)::text = ANY ((ARRAY['PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[]))),
    CONSTRAINT ck_peripheral_profile_run_status CHECK (((run_status)::text = 'SUCCEEDED'::text))
);


--
-- Name: plan_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plan_versions (
    id uuid NOT NULL,
    idea_revision_id uuid NOT NULL,
    planning_run_id uuid NOT NULL,
    sequence_no integer NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    parent_plan_id uuid,
    status character varying(32) DEFAULT 'DRAFT'::character varying NOT NULL,
    body_json text NOT NULL,
    content_hash character varying(80) NOT NULL,
    created_by uuid NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_plan_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'CONFIRMED'::character varying, 'SUPERSEDED'::character varying])::text[])))
);


--
-- Name: planning_input_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.planning_input_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    content_hash character varying(80) NOT NULL,
    input_json text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    repository_snapshot_id uuid
);


--
-- Name: planning_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.planning_questions (
    id uuid NOT NULL,
    planning_run_id uuid NOT NULL,
    question_key character varying(100) NOT NULL,
    question text NOT NULL,
    reason text NOT NULL,
    answer text,
    answered_by uuid,
    answered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: planning_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.planning_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    created_by uuid NOT NULL,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    idea_revision_id uuid,
    request_key character varying(200),
    request_hash character varying(80)
);


--
-- Name: project_health_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_health_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    scope jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_manifest jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_hash character varying(80) NOT NULL,
    snapshot_hash character varying(80) NOT NULL,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    as_of timestamp with time zone NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: project_knowledge_bases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_knowledge_bases (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    knowledge_base_id uuid NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: project_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_members (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_members_role CHECK (((role)::text = ANY ((ARRAY['SUBMITTER'::character varying, 'REVIEWER'::character varying, 'ADMIN'::character varying])::text[])))
);


--
-- Name: project_retrieval_indexes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_retrieval_indexes (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    index_version character varying(512) NOT NULL,
    parser_version character varying(64) NOT NULL,
    embedding_provider character varying(64) NOT NULL,
    embedding_model character varying(255) NOT NULL,
    dimensions integer NOT NULL,
    status character varying(32) DEFAULT 'HISTORICAL'::character varying NOT NULL,
    created_by uuid NOT NULL,
    activated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_retrieval_index_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'HISTORICAL'::character varying])::text[])))
);


--
-- Name: project_summary_drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_summary_drafts (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    health_snapshot_id uuid NOT NULL,
    period_type character varying(24) NOT NULL,
    title character varying(300) NOT NULL,
    content jsonb DEFAULT '{}'::jsonb NOT NULL,
    content_hash character varying(80) NOT NULL,
    draft_status character varying(24) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_summary_draft_period_type CHECK (((period_type)::text = ANY ((ARRAY['DAILY'::character varying, 'WEEKLY'::character varying, 'ITERATION'::character varying])::text[]))),
    CONSTRAINT ck_project_summary_draft_status CHECK (((draft_status)::text = ANY ((ARRAY['DRAFT'::character varying, 'PUBLISHED'::character varying])::text[])))
);


--
-- Name: project_summary_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_summary_records (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    health_snapshot_id uuid NOT NULL,
    summary_draft_id uuid NOT NULL,
    record_no character varying(96) NOT NULL,
    record_hash character varying(80) NOT NULL,
    confirmation_type character varying(32) DEFAULT 'PERSONAL_CONFIRMED'::character varying NOT NULL,
    published_by uuid NOT NULL,
    published_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_project_summary_record_confirmation_type CHECK (((confirmation_type)::text = 'PERSONAL_CONFIRMED'::text))
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    owner_id uuid NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: published_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.published_records (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    report_version_id uuid NOT NULL,
    record_no character varying(64) NOT NULL,
    record_hash character varying(80) NOT NULL,
    published_by uuid NOT NULL,
    published_at timestamp with time zone DEFAULT now() NOT NULL,
    record_type character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    CONSTRAINT ck_published_records_record_type CHECK (((record_type)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[])))
);


--
-- Name: published_report_bodies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.published_report_bodies (
    report_version_id uuid NOT NULL,
    schema_version character varying(64) NOT NULL,
    content_hash character varying(80) NOT NULL,
    body_json text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: report_generation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_generation_jobs (
    run_id uuid NOT NULL,
    status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    attempt_no integer DEFAULT 0 NOT NULL,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    last_error_code character varying(100),
    report_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_report_generation_job CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[])))
);


--
-- Name: report_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_items (
    id uuid NOT NULL,
    report_version_id uuid NOT NULL,
    result_id uuid NOT NULL,
    display_order integer NOT NULL,
    result_snapshot jsonb NOT NULL,
    citation_snapshot jsonb NOT NULL,
    disposition text
);


--
-- Name: report_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_versions (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    sequence_no integer NOT NULL,
    status character varying(32) NOT NULL,
    parent_report_version_id uuid,
    content_hash character varying(80) NOT NULL,
    snapshot_hash character varying(80) NOT NULL,
    run_id uuid NOT NULL,
    submitted_by uuid,
    submitted_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    editorial_note text DEFAULT ''::text NOT NULL,
    record_type character varying(48) DEFAULT 'DELIVERY_VERIFICATION'::character varying NOT NULL,
    CONSTRAINT ck_report_versions_record_type CHECK (((record_type)::text = ANY ((ARRAY['DELIVERY_VERIFICATION'::character varying, 'PROJECT_STATUS_SUMMARY'::character varying, 'SECURITY_BASELINE'::character varying, 'QUALITY_TREND'::character varying])::text[])))
);


--
-- Name: repository_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.repository_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    target_sha character varying(64) NOT NULL,
    content_hash character varying(80) NOT NULL,
    body_json text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: retrieval_index_build_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.retrieval_index_build_runs (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    target_index_version character varying(512) NOT NULL,
    status character varying(32) DEFAULT 'RUNNING'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    source_count integer DEFAULT 0 NOT NULL,
    reindexed_source_count integer DEFAULT 0 NOT NULL,
    reindexed_chunk_count integer DEFAULT 0 NOT NULL,
    error_code character varying(64),
    error_message character varying(500),
    created_by uuid NOT NULL,
    executor_owner character varying(16) DEFAULT 'PYTHON'::character varying NOT NULL,
    compute_configuration jsonb,
    configuration_hash character varying(80),
    lease_owner character varying(160),
    last_error_code character varying(64),
    lease_expires_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    available_at timestamp with time zone,
    attempt_no integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    input_manifest jsonb,
    CONSTRAINT ck_retrieval_index_build_run_status CHECK (((status)::text = ANY ((ARRAY['RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_retrieval_index_build_runs_configuration CHECK (((compute_configuration IS NULL) = (configuration_hash IS NULL))),
    CONSTRAINT ck_retrieval_index_build_runs_executor CHECK (((executor_owner)::text = ANY ((ARRAY['PYTHON'::character varying, 'JAVA'::character varying])::text[])))
);


--
-- Name: risk_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_findings (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    evidence_id uuid NOT NULL,
    severity character varying(16) NOT NULL,
    category character varying(64) NOT NULL,
    finding_kind character varying(32) NOT NULL,
    recommendation text NOT NULL
);


--
-- Name: run_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.run_events (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    node_id character varying(64),
    event_type character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    payload_redacted jsonb DEFAULT '{}'::jsonb NOT NULL,
    correlation_id character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: security_baseline_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_baseline_records (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    baseline_snapshot_id uuid NOT NULL,
    record_no character varying(96) NOT NULL,
    record_hash character varying(80) NOT NULL,
    confirmation_reason text NOT NULL,
    confirmed_by uuid NOT NULL,
    confirmed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: security_baseline_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_baseline_snapshots (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    target_sha character varying(64) NOT NULL,
    input_manifest jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_hash character varying(80) NOT NULL,
    snapshot_hash character varying(80) NOT NULL,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: security_findings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_findings (
    id uuid NOT NULL,
    scan_artifact_id uuid NOT NULL,
    fingerprint character varying(255) NOT NULL,
    severity character varying(16) NOT NULL,
    category character varying(128) NOT NULL,
    title text NOT NULL,
    locator jsonb DEFAULT '{}'::jsonb NOT NULL,
    finding_status character varying(32) DEFAULT 'OPEN'::character varying NOT NULL,
    status_reason text DEFAULT ''::text NOT NULL,
    status_updated_by uuid,
    status_updated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_finding_severity CHECK (((severity)::text = ANY ((ARRAY['INFO'::character varying, 'LOW'::character varying, 'MEDIUM'::character varying, 'HIGH'::character varying, 'CRITICAL'::character varying])::text[]))),
    CONSTRAINT ck_security_finding_status CHECK (((finding_status)::text = ANY ((ARRAY['OPEN'::character varying, 'ACCEPTED_RISK'::character varying, 'REMEDIATION_CLAIMED'::character varying])::text[])))
);


--
-- Name: security_scan_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.security_scan_artifacts (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    target_sha character varying(64) NOT NULL,
    scan_type character varying(24) NOT NULL,
    scanner_name character varying(160) NOT NULL,
    scanner_version character varying(160) NOT NULL,
    rule_set_version character varying(160) NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    content_hash character varying(80) NOT NULL,
    artifact_uri text NOT NULL,
    imported_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_security_scan_artifact_type CHECK (((scan_type)::text = ANY ((ARRAY['SAST'::character varying, 'DEPENDENCY'::character varying, 'SECRET'::character varying, 'CONFIG'::character varying, 'CI'::character varying])::text[])))
);


--
-- Name: source_ingestion_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_ingestion_jobs (
    id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    job_status character varying(32) DEFAULT 'QUEUED'::character varying NOT NULL,
    lease_owner character varying(128),
    lease_expires_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    available_at timestamp with time zone DEFAULT now(),
    attempt_no integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_error_code character varying(64),
    last_error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    executor_owner character varying(16) DEFAULT 'PYTHON'::character varying NOT NULL,
    compute_configuration jsonb,
    configuration_hash character varying(80),
    CONSTRAINT ck_source_ingestion_job_status CHECK (((job_status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_source_ingestion_jobs_configuration CHECK (((compute_configuration IS NULL) = (configuration_hash IS NULL))),
    CONSTRAINT ck_source_ingestion_jobs_executor CHECK (((executor_owner)::text = ANY ((ARRAY['PYTHON'::character varying, 'JAVA'::character varying])::text[])))
);


--
-- Name: source_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_revisions (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    source_role character varying(64) NOT NULL,
    logical_name character varying(255) NOT NULL,
    revision_no integer NOT NULL,
    content_hash character varying(80) NOT NULL,
    artifact_uri text NOT NULL,
    media_type character varying(100) NOT NULL,
    processing_status character varying(32) DEFAULT 'UPLOADED'::character varying NOT NULL,
    parser_version character varying(64),
    failure_code character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    original_filename character varying(255) NOT NULL,
    extracted_artifact_uri text,
    extraction_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    ocr_confidence double precision,
    force_ocr boolean DEFAULT false NOT NULL,
    knowledge_base_id uuid,
    normalized_text_hash character varying(80),
    CONSTRAINT ck_source_processing_status CHECK (((processing_status)::text = ANY ((ARRAY['UPLOADED'::character varying, 'PARSING'::character varying, 'OCR_CHECKING'::character varying, 'CHUNKING'::character varying, 'INDEXING'::character varying, 'READY'::character varying, 'FAILED'::character varying])::text[])))
);


--
-- Name: source_sync_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_sync_runs (
    id uuid NOT NULL,
    connection_id uuid NOT NULL,
    status character varying(32) DEFAULT 'RUNNING'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    fetched_count integer DEFAULT 0 NOT NULL,
    changed_count integer DEFAULT 0 NOT NULL,
    error_code character varying(64),
    error_message text,
    page_count integer DEFAULT 0 NOT NULL,
    continuation_cursor jsonb DEFAULT '{}'::jsonb NOT NULL,
    requested_by uuid,
    lease_owner character varying(128),
    lease_expires_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    available_at timestamp with time zone DEFAULT now(),
    attempt_no integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_error_code character varying(64),
    last_error_message text,
    executor_owner character varying(16) DEFAULT 'PYTHON'::character varying NOT NULL,
    CONSTRAINT ck_source_sync_executor_owner CHECK (((executor_owner)::text = ANY ((ARRAY['PYTHON'::character varying, 'JAVA'::character varying])::text[]))),
    CONSTRAINT ck_source_sync_run_status CHECK (((status)::text = ANY ((ARRAY['RUNNING'::character varying, 'SUCCEEDED'::character varying, 'PARTIALLY_SUCCEEDED'::character varying, 'FAILED'::character varying])::text[])))
);


--
-- Name: task_orchestration_bindings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_orchestration_bindings (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    template_id uuid NOT NULL,
    template_version integer NOT NULL,
    bound_by uuid NOT NULL,
    bound_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    display_name character varying(100) NOT NULL,
    status character varying(32) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: verification_cycles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verification_cycles (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    sequence_no integer NOT NULL,
    business_status character varying(32) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_from_cycle_id uuid,
    active_run_id uuid,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_cycle_business_status CHECK (((business_status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ANALYZING'::character varying, 'DRAFT_READY'::character varying, 'NEEDS_EVIDENCE'::character varying, 'NEEDS_CONFIRMATION'::character varying, 'PENDING_REVIEW'::character varying, 'REJECTED'::character varying, 'APPROVED'::character varying, 'PUBLISHED'::character varying])::text[])))
);


--
-- Name: verification_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verification_results (
    id uuid NOT NULL,
    analysis_run_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    protocol_version character varying(64) NOT NULL,
    status character varying(48) NOT NULL,
    reason text NOT NULL,
    evidence_ids jsonb NOT NULL,
    requires_human_confirmation boolean DEFAULT false NOT NULL,
    produced_by character varying(32) NOT NULL
);


--
-- Name: verification_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.verification_tasks (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    title character varying(300) NOT NULL,
    requirement_key character varying(100) NOT NULL,
    created_by uuid NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    delivery_item_id uuid NOT NULL
);


--
-- Name: agent_capabilities agent_capabilities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capabilities
    ADD CONSTRAINT agent_capabilities_pkey PRIMARY KEY (id);


--
-- Name: agent_capability_versions agent_capability_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capability_versions
    ADD CONSTRAINT agent_capability_versions_pkey PRIMARY KEY (id);


--
-- Name: agent_change_proposal_runs agent_change_proposal_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_change_proposal_runs
    ADD CONSTRAINT agent_change_proposal_runs_pkey PRIMARY KEY (id);


--
-- Name: agent_task_attempts agent_task_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_attempts
    ADD CONSTRAINT agent_task_attempts_pkey PRIMARY KEY (id);


--
-- Name: agent_task_events agent_task_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_events
    ADD CONSTRAINT agent_task_events_pkey PRIMARY KEY (task_id, attempt_id, event_seq);


--
-- Name: agent_tasks agent_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_pkey PRIMARY KEY (id);


--
-- Name: agent_tool_executions agent_tool_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_executions
    ADD CONSTRAINT agent_tool_executions_pkey PRIMARY KEY (id);


--
-- Name: agent_tools agent_tools_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: analysis_coverages analysis_coverages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_coverages
    ADD CONSTRAINT analysis_coverages_pkey PRIMARY KEY (id);


--
-- Name: analysis_jobs analysis_jobs_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_jobs
    ADD CONSTRAINT analysis_jobs_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: analysis_jobs analysis_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_jobs
    ADD CONSTRAINT analysis_jobs_pkey PRIMARY KEY (id);


--
-- Name: analysis_jobs analysis_jobs_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_jobs
    ADD CONSTRAINT analysis_jobs_run_id_key UNIQUE (run_id);


--
-- Name: analysis_run_context_artifacts analysis_run_context_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_context_artifacts
    ADD CONSTRAINT analysis_run_context_artifacts_pkey PRIMARY KEY (id);


--
-- Name: analysis_run_manifests analysis_run_manifests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_manifests
    ADD CONSTRAINT analysis_run_manifests_pkey PRIMARY KEY (id);


--
-- Name: analysis_run_manifests analysis_run_manifests_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_manifests
    ADD CONSTRAINT analysis_run_manifests_run_id_key UNIQUE (run_id);


--
-- Name: analysis_run_orchestration_snapshots analysis_run_orchestration_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_orchestration_snapshots
    ADD CONSTRAINT analysis_run_orchestration_snapshots_pkey PRIMARY KEY (id);


--
-- Name: analysis_run_orchestration_snapshots analysis_run_orchestration_snapshots_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_orchestration_snapshots
    ADD CONSTRAINT analysis_run_orchestration_snapshots_run_id_key UNIQUE (run_id);


--
-- Name: analysis_runs analysis_runs_checkpoint_ns_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_checkpoint_ns_key UNIQUE (checkpoint_ns);


--
-- Name: analysis_runs analysis_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_pkey PRIMARY KEY (id);


--
-- Name: approval_actions approval_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_actions
    ADD CONSTRAINT approval_actions_pkey PRIMARY KEY (id);


--
-- Name: artifact_objects artifact_objects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artifact_objects
    ADD CONSTRAINT artifact_objects_pkey PRIMARY KEY (id);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);


--
-- Name: business_write_owners business_write_owners_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_write_owners
    ADD CONSTRAINT business_write_owners_pkey PRIMARY KEY (aggregate_key);


--
-- Name: claim_evidence_links claim_evidence_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_evidence_links
    ADD CONSTRAINT claim_evidence_links_pkey PRIMARY KEY (id);


--
-- Name: claims claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_pkey PRIMARY KEY (id);


--
-- Name: code_review_finding_challenges code_review_finding_challenges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_finding_challenges
    ADD CONSTRAINT code_review_finding_challenges_pkey PRIMARY KEY (id);


--
-- Name: code_review_findings code_review_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_findings
    ADD CONSTRAINT code_review_findings_pkey PRIMARY KEY (id);


--
-- Name: cycle_plan_selection_current cycle_plan_selection_current_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selection_current
    ADD CONSTRAINT cycle_plan_selection_current_pkey PRIMARY KEY (cycle_id);


--
-- Name: cycle_plan_selections cycle_plan_selections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT cycle_plan_selections_pkey PRIMARY KEY (id);


--
-- Name: delivery_change_links delivery_change_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_pkey PRIMARY KEY (id);


--
-- Name: delivery_claim_drafts delivery_claim_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_drafts
    ADD CONSTRAINT delivery_claim_drafts_pkey PRIMARY KEY (id);


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_proposal_runs
    ADD CONSTRAINT delivery_claim_proposal_runs_pkey PRIMARY KEY (id);


--
-- Name: delivery_item_source_links delivery_item_source_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_item_source_links
    ADD CONSTRAINT delivery_item_source_links_pkey PRIMARY KEY (id);


--
-- Name: delivery_items delivery_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_items
    ADD CONSTRAINT delivery_items_pkey PRIMARY KEY (id);


--
-- Name: document_chunks document_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);


--
-- Name: evidence_items evidence_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT evidence_items_pkey PRIMARY KEY (id);


--
-- Name: evidence_question_runs evidence_question_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_question_runs
    ADD CONSTRAINT evidence_question_runs_pkey PRIMARY KEY (id);


--
-- Name: external_connections external_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_connections
    ADD CONSTRAINT external_connections_pkey PRIMARY KEY (id);


--
-- Name: external_evidence external_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_evidence
    ADD CONSTRAINT external_evidence_pkey PRIMARY KEY (id);


--
-- Name: external_resource_revisions external_resource_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resource_revisions
    ADD CONSTRAINT external_resource_revisions_pkey PRIMARY KEY (id);


--
-- Name: external_resources external_resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resources
    ADD CONSTRAINT external_resources_pkey PRIMARY KEY (id);


--
-- Name: git_repositories git_repositories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_repositories
    ADD CONSTRAINT git_repositories_pkey PRIMARY KEY (id);


--
-- Name: git_snapshots git_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_snapshots
    ADD CONSTRAINT git_snapshots_pkey PRIMARY KEY (id);


--
-- Name: human_verification_decisions human_verification_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_verification_decisions
    ADD CONSTRAINT human_verification_decisions_pkey PRIMARY KEY (id);


--
-- Name: idea_revisions idea_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idea_revisions
    ADD CONSTRAINT idea_revisions_pkey PRIMARY KEY (id);


--
-- Name: ideas ideas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas
    ADD CONSTRAINT ideas_pkey PRIMARY KEY (id);


--
-- Name: idempotency_records idempotency_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT idempotency_records_pkey PRIMARY KEY (id);


--
-- Name: input_snapshot_bodies input_snapshot_bodies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_bodies
    ADD CONSTRAINT input_snapshot_bodies_pkey PRIMARY KEY (snapshot_id);


--
-- Name: input_snapshot_claims input_snapshot_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_claims
    ADD CONSTRAINT input_snapshot_claims_pkey PRIMARY KEY (id);


--
-- Name: input_snapshot_external_evidence input_snapshot_external_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_external_evidence
    ADD CONSTRAINT input_snapshot_external_evidence_pkey PRIMARY KEY (id);


--
-- Name: input_snapshot_git input_snapshot_git_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_git
    ADD CONSTRAINT input_snapshot_git_pkey PRIMARY KEY (id);


--
-- Name: input_snapshot_git input_snapshot_git_snapshot_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_git
    ADD CONSTRAINT input_snapshot_git_snapshot_id_key UNIQUE (snapshot_id);


--
-- Name: input_snapshot_manual_evidence input_snapshot_manual_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_manual_evidence
    ADD CONSTRAINT input_snapshot_manual_evidence_pkey PRIMARY KEY (id);


--
-- Name: input_snapshot_plans input_snapshot_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_plans
    ADD CONSTRAINT input_snapshot_plans_pkey PRIMARY KEY (snapshot_id);


--
-- Name: input_snapshot_sources input_snapshot_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_sources
    ADD CONSTRAINT input_snapshot_sources_pkey PRIMARY KEY (id);


--
-- Name: input_snapshots input_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshots
    ADD CONSTRAINT input_snapshots_pkey PRIMARY KEY (id);


--
-- Name: knowledge_bases knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id);


--
-- Name: manual_evidence manual_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT manual_evidence_pkey PRIMARY KEY (id);


--
-- Name: model_calls model_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls
    ADD CONSTRAINT model_calls_pkey PRIMARY KEY (id);


--
-- Name: node_attempts node_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_attempts
    ADD CONSTRAINT node_attempts_pkey PRIMARY KEY (id);


--
-- Name: orchestration_template_nodes orchestration_template_nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_template_nodes
    ADD CONSTRAINT orchestration_template_nodes_pkey PRIMARY KEY (id);


--
-- Name: orchestration_templates orchestration_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_templates
    ADD CONSTRAINT orchestration_templates_pkey PRIMARY KEY (id);


--
-- Name: peripheral_profile_runs peripheral_profile_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peripheral_profile_runs
    ADD CONSTRAINT peripheral_profile_runs_pkey PRIMARY KEY (id);


--
-- Name: plan_versions plan_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_pkey PRIMARY KEY (id);


--
-- Name: planning_input_snapshots planning_input_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_input_snapshots
    ADD CONSTRAINT planning_input_snapshots_pkey PRIMARY KEY (id);


--
-- Name: planning_questions planning_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_questions
    ADD CONSTRAINT planning_questions_pkey PRIMARY KEY (id);


--
-- Name: planning_runs planning_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT planning_runs_pkey PRIMARY KEY (id);


--
-- Name: project_health_snapshots project_health_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_health_snapshots
    ADD CONSTRAINT project_health_snapshots_pkey PRIMARY KEY (id);


--
-- Name: project_health_snapshots project_health_snapshots_snapshot_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_health_snapshots
    ADD CONSTRAINT project_health_snapshots_snapshot_hash_key UNIQUE (snapshot_hash);


--
-- Name: project_knowledge_bases project_knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_knowledge_bases
    ADD CONSTRAINT project_knowledge_bases_pkey PRIMARY KEY (id);


--
-- Name: project_members project_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_pkey PRIMARY KEY (id);


--
-- Name: project_retrieval_indexes project_retrieval_indexes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_retrieval_indexes
    ADD CONSTRAINT project_retrieval_indexes_pkey PRIMARY KEY (id);


--
-- Name: project_summary_drafts project_summary_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_drafts
    ADD CONSTRAINT project_summary_drafts_pkey PRIMARY KEY (id);


--
-- Name: project_summary_records project_summary_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_pkey PRIMARY KEY (id);


--
-- Name: project_summary_records project_summary_records_record_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_record_hash_key UNIQUE (record_hash);


--
-- Name: project_summary_records project_summary_records_record_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_record_no_key UNIQUE (record_no);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: published_records published_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_pkey PRIMARY KEY (id);


--
-- Name: published_records published_records_record_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_record_hash_key UNIQUE (record_hash);


--
-- Name: published_records published_records_record_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_record_no_key UNIQUE (record_no);


--
-- Name: published_report_bodies published_report_bodies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_report_bodies
    ADD CONSTRAINT published_report_bodies_pkey PRIMARY KEY (report_version_id);


--
-- Name: report_generation_jobs report_generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_pkey PRIMARY KEY (run_id);


--
-- Name: report_items report_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_items
    ADD CONSTRAINT report_items_pkey PRIMARY KEY (id);


--
-- Name: report_versions report_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_pkey PRIMARY KEY (id);


--
-- Name: repository_snapshots repository_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repository_snapshots
    ADD CONSTRAINT repository_snapshots_pkey PRIMARY KEY (id);


--
-- Name: retrieval_index_build_runs retrieval_index_build_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_index_build_runs
    ADD CONSTRAINT retrieval_index_build_runs_pkey PRIMARY KEY (id);


--
-- Name: risk_findings risk_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_findings
    ADD CONSTRAINT risk_findings_pkey PRIMARY KEY (id);


--
-- Name: run_events run_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.run_events
    ADD CONSTRAINT run_events_pkey PRIMARY KEY (id);


--
-- Name: security_baseline_records security_baseline_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_pkey PRIMARY KEY (id);


--
-- Name: security_baseline_records security_baseline_records_record_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_record_hash_key UNIQUE (record_hash);


--
-- Name: security_baseline_records security_baseline_records_record_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_record_no_key UNIQUE (record_no);


--
-- Name: security_baseline_snapshots security_baseline_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_snapshots
    ADD CONSTRAINT security_baseline_snapshots_pkey PRIMARY KEY (id);


--
-- Name: security_baseline_snapshots security_baseline_snapshots_snapshot_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_snapshots
    ADD CONSTRAINT security_baseline_snapshots_snapshot_hash_key UNIQUE (snapshot_hash);


--
-- Name: security_findings security_findings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_findings
    ADD CONSTRAINT security_findings_pkey PRIMARY KEY (id);


--
-- Name: security_scan_artifacts security_scan_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_scan_artifacts
    ADD CONSTRAINT security_scan_artifacts_pkey PRIMARY KEY (id);


--
-- Name: source_ingestion_jobs source_ingestion_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_ingestion_jobs
    ADD CONSTRAINT source_ingestion_jobs_pkey PRIMARY KEY (id);


--
-- Name: source_revisions source_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revisions
    ADD CONSTRAINT source_revisions_pkey PRIMARY KEY (id);


--
-- Name: source_sync_runs source_sync_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_sync_runs
    ADD CONSTRAINT source_sync_runs_pkey PRIMARY KEY (id);


--
-- Name: task_orchestration_bindings task_orchestration_bindings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_orchestration_bindings
    ADD CONSTRAINT task_orchestration_bindings_pkey PRIMARY KEY (id);


--
-- Name: task_orchestration_bindings task_orchestration_bindings_task_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_orchestration_bindings
    ADD CONSTRAINT task_orchestration_bindings_task_id_key UNIQUE (task_id);


--
-- Name: agent_capabilities uq_agent_capability_project_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capabilities
    ADD CONSTRAINT uq_agent_capability_project_key UNIQUE (project_id, key);


--
-- Name: agent_capability_versions uq_agent_capability_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capability_versions
    ADD CONSTRAINT uq_agent_capability_version UNIQUE (capability_id, version_no);


--
-- Name: agent_tool_executions uq_agent_tool_execution_run_tool; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_executions
    ADD CONSTRAINT uq_agent_tool_execution_run_tool UNIQUE (analysis_run_id, capability_key, tool_key);


--
-- Name: agent_tools uq_agent_tool_project_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT uq_agent_tool_project_key UNIQUE (project_id, key);


--
-- Name: artifact_objects uq_artifact_project_kind_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artifact_objects
    ADD CONSTRAINT uq_artifact_project_kind_hash UNIQUE (project_id, kind, content_hash);


--
-- Name: agent_task_attempts uq_attempt_task; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_attempts
    ADD CONSTRAINT uq_attempt_task UNIQUE (id, task_id);


--
-- Name: claim_evidence_links uq_claim_evidence_relation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_evidence_links
    ADD CONSTRAINT uq_claim_evidence_relation UNIQUE (claim_id, evidence_id, relation);


--
-- Name: claims uq_claim_run_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT uq_claim_run_key UNIQUE (analysis_run_id, claim_key);


--
-- Name: code_review_finding_challenges uq_code_review_challenge_run_finding; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_finding_challenges
    ADD CONSTRAINT uq_code_review_challenge_run_finding UNIQUE (analysis_run_id, finding_id);


--
-- Name: code_review_findings uq_code_review_finding_run_fingerprint; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_findings
    ADD CONSTRAINT uq_code_review_finding_run_fingerprint UNIQUE (analysis_run_id, fingerprint);


--
-- Name: cycle_plan_selections uq_cycle_plan_baseline; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT uq_cycle_plan_baseline UNIQUE (id, plan_version_id, plan_content_hash, content_hash);


--
-- Name: cycle_plan_selections uq_cycle_plan_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT uq_cycle_plan_identity UNIQUE (id, cycle_id);


--
-- Name: cycle_plan_selections uq_cycle_plan_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT uq_cycle_plan_sequence UNIQUE (cycle_id, sequence_no);


--
-- Name: verification_cycles uq_cycle_task_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_cycles
    ADD CONSTRAINT uq_cycle_task_sequence UNIQUE (task_id, sequence_no);


--
-- Name: delivery_change_links uq_delivery_change_link_item_git_snapshot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT uq_delivery_change_link_item_git_snapshot UNIQUE (delivery_item_id, git_snapshot_id);


--
-- Name: delivery_change_links uq_delivery_change_link_item_pr; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT uq_delivery_change_link_item_pr UNIQUE (delivery_item_id, pull_request_resource_id);


--
-- Name: delivery_claim_drafts uq_delivery_claim_draft_cycle_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_drafts
    ADD CONSTRAINT uq_delivery_claim_draft_cycle_key UNIQUE (cycle_id, claim_key);


--
-- Name: delivery_items uq_delivery_item_project_external_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_items
    ADD CONSTRAINT uq_delivery_item_project_external_key UNIQUE (project_id, external_key);


--
-- Name: document_chunks uq_document_chunk_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT uq_document_chunk_version UNIQUE (source_revision_id, chunk_index, index_version);


--
-- Name: external_connections uq_external_connection_project_provider_repo; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_connections
    ADD CONSTRAINT uq_external_connection_project_provider_repo UNIQUE (project_id, provider, repository_slug);


--
-- Name: external_resources uq_external_resource_connection_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resources
    ADD CONSTRAINT uq_external_resource_connection_type_key UNIQUE (connection_id, resource_type, external_key);


--
-- Name: external_resource_revisions uq_external_resource_revision; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resource_revisions
    ADD CONSTRAINT uq_external_resource_revision UNIQUE (resource_id, revision_no);


--
-- Name: idea_revisions uq_idea_revision; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idea_revisions
    ADD CONSTRAINT uq_idea_revision UNIQUE (idea_id, revision_no);


--
-- Name: idempotency_records uq_idempotency_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT uq_idempotency_request UNIQUE (principal_hash, request_method, request_path, idempotency_key);


--
-- Name: input_snapshot_claims uq_input_snapshot_claim_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_claims
    ADD CONSTRAINT uq_input_snapshot_claim_key UNIQUE (snapshot_id, claim_key);


--
-- Name: input_snapshots uq_input_snapshot_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshots
    ADD CONSTRAINT uq_input_snapshot_hash UNIQUE (snapshot_hash);


--
-- Name: manual_evidence uq_manual_evidence_tool_execution; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT uq_manual_evidence_tool_execution UNIQUE (source_tool_execution_id);


--
-- Name: node_attempts uq_node_attempt; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_attempts
    ADD CONSTRAINT uq_node_attempt UNIQUE (analysis_run_id, node_id, attempt_no);


--
-- Name: orchestration_template_nodes uq_orchestration_template_capability; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_template_nodes
    ADD CONSTRAINT uq_orchestration_template_capability UNIQUE (template_id, capability_version_id);


--
-- Name: orchestration_template_nodes uq_orchestration_template_node_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_template_nodes
    ADD CONSTRAINT uq_orchestration_template_node_order UNIQUE (template_id, display_order);


--
-- Name: orchestration_templates uq_orchestration_template_project_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_templates
    ADD CONSTRAINT uq_orchestration_template_project_name UNIQUE (project_id, name);


--
-- Name: plan_versions uq_plan_revision_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT uq_plan_revision_sequence UNIQUE (idea_revision_id, sequence_no);


--
-- Name: planning_questions uq_planning_question; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_questions
    ADD CONSTRAINT uq_planning_question UNIQUE (planning_run_id, question_key);


--
-- Name: planning_runs uq_planning_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT uq_planning_request UNIQUE (project_id, created_by, request_key);


--
-- Name: git_repositories uq_project_git_repository; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_repositories
    ADD CONSTRAINT uq_project_git_repository UNIQUE (project_id, canonical_url_hash);


--
-- Name: project_knowledge_bases uq_project_knowledge_base; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_knowledge_bases
    ADD CONSTRAINT uq_project_knowledge_base UNIQUE (project_id, knowledge_base_id);


--
-- Name: project_members uq_project_members_project_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id);


--
-- Name: project_retrieval_indexes uq_project_retrieval_index_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_retrieval_indexes
    ADD CONSTRAINT uq_project_retrieval_index_version UNIQUE (project_id, index_version);


--
-- Name: project_summary_records uq_project_summary_record_draft; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT uq_project_summary_record_draft UNIQUE (summary_draft_id);


--
-- Name: published_records uq_published_report; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT uq_published_report UNIQUE (report_version_id);


--
-- Name: report_versions uq_report_cycle_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT uq_report_cycle_sequence UNIQUE (cycle_id, sequence_no);


--
-- Name: report_items uq_report_item_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_items
    ADD CONSTRAINT uq_report_item_order UNIQUE (report_version_id, display_order);


--
-- Name: verification_results uq_result_run_claim; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT uq_result_run_claim UNIQUE (analysis_run_id, claim_id);


--
-- Name: risk_findings uq_risk_finding; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_findings
    ADD CONSTRAINT uq_risk_finding UNIQUE (analysis_run_id, claim_id, evidence_id, category);


--
-- Name: analysis_run_context_artifacts uq_run_context_artifact_round; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_context_artifacts
    ADD CONSTRAINT uq_run_context_artifact_round UNIQUE (analysis_run_id, round_no);


--
-- Name: security_baseline_records uq_security_baseline_record_snapshot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT uq_security_baseline_record_snapshot UNIQUE (baseline_snapshot_id);


--
-- Name: security_findings uq_security_finding_artifact_fingerprint; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_findings
    ADD CONSTRAINT uq_security_finding_artifact_fingerprint UNIQUE (scan_artifact_id, fingerprint);


--
-- Name: input_snapshots uq_snapshot_body_identity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshots
    ADD CONSTRAINT uq_snapshot_body_identity UNIQUE (id, snapshot_hash);


--
-- Name: input_snapshot_external_evidence uq_snapshot_external_evidence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_external_evidence
    ADD CONSTRAINT uq_snapshot_external_evidence UNIQUE (snapshot_id, external_evidence_id);


--
-- Name: input_snapshot_manual_evidence uq_snapshot_manual_evidence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_manual_evidence
    ADD CONSTRAINT uq_snapshot_manual_evidence UNIQUE (snapshot_id, manual_evidence_id);


--
-- Name: input_snapshot_sources uq_snapshot_source; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_sources
    ADD CONSTRAINT uq_snapshot_source UNIQUE (snapshot_id, source_revision_id);


--
-- Name: source_ingestion_jobs uq_source_ingestion_job_source; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_ingestion_jobs
    ADD CONSTRAINT uq_source_ingestion_job_source UNIQUE (source_revision_id);


--
-- Name: source_revisions uq_source_revision; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revisions
    ADD CONSTRAINT uq_source_revision UNIQUE (project_id, logical_name, revision_no);


--
-- Name: agent_task_attempts uq_task_fencing; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_attempts
    ADD CONSTRAINT uq_task_fencing UNIQUE (task_id, fencing_token);


--
-- Name: verification_tasks uq_task_project_requirement; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_tasks
    ADD CONSTRAINT uq_task_project_requirement UNIQUE (project_id, requirement_key);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: verification_cycles verification_cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_cycles
    ADD CONSTRAINT verification_cycles_pkey PRIMARY KEY (id);


--
-- Name: verification_results verification_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT verification_results_pkey PRIMARY KEY (id);


--
-- Name: verification_tasks verification_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_tasks
    ADD CONSTRAINT verification_tasks_pkey PRIMARY KEY (id);


--
-- Name: ix_agent_task_queue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_task_queue ON public.agent_tasks USING btree (status, available_at, created_at);


--
-- Name: ix_analysis_jobs_available; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_analysis_jobs_available ON public.analysis_jobs USING btree (job_status, available_at);


--
-- Name: ix_code_review_challenge_run_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_code_review_challenge_run_fingerprint ON public.code_review_finding_challenges USING btree (analysis_run_id, fingerprint);


--
-- Name: ix_document_chunks_content_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_content_fts ON public.document_chunks USING gin (to_tsvector('simple'::regconfig, content));


--
-- Name: ix_document_chunks_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_chunks_fts ON public.document_chunks USING gin (to_tsvector('simple'::regconfig, content));


--
-- Name: ix_human_verification_decision_result_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_human_verification_decision_result_created ON public.human_verification_decisions USING btree (result_id, created_at);


--
-- Name: ix_knowledge_bases_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_bases_project_id ON public.knowledge_bases USING btree (project_id);


--
-- Name: ix_model_calls_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_calls_run_id ON public.model_calls USING btree (run_id);


--
-- Name: ix_peripheral_profile_runs_project_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_peripheral_profile_runs_project_created ON public.peripheral_profile_runs USING btree (project_id, created_at);


--
-- Name: ix_project_knowledge_bases_kb_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_knowledge_bases_kb_id ON public.project_knowledge_bases USING btree (knowledge_base_id);


--
-- Name: ix_project_knowledge_bases_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_knowledge_bases_project_id ON public.project_knowledge_bases USING btree (project_id);


--
-- Name: ix_project_retrieval_indexes_project_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_project_retrieval_indexes_project_status ON public.project_retrieval_indexes USING btree (project_id, status);


--
-- Name: ix_report_generation_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_generation_pending ON public.report_generation_jobs USING btree (available_at) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: ix_retrieval_index_build_runs_project_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_retrieval_index_build_runs_project_started ON public.retrieval_index_build_runs USING btree (project_id, started_at);


--
-- Name: ix_source_revisions_knowledge_base_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_source_revisions_knowledge_base_id ON public.source_revisions USING btree (knowledge_base_id);


--
-- Name: ix_verification_tasks_delivery_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_verification_tasks_delivery_item_id ON public.verification_tasks USING btree (delivery_item_id);


--
-- Name: uq_active_planning_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_active_planning_revision ON public.planning_runs USING btree (idea_revision_id) WHERE (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying])::text[])) AND (idea_revision_id IS NOT NULL));


--
-- Name: uq_active_run_config; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_active_run_config ON public.analysis_runs USING btree (snapshot_id, analysis_config_hash) WHERE ((run_status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying])::text[]));


--
-- Name: uq_agent_task_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_agent_task_analysis ON public.agent_tasks USING btree (analysis_run_id) WHERE (analysis_run_id IS NOT NULL);


--
-- Name: uq_agent_task_claim_proposal; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_agent_task_claim_proposal ON public.agent_tasks USING btree (claim_proposal_run_id) WHERE (claim_proposal_run_id IS NOT NULL);


--
-- Name: uq_agent_task_evidence_question; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_agent_task_evidence_question ON public.agent_tasks USING btree (question_run_id) WHERE (question_run_id IS NOT NULL);


--
-- Name: uq_agent_task_planning; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_agent_task_planning ON public.agent_tasks USING btree (planning_run_id) WHERE (planning_run_id IS NOT NULL);


--
-- Name: uq_claim_proposal_active_cycle; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_claim_proposal_active_cycle ON public.delivery_claim_proposal_runs USING btree (cycle_id) WHERE ((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying])::text[]));


--
-- Name: uq_project_retrieval_active_index; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_project_retrieval_active_index ON public.project_retrieval_indexes USING btree (project_id) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: agent_capabilities agent_capabilities_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER agent_capabilities_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.agent_capabilities FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: agent_capability_versions agent_capability_versions_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER agent_capability_versions_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.agent_capability_versions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: agent_change_proposal_runs agent_change_proposal_runs_association_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER agent_change_proposal_runs_association_writer BEFORE INSERT OR DELETE OR UPDATE ON public.agent_change_proposal_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_delivery_association_writer();


--
-- Name: agent_tool_executions agent_tool_executions_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER agent_tool_executions_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.agent_tool_executions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: agent_tools agent_tools_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER agent_tools_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.agent_tools FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: analysis_coverages analysis_coverages_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_coverages_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.analysis_coverages FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: analysis_run_context_artifacts analysis_run_context_artifacts_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_run_context_artifacts_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.analysis_run_context_artifacts FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: analysis_run_manifests analysis_run_manifests_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_run_manifests_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.analysis_run_manifests FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: analysis_run_orchestration_snapshots analysis_run_orchestration_snapshots_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_run_orchestration_snapshots_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.analysis_run_orchestration_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: analysis_runs analysis_run_plan_scope; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_run_plan_scope BEFORE INSERT OR UPDATE OF snapshot_id, plan_version_id, plan_baseline_hash ON public.analysis_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_run_plan();


--
-- Name: analysis_runs analysis_runs_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER analysis_runs_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.analysis_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: approval_actions approval_actions_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER approval_actions_append_only BEFORE DELETE OR UPDATE ON public.approval_actions FOR EACH ROW EXECUTE FUNCTION public.devproof_append_only_report_fact();


--
-- Name: approval_actions approval_actions_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER approval_actions_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.approval_actions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: agent_capability_versions capability_version_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER capability_version_immutable BEFORE UPDATE ON public.agent_capability_versions FOR EACH ROW EXECUTE FUNCTION public.devproof_preserve_capability_version();


--
-- Name: claim_evidence_links claim_evidence_links_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER claim_evidence_links_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.claim_evidence_links FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: claims claims_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER claims_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.claims FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: code_review_finding_challenges code_review_finding_challenges_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER code_review_finding_challenges_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.code_review_finding_challenges FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: code_review_findings code_review_findings_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER code_review_findings_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.code_review_findings FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: plan_versions confirmed_plan_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER confirmed_plan_immutable BEFORE DELETE OR UPDATE ON public.plan_versions FOR EACH ROW EXECUTE FUNCTION public.devproof_confirmed_plan_immutable();


--
-- Name: cycle_plan_selection_current current_plan_selection_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER current_plan_selection_guard BEFORE INSERT OR DELETE OR UPDATE ON public.cycle_plan_selection_current FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_plan_selection();


--
-- Name: cycle_plan_selections cycle_plan_selections_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER cycle_plan_selections_immutable BEFORE DELETE OR UPDATE ON public.cycle_plan_selections FOR EACH ROW EXECUTE FUNCTION public.devproof_immutable_plan_binding();


--
-- Name: delivery_change_links delivery_change_links_association_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER delivery_change_links_association_writer BEFORE INSERT OR DELETE OR UPDATE ON public.delivery_change_links FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_delivery_association_writer();


--
-- Name: delivery_claim_drafts delivery_claim_drafts_claim_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER delivery_claim_drafts_claim_writer BEFORE INSERT OR DELETE OR UPDATE ON public.delivery_claim_drafts FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_delivery_claim_writer();


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_claim_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER delivery_claim_proposal_runs_claim_writer BEFORE INSERT OR DELETE OR UPDATE ON public.delivery_claim_proposal_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_delivery_claim_writer();


--
-- Name: delivery_item_source_links delivery_item_source_links_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER delivery_item_source_links_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.delivery_item_source_links FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: delivery_items delivery_items_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER delivery_items_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.delivery_items FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: document_chunks document_chunks_source_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER document_chunks_source_writer BEFORE INSERT OR DELETE OR UPDATE ON public.document_chunks FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_source_writer();


--
-- Name: evidence_items evidence_items_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evidence_items_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.evidence_items FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: evidence_question_runs evidence_question_runs_question_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER evidence_question_runs_question_writer BEFORE INSERT OR DELETE OR UPDATE ON public.evidence_question_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_evidence_question_writer();


--
-- Name: external_connections external_connections_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER external_connections_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.external_connections FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: external_evidence external_evidence_material_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER external_evidence_material_writer BEFORE INSERT OR DELETE OR UPDATE ON public.external_evidence FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_evidence_material_writer();


--
-- Name: external_resource_revisions external_resource_revisions_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER external_resource_revisions_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.external_resource_revisions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: external_resources external_resources_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER external_resources_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.external_resources FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: git_repositories git_repositories_git_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER git_repositories_git_writer BEFORE INSERT OR DELETE OR UPDATE ON public.git_repositories FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_git_input_writer();


--
-- Name: git_snapshots git_snapshots_git_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER git_snapshots_git_writer BEFORE INSERT OR DELETE OR UPDATE ON public.git_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_git_input_writer();


--
-- Name: human_verification_decisions human_verification_decisions_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER human_verification_decisions_append_only BEFORE DELETE OR UPDATE ON public.human_verification_decisions FOR EACH ROW EXECUTE FUNCTION public.devproof_append_only_report_fact();


--
-- Name: human_verification_decisions human_verification_decisions_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER human_verification_decisions_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.human_verification_decisions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: input_snapshot_bodies input_snapshot_bodies_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_bodies_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_bodies FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_claims input_snapshot_claims_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_claims_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_claims FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_external_evidence input_snapshot_external_evidence_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_external_evidence_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_external_evidence FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_git input_snapshot_git_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_git_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_git FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_manual_evidence input_snapshot_manual_evidence_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_manual_evidence_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_manual_evidence FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_plans input_snapshot_plans_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_plans_immutable BEFORE DELETE OR UPDATE ON public.input_snapshot_plans FOR EACH ROW EXECUTE FUNCTION public.devproof_immutable_plan_binding();


--
-- Name: input_snapshot_plans input_snapshot_plans_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_plans_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_plans FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshot_sources input_snapshot_sources_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshot_sources_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshot_sources FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: input_snapshots input_snapshots_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER input_snapshots_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.input_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_input_writer();


--
-- Name: knowledge_bases knowledge_bases_java_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER knowledge_bases_java_writer BEFORE INSERT OR DELETE OR UPDATE ON public.knowledge_bases FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_base_writer();


--
-- Name: manual_evidence manual_evidence_material_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER manual_evidence_material_writer BEFORE INSERT OR DELETE OR UPDATE ON public.manual_evidence FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_evidence_material_writer();


--
-- Name: model_calls model_calls_question_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER model_calls_question_writer BEFORE INSERT OR DELETE OR UPDATE ON public.model_calls FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_question_model_call_writer();


--
-- Name: model_calls model_calls_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER model_calls_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.model_calls FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: node_attempts node_attempts_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER node_attempts_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.node_attempts FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: orchestration_template_nodes orchestration_template_nodes_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER orchestration_template_nodes_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.orchestration_template_nodes FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: orchestration_templates orchestration_templates_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER orchestration_templates_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.orchestration_templates FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: peripheral_profile_runs peripheral_profile_runs_security_profile_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER peripheral_profile_runs_security_profile_writer BEFORE INSERT OR DELETE OR UPDATE ON public.peripheral_profile_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_security_profile_writer();


--
-- Name: project_health_snapshots project_health_snapshots_status_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_health_snapshots_status_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_health_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_project_status_writer();


--
-- Name: project_knowledge_bases project_knowledge_bases_java_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_knowledge_bases_java_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_knowledge_bases FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_base_writer();


--
-- Name: project_members project_members_management_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_members_management_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_members FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_management_writer('projects');


--
-- Name: project_retrieval_indexes project_retrieval_indexes_source_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_retrieval_indexes_source_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_retrieval_indexes FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_source_writer();


--
-- Name: project_summary_drafts project_summary_drafts_status_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_summary_drafts_status_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_summary_drafts FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_project_status_writer();


--
-- Name: project_summary_records project_summary_records_status_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER project_summary_records_status_writer BEFORE INSERT OR DELETE OR UPDATE ON public.project_summary_records FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_project_status_writer();


--
-- Name: projects projects_management_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER projects_management_writer BEFORE INSERT OR DELETE OR UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_management_writer('projects');


--
-- Name: published_report_bodies published_body_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER published_body_immutable BEFORE DELETE OR UPDATE ON public.published_report_bodies FOR EACH ROW EXECUTE FUNCTION public.devproof_reject_body_mutation();


--
-- Name: published_records published_records_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER published_records_append_only BEFORE DELETE OR UPDATE ON public.published_records FOR EACH ROW EXECUTE FUNCTION public.devproof_append_only_report_fact();


--
-- Name: published_records published_records_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER published_records_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.published_records FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: published_report_bodies published_report_bodies_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER published_report_bodies_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.published_report_bodies FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: report_items report_items_publication_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER report_items_publication_guard BEFORE INSERT OR DELETE OR UPDATE ON public.report_items FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_published_report();


--
-- Name: report_items report_items_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER report_items_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.report_items FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: report_versions report_versions_publication_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER report_versions_publication_guard BEFORE INSERT OR DELETE OR UPDATE ON public.report_versions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_published_report();


--
-- Name: report_versions report_versions_writer_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER report_versions_writer_guard BEFORE INSERT OR DELETE OR UPDATE ON public.report_versions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_report_writer();


--
-- Name: repository_snapshots repository_snapshot_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER repository_snapshot_immutable BEFORE DELETE OR UPDATE ON public.repository_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_immutable_repository_snapshot();


--
-- Name: retrieval_index_build_runs retrieval_index_build_runs_compute_config; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER retrieval_index_build_runs_compute_config BEFORE UPDATE ON public.retrieval_index_build_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_preserve_source_compute_config();


--
-- Name: retrieval_index_build_runs retrieval_index_build_runs_source_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER retrieval_index_build_runs_source_writer BEFORE INSERT OR DELETE OR UPDATE ON public.retrieval_index_build_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_source_writer();


--
-- Name: risk_findings risk_findings_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER risk_findings_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.risk_findings FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: run_events run_events_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER run_events_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.run_events FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: analysis_run_orchestration_snapshots run_orchestration_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER run_orchestration_immutable BEFORE UPDATE ON public.analysis_run_orchestration_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_preserve_orchestration_body();


--
-- Name: security_baseline_records security_baseline_records_security_profile_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER security_baseline_records_security_profile_writer BEFORE INSERT OR DELETE OR UPDATE ON public.security_baseline_records FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_security_profile_writer();


--
-- Name: security_baseline_snapshots security_baseline_snapshots_security_profile_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER security_baseline_snapshots_security_profile_writer BEFORE INSERT OR DELETE OR UPDATE ON public.security_baseline_snapshots FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_security_profile_writer();


--
-- Name: security_findings security_findings_security_profile_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER security_findings_security_profile_writer BEFORE INSERT OR DELETE OR UPDATE ON public.security_findings FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_security_profile_writer();


--
-- Name: security_scan_artifacts security_scan_artifacts_security_profile_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER security_scan_artifacts_security_profile_writer BEFORE INSERT OR DELETE OR UPDATE ON public.security_scan_artifacts FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_security_profile_writer();


--
-- Name: input_snapshot_bodies snapshot_body_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER snapshot_body_immutable BEFORE DELETE OR UPDATE ON public.input_snapshot_bodies FOR EACH ROW EXECUTE FUNCTION public.devproof_immutable_snapshot_body();


--
-- Name: input_snapshot_bodies snapshot_body_scope; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER snapshot_body_scope BEFORE INSERT ON public.input_snapshot_bodies FOR EACH ROW EXECUTE FUNCTION public.devproof_validate_snapshot_body();


--
-- Name: input_snapshot_plans snapshot_plan_scope; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER snapshot_plan_scope BEFORE INSERT ON public.input_snapshot_plans FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_snapshot_plan();


--
-- Name: source_ingestion_jobs source_ingestion_jobs_compute_config; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_ingestion_jobs_compute_config BEFORE UPDATE ON public.source_ingestion_jobs FOR EACH ROW EXECUTE FUNCTION public.devproof_preserve_source_compute_config();


--
-- Name: source_ingestion_jobs source_ingestion_jobs_source_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_ingestion_jobs_source_writer BEFORE INSERT OR DELETE OR UPDATE ON public.source_ingestion_jobs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_source_writer();


--
-- Name: source_revisions source_revision_identity; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_revision_identity BEFORE UPDATE ON public.source_revisions FOR EACH ROW EXECUTE FUNCTION public.devproof_preserve_ready_source();


--
-- Name: source_revisions source_revisions_source_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_revisions_source_writer BEFORE INSERT OR DELETE OR UPDATE ON public.source_revisions FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_knowledge_source_writer();


--
-- Name: source_sync_runs source_sync_runs_github_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_sync_runs_github_writer BEFORE INSERT OR DELETE OR UPDATE ON public.source_sync_runs FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_github_writer();


--
-- Name: task_orchestration_bindings task_orchestration_bindings_orchestration_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER task_orchestration_bindings_orchestration_writer BEFORE INSERT OR DELETE OR UPDATE ON public.task_orchestration_bindings FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_orchestration_writer();


--
-- Name: users users_identity_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER users_identity_writer BEFORE INSERT OR DELETE OR UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_identity_writer();


--
-- Name: verification_cycles verification_cycles_management_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER verification_cycles_management_writer BEFORE INSERT OR DELETE OR UPDATE ON public.verification_cycles FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_management_writer('task-management');


--
-- Name: verification_results verification_results_verification_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER verification_results_verification_writer BEFORE INSERT OR DELETE OR UPDATE ON public.verification_results FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_verification_writer();


--
-- Name: verification_tasks verification_tasks_management_writer; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER verification_tasks_management_writer BEFORE INSERT OR DELETE OR UPDATE ON public.verification_tasks FOR EACH ROW EXECUTE FUNCTION public.devproof_guard_management_writer('task-management');


--
-- Name: agent_capabilities agent_capabilities_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capabilities
    ADD CONSTRAINT agent_capabilities_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: agent_capabilities agent_capabilities_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capabilities
    ADD CONSTRAINT agent_capabilities_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: agent_capability_versions agent_capability_versions_capability_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capability_versions
    ADD CONSTRAINT agent_capability_versions_capability_id_fkey FOREIGN KEY (capability_id) REFERENCES public.agent_capabilities(id) ON DELETE CASCADE;


--
-- Name: agent_capability_versions agent_capability_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_capability_versions
    ADD CONSTRAINT agent_capability_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: agent_change_proposal_runs agent_change_proposal_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_change_proposal_runs
    ADD CONSTRAINT agent_change_proposal_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: agent_change_proposal_runs agent_change_proposal_runs_delivery_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_change_proposal_runs
    ADD CONSTRAINT agent_change_proposal_runs_delivery_item_id_fkey FOREIGN KEY (delivery_item_id) REFERENCES public.delivery_items(id) ON DELETE CASCADE;


--
-- Name: agent_change_proposal_runs agent_change_proposal_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_change_proposal_runs
    ADD CONSTRAINT agent_change_proposal_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: agent_task_attempts agent_task_attempts_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_attempts
    ADD CONSTRAINT agent_task_attempts_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id);


--
-- Name: agent_task_events agent_task_events_attempt_id_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_task_events
    ADD CONSTRAINT agent_task_events_attempt_id_task_id_fkey FOREIGN KEY (attempt_id, task_id) REFERENCES public.agent_task_attempts(id, task_id);


--
-- Name: agent_tasks agent_tasks_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id);


--
-- Name: agent_tasks agent_tasks_claim_proposal_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_claim_proposal_run_id_fkey FOREIGN KEY (claim_proposal_run_id) REFERENCES public.delivery_claim_proposal_runs(id);


--
-- Name: agent_tasks agent_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: agent_tasks agent_tasks_planning_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_planning_run_id_fkey FOREIGN KEY (planning_run_id) REFERENCES public.planning_runs(id);


--
-- Name: agent_tasks agent_tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: agent_tasks agent_tasks_question_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_question_run_id_fkey FOREIGN KEY (question_run_id) REFERENCES public.evidence_question_runs(id);


--
-- Name: agent_tool_executions agent_tool_executions_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_executions
    ADD CONSTRAINT agent_tool_executions_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: agent_tool_executions agent_tool_executions_input_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_executions
    ADD CONSTRAINT agent_tool_executions_input_snapshot_id_fkey FOREIGN KEY (input_snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: agent_tool_executions agent_tool_executions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tool_executions
    ADD CONSTRAINT agent_tool_executions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: agent_tools agent_tools_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: agent_tools agent_tools_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tools
    ADD CONSTRAINT agent_tools_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: analysis_jobs analysis_jobs_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_jobs
    ADD CONSTRAINT analysis_jobs_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: analysis_run_context_artifacts analysis_run_context_artifacts_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_context_artifacts
    ADD CONSTRAINT analysis_run_context_artifacts_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: analysis_run_context_artifacts analysis_run_context_artifacts_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_context_artifacts
    ADD CONSTRAINT analysis_run_context_artifacts_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES public.artifact_objects(id) ON DELETE RESTRICT;


--
-- Name: analysis_run_manifests analysis_run_manifests_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_manifests
    ADD CONSTRAINT analysis_run_manifests_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: analysis_run_orchestration_snapshots analysis_run_orchestration_snapshots_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_orchestration_snapshots
    ADD CONSTRAINT analysis_run_orchestration_snapshots_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: analysis_run_orchestration_snapshots analysis_run_orchestration_snapshots_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_run_orchestration_snapshots
    ADD CONSTRAINT analysis_run_orchestration_snapshots_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.orchestration_templates(id);


--
-- Name: analysis_runs analysis_runs_plan_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_plan_version_id_fkey FOREIGN KEY (plan_version_id) REFERENCES public.plan_versions(id);


--
-- Name: analysis_runs analysis_runs_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: approval_actions approval_actions_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_actions
    ADD CONSTRAINT approval_actions_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: approval_actions approval_actions_report_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_actions
    ADD CONSTRAINT approval_actions_report_version_id_fkey FOREIGN KEY (report_version_id) REFERENCES public.report_versions(id) ON DELETE CASCADE;


--
-- Name: approval_actions approval_actions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_actions
    ADD CONSTRAINT approval_actions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id);


--
-- Name: artifact_objects artifact_objects_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artifact_objects
    ADD CONSTRAINT artifact_objects_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: audit_events audit_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: audit_events audit_events_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: claim_evidence_links claim_evidence_links_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_evidence_links
    ADD CONSTRAINT claim_evidence_links_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE CASCADE;


--
-- Name: claim_evidence_links claim_evidence_links_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claim_evidence_links
    ADD CONSTRAINT claim_evidence_links_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.evidence_items(id) ON DELETE CASCADE;


--
-- Name: claims claims_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id);


--
-- Name: code_review_finding_challenges code_review_finding_challenges_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_finding_challenges
    ADD CONSTRAINT code_review_finding_challenges_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: code_review_finding_challenges code_review_finding_challenges_finding_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_finding_challenges
    ADD CONSTRAINT code_review_finding_challenges_finding_id_fkey FOREIGN KEY (finding_id) REFERENCES public.code_review_findings(id) ON DELETE CASCADE;


--
-- Name: code_review_finding_challenges code_review_finding_challenges_model_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_finding_challenges
    ADD CONSTRAINT code_review_finding_challenges_model_call_id_fkey FOREIGN KEY (model_call_id) REFERENCES public.model_calls(id) ON DELETE SET NULL;


--
-- Name: code_review_findings code_review_findings_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_findings
    ADD CONSTRAINT code_review_findings_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: code_review_findings code_review_findings_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_findings
    ADD CONSTRAINT code_review_findings_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE SET NULL;


--
-- Name: code_review_findings code_review_findings_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.code_review_findings
    ADD CONSTRAINT code_review_findings_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.evidence_items(id);


--
-- Name: cycle_plan_selection_current cycle_plan_selection_current_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selection_current
    ADD CONSTRAINT cycle_plan_selection_current_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id);


--
-- Name: cycle_plan_selection_current cycle_plan_selection_current_selection_id_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selection_current
    ADD CONSTRAINT cycle_plan_selection_current_selection_id_cycle_id_fkey FOREIGN KEY (selection_id, cycle_id) REFERENCES public.cycle_plan_selections(id, cycle_id);


--
-- Name: cycle_plan_selections cycle_plan_selections_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT cycle_plan_selections_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: cycle_plan_selections cycle_plan_selections_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT cycle_plan_selections_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id);


--
-- Name: cycle_plan_selections cycle_plan_selections_plan_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cycle_plan_selections
    ADD CONSTRAINT cycle_plan_selections_plan_version_id_fkey FOREIGN KEY (plan_version_id) REFERENCES public.plan_versions(id);


--
-- Name: delivery_change_links delivery_change_links_confirmed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_confirmed_by_fkey FOREIGN KEY (confirmed_by) REFERENCES public.users(id);


--
-- Name: delivery_change_links delivery_change_links_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: delivery_change_links delivery_change_links_delivery_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_delivery_item_id_fkey FOREIGN KEY (delivery_item_id) REFERENCES public.delivery_items(id) ON DELETE CASCADE;


--
-- Name: delivery_change_links delivery_change_links_git_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_git_snapshot_id_fkey FOREIGN KEY (git_snapshot_id) REFERENCES public.git_snapshots(id) ON DELETE RESTRICT;


--
-- Name: delivery_change_links delivery_change_links_pull_request_resource_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT delivery_change_links_pull_request_resource_id_fkey FOREIGN KEY (pull_request_resource_id) REFERENCES public.external_resources(id) ON DELETE RESTRICT;


--
-- Name: delivery_claim_drafts delivery_claim_drafts_confirmed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_drafts
    ADD CONSTRAINT delivery_claim_drafts_confirmed_by_fkey FOREIGN KEY (confirmed_by) REFERENCES public.users(id);


--
-- Name: delivery_claim_drafts delivery_claim_drafts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_drafts
    ADD CONSTRAINT delivery_claim_drafts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: delivery_claim_drafts delivery_claim_drafts_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_drafts
    ADD CONSTRAINT delivery_claim_drafts_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_proposal_runs
    ADD CONSTRAINT delivery_claim_proposal_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_proposal_runs
    ADD CONSTRAINT delivery_claim_proposal_runs_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id);


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_proposal_runs
    ADD CONSTRAINT delivery_claim_proposal_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: delivery_claim_proposal_runs delivery_claim_proposal_runs_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_claim_proposal_runs
    ADD CONSTRAINT delivery_claim_proposal_runs_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.verification_tasks(id);


--
-- Name: delivery_item_source_links delivery_item_source_links_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_item_source_links
    ADD CONSTRAINT delivery_item_source_links_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: delivery_item_source_links delivery_item_source_links_delivery_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_item_source_links
    ADD CONSTRAINT delivery_item_source_links_delivery_item_id_fkey FOREIGN KEY (delivery_item_id) REFERENCES public.delivery_items(id) ON DELETE CASCADE;


--
-- Name: delivery_item_source_links delivery_item_source_links_external_resource_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_item_source_links
    ADD CONSTRAINT delivery_item_source_links_external_resource_revision_id_fkey FOREIGN KEY (external_resource_revision_id) REFERENCES public.external_resource_revisions(id) ON DELETE RESTRICT;


--
-- Name: delivery_item_source_links delivery_item_source_links_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_item_source_links
    ADD CONSTRAINT delivery_item_source_links_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id) ON DELETE RESTRICT;


--
-- Name: delivery_items delivery_items_external_resource_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_items
    ADD CONSTRAINT delivery_items_external_resource_id_fkey FOREIGN KEY (external_resource_id) REFERENCES public.external_resources(id) ON DELETE RESTRICT;


--
-- Name: delivery_items delivery_items_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_items
    ADD CONSTRAINT delivery_items_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: document_chunks document_chunks_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id) ON DELETE CASCADE;


--
-- Name: evidence_items evidence_items_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT evidence_items_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: evidence_items evidence_items_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT evidence_items_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: evidence_items evidence_items_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_items
    ADD CONSTRAINT evidence_items_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id);


--
-- Name: evidence_question_runs evidence_question_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_question_runs
    ADD CONSTRAINT evidence_question_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: evidence_question_runs evidence_question_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_question_runs
    ADD CONSTRAINT evidence_question_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: evidence_question_runs evidence_question_runs_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evidence_question_runs
    ADD CONSTRAINT evidence_question_runs_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id);


--
-- Name: external_connections external_connections_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_connections
    ADD CONSTRAINT external_connections_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: external_connections external_connections_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_connections
    ADD CONSTRAINT external_connections_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: external_evidence external_evidence_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_evidence
    ADD CONSTRAINT external_evidence_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: external_evidence external_evidence_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_evidence
    ADD CONSTRAINT external_evidence_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: external_evidence external_evidence_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_evidence
    ADD CONSTRAINT external_evidence_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id);


--
-- Name: external_resource_revisions external_resource_revisions_resource_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resource_revisions
    ADD CONSTRAINT external_resource_revisions_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES public.external_resources(id) ON DELETE CASCADE;


--
-- Name: external_resources external_resources_connection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_resources
    ADD CONSTRAINT external_resources_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES public.external_connections(id) ON DELETE CASCADE;


--
-- Name: delivery_change_links fk_delivery_change_link_agent_proposal_run; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.delivery_change_links
    ADD CONSTRAINT fk_delivery_change_link_agent_proposal_run FOREIGN KEY (agent_proposal_run_id) REFERENCES public.agent_change_proposal_runs(id) ON DELETE RESTRICT;


--
-- Name: manual_evidence fk_manual_evidence_tool_execution; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT fk_manual_evidence_tool_execution FOREIGN KEY (source_tool_execution_id) REFERENCES public.agent_tool_executions(id) ON DELETE RESTRICT;


--
-- Name: git_repositories git_repositories_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_repositories
    ADD CONSTRAINT git_repositories_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: git_snapshots git_snapshots_code_change_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_snapshots
    ADD CONSTRAINT git_snapshots_code_change_artifact_id_fkey FOREIGN KEY (code_change_artifact_id) REFERENCES public.artifact_objects(id);


--
-- Name: git_snapshots git_snapshots_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_snapshots
    ADD CONSTRAINT git_snapshots_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: git_snapshots git_snapshots_diff_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_snapshots
    ADD CONSTRAINT git_snapshots_diff_artifact_id_fkey FOREIGN KEY (diff_artifact_id) REFERENCES public.artifact_objects(id);


--
-- Name: git_snapshots git_snapshots_repository_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.git_snapshots
    ADD CONSTRAINT git_snapshots_repository_id_fkey FOREIGN KEY (repository_id) REFERENCES public.git_repositories(id);


--
-- Name: human_verification_decisions human_verification_decisions_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_verification_decisions
    ADD CONSTRAINT human_verification_decisions_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: human_verification_decisions human_verification_decisions_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_verification_decisions
    ADD CONSTRAINT human_verification_decisions_result_id_fkey FOREIGN KEY (result_id) REFERENCES public.verification_results(id) ON DELETE CASCADE;


--
-- Name: human_verification_decisions human_verification_decisions_supersedes_decision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.human_verification_decisions
    ADD CONSTRAINT human_verification_decisions_supersedes_decision_id_fkey FOREIGN KEY (supersedes_decision_id) REFERENCES public.human_verification_decisions(id);


--
-- Name: idea_revisions idea_revisions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idea_revisions
    ADD CONSTRAINT idea_revisions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: idea_revisions idea_revisions_idea_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idea_revisions
    ADD CONSTRAINT idea_revisions_idea_id_fkey FOREIGN KEY (idea_id) REFERENCES public.ideas(id);


--
-- Name: ideas ideas_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas
    ADD CONSTRAINT ideas_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: ideas ideas_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ideas
    ADD CONSTRAINT ideas_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: input_snapshot_bodies input_snapshot_bodies_snapshot_id_content_hash_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_bodies
    ADD CONSTRAINT input_snapshot_bodies_snapshot_id_content_hash_fkey FOREIGN KEY (snapshot_id, content_hash) REFERENCES public.input_snapshots(id, snapshot_hash);


--
-- Name: input_snapshot_claims input_snapshot_claims_delivery_claim_draft_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_claims
    ADD CONSTRAINT input_snapshot_claims_delivery_claim_draft_id_fkey FOREIGN KEY (delivery_claim_draft_id) REFERENCES public.delivery_claim_drafts(id);


--
-- Name: input_snapshot_claims input_snapshot_claims_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_claims
    ADD CONSTRAINT input_snapshot_claims_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: input_snapshot_external_evidence input_snapshot_external_evidence_external_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_external_evidence
    ADD CONSTRAINT input_snapshot_external_evidence_external_evidence_id_fkey FOREIGN KEY (external_evidence_id) REFERENCES public.external_evidence(id);


--
-- Name: input_snapshot_external_evidence input_snapshot_external_evidence_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_external_evidence
    ADD CONSTRAINT input_snapshot_external_evidence_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: input_snapshot_git input_snapshot_git_git_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_git
    ADD CONSTRAINT input_snapshot_git_git_snapshot_id_fkey FOREIGN KEY (git_snapshot_id) REFERENCES public.git_snapshots(id);


--
-- Name: input_snapshot_git input_snapshot_git_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_git
    ADD CONSTRAINT input_snapshot_git_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: input_snapshot_manual_evidence input_snapshot_manual_evidence_manual_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_manual_evidence
    ADD CONSTRAINT input_snapshot_manual_evidence_manual_evidence_id_fkey FOREIGN KEY (manual_evidence_id) REFERENCES public.manual_evidence(id);


--
-- Name: input_snapshot_manual_evidence input_snapshot_manual_evidence_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_manual_evidence
    ADD CONSTRAINT input_snapshot_manual_evidence_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: input_snapshot_plans input_snapshot_plans_selection_id_plan_version_id_plan_con_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_plans
    ADD CONSTRAINT input_snapshot_plans_selection_id_plan_version_id_plan_con_fkey FOREIGN KEY (selection_id, plan_version_id, plan_content_hash, selection_hash) REFERENCES public.cycle_plan_selections(id, plan_version_id, plan_content_hash, content_hash);


--
-- Name: input_snapshot_plans input_snapshot_plans_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_plans
    ADD CONSTRAINT input_snapshot_plans_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id);


--
-- Name: input_snapshot_sources input_snapshot_sources_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_sources
    ADD CONSTRAINT input_snapshot_sources_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.input_snapshots(id) ON DELETE CASCADE;


--
-- Name: input_snapshot_sources input_snapshot_sources_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshot_sources
    ADD CONSTRAINT input_snapshot_sources_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id);


--
-- Name: input_snapshots input_snapshots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshots
    ADD CONSTRAINT input_snapshots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: input_snapshots input_snapshots_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.input_snapshots
    ADD CONSTRAINT input_snapshots_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: knowledge_bases knowledge_bases_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: knowledge_bases knowledge_bases_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: manual_evidence manual_evidence_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT manual_evidence_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: manual_evidence manual_evidence_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT manual_evidence_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: manual_evidence manual_evidence_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_evidence
    ADD CONSTRAINT manual_evidence_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id);


--
-- Name: model_calls model_calls_agent_task_attempt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls
    ADD CONSTRAINT model_calls_agent_task_attempt_id_fkey FOREIGN KEY (agent_task_attempt_id) REFERENCES public.agent_task_attempts(id);


--
-- Name: model_calls model_calls_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_calls
    ADD CONSTRAINT model_calls_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: node_attempts node_attempts_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_attempts
    ADD CONSTRAINT node_attempts_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: orchestration_template_nodes orchestration_template_nodes_capability_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_template_nodes
    ADD CONSTRAINT orchestration_template_nodes_capability_version_id_fkey FOREIGN KEY (capability_version_id) REFERENCES public.agent_capability_versions(id);


--
-- Name: orchestration_template_nodes orchestration_template_nodes_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_template_nodes
    ADD CONSTRAINT orchestration_template_nodes_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.orchestration_templates(id) ON DELETE CASCADE;


--
-- Name: orchestration_templates orchestration_templates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_templates
    ADD CONSTRAINT orchestration_templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: orchestration_templates orchestration_templates_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestration_templates
    ADD CONSTRAINT orchestration_templates_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: peripheral_profile_runs peripheral_profile_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peripheral_profile_runs
    ADD CONSTRAINT peripheral_profile_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: peripheral_profile_runs peripheral_profile_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peripheral_profile_runs
    ADD CONSTRAINT peripheral_profile_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: plan_versions plan_versions_confirmed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_confirmed_by_fkey FOREIGN KEY (confirmed_by) REFERENCES public.users(id);


--
-- Name: plan_versions plan_versions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: plan_versions plan_versions_idea_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_idea_revision_id_fkey FOREIGN KEY (idea_revision_id) REFERENCES public.idea_revisions(id);


--
-- Name: plan_versions plan_versions_parent_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_parent_plan_id_fkey FOREIGN KEY (parent_plan_id) REFERENCES public.plan_versions(id);


--
-- Name: plan_versions plan_versions_planning_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plan_versions
    ADD CONSTRAINT plan_versions_planning_run_id_fkey FOREIGN KEY (planning_run_id) REFERENCES public.planning_runs(id);


--
-- Name: planning_input_snapshots planning_input_snapshots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_input_snapshots
    ADD CONSTRAINT planning_input_snapshots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: planning_input_snapshots planning_input_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_input_snapshots
    ADD CONSTRAINT planning_input_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: planning_input_snapshots planning_input_snapshots_repository_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_input_snapshots
    ADD CONSTRAINT planning_input_snapshots_repository_snapshot_id_fkey FOREIGN KEY (repository_snapshot_id) REFERENCES public.repository_snapshots(id);


--
-- Name: planning_questions planning_questions_answered_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_questions
    ADD CONSTRAINT planning_questions_answered_by_fkey FOREIGN KEY (answered_by) REFERENCES public.users(id);


--
-- Name: planning_questions planning_questions_planning_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_questions
    ADD CONSTRAINT planning_questions_planning_run_id_fkey FOREIGN KEY (planning_run_id) REFERENCES public.planning_runs(id);


--
-- Name: planning_runs planning_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT planning_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: planning_runs planning_runs_idea_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT planning_runs_idea_revision_id_fkey FOREIGN KEY (idea_revision_id) REFERENCES public.idea_revisions(id);


--
-- Name: planning_runs planning_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT planning_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: planning_runs planning_runs_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.planning_runs
    ADD CONSTRAINT planning_runs_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.planning_input_snapshots(id);


--
-- Name: project_health_snapshots project_health_snapshots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_health_snapshots
    ADD CONSTRAINT project_health_snapshots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: project_health_snapshots project_health_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_health_snapshots
    ADD CONSTRAINT project_health_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_knowledge_bases project_knowledge_bases_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_knowledge_bases
    ADD CONSTRAINT project_knowledge_bases_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: project_knowledge_bases project_knowledge_bases_knowledge_base_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_knowledge_bases
    ADD CONSTRAINT project_knowledge_bases_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE;


--
-- Name: project_knowledge_bases project_knowledge_bases_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_knowledge_bases
    ADD CONSTRAINT project_knowledge_bases_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_members project_members_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_members project_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_retrieval_indexes project_retrieval_indexes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_retrieval_indexes
    ADD CONSTRAINT project_retrieval_indexes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: project_retrieval_indexes project_retrieval_indexes_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_retrieval_indexes
    ADD CONSTRAINT project_retrieval_indexes_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_summary_drafts project_summary_drafts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_drafts
    ADD CONSTRAINT project_summary_drafts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: project_summary_drafts project_summary_drafts_health_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_drafts
    ADD CONSTRAINT project_summary_drafts_health_snapshot_id_fkey FOREIGN KEY (health_snapshot_id) REFERENCES public.project_health_snapshots(id) ON DELETE RESTRICT;


--
-- Name: project_summary_drafts project_summary_drafts_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_drafts
    ADD CONSTRAINT project_summary_drafts_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_summary_records project_summary_records_health_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_health_snapshot_id_fkey FOREIGN KEY (health_snapshot_id) REFERENCES public.project_health_snapshots(id) ON DELETE RESTRICT;


--
-- Name: project_summary_records project_summary_records_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_summary_records project_summary_records_published_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_published_by_fkey FOREIGN KEY (published_by) REFERENCES public.users(id);


--
-- Name: project_summary_records project_summary_records_summary_draft_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_summary_records
    ADD CONSTRAINT project_summary_records_summary_draft_id_fkey FOREIGN KEY (summary_draft_id) REFERENCES public.project_summary_drafts(id) ON DELETE RESTRICT;


--
-- Name: projects projects_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id);


--
-- Name: published_records published_records_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id);


--
-- Name: published_records published_records_published_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_published_by_fkey FOREIGN KEY (published_by) REFERENCES public.users(id);


--
-- Name: published_records published_records_report_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_report_version_id_fkey FOREIGN KEY (report_version_id) REFERENCES public.report_versions(id);


--
-- Name: published_records published_records_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_records
    ADD CONSTRAINT published_records_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.verification_tasks(id);


--
-- Name: published_report_bodies published_report_bodies_report_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.published_report_bodies
    ADD CONSTRAINT published_report_bodies_report_version_id_fkey FOREIGN KEY (report_version_id) REFERENCES public.report_versions(id);


--
-- Name: report_generation_jobs report_generation_jobs_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.report_versions(id);


--
-- Name: report_generation_jobs report_generation_jobs_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_generation_jobs
    ADD CONSTRAINT report_generation_jobs_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id);


--
-- Name: report_items report_items_report_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_items
    ADD CONSTRAINT report_items_report_version_id_fkey FOREIGN KEY (report_version_id) REFERENCES public.report_versions(id) ON DELETE CASCADE;


--
-- Name: report_items report_items_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_items
    ADD CONSTRAINT report_items_result_id_fkey FOREIGN KEY (result_id) REFERENCES public.verification_results(id);


--
-- Name: report_versions report_versions_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.verification_cycles(id) ON DELETE CASCADE;


--
-- Name: report_versions report_versions_parent_report_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_parent_report_version_id_fkey FOREIGN KEY (parent_report_version_id) REFERENCES public.report_versions(id);


--
-- Name: report_versions report_versions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id);


--
-- Name: report_versions report_versions_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_versions
    ADD CONSTRAINT report_versions_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id);


--
-- Name: repository_snapshots repository_snapshots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repository_snapshots
    ADD CONSTRAINT repository_snapshots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: repository_snapshots repository_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repository_snapshots
    ADD CONSTRAINT repository_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: repository_snapshots repository_snapshots_repository_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repository_snapshots
    ADD CONSTRAINT repository_snapshots_repository_id_fkey FOREIGN KEY (repository_id) REFERENCES public.git_repositories(id);


--
-- Name: retrieval_index_build_runs retrieval_index_build_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_index_build_runs
    ADD CONSTRAINT retrieval_index_build_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: retrieval_index_build_runs retrieval_index_build_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_index_build_runs
    ADD CONSTRAINT retrieval_index_build_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: risk_findings risk_findings_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_findings
    ADD CONSTRAINT risk_findings_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: risk_findings risk_findings_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_findings
    ADD CONSTRAINT risk_findings_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE CASCADE;


--
-- Name: risk_findings risk_findings_evidence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_findings
    ADD CONSTRAINT risk_findings_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES public.evidence_items(id);


--
-- Name: run_events run_events_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.run_events
    ADD CONSTRAINT run_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.analysis_runs(id) ON DELETE CASCADE;


--
-- Name: security_baseline_records security_baseline_records_baseline_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_baseline_snapshot_id_fkey FOREIGN KEY (baseline_snapshot_id) REFERENCES public.security_baseline_snapshots(id) ON DELETE RESTRICT;


--
-- Name: security_baseline_records security_baseline_records_confirmed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_confirmed_by_fkey FOREIGN KEY (confirmed_by) REFERENCES public.users(id);


--
-- Name: security_baseline_records security_baseline_records_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_records
    ADD CONSTRAINT security_baseline_records_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: security_baseline_snapshots security_baseline_snapshots_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_snapshots
    ADD CONSTRAINT security_baseline_snapshots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: security_baseline_snapshots security_baseline_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_snapshots
    ADD CONSTRAINT security_baseline_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: security_baseline_snapshots security_baseline_snapshots_repository_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_baseline_snapshots
    ADD CONSTRAINT security_baseline_snapshots_repository_id_fkey FOREIGN KEY (repository_id) REFERENCES public.git_repositories(id) ON DELETE RESTRICT;


--
-- Name: security_findings security_findings_scan_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_findings
    ADD CONSTRAINT security_findings_scan_artifact_id_fkey FOREIGN KEY (scan_artifact_id) REFERENCES public.security_scan_artifacts(id) ON DELETE CASCADE;


--
-- Name: security_findings security_findings_status_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_findings
    ADD CONSTRAINT security_findings_status_updated_by_fkey FOREIGN KEY (status_updated_by) REFERENCES public.users(id);


--
-- Name: security_scan_artifacts security_scan_artifacts_imported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_scan_artifacts
    ADD CONSTRAINT security_scan_artifacts_imported_by_fkey FOREIGN KEY (imported_by) REFERENCES public.users(id);


--
-- Name: security_scan_artifacts security_scan_artifacts_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_scan_artifacts
    ADD CONSTRAINT security_scan_artifacts_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: security_scan_artifacts security_scan_artifacts_repository_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_scan_artifacts
    ADD CONSTRAINT security_scan_artifacts_repository_id_fkey FOREIGN KEY (repository_id) REFERENCES public.git_repositories(id) ON DELETE RESTRICT;


--
-- Name: source_ingestion_jobs source_ingestion_jobs_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_ingestion_jobs
    ADD CONSTRAINT source_ingestion_jobs_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: source_ingestion_jobs source_ingestion_jobs_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_ingestion_jobs
    ADD CONSTRAINT source_ingestion_jobs_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revisions(id) ON DELETE CASCADE;


--
-- Name: source_revisions source_revisions_knowledge_base_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revisions
    ADD CONSTRAINT source_revisions_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE SET NULL;


--
-- Name: source_revisions source_revisions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revisions
    ADD CONSTRAINT source_revisions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: source_sync_runs source_sync_runs_connection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_sync_runs
    ADD CONSTRAINT source_sync_runs_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES public.external_connections(id) ON DELETE CASCADE;


--
-- Name: source_sync_runs source_sync_runs_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_sync_runs
    ADD CONSTRAINT source_sync_runs_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: task_orchestration_bindings task_orchestration_bindings_bound_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_orchestration_bindings
    ADD CONSTRAINT task_orchestration_bindings_bound_by_fkey FOREIGN KEY (bound_by) REFERENCES public.users(id);


--
-- Name: task_orchestration_bindings task_orchestration_bindings_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_orchestration_bindings
    ADD CONSTRAINT task_orchestration_bindings_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.verification_tasks(id) ON DELETE CASCADE;


--
-- Name: task_orchestration_bindings task_orchestration_bindings_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_orchestration_bindings
    ADD CONSTRAINT task_orchestration_bindings_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.orchestration_templates(id);


--
-- Name: verification_cycles verification_cycles_created_from_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_cycles
    ADD CONSTRAINT verification_cycles_created_from_cycle_id_fkey FOREIGN KEY (created_from_cycle_id) REFERENCES public.verification_cycles(id);


--
-- Name: verification_cycles verification_cycles_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_cycles
    ADD CONSTRAINT verification_cycles_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.verification_tasks(id) ON DELETE CASCADE;


--
-- Name: verification_results verification_results_claim_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_results
    ADD CONSTRAINT verification_results_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES public.claims(id) ON DELETE CASCADE;


--
-- Name: verification_tasks verification_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_tasks
    ADD CONSTRAINT verification_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: verification_tasks verification_tasks_delivery_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_tasks
    ADD CONSTRAINT verification_tasks_delivery_item_id_fkey FOREIGN KEY (delivery_item_id) REFERENCES public.delivery_items(id) ON DELETE RESTRICT;


--
-- Name: verification_tasks verification_tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.verification_tasks
    ADD CONSTRAINT verification_tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--



SET search_path TO public;
INSERT INTO public.alembic_version(version_num) VALUES ('059_java_security_profiles');
INSERT INTO public.business_write_owners(aggregate_key,owner) VALUES
('delivery-associations','JAVA'),
('delivery-claims','JAVA'),
('evidence-materials','JAVA'),
('evidence-questions','JAVA'),
('github-sources','JAVA'),
('git-inputs','JAVA'),
('identity','JAVA'),
('knowledge-bases','JAVA'),
('knowledge-sources','JAVA'),
('orchestration','JAVA'),
('peripheral-profiles','JAVA'),
('projects','JAVA'),
('project-status','JAVA'),
('reports','JAVA'),
('security-baselines','JAVA'),
('task-management','JAVA'),
('verification','JAVA'),
('verification-inputs','JAVA');
