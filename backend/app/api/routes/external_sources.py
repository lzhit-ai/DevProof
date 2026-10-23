from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    DeliveryItemResponse,
    ExternalConnectionCreateRequest,
    ExternalConnectionResponse,
    SourceSyncRunResponse,
)
from app.application.services.external_source_service import (
    create_connection,
    list_connections,
    list_delivery_items,
    list_sync_runs,
    sync_connection,
)
from app.domain.errors import DomainError


router = APIRouter(prefix="/projects/{project_id}")


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {"INPUT_INVALID", "SOURCE_CONNECTION_INVALID"}:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


def _connection_response(connection) -> ExternalConnectionResponse:
    return ExternalConnectionResponse(
        id=connection.id,
        project_id=connection.project_id,
        provider=connection.provider,
        name=connection.name,
        repository_slug=connection.repository_slug,
        secret_ref_configured=connection.secret_ref is not None,
        is_active=connection.is_active,
        created_at=connection.created_at,
    )


def _sync_response(sync) -> SourceSyncRunResponse:
    return SourceSyncRunResponse(
        id=sync.id,
        connection_id=sync.connection_id,
        status=sync.status,
        started_at=sync.started_at,
        finished_at=sync.finished_at,
        fetched_count=sync.fetched_count,
        changed_count=sync.changed_count,
        page_count=sync.page_count,
        continuation_cursor=sync.continuation_cursor,
        error_code=sync.error_code,
        error_message=sync.error_message,
    )


@router.post("/external-connections", response_model=ExternalConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_external_connection(
    project_id: UUID,
    payload: ExternalConnectionCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ExternalConnectionResponse:
    try:
        connection = create_connection(
            session,
            project_id=project_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
            **payload.model_dump(),
        )
        session.commit()
        return _connection_response(connection)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/external-connections", response_model=list[ExternalConnectionResponse])
def get_external_connections(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[ExternalConnectionResponse]:
    try:
        return [_connection_response(item) for item in list_connections(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/external-connections/{connection_id}/sync", response_model=SourceSyncRunResponse)
def sync_external_connection(
    project_id: UUID,
    connection_id: UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SourceSyncRunResponse:
    try:
        sync = sync_connection(
            session,
            project_id=project_id,
            connection_id=connection_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _sync_response(sync)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/source-sync-runs", response_model=list[SourceSyncRunResponse])
def get_source_sync_runs(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SourceSyncRunResponse]:
    try:
        return [_sync_response(item) for item in list_sync_runs(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.get("/delivery-items", response_model=list[DeliveryItemResponse])
def get_delivery_items(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[DeliveryItemResponse]:
    try:
        return [DeliveryItemResponse(**item) for item in list_delivery_items(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)
