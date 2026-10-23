from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    AgentToolExecutionImportRequest,
    AgentToolExecutionImportResponse,
    AgentToolExecutionResponse,
)
from app.application.services.agent_tool_execution_service import (
    import_tool_execution_as_manual_evidence,
    list_tool_executions,
)
from app.domain.errors import DomainError


router = APIRouter(prefix="/analysis-runs/{run_id}/tool-executions")


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "INPUT_STALE":
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


@router.get("", response_model=list[AgentToolExecutionResponse])
def get_tool_executions(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[AgentToolExecutionResponse]:
    try:
        return [AgentToolExecutionResponse(**item) for item in list_tool_executions(session, run_id=run_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/{execution_id}/import-manual-evidence", response_model=AgentToolExecutionImportResponse, status_code=status.HTTP_201_CREATED)
def import_manual_evidence(
    run_id: UUID,
    execution_id: UUID,
    payload: AgentToolExecutionImportRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> AgentToolExecutionImportResponse:
    try:
        evidence = import_tool_execution_as_manual_evidence(
            session,
            run_id=run_id,
            execution_id=execution_id,
            logical_name=payload.logical_name,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return AgentToolExecutionImportResponse(
            manual_evidence_id=evidence.id,
            cycle_id=evidence.cycle_id,
            content_hash=evidence.content_hash,
            origin_type=evidence.origin_type,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)
