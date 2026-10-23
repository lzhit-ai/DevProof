from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    ProjectHealthSnapshotCreateRequest,
    ProjectHealthSnapshotResponse,
    ProjectSummaryDraftCreateRequest,
    ProjectSummaryDraftResponse,
    ProjectSummaryRecordResponse,
)
from app.application.services.project_status_service import (
    create_project_health_snapshot,
    create_project_summary_draft,
    get_project_health_snapshot,
    list_project_health_snapshots,
    list_project_summary_drafts,
    list_project_summary_records,
    publish_project_summary_draft,
)
from app.domain.errors import DomainError


router = APIRouter(prefix="/projects/{project_id}")


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "INPUT_INVALID":
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


def _health_response(snapshot) -> ProjectHealthSnapshotResponse:
    return ProjectHealthSnapshotResponse(
        id=snapshot.id,
        project_id=snapshot.project_id,
        scope=snapshot.scope,
        input_manifest=snapshot.input_manifest,
        input_hash=snapshot.input_hash,
        snapshot_hash=snapshot.snapshot_hash,
        summary=snapshot.summary,
        coverage=snapshot.coverage,
        as_of=snapshot.as_of,
        created_at=snapshot.created_at,
    )


def _draft_response(draft) -> ProjectSummaryDraftResponse:
    return ProjectSummaryDraftResponse(
        id=draft.id,
        project_id=draft.project_id,
        health_snapshot_id=draft.health_snapshot_id,
        period_type=draft.period_type,
        title=draft.title,
        content=draft.content,
        content_hash=draft.content_hash,
        draft_status=draft.draft_status,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _record_response(record) -> ProjectSummaryRecordResponse:
    return ProjectSummaryRecordResponse(
        id=record.id,
        project_id=record.project_id,
        health_snapshot_id=record.health_snapshot_id,
        summary_draft_id=record.summary_draft_id,
        record_no=record.record_no,
        record_hash=record.record_hash,
        confirmation_type=record.confirmation_type,
        published_at=record.published_at,
    )


@router.post("/health-snapshots", response_model=ProjectHealthSnapshotResponse, status_code=status.HTTP_201_CREATED)
def create_health_snapshot(
    project_id: UUID,
    payload: ProjectHealthSnapshotCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ProjectHealthSnapshotResponse:
    try:
        snapshot = create_project_health_snapshot(
            session,
            project_id=project_id,
            milestone_key=payload.milestone_key,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _health_response(snapshot)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/health-snapshots", response_model=list[ProjectHealthSnapshotResponse])
def get_health_snapshots(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[ProjectHealthSnapshotResponse]:
    try:
        return [_health_response(snapshot) for snapshot in list_project_health_snapshots(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.get("/health-snapshots/{health_snapshot_id}", response_model=ProjectHealthSnapshotResponse)
def get_health_snapshot(project_id: UUID, health_snapshot_id: UUID, session: SessionDep, user: CurrentUserDep) -> ProjectHealthSnapshotResponse:
    try:
        return _health_response(get_project_health_snapshot(session, project_id=project_id, health_snapshot_id=health_snapshot_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@router.post("/project-summary-drafts", response_model=ProjectSummaryDraftResponse, status_code=status.HTTP_201_CREATED)
def create_summary_draft(
    project_id: UUID,
    payload: ProjectSummaryDraftCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ProjectSummaryDraftResponse:
    try:
        draft = create_project_summary_draft(
            session,
            project_id=project_id,
            health_snapshot_id=payload.health_snapshot_id,
            period_type=payload.period_type,
            title=payload.title,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _draft_response(draft)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/project-summary-drafts", response_model=list[ProjectSummaryDraftResponse])
def get_summary_drafts(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[ProjectSummaryDraftResponse]:
    try:
        return [_draft_response(draft) for draft in list_project_summary_drafts(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/project-summary-drafts/{draft_id}/publish", response_model=ProjectSummaryRecordResponse, status_code=status.HTTP_201_CREATED)
def publish_summary_draft(
    project_id: UUID,
    draft_id: UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ProjectSummaryRecordResponse:
    try:
        record = publish_project_summary_draft(
            session,
            project_id=project_id,
            draft_id=draft_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _record_response(record)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/project-summary-records", response_model=list[ProjectSummaryRecordResponse])
def get_summary_records(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[ProjectSummaryRecordResponse]:
    try:
        return [_record_response(record) for record in list_project_summary_records(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)
