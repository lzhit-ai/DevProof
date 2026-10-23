from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.application.services.common import append_audit_event, require_project_role
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import (
    AnalysisJob, AnalysisRun, ExternalConnection, InputSnapshot, Project, ProjectMember,
    RetrievalIndexBuildRun, SourceIngestionJob, SourceRevision, User, VerificationCycle, VerificationTask,
)
from app.application.services.orchestration_service import ensure_default_orchestration
from app.application.services.external_source_service import (
    create_connection,
    sync_connection,
)
from app.application.services.git_service import register_repository
from app.application.services.source_service import mount_knowledge_base
from app.infrastructure.persistence.models import SourceSyncRun
from app.infrastructure.business_ownership import require_python_projects


def create_project(
    session: Session, *, name: str, description: str | None, actor_id: UUID, correlation_id: str
) -> Project:
    require_python_projects(session)
    project = Project(name=name, description=description, owner_id=actor_id)
    session.add(project)
    session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=actor_id, role=ProjectRole.ADMIN))
    ensure_default_orchestration(session, project_id=project.id, actor_id=actor_id)
    append_audit_event(
        session,
        project_id=project.id,
        actor_id=actor_id,
        aggregate_type="Project",
        aggregate_id=project.id,
        action="PROJECT_CREATED",
        correlation_id=correlation_id,
        after_version=project.version,
    )
    return project


