from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    AgentCapabilityCreateRequest,
    AgentCapabilityVersionCreateRequest,
    AgentToolCreateRequest,
    OrchestrationTemplateCreateRequest,
    TaskOrchestrationBindingRequest,
)
from app.application.services.orchestration_service import (
    bind_task_template,
    create_capability_version,
    create_custom_capability,
    create_custom_tool,
    create_template,
    deactivate_custom_capability,
    ensure_default_orchestration,
    get_capability_latest_version,
    get_run_orchestration,
    list_orchestration,
    list_task_orchestration_bindings,
)
from app.application.services.common import require_project_role
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError


project_router = APIRouter(prefix="/projects/{project_id}/agent-orchestration")
task_router = APIRouter(prefix="/verification-tasks/{task_id}/agent-orchestration")
run_router = APIRouter(prefix="/analysis-runs")


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


@project_router.get("")
def list_project_orchestration(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> dict:
    try:
        require_project_role(session, project_id, user.id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
        ensure_default_orchestration(session, project_id=project_id, actor_id=user.id)
        session.commit()
        return list_orchestration(session, project_id=project_id, actor_id=user.id)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@project_router.post("/tools", status_code=status.HTTP_201_CREATED)
def create_tool(project_id: UUID, payload: AgentToolCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        tool = create_custom_tool(session, project_id=project_id, actor_id=user.id, correlation_id=correlation_id(request), **payload.model_dump())
        session.commit()
        return {"id": str(tool.id), "key": tool.key, "name": tool.name, "toolType": tool.tool_type}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@project_router.post("/capabilities", status_code=status.HTTP_201_CREATED)
def create_capability(project_id: UUID, payload: AgentCapabilityCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        capability = create_custom_capability(session, project_id=project_id, actor_id=user.id, correlation_id=correlation_id(request), **payload.model_dump())
        session.commit()
        return {"id": str(capability.id), "key": capability.key, "name": capability.name, "coreScope": capability.core_scope}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@project_router.post("/capabilities/{capability_id}/versions", status_code=status.HTTP_201_CREATED)
def version_capability(project_id: UUID, capability_id: UUID, payload: AgentCapabilityVersionCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        version = create_capability_version(session, project_id=project_id, capability_id=capability_id, actor_id=user.id, correlation_id=correlation_id(request), **payload.model_dump())
        session.commit()
        return {"id": str(version.id), "version": version.version_no, "contentHash": version.content_hash}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@project_router.get("/capabilities/{capability_id}/latest-version")
def get_latest_capability_version(project_id: UUID, capability_id: UUID, session: SessionDep, user: CurrentUserDep) -> dict:
    try:
        return get_capability_latest_version(session, project_id=project_id, capability_id=capability_id, actor_id=user.id)
    except DomainError as exc:
        raise _failure(exc)


@project_router.post("/capabilities/{capability_id}/deactivate")
def deactivate_capability(project_id: UUID, capability_id: UUID, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        capability = deactivate_custom_capability(
            session,
            project_id=project_id,
            capability_id=capability_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return {"id": str(capability.id), "isActive": capability.is_active}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@project_router.get("/task-bindings")
def list_project_task_bindings(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[dict]:
    try:
        return list_task_orchestration_bindings(session, project_id=project_id, actor_id=user.id)
    except DomainError as exc:
        raise _failure(exc)


@project_router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_orchestration_template(project_id: UUID, payload: OrchestrationTemplateCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        template = create_template(session, project_id=project_id, actor_id=user.id, correlation_id=correlation_id(request), name=payload.name, description=payload.description, assessment_profile=payload.assessment_profile, nodes=[item.model_dump() for item in payload.nodes])
        session.commit()
        return {"id": str(template.id), "name": template.name, "assessmentProfile": template.assessment_profile, "version": template.version}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@task_router.put("")
def bind_orchestration_template(task_id: UUID, payload: TaskOrchestrationBindingRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        binding = bind_task_template(session, task_id=task_id, template_id=payload.template_id, actor_id=user.id, correlation_id=correlation_id(request))
        session.commit()
        return {"taskId": str(binding.task_id), "templateId": str(binding.template_id), "templateVersion": binding.template_version}
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@run_router.get("/{run_id}/orchestration")
def run_orchestration(run_id: UUID, session: SessionDep, user: CurrentUserDep) -> dict:
    try:
        return get_run_orchestration(session, run_id=run_id, actor_id=user.id)
    except DomainError as exc:
        raise _failure(exc)
