from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import ApprovalRequest, ProjectReportResponse, PublishedRecordResponse, ReportContentResponse, ReportDraftUpdateRequest, ReportResponse
from app.application.services.report_service import approve, create_draft, get_project_report, get_published_record, get_report_content, list_project_reports, list_published_records, publish, reject, request_changes, submit_for_review, update_draft
from app.domain.errors import DomainError

cycle_router = APIRouter(prefix="/cycles/{cycle_id}/reports")
report_router = APIRouter(prefix="/report-versions")
project_router = APIRouter(prefix="/projects/{project_id}")


def to_response(report) -> ReportResponse:
    return ReportResponse(id=report.id, cycle_id=report.cycle_id, sequence_no=report.sequence_no, status=report.status, record_type=report.record_type, content_hash=report.content_hash, editorial_note=report.editorial_note, version=report.version)


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


@project_router.get("/report-versions", response_model=list[ProjectReportResponse])
def get_project_reports(project_id: UUID, session: SessionDep, user: CurrentUserDep, status_filter: str | None = None) -> list[ProjectReportResponse]:
    try:
        return [ProjectReportResponse(**item) for item in list_project_reports(session, project_id=project_id, actor_id=user.id, report_status=status_filter)]
    except DomainError as exc:
        raise _failure(exc)


@project_router.get("/report-versions/{report_id}", response_model=ProjectReportResponse)
def get_report(project_id: UUID, report_id: UUID, session: SessionDep, user: CurrentUserDep) -> ProjectReportResponse:
    try:
        return ProjectReportResponse(**get_project_report(session, project_id=project_id, report_id=report_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@project_router.get("/report-versions/{report_id}/content", response_model=ReportContentResponse)
def get_report_content_view(project_id: UUID, report_id: UUID, session: SessionDep, user: CurrentUserDep) -> ReportContentResponse:
    try:
        return ReportContentResponse(**get_report_content(session, project_id=project_id, report_id=report_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@project_router.get("/published-records", response_model=list[PublishedRecordResponse])
def get_published_records(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[PublishedRecordResponse]:
    try:
        return [PublishedRecordResponse(**item) for item in list_published_records(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@project_router.get("/published-records/{record_id}", response_model=PublishedRecordResponse)
def get_record(project_id: UUID, record_id: UUID, session: SessionDep, user: CurrentUserDep) -> PublishedRecordResponse:
    try:
        return PublishedRecordResponse(**get_published_record(session, project_id=project_id, record_id=record_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@cycle_router.post("/from-run/{run_id}", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def draft(cycle_id: UUID, run_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = create_draft(session, cycle_id=cycle_id, run_id=run_id, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=403 if exc.code == "AUTH_FORBIDDEN" else 409, detail={"code": exc.code, "message": exc.message})


@report_router.post("/{report_id}/submit", response_model=ReportResponse)
def submit(report_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = submit_for_review(session, report_id=report_id, actor_id=user.id, correlation_id=correlation_id(request)); session.commit(); return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


@report_router.put("/{report_id}", response_model=ReportResponse)
def update(report_id: UUID, payload: ReportDraftUpdateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = update_draft(session, report_id=report_id, editorial_note=payload.editorial_note, item_dispositions=payload.item_dispositions, expected_version=payload.expected_version, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


@report_router.post("/{report_id}/approve", response_model=ReportResponse)
def approve_report(report_id: UUID, payload: ApprovalRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = approve(session, report_id=report_id, actor_id=user.id, reason=payload.reason, correlation_id=correlation_id(request)); session.commit(); return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=403 if exc.code == "AUTH_FORBIDDEN" else 409, detail={"code": exc.code, "message": exc.message})


@report_router.post("/{report_id}/request-changes", response_model=ReportResponse)
def changes(report_id: UUID, payload: ApprovalRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = request_changes(session, report_id=report_id, actor_id=user.id, reason=payload.reason, correlation_id=correlation_id(request)); session.commit(); return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=403 if exc.code == "AUTH_FORBIDDEN" else 409, detail={"code": exc.code, "message": exc.message})


@report_router.post("/{report_id}/reject", response_model=ReportResponse)
def reject_report(report_id: UUID, payload: ApprovalRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> ReportResponse:
    try:
        report = reject(session, report_id=report_id, actor_id=user.id, reason=payload.reason, correlation_id=correlation_id(request)); session.commit(); return to_response(report)
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=403 if exc.code == "AUTH_FORBIDDEN" else 409, detail={"code": exc.code, "message": exc.message})


@report_router.post("/{report_id}/publish", status_code=status.HTTP_201_CREATED)
def publish_report(report_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        record = publish(session, report_id=report_id, actor_id=user.id, correlation_id=correlation_id(request)); session.commit(); return {"id": str(record.id), "recordType": record.record_type, "recordNo": record.record_no, "recordHash": record.record_hash}
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=403 if exc.code == "AUTH_FORBIDDEN" else 409, detail={"code": exc.code, "message": exc.message})
