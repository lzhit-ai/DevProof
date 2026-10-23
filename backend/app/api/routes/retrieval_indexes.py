from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import RetrievalIndexBuildRunResponse, RetrievalIndexRebuildResponse, RetrievalIndexResponse
from app.application.services.retrieval_index_service import (
    finish_retrieval_index_build_run,
    list_retrieval_index_build_runs,
    list_project_retrieval_indexes,
    rebuild_project_retrieval_index,
    start_retrieval_index_build_run,
)
from app.domain.errors import DomainError


router = APIRouter(prefix="/projects/{project_id}/retrieval-indexes")


@router.get("", response_model=list[RetrievalIndexResponse])
def list_indexes(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[RetrievalIndexResponse]:
    try:
        return [
            RetrievalIndexResponse(**item)
            for item in list_project_retrieval_indexes(session, project_id=project_id, actor_id=user.id)
        ]
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT if exc.code == "BUSINESS_OWNER_MISMATCH" else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        )


@router.post("/rebuild", response_model=RetrievalIndexRebuildResponse)
def rebuild(
    project_id: UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> RetrievalIndexRebuildResponse:
    build_run = None
    try:
        build_run = start_retrieval_index_build_run(session, project_id=project_id, actor_id=user.id)
        try:
            with session.begin_nested():
                result = rebuild_project_retrieval_index(
                    session,
                    project_id=project_id,
                    actor_id=user.id,
                    correlation_id=correlation_id(request),
                )
        except DomainError as exc:
            finish_retrieval_index_build_run(build_run, error=exc)
            session.commit()
            raise
        finish_retrieval_index_build_run(build_run, result=result)
        session.commit()
        return RetrievalIndexRebuildResponse(**{**result, "build_run_id": build_run.id})
    except DomainError as exc:
        if build_run is None:
            session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT if exc.code == "BUSINESS_OWNER_MISMATCH" else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        )


@router.get("/rebuild-runs", response_model=list[RetrievalIndexBuildRunResponse])
def list_build_runs(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[RetrievalIndexBuildRunResponse]:
    try:
        return [
            RetrievalIndexBuildRunResponse(**item)
            for item in list_retrieval_index_build_runs(session, project_id=project_id, actor_id=user.id)
        ]
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT if exc.code == "BUSINESS_OWNER_MISMATCH" else status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        )
