from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import AnalysisResultResponse, AnalysisRunResponse, CodeReviewResponse, HumanVerificationDecisionRequest
from app.application.services.analysis_service import get_analysis_results, get_analysis_run, get_code_review, get_latest_task_analysis_run, record_human_verification_decision, request_cancel, start_analysis_run
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import RunEvent

snapshot_router = APIRouter(prefix="/input-snapshots/{snapshot_id}/analysis-runs")
run_router = APIRouter(prefix="/analysis-runs")
task_router = APIRouter(prefix="/verification-tasks")


@snapshot_router.post("", response_model=AnalysisRunResponse, status_code=status.HTTP_202_ACCEPTED)
def start(snapshot_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, key: str = Depends(idempotency_key)) -> AnalysisRunResponse:
    try:
        run = start_analysis_run(session, snapshot_id=snapshot_id, actor_id=user.id, idempotency_key=key, correlation_id=correlation_id(request))
        session.commit()
        return AnalysisRunResponse(id=run.id, snapshot_id=run.snapshot_id, assessment_profile=run.assessment_profile, run_status=run.run_status, poll_url=f"/api/v1/analysis-runs/{run.id}")
    except DomainError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})


@run_router.get("/{run_id}", response_model=AnalysisRunResponse)
def get_run(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> AnalysisRunResponse:
    try:
        run = get_analysis_run(session, run_id=run_id, actor_id=user.id)
        return AnalysisRunResponse(id=run.id, snapshot_id=run.snapshot_id, assessment_profile=run.assessment_profile, run_status=run.run_status, poll_url=f"/api/v1/analysis-runs/{run.id}")
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if exc.code == "RESOURCE_NOT_FOUND" else status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})


@task_router.get("/{task_id}/latest-analysis-run", response_model=AnalysisRunResponse)
def get_latest_task_run(task_id: UUID, session: SessionDep, user: CurrentUserDep) -> AnalysisRunResponse:
    try:
        run = get_latest_task_analysis_run(session, task_id=task_id, actor_id=user.id)
        return AnalysisRunResponse(
            id=run.id,
            snapshot_id=run.snapshot_id,
            assessment_profile=run.assessment_profile,
            run_status=run.run_status,
            poll_url=f"/api/v1/analysis-runs/{run.id}",
        )
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if exc.code == "RESOURCE_NOT_FOUND" else status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )


@run_router.post("/{run_id}/cancel", response_model=AnalysisRunResponse)
def cancel(run_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> AnalysisRunResponse:
    try:
        run = request_cancel(session, run_id=run_id, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return AnalysisRunResponse(id=run.id, snapshot_id=run.snapshot_id, assessment_profile=run.assessment_profile, run_status=run.run_status, poll_url=f"/api/v1/analysis-runs/{run.id}")
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message})


@run_router.get("/{run_id}/events")
def events(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> dict:
    try:
        get_analysis_run(session, run_id=run_id, actor_id=user.id)
        items = session.query(RunEvent).filter_by(run_id=run_id).order_by(RunEvent.created_at).all()
        return {
            "items": [
                {
                    "id": str(item.id),
                    "nodeId": item.node_id,
                    "eventType": item.event_type,
                    "status": item.status,
                    "details": item.payload_redacted,
                    "createdAt": item.created_at.isoformat(),
                }
                for item in items
            ]
        }
    except DomainError as exc:
        raise HTTPException(status_code=404 if exc.code == "RESOURCE_NOT_FOUND" else 403, detail={"code": exc.code, "message": exc.message})


@run_router.get("/{run_id}/results", response_model=list[AnalysisResultResponse])
def results(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[AnalysisResultResponse]:
    try:
        return [AnalysisResultResponse(**item) for item in get_analysis_results(session, run_id=run_id, actor_id=user.id)]
    except DomainError as exc:
        raise HTTPException(status_code=404 if exc.code == "RESOURCE_NOT_FOUND" else 403, detail={"code": exc.code, "message": exc.message})


@run_router.post("/{run_id}/results/{result_id}/human-decisions")
def decide_result(
    run_id: UUID,
    result_id: UUID,
    payload: HumanVerificationDecisionRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> dict:
    try:
        decision = record_human_verification_decision(
            session,
            run_id=run_id,
            result_id=result_id,
            decision=payload.decision,
            note=payload.note,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return decision
    except DomainError as exc:
        session.rollback()
        raise HTTPException(
            status_code=404 if exc.code == "RESOURCE_NOT_FOUND" else 409,
            detail={"code": exc.code, "message": exc.message},
        )


@run_router.get("/{run_id}/code-review", response_model=CodeReviewResponse)
def code_review(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> CodeReviewResponse:
    try:
        return CodeReviewResponse(**get_code_review(session, run_id=run_id, actor_id=user.id))
    except DomainError as exc:
        raise HTTPException(status_code=404 if exc.code == "RESOURCE_NOT_FOUND" else 403, detail={"code": exc.code, "message": exc.message})
