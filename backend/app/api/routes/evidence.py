from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.schemas import EvidenceResponse
from app.application.services.citation_resolver import resolve_citation
from app.domain.errors import DomainError

router = APIRouter(prefix="/input-snapshots/{snapshot_id}/evidence")


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    snapshot_id: UUID, evidence_id: UUID, session: SessionDep, user: CurrentUserDep
) -> EvidenceResponse:
    try:
        evidence = resolve_citation(
            session, evidence_id=evidence_id, snapshot_id=snapshot_id, actor_id=user.id
        )
        return EvidenceResponse(
            id=evidence.id,
            snapshot_id=evidence.snapshot_id,
            source_type=evidence.source_type,
            evidence_kind=evidence.evidence_kind,
            excerpt_safe=evidence.excerpt_safe,
            locator=evidence.locator,
            locator_precision=evidence.locator_precision,
        )
    except DomainError as exc:
        status_code = status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})
