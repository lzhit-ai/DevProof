from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    QualityTrendResponse,
    SecurityArtifactExplanationResponse,
    SecurityBaselineConfirmRequest,
    SecurityBaselineCreateRequest,
    SecurityBaselineRecordResponse,
    SecurityBaselineSnapshotResponse,
    SecurityFindingResponse,
    SecurityFindingStatusUpdateRequest,
    SecurityScanArtifactCreateRequest,
    SecurityScanArtifactResponse,
)
from app.application.services.security_baseline_service import (
    confirm_security_baseline,
    create_security_baseline,
    explain_security_scan_artifact,
    import_security_scan_artifact,
    list_security_baseline_records,
    list_security_baselines,
    list_security_findings,
    list_security_scan_artifacts,
    list_quality_trend,
    update_security_finding_status,
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


def _artifact_response(item) -> SecurityScanArtifactResponse:
    artifact = item["artifact"]
    return SecurityScanArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        repository_id=artifact.repository_id,
        target_sha=artifact.target_sha,
        scan_type=artifact.scan_type,
        scanner_name=artifact.scanner_name,
        scanner_version=artifact.scanner_version,
        rule_set_version=artifact.rule_set_version,
        coverage=artifact.coverage,
        content_hash=artifact.content_hash,
        finding_count=item["finding_count"],
        created_at=artifact.created_at,
    )


def _finding_response(finding) -> SecurityFindingResponse:
    return SecurityFindingResponse(
        id=finding.id,
        scan_artifact_id=finding.scan_artifact_id,
        fingerprint=finding.fingerprint,
        severity=finding.severity,
        category=finding.category,
        title=finding.title,
        locator=finding.locator,
        finding_status=finding.finding_status,
        status_reason=finding.status_reason,
        status_updated_at=finding.status_updated_at,
    )


def _baseline_response(baseline) -> SecurityBaselineSnapshotResponse:
    return SecurityBaselineSnapshotResponse(
        id=baseline.id,
        project_id=baseline.project_id,
        repository_id=baseline.repository_id,
        target_sha=baseline.target_sha,
        input_manifest=baseline.input_manifest,
        input_hash=baseline.input_hash,
        snapshot_hash=baseline.snapshot_hash,
        summary=baseline.summary,
        coverage=baseline.coverage,
        created_at=baseline.created_at,
    )


def _record_response(record) -> SecurityBaselineRecordResponse:
    return SecurityBaselineRecordResponse(
        id=record.id,
        project_id=record.project_id,
        baseline_snapshot_id=record.baseline_snapshot_id,
        record_no=record.record_no,
        record_hash=record.record_hash,
        confirmation_reason=record.confirmation_reason,
        confirmed_at=record.confirmed_at,
    )


@router.post("/security-scan-artifacts", response_model=SecurityScanArtifactResponse, status_code=status.HTTP_201_CREATED)
def create_scan_artifact(
    project_id: UUID,
    payload: SecurityScanArtifactCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SecurityScanArtifactResponse:
    try:
        artifact = import_security_scan_artifact(
            session,
            project_id=project_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
            **payload.model_dump(),
        )
        session.commit()
        return _artifact_response({"artifact": artifact, "finding_count": len(payload.findings)})
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/security-scan-artifacts", response_model=list[SecurityScanArtifactResponse])
def get_scan_artifacts(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SecurityScanArtifactResponse]:
    try:
        return [_artifact_response(item) for item in list_security_scan_artifacts(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.get("/security-scan-artifacts/{artifact_id}/findings", response_model=list[SecurityFindingResponse])
def get_findings(project_id: UUID, artifact_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SecurityFindingResponse]:
    try:
        return [_finding_response(item) for item in list_security_findings(session, project_id=project_id, artifact_id=artifact_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.get("/security-scan-artifacts/{artifact_id}/explanation", response_model=SecurityArtifactExplanationResponse)
def get_scan_artifact_explanation(project_id: UUID, artifact_id: UUID, session: SessionDep, user: CurrentUserDep) -> SecurityArtifactExplanationResponse:
    try:
        return SecurityArtifactExplanationResponse(
            **explain_security_scan_artifact(session, project_id=project_id, artifact_id=artifact_id, actor_id=user.id)
        )
    except DomainError as exc:
        raise _failure(exc)


@router.get("/quality-trend", response_model=QualityTrendResponse)
def get_quality_trend(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> QualityTrendResponse:
    try:
        return QualityTrendResponse(**list_quality_trend(session, project_id=project_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@router.put("/security-findings/{finding_id}/status", response_model=SecurityFindingResponse)
def update_finding_status(
    project_id: UUID,
    finding_id: UUID,
    payload: SecurityFindingStatusUpdateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SecurityFindingResponse:
    try:
        finding = update_security_finding_status(
            session,
            project_id=project_id,
            finding_id=finding_id,
            finding_status=payload.finding_status,
            reason=payload.reason,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _finding_response(finding)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.post("/security-baselines", response_model=SecurityBaselineSnapshotResponse, status_code=status.HTTP_201_CREATED)
def create_baseline(
    project_id: UUID,
    payload: SecurityBaselineCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SecurityBaselineSnapshotResponse:
    try:
        baseline = create_security_baseline(
            session,
            project_id=project_id,
            repository_id=payload.repository_id,
            target_sha=payload.target_sha,
            scan_artifact_ids=payload.scan_artifact_ids,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _baseline_response(baseline)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/security-baselines", response_model=list[SecurityBaselineSnapshotResponse])
def get_baselines(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SecurityBaselineSnapshotResponse]:
    try:
        return [_baseline_response(item) for item in list_security_baselines(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/security-baselines/{baseline_id}/confirm", response_model=SecurityBaselineRecordResponse, status_code=status.HTTP_201_CREATED)
def confirm_baseline(
    project_id: UUID,
    baseline_id: UUID,
    payload: SecurityBaselineConfirmRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> SecurityBaselineRecordResponse:
    try:
        record = confirm_security_baseline(
            session,
            project_id=project_id,
            baseline_id=baseline_id,
            reason=payload.reason,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _record_response(record)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/security-baseline-records", response_model=list[SecurityBaselineRecordResponse])
def get_baseline_records(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SecurityBaselineRecordResponse]:
    try:
        return [_record_response(item) for item in list_security_baseline_records(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)