def create_project_with_source(
    session: Session,
    *,
    name: str,
    description: str | None,
    repository_url: str,
    actor_id: UUID,
    correlation_id: str,
    knowledge_base_ids: list[UUID] | None = None,
) -> tuple[Project, SourceSyncRun]:
    """Create a project and register + queue its GitHub source in one transaction.

    This keeps the create-project flow to a single request so a GitHub source
    connection never leaves the UI in a half-created state: either the whole
    project+connection+repository lands, or the request rolls back.
    """
    slug = _repository_slug(repository_url)
    project = create_project(
        session, name=name, description=description, actor_id=actor_id, correlation_id=correlation_id
    )
    connection = create_connection(
        session,
        project_id=project.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        provider="GITHUB",
        name=slug,
        repository_slug=slug,
        secret_ref=None,
    )
    register_repository(
        session,
        project_id=project.id,
        display_url=f"https://github.com/{slug}.git",
        credential_ref=None,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    for knowledge_base_id in knowledge_base_ids or []:
        mount_knowledge_base(
            session,
            project_id=project.id,
            knowledge_base_id=knowledge_base_id,
            actor_id=actor_id,
        )
    sync = sync_connection(
        session,
        project_id=project.id,
        connection_id=connection.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    return project, sync


def _repository_slug(value: str) -> str:
    """Normalize a GitHub repository URL or bare owner/repo slug."""
    trimmed = value.strip().rstrip("/").replace(".git", "").replace("https://github.com/", "").replace("http://github.com/", "")
    if not trimmed or "/" not in trimmed or trimmed.count("/") > 1:
        raise DomainError("INPUT_INVALID", "GitHub 仓库地址无效，例如 https://github.com/owner/repository")
    return trimmed


def list_projects(session: Session, *, actor_id: UUID) -> list[Project]:
    """Return only projects the current user can actually enter."""

    return (
        session.query(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(ProjectMember.user_id == actor_id, Project.deleted_at.is_(None))
        .order_by(Project.updated_at.desc(), Project.created_at.desc())
        .all()
    )


def delete_project(
    session: Session, *, project_id: UUID, confirmation_name: str, actor_id: UUID, correlation_id: str
) -> None:
    require_python_projects(session)
    try:
        project = session.query(Project).filter_by(id=project_id).with_for_update(nowait=True).one_or_none()
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise DomainError("PROJECT_BUSY", "项目仍有操作进行中，请稍后再删除") from exc
        raise
    member = session.query(ProjectMember).filter_by(project_id=project_id, user_id=actor_id).one_or_none()
    if project is None or member is None:
        raise DomainError("RESOURCE_NOT_FOUND", "项目不存在或无法访问")
    if member.role != ProjectRole.ADMIN:
        raise DomainError("AUTH_FORBIDDEN", "只有项目管理员可以删除项目")
    if confirmation_name != project.name:
        raise DomainError("INPUT_INVALID", "项目名称不匹配，请输入完整项目名称")
    if project.deleted_at is not None:
        return

    run_scope = (
        session.query(AnalysisRun.id)
        .join(InputSnapshot, InputSnapshot.id == AnalysisRun.snapshot_id)
        .join(VerificationCycle, VerificationCycle.id == InputSnapshot.cycle_id)
        .join(VerificationTask, VerificationTask.id == VerificationCycle.task_id)
        .filter(VerificationTask.project_id == project_id)
    )
    active_work = [
        run_scope.filter(AnalysisRun.run_status.in_(("QUEUED", "RUNNING"))),
        session.query(AnalysisJob.id).filter(AnalysisJob.run_id.in_(run_scope), AnalysisJob.job_status.in_(("QUEUED", "RUNNING"))),
        session.query(SourceSyncRun.id).join(ExternalConnection, ExternalConnection.id == SourceSyncRun.connection_id)
        .filter(ExternalConnection.project_id == project_id, SourceSyncRun.status == "RUNNING"),
        session.query(SourceIngestionJob.id).join(SourceRevision, SourceRevision.id == SourceIngestionJob.source_revision_id)
        .filter(SourceRevision.project_id == project_id, SourceIngestionJob.job_status.in_(("QUEUED", "RUNNING"))),
        session.query(RetrievalIndexBuildRun.id).filter_by(project_id=project_id, status="RUNNING"),
    ]
    if any(query.first() is not None for query in active_work):
        raise DomainError("PROJECT_BUSY", "项目仍有待处理或运行中的任务，请等待审查、同步或资料处理结束后再删除")

    before_version = project.version
    project.deleted_at = datetime.now(UTC)
    project.version += 1
    session.query(ExternalConnection).filter_by(project_id=project_id).update({"is_active": False})
    append_audit_event(
        session, project_id=project_id, actor_id=actor_id, aggregate_type="Project", aggregate_id=project_id,
        action="PROJECT_DELETED", correlation_id=correlation_id, payload={"name": project.name},
        before_version=before_version, after_version=project.version,
    )
    session.flush()


def add_member(session: Session, *, project_id: UUID, user_id: UUID, role: str, actor_id: UUID, correlation_id: str) -> ProjectMember:
    require_python_projects(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.ADMIN})
    if session.get(User, user_id) is None:
        raise DomainError("RESOURCE_NOT_FOUND", "待添加用户不存在")
    member = session.query(ProjectMember).filter_by(project_id=project_id, user_id=user_id).one_or_none()
    if member is not None:
        raise DomainError("STATE_CONFLICT", "用户已是项目成员")
    member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
    session.add(member); session.flush()
    append_audit_event(session, project_id=project_id, actor_id=actor_id, aggregate_type="ProjectMember", aggregate_id=member.id, action="PROJECT_MEMBER_ADDED", correlation_id=correlation_id, payload={"memberUserId": str(user_id), "role": role})
    return member


def add_member_by_email(session: Session, *, project_id: UUID, user_email: str, role: str, actor_id: UUID, correlation_id: str) -> ProjectMember:
    require_project_role(session, project_id, actor_id, {ProjectRole.ADMIN})
    target = session.query(User).filter_by(email=user_email.strip().lower()).one_or_none()
    if target is None:
        raise DomainError("RESOURCE_NOT_FOUND", "待添加用户不存在")
    return add_member(session, project_id=project_id, user_id=target.id, role=role, actor_id=actor_id, correlation_id=correlation_id)
