from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import ExternalEvidenceCreateRequest, ExternalEvidenceResponse
from app.application.services.external_evidence_service import import_external_evidence
from app.domain.errors import DomainError


router = APIRouter(prefix="/cycles/{cycle_id}/external-evidence")


@router.post("", response_model=ExternalEvidenceResponse, status_code=status.HTTP_201_CREATED)
def create(cycle_id: UUID, payload: ExternalEvidenceCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ExternalEvidenceResponse:
    try:
        evidence = import_external_evidence(session, cycle_id=cycle_id, evidence_type=payload.evidence_type, logical_name=payload.logical_name, commit_sha=payload.commit_sha, content=payload.content, exit_code=payload.exit_code, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return ExternalEvidenceResponse(id=evidence.id, project_id=evidence.project_id, cycle_id=evidence.cycle_id, evidence_type=evidence.evidence_type, logical_name=evidence.logical_name, commit_sha=evidence.commit_sha, content_hash=evidence.content_hash, exit_code=evidence.exit_code)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=409 if exc.code in {"STATE_CONFLICT", "BUSINESS_OWNER_MISMATCH"} else 403 if exc.code == "AUTH_FORBIDDEN" else 404, detail={"code": exc.code, "message": exc.message})
