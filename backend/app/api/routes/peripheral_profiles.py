from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import PeripheralProfileRunCreateRequest, PeripheralProfileRunResponse
from app.application.services.peripheral_profile_service import create_peripheral_profile_run, list_peripheral_profile_runs
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


def _response(run) -> PeripheralProfileRunResponse:
    return PeripheralProfileRunResponse(
        id=run.id,
        project_id=run.project_id,
        assessment_profile=run.assessment_profile,
        run_status=run.run_status,
        input_manifest=run.input_manifest,
        input_hash=run.input_hash,
        output=run.output,
        coverage=run.coverage,
        limitations=run.limitations,
        created_at=run.created_at,
    )


@router.post("/peripheral-profile-runs", response_model=PeripheralProfileRunResponse, status_code=status.HTTP_201_CREATED)
def create_run(
    project_id: UUID,
    payload: PeripheralProfileRunCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> PeripheralProfileRunResponse:
    try:
        run = create_peripheral_profile_run(
            session,
            project_id=project_id,
            assessment_profile=payload.assessment_profile,
            health_snapshot_id=payload.health_snapshot_id,
            security_baseline_id=payload.security_baseline_id,
            scan_artifact_ids=payload.scan_artifact_ids,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return _response(run)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/peripheral-profile-runs", response_model=list[PeripheralProfileRunResponse])
def get_runs(
    project_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
    assessment_profile: str | None = None,
) -> list[PeripheralProfileRunResponse]:
    try:
        return [
            _response(run)
            for run in list_peripheral_profile_runs(
                session,
                project_id=project_id,
                actor_id=user.id,
                assessment_profile=assessment_profile,
            )
        ]
    except DomainError as exc:
        raise _failure(exc)
