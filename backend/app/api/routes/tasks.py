from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import DeliveryClaimConfirmRequest, DeliveryClaimProposalRequest, DeliveryClaimResponse, TaskCreateRequest, TaskDeliveryItemBindingRequest, TaskResponse, VerificationTaskListResponse
from app.application.services.delivery_claim_service import confirm_delivery_claims, list_delivery_claims, propose_delivery_claims
from app.application.services.delivery_association_service import bind_task_delivery_item
from app.application.services.task_service import create_next_cycle, create_task, list_tasks
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import VerificationCycle

router = APIRouter(prefix="/projects/{project_id}/verification-tasks")


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


@router.get("", response_model=list[VerificationTaskListResponse])
def get_tasks(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[VerificationTaskListResponse]:
    try:
        return [VerificationTaskListResponse(**item) for item in list_tasks(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.get("/{task_id}/delivery-claims", response_model=list[DeliveryClaimResponse])
def get_delivery_claims(project_id: UUID, task_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[DeliveryClaimResponse]:
    try:
        return [DeliveryClaimResponse(**item) for item in list_delivery_claims(session, project_id=project_id, task_id=task_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/{task_id}/delivery-claims/propose", response_model=list[DeliveryClaimResponse])
def propose_claims(project_id: UUID, task_id: UUID, payload: DeliveryClaimProposalRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> list[DeliveryClaimResponse]:
    try:
        claims = propose_delivery_claims(session, project_id=project_id, task_id=task_id, source_revision_ids=payload.source_revision_ids, actor_id=user.id, correlation_id=correlation_id(request))
        session.commit()
        return [DeliveryClaimResponse(**item) for item in claims]
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.put("/{task_id}/delivery-claims", response_model=list[DeliveryClaimResponse])
def confirm_claims(project_id: UUID, task_id: UUID, payload: DeliveryClaimConfirmRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> list[DeliveryClaimResponse]:
    try:
        claims = confirm_delivery_claims(session, project_id=project_id, task_id=task_id, claims=[item.model_dump() for item in payload.claims], actor_id=user.id, correlation_id=correlation_id(request))
        session.commit()
        return [DeliveryClaimResponse(**item) for item in claims]
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create(
    project_id: UUID,
    payload: TaskCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> TaskResponse:
    try:
        task, cycle = create_task(
            session,
            project_id=project_id,
            title=payload.title,
            requirement_key=payload.requirement_key,
            actor_id=user.id,
            correlation_id=correlation_id(request),
            delivery_item_id=payload.delivery_item_id,
            orchestration_template_id=payload.orchestration_template_id,
        )
        session.commit()
        return TaskResponse(
            id=task.id,
            project_id=task.project_id,
            delivery_item_id=task.delivery_item_id,
            title=task.title,
            requirement_key=task.requirement_key,
            cycle_id=cycle.id,
            cycle_status=cycle.business_status,
            version=task.version,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.post("/{task_id}/cycles", status_code=status.HTTP_201_CREATED)
def create_cycle(project_id: UUID, task_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        cycle = create_next_cycle(session, task_id=task_id, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return {"id": str(cycle.id), "taskId": str(cycle.task_id), "sequenceNo": cycle.sequence_no, "status": cycle.business_status}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.put("/{task_id}/delivery-item", response_model=TaskResponse)
def bind_delivery_item(
    project_id: UUID,
    task_id: UUID,
    payload: TaskDeliveryItemBindingRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> TaskResponse:
    try:
        task = bind_task_delivery_item(
            session,
            project_id=project_id,
            task_id=task_id,
            delivery_item_id=payload.delivery_item_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        cycle = session.query(VerificationCycle).filter_by(task_id=task.id).order_by(VerificationCycle.sequence_no.desc()).first()
        if cycle is None:
            raise DomainError("RESOURCE_NOT_FOUND", "核验任务没有轮次")
        session.commit()
        return TaskResponse(
            id=task.id,
            project_id=task.project_id,
            delivery_item_id=task.delivery_item_id,
            title=task.title,
            requirement_key=task.requirement_key,
            cycle_id=cycle.id,
            cycle_status=cycle.business_status,
            version=task.version,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)
