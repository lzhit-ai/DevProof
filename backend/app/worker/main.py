"""Durable worker: short claim transaction, visible lease heartbeat, bounded retry."""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.domain.enums import AssessmentProfile
from app.domain.errors import DomainError
from app.application.services.report_service import create_automatic_draft
from app.infrastructure.persistence.models import AnalysisJob, AnalysisRun, AnalysisRunManifest, AnalysisRunOrchestrationSnapshot, InputSnapshot, RunEvent, VerificationCycle, VerificationResult
from app.application.services.verification_workflow_service import run_verification_graph
from app.worker.source_ingestion import claim_and_complete_one as claim_and_complete_one_source_ingestion
from app.worker.github_sync import claim_and_complete_one_sync
from app.infrastructure.business_ownership import verification_owner, require_python_verification

logger = logging.getLogger(__name__)
_RETRY_SECONDS = (30, 120, 300)
_DELIVERY_PROFILE = AssessmentProfile.DELIVERY_VERIFICATION.value


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("worker_started worker_id=%s", settings.worker_id)
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            _claim_and_complete_one(settings.worker_id, settings.job_lease_seconds)
            claim_and_complete_one_source_ingestion(worker_id=settings.worker_id, lease_seconds=settings.job_lease_seconds)
            claim_and_complete_one_sync(worker_id=settings.worker_id, lease_seconds=settings.job_lease_seconds)
            logger.info("worker_heartbeat worker_id=%s", settings.worker_id)
        except SQLAlchemyError:
            logger.exception("worker_database_unavailable worker_id=%s", settings.worker_id)
        time.sleep(15)


