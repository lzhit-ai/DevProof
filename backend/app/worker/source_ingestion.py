"""Durable worker lane for source parsing, Office conversion and OCR."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_

from app.application.services.source_service import process_source_ingestion
from app.core.db import SessionLocal
from app.domain.enums import SourceProcessingStatus
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import SourceIngestionJob, SourceRevision
from app.infrastructure.business_ownership import knowledge_source_owner

logger = logging.getLogger(__name__)
_RETRY_SECONDS = (30, 120, 300)


class _Heartbeat:
    def __init__(self, job_id: UUID, worker_id: str, lease_seconds: int) -> None:
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"source-ingestion-{job_id}")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(5, min(15, self.lease_seconds // 3))
        while not self.stop_event.wait(interval):
            now = datetime.now(UTC)
            with SessionLocal.begin() as session:
                if knowledge_source_owner(session) != "PYTHON":
                    return
                job = session.get(SourceIngestionJob, self.job_id)
                if job is None or job.job_status != "RUNNING" or job.lease_owner != self.worker_id:
                    return
                job.heartbeat_at = now
                job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)


def claim_and_complete_one(*, worker_id: str, lease_seconds: int) -> None:
    claimed = _claim_one(worker_id=worker_id, lease_seconds=lease_seconds)
    if claimed is None:
        return
    heartbeat = _Heartbeat(claimed, worker_id, lease_seconds)
    heartbeat.start()
    failure: DomainError | None = None
    try:
        with SessionLocal.begin() as session:
            if knowledge_source_owner(session) != "PYTHON":
                return
            job = session.get(SourceIngestionJob, claimed)
            if job is None or job.lease_owner != worker_id:
                return
            process_source_ingestion(session, job=job, correlation_id=str(job.id))
    except DomainError as exc:
        failure = exc
        logger.warning("source_ingestion_failed job_id=%s code=%s", claimed, exc.code)
    except Exception:
        failure = DomainError("SOURCE_INGESTION_FAILED", "资料解析、OCR 或索引失败")
        logger.exception("source_ingestion_failed job_id=%s", claimed)
    finally:
        heartbeat.stop()
    _complete(job_id=claimed, worker_id=worker_id, failure=failure)


def _claim_one(*, worker_id: str, lease_seconds: int) -> UUID | None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        if knowledge_source_owner(session) != "PYTHON":
            return None
        job = (
            session.query(SourceIngestionJob)
            .filter(SourceIngestionJob.executor_owner == "PYTHON")
            .filter(or_(and_(SourceIngestionJob.job_status == "QUEUED", or_(SourceIngestionJob.available_at.is_(None), SourceIngestionJob.available_at <= now)), and_(SourceIngestionJob.job_status == "RUNNING", SourceIngestionJob.lease_expires_at < now)))
            .order_by(SourceIngestionJob.available_at.nullsfirst(), SourceIngestionJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            return None
        job.job_status = "RUNNING"
        job.attempt_no += 1
        job.lease_owner = worker_id
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.available_at = None
        source = session.get(SourceRevision, job.source_revision_id)
        if source is not None and source.processing_status != SourceProcessingStatus.READY:
            source.processing_status = SourceProcessingStatus.PARSING
        return job.id


def _complete(*, job_id: UUID, worker_id: str, failure: DomainError | None) -> None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        if knowledge_source_owner(session) != "PYTHON":
            return
        job = session.get(SourceIngestionJob, job_id)
        if job is None or job.lease_owner != worker_id:
            return
        source = session.get(SourceRevision, job.source_revision_id)
        job.lease_owner = None
        job.lease_expires_at = None
        if failure is None:
            job.job_status = "SUCCEEDED"
            return
        job.last_error_code = failure.code
        job.last_error_message = failure.message
        if job.attempt_no >= job.max_attempts:
            if source is not None:
                source.processing_status = SourceProcessingStatus.FAILED
                source.failure_code = failure.code
            job.job_status = "FAILED"
            return
        if source is not None:
            # A scheduled retry is not a terminal failure.  Keep the error
            # available to the UI, but do not let a user mistake it for a
            # final, non-retryable ingestion result.
            source.processing_status = SourceProcessingStatus.PARSING
            source.failure_code = failure.code
        job.job_status = "QUEUED"
        job.available_at = now + timedelta(seconds=_RETRY_SECONDS[min(job.attempt_no - 1, len(_RETRY_SECONDS) - 1)])
