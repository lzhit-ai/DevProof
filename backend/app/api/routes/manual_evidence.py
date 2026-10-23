from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import ManualEvidenceCreateRequest, ManualEvidenceResponse
from app.application.services.manual_evidence_service import submit_manual_evidence
from app.domain.errors import DomainError

router = APIRouter(prefix="/cycles/{cycle_id}/manual-evidence")


@router.post("", response_model=ManualEvidenceResponse, status_code=status.HTTP_201_CREATED)
def create(
    cycle_id: UUID,
    payload: ManualEvidenceCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ManualEvidenceResponse:
    try:
        evidence = submit_manual_evidence(
            session,
            cycle_id=cycle_id,
            logical_name=payload.logical_name,
            content=payload.content,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return ManualEvidenceResponse(
            id=evidence.id,
            project_id=evidence.project_id,
            cycle_id=evidence.cycle_id,
            logical_name=evidence.logical_name,
            content_hash=evidence.content_hash,
        )
    except DomainError as exc:
        session.rollback()
        http_status = status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