class _LeaseHeartbeat:
    def __init__(self, job_id: UUID, worker_id: str, lease_seconds: int) -> None:
        self._job_id = job_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"lease-{job_id}")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(5, min(15, self._lease_seconds // 3))
        while not self._stop.wait(interval):
            now = datetime.now(UTC)
            try:
                with SessionLocal.begin() as session:
                    job = session.get(AnalysisJob, self._job_id)
                    if job is None or job.job_status != "RUNNING" or job.lease_owner != self._worker_id:
                        return
                    job.heartbeat_at = now
                    job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
            except SQLAlchemyError:
                logger.exception("lease_heartbeat_failed job_id=%s", self._job_id)


def _claim_one(worker_id: str, lease_seconds: int) -> tuple[UUID, UUID] | None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        owner = verification_owner(session)
        job = (
            session.query(AnalysisJob)
            .join(AnalysisRun, AnalysisRun.id == AnalysisJob.run_id)
            .filter(
                AnalysisRun.executor_owner == "PYTHON",
                AnalysisRun.assessment_profile != _DELIVERY_PROFILE if owner == "JAVA" else True,
                or_(
                    and_(AnalysisJob.job_status == "QUEUED", or_(AnalysisJob.available_at.is_(None), AnalysisJob.available_at <= now)),
                    and_(AnalysisJob.job_status == "RUNNING", AnalysisJob.lease_expires_at < now),
                )
            )
            .order_by(AnalysisJob.available_at.nullsfirst(), AnalysisJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            return None
        run = session.get(AnalysisRun, job.run_id)
        if run is None:
            job.job_status = "FAILED"
            job.last_error_code = "RUN_MISSING"
            return None
        if run.cancel_requested_at is not None:
            _cancel(session, job, run, now, worker_id)
            return None
        job.job_status = "RUNNING"
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.heartbeat_at = now
        job.available_at = None
        job.attempt_no += 1
        run.run_status = "RUNNING"
        run.started_at = run.started_at or now
        session.add(RunEvent(run_id=run.id, node_id=None, event_type="JOB_CLAIMED", status="RUNNING", correlation_id=str(run.id), payload_redacted={"workerId": worker_id, "attempt": job.attempt_no}))
        return job.id, run.id


def _claim_and_complete_one(worker_id: str, lease_seconds: int) -> None:
    claimed = _claim_one(worker_id, lease_seconds)
    if claimed is None:
        return
    job_id, run_id = claimed
    heartbeat = _LeaseHeartbeat(job_id, worker_id, lease_seconds)
    heartbeat.start()
    graph_state: dict | None = None
    failure: Exception | None = None
    try:
        with SessionLocal.begin() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise DomainError("RUN_MISSING", "analysis run is missing")
            graph_state = _run_profile_workflow(session, run)
    except Exception as exc:
        failure = exc
        logger.exception("workflow_failed run_id=%s", run_id)
    finally:
        heartbeat.stop()
    _complete(job_id, run_id, worker_id, graph_state, failure)


def _complete(job_id: UUID, run_id: UUID, worker_id: str, graph_state: dict | None, failure: Exception | None) -> None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        job = session.get(AnalysisJob, job_id)
        run = session.get(AnalysisRun, run_id)
        if job is None or run is None or job.lease_owner != worker_id:
            return
        if run.assessment_profile == _DELIVERY_PROFILE:
            require_python_verification(session)
            from app.infrastructure.business_ownership import report_owner
            report_owner(session)
        if run.cancel_requested_at is not None or (isinstance(failure, DomainError) and failure.code == "RUN_CANCELLED"):
            _cancel(session, job, run, now, worker_id)
            return
        if failure is None:
            job.job_status = "SUCCEEDED"
            run.run_status = "PARTIALLY_COMPLETED" if graph_state and graph_state.get("node_errors") else "SUCCEEDED"
            run.finished_at = now
            job.lease_owner = None
            job.lease_expires_at = None
            _derive_cycle_status(session, run)
            _create_report_draft_when_enabled(session, run)
        else:
            job.last_error_code = "WORKFLOW_FAILED"
            if job.attempt_no >= job.max_attempts:
                job.job_status = "FAILED"
                run.run_status = "FAILED"
                run.finished_at = now
                job.lease_owner = None
                job.lease_expires_at = None
                _derive_cycle_status(session, run)
            else:
                job.job_status = "QUEUED"
                job.available_at = now + timedelta(seconds=_RETRY_SECONDS[min(job.attempt_no - 1, len(_RETRY_SECONDS) - 1)])
                job.lease_owner = None
                job.lease_expires_at = None
                run.run_status = "QUEUED"
        session.add(RunEvent(run_id=run.id, node_id=None, event_type="JOB_EXECUTION", status=run.run_status, correlation_id=str(run.id), payload_redacted={"workerId": worker_id, "attempt": job.attempt_no, "error": job.last_error_code}))


def _create_report_draft_when_enabled(session, run: AnalysisRun) -> None:
    if run.assessment_profile != _DELIVERY_PROFILE:
        return
    orchestration = session.query(AnalysisRunOrchestrationSnapshot).filter_by(run_id=run.id).one_or_none()
    is_enabled = orchestration is not None and any(
        item.get("capabilityKey") == "report-draft" and item.get("enabled")
        for item in orchestration.nodes_snapshot
    )
    if not is_enabled:
        return
    from app.infrastructure.business_ownership import enqueue_report_draft, report_owner

    if report_owner(session) == "JAVA":
        enqueue_report_draft(session, run_id=run.id)
        session.add(RunEvent(run_id=run.id, node_id="report-draft", event_type="REPORT_DRAFT", status="QUEUED",
            correlation_id=str(run.id), payload_redacted={"automatic": True, "businessOwner": "JAVA"}))
        return
    try:
        report = create_automatic_draft(session, run_id=run.id, correlation_id=str(run.id))
        session.add(RunEvent(
            run_id=run.id,
            node_id="report-draft",
            event_type="REPORT_DRAFT",
            status="SUCCEEDED",
            correlation_id=str(run.id),
            payload_redacted={"reportId": str(report.id), "automatic": True},
        ))
    except DomainError as exc:
        manifest = session.query(AnalysisRunManifest).filter_by(run_id=run.id).one_or_none()
        if manifest is not None:
            manifest.degradation = {**manifest.degradation, "reportDraft": {"code": exc.code}}
        if run.run_status == "SUCCEEDED":
            run.run_status = "PARTIALLY_COMPLETED"
        session.add(RunEvent(
            run_id=run.id,
            node_id="report-draft",
            event_type="REPORT_DRAFT",
            status="FAILED",
            correlation_id=str(run.id),
            payload_redacted={"errorCode": exc.code, "automatic": True},
        ))


def _cancel(session, job: AnalysisJob, run: AnalysisRun, now: datetime, worker_id: str) -> None:
    job.job_status = "CANCELLED"
    job.lease_owner = None
    job.lease_expires_at = None
    run.run_status = "CANCELLED"
    run.finished_at = now
    snapshot = session.get(InputSnapshot, run.snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    if cycle is not None:
        cycle.business_status = "DRAFT"
    session.add(RunEvent(run_id=run.id, node_id=None, event_type="JOB_CANCELLED", status="CANCELLED", correlation_id=str(run.id), payload_redacted={"workerId": worker_id}))


def _derive_cycle_status(session, run: AnalysisRun) -> None:
    if run.assessment_profile != _DELIVERY_PROFILE:
        return
    snapshot = session.get(InputSnapshot, run.snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    if cycle is None:
        return
    results = session.query(VerificationResult).filter_by(analysis_run_id=run.id).all()
    if not results:
        cycle.business_status = "NEEDS_EVIDENCE"
    elif any(item.requires_human_confirmation for item in results):
        cycle.business_status = "NEEDS_CONFIRMATION"
    elif all(item.status in {"NOT_PROVEN", "NOT_ANALYZED"} for item in results):
        cycle.business_status = "NEEDS_EVIDENCE"
    else:
        cycle.business_status = "DRAFT_READY"


def _run_profile_workflow(session, run: AnalysisRun) -> dict:
    if run.assessment_profile == _DELIVERY_PROFILE:
        return run_verification_graph(session, run.id, run.snapshot_id)
    raise DomainError("ASSESSMENT_PROFILE_NOT_ENABLED", f"运行配置 {run.assessment_profile} 尚未开放 Worker workflow")


if __name__ == "__main__":
    main()
