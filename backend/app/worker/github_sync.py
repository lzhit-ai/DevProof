"""Durable worker lane for asynchronous GitHub source synchronization."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_

from app.application.services.external_source_service import execute_source_sync
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.enums import SourceSyncStatus
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import SourceSyncRun
from app.infrastructure.business_ownership import github_source_owner

logger = logging.getLogger(__name__)
_RETRY_SECONDS = (30, 120, 300)


class _Heartbeat:
    def __init__(self, run_id: UUID, worker_id: str, lease_seconds: int) -> None:
        self.run_id = run_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"github-sync-{run_id}")

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
                if github_source_owner(session) != "PYTHON":
                    return
                run = session.get(SourceSyncRun, self.run_id)
                if run is None or run.status != SourceSyncStatus.RUNNING.value or run.lease_owner != self.worker_id:
                    return
                run.heartbeat_at = now
                run.lease_expires_at = now + timedelta(seconds=self.lease_seconds)


def claim_and_complete_one_sync(*, worker_id: str, lease_seconds: int) -> None:
    claimed = _claim_one(worker_id=worker_id, lease_seconds=lease_seconds)
    if claimed is None:
        return
    heartbeat = _Heartbeat(claimed, worker_id, lease_seconds)
    heartbeat.start()
    failure: DomainError | None = None
    try:
        with SessionLocal.begin() as session:
            sync = session.get(SourceSyncRun, claimed)
            if sync is None or sync.lease_owner != worker_id:
                return
            actor_id = sync.requested_by or _FALLBACK_ACTOR
            execute_source_sync(session, sync=sync, actor_id=actor_id, correlation_id=str(sync.id))
    except DomainError as exc:
        failure = exc
        logger.warning("github_sync_failed run_id=%s code=%s", claimed, exc.code)
    except Exception:
        failure = DomainError("SOURCE_SYNC_FAILED", "GitHub 同步失败")
        logger.exception("github_sync_failed run_id=%s", claimed)
    finally:
        heartbeat.stop()
    _complete(run_id=claimed, worker_id=worker_id, failure=failure)


# A fixed namespace UUID used only when a sync run has no recorded requester.
_FALLBACK_ACTOR = UUID("00000000-0000-0000-0000-000000000001")


def _claim_one(*, worker_id: str, lease_seconds: int) -> UUID | None:
    now = datetime.now(UTC)
    with SessionLocal.begin() as session:
        if github_source_owner(session) != "PYTHON":
            return None
        run = (
            session.query(SourceSyncRun)
            .filter(
                SourceSyncRun.executor_owner == "PYTHON",
                and_(
                    SourceSyncRun.status == SourceSyncStatus.RUNNING.value,
                    or_(
                        SourceSyncRun.lease_owner.is_(None),
                        SourceSyncRun.lease_expires_at.is_(None),
                        SourceSyncRun.lease_expires_at < now,
                    ),
                )
            )
            .order_by(SourceSyncRun.started_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if run is None:
            return None
        run.lease_owner = worker_id
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        run.heartbeat_at = now
        run.available_at = None
        run.attempt_no += 1
        return run.id


def _complete(*, run_id: UUID, worker_id: str, failure: DomainError | None) -> None:
    now = datetime.now(UTC)
    settings = get_settings()
    with SessionLocal.begin() as session:
        if github_source_owner(session) != "PYTHON":
            return
        run = session.get(SourceSyncRun, run_id)
        if run is None or run.lease_owner != worker_id:
            return
        run.lease_owner = None
        run.lease_expires_at = None
        if failure is None:
            # execute_source_sync already set status/finished_at; just release lease.
            return
        run.last_error_code = failure.code
        run.last_error_message = failure.message
        if run.attempt_no >= run.max_attempts:
            run.status = SourceSyncStatus.FAILED.value
            run.error_code = failure.code
            run.error_message = failure.message
            run.finished_at = now
            return
        run.available_at = now + timedelta(seconds=_RETRY_SECONDS[min(run.attempt_no - 1, len(_RETRY_SECONDS) - 1)])
