from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import ProjectCreateRequest, ProjectDeleteRequest, ProjectMemberCreateRequest, ProjectResponse
from app.application.services.project_service import add_member, add_member_by_email, create_project, create_project_with_source, delete_project, list_projects
from app.application.services.source_service import mount_knowledge_base
from app.domain.errors import DomainError
from app.domain.enums import ProjectRole
from app.infrastructure.persistence.models import Project, ProjectMember

router = APIRouter(prefix="/projects")


def _project_response(project: Project, *, can_delete: bool) -> ProjectResponse:
    return ProjectResponse.model_validate(project, from_attributes=True).model_copy(update={"can_delete": can_delete})


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create(
    payload: ProjectCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> ProjectResponse:
    try:
        if payload.repository_url:
            project, _sync = create_project_with_source(
                session,
                name=payload.name,
                description=payload.description,
                repository_url=payload.repository_url,
                actor_id=user.id,
                correlation_id=correlation_id(request),
                knowledge_base_ids=payload.knowledge_base_ids,
            )
        else:
            project = create_project(
                session,
                name=payload.name,
                description=payload.description,
                actor_id=user.id,
                correlation_id=correlation_id(request),
            )
            for knowledge_base_id in payload.knowledge_base_ids:
                mount_knowledge_base(
                    session,
                    project_id=project.id,
                    knowledge_base_id=knowledge_base_id,
                    actor_id=user.id,
                )
        session.commit()
        session.refresh(project)
        return _project_response(project, can_delete=True)
    except DomainError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})


@router.get("", response_model=list[ProjectResponse])
def get_projects(session: SessionDep, user: CurrentUserDep) -> list[ProjectResponse]:
    admin_ids = {
        row.project_id for row in session.query(ProjectMember.project_id)
        .filter_by(user_id=user.id, role=ProjectRole.ADMIN).all()
    }
    return [_project_response(project, can_delete=project.id in admin_ids) for project in list_projects(session, actor_id=user.id)]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> ProjectResponse:
    project = session.get(Project, project_id)
    member = session.query(ProjectMember).filter_by(project_id=project_id, user_id=user.id).one_or_none()
    if project is None or project.deleted_at is not None or member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return _project_response(project, can_delete=member.role == ProjectRole.ADMIN)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project(
    project_id: UUID, payload: ProjectDeleteRequest, request: Request, session: SessionDep, user: CurrentUserDep
) -> Response:
    try:
        delete_project(
            session, project_id=project_id, confirmation_name=payload.confirmation_name,
            actor_id=user.id, correlation_id=correlation_id(request),
        )
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except DomainError as exc:
        session.rollback()
        error_status = {"AUTH_FORBIDDEN": 403, "RESOURCE_NOT_FOUND": 404, "INPUT_INVALID": 422}.get(exc.code, 409)
        raise HTTPException(status_code=error_status, detail={"code": exc.code, "message": exc.message}) from exc


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED)
def add_project_member(project_id: UUID, payload: ProjectMemberCreateRequest, request: Request, session: SessionDep, user: CurrentUserDep, _: str = Depends(idempotency_key)) -> dict:
    try:
        member = add_member_by_email(session, project_id=project_id, user_email=payload.user_email, role=payload.role, actor_id=user.id, correlation_id=correlation_id(request)) if payload.user_email else add_member(session, project_id=project_id, user_id=payload.user_id, role=payload.role, actor_id=user.id, correlation_id=correlation_id(request)); session.commit()
        return {"id": str(member.id), "userId": str(member.user_id), "role": member.role}
    except DomainError as exc:
        session.rollback(); raise HTTPException(status_code=status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})
