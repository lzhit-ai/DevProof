from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import FormalSnapshotCreateRequest, SnapshotCreateRequest, SnapshotResponse
from app.application.services.snapshot_service import freeze_formal_snapshot, freeze_preparation_snapshot
from app.domain.errors import DomainError

router = APIRouter(prefix="/cycles/{cycle_id}/input-snapshots")


@router.post("", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
def freeze(
    cycle_id: UUID,
    payload: SnapshotCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SnapshotResponse:
    try:
        snapshot = freeze_preparation_snapshot(
            session,
            cycle_id=cycle_id,
            source_revision_ids=payload.source_revision_ids,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return SnapshotResponse(
            id=snapshot.id,
            cycle_id=snapshot.cycle_id,
            snapshot_hash=snapshot.snapshot_hash,
            purpose=snapshot.purpose,
            assessment_profile=snapshot.assessment_profile,
            policy_version=snapshot.policy_version,
            workflow_version=snapshot.workflow_version,
            created_at=snapshot.created_at,
        )
    except DomainError as exc:
        session.rollback()
        http_status = status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})


@router.post("/formal", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
def freeze_formal(cycle_id: UUID, payload: FormalSnapshotCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> SnapshotResponse:
    try:
        snapshot = freeze_formal_snapshot(session, cycle_id=cycle_id, source_revision_ids=payload.source_revision_ids, git_snapshot_id=payload.git_snapshot_id, external_evidence_ids=payload.external_evidence_ids, manual_evidence_ids=payload.manual_evidence_ids, actor_id=user.id, correlation_id=correlation_id(request))
        session.commit()
        return SnapshotResponse(id=snapshot.id, cycle_id=snapshot.cycle_id, snapshot_hash=snapshot.snapshot_hash, purpose=snapshot.purpose, assessment_profile=snapshot.assessment_profile, policy_version=snapshot.policy_version, workflow_version=snapshot.workflow_version, created_at=snapshot.created_at)
    except DomainError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": exc.message})
