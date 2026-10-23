from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.schemas import SnapshotSearchRequest, SnapshotSearchResponse
from app.application.services.retrieval_service import search_snapshot
from app.domain.errors import DomainError


router = APIRouter(prefix="/input-snapshots/{snapshot_id}")


@router.post("/search", response_model=SnapshotSearchResponse)
def search(snapshot_id: UUID, payload: SnapshotSearchRequest, session: SessionDep, user: CurrentUserDep) -> SnapshotSearchResponse:
    try:
        return SnapshotSearchResponse(items=search_snapshot(
            session,
            snapshot_id=snapshot_id,
            query=payload.query,
            limit=payload.limit,
            actor_id=user.id,
            preferred_source_roles=payload.preferred_source_roles,
        ))
    except DomainError as exc:
        raise HTTPException(status_code=409 if exc.code == "BUSINESS_OWNER_MISMATCH" else 404 if exc.code == "RESOURCE_NOT_FOUND" else 403, detail={"code": exc.code, "message": exc.message})
