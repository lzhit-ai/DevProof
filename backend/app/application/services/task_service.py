from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.domain.enums import CycleStatus, ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import (
    DeliveryItem,
    ExternalResource,
    ExternalResourceRevision,
    InputSnapshot,
    PublishedRecord,
    ReportVersion,
    VerificationCycle,
    VerificationTask,
)
from app.application.services.orchestration_service import bind_task_default_orchestration, bind_task_template
from app.infrastructure.business_ownership import require_python_task_management


def create_task(
    session: Session,
    *,
    project_id: UUID,
    title: str,
    requirement_key: str,
    actor_id: UUID,
    correlation_id: str,
    delivery_item_id: UUID,
    orchestration_template_id: UUID | None = None,
) -> tuple[VerificationTask, VerificationCycle]:
    require_python_task_management(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = session.get(DeliveryItem, delivery_item_id)
    if item is None or item.project_id != project_id:
        raise DomainError("INPUT_INVALID", "代码交付不存在或不属于当前项目")
    resource = session.get(ExternalResource, item.external_resource_id)
    if resource is None or resource.resource_type != "PULL_REQUEST":
        raise DomainError("INPUT_INVALID", "审查任务只能从当前项目已同步的 GitHub PR 创建")
    task = VerificationTask(
        project_id=project_id, delivery_item_id=delivery_item_id, title=title, requirement_key=requirement_key, created_by=actor_id
    )
    session.add(task)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DomainError("STATE_CONFLICT", "项目内需求标识已存在") from exc
    cycle = VerificationCycle(task_id=task.id, sequence_no=1, business_status=CycleStatus.DRAFT)
    session.add(cycle)
    session.flush()
    if orchestration_template_id is None:
        bind_task_default_orchestration(session, task_id=task.id, project_id=project_id, actor_id=actor_id)
    else:
        bind_task_template(session, task_id=task.id, template_id=orchestration_template_id, actor_id=actor_id, correlation_id=correlation_id)
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="VerificationTask",
        aggregate_id=task.id,
        action="VERIFICATION_TASK_CREATED",
        correlation_id=correlation_id,
        after_version=task.version,
        payload={"cycleId": str(cycle.id), "deliveryItemId": str(delivery_item_id)},
    )
    return task, cycle


def create_next_cycle(session: Session, *, task_id: UUID, actor_id: UUID, correlation_id: str) -> VerificationCycle:
    require_python_task_management(session)
    task = session.get(VerificationTask, task_id)
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    previous = session.query(VerificationCycle).filter_by(task_id=task.id).order_by(VerificationCycle.sequence_no.desc()).first()
    if previous is None or previous.business_status != CycleStatus.PUBLISHED:
        raise DomainError("STATE_CONFLICT", "仅已发布核验轮次可以创建新版本")
    cycle = VerificationCycle(task_id=task.id, sequence_no=previous.sequence_no + 1, business_status=CycleStatus.DRAFT, created_from_cycle_id=previous.id)
    session.add(cycle); session.flush()
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="VerificationCycle", aggregate_id=cycle.id, action="VERIFICATION_CYCLE_CREATED", correlation_id=correlation_id, payload={"previousCycleId": str(previous.id)})
    return cycle


def list_tasks(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 100) -> list[dict]:
    """Expose task state without treating a task or a linked PR as delivery proof."""

    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    tasks = (
        session.query(VerificationTask)
        .filter_by(project_id=project_id)
        .order_by(VerificationTask.updated_at.desc(), VerificationTask.created_at.desc())
        .limit(limit)
        .all()
    )
    result: list[dict] = []
    for task in tasks:
        item = session.get(DeliveryItem, task.delivery_item_id)
        resource = session.get(ExternalResource, item.external_resource_id) if item else None
        revision = (
            session.query(ExternalResourceRevision)
            .filter_by(resource_id=resource.id)
            .order_by(ExternalResourceRevision.revision_no.desc())
            .first()
            if resource is not None
            else None
        )
        pull_request = (
            revision.payload.get("pullRequest")
            if resource is not None and resource.resource_type == "PULL_REQUEST" and revision is not None and isinstance(revision.payload, dict)
            else None
        )
        cycle = (
            session.query(VerificationCycle)
            .filter_by(task_id=task.id)
            .order_by(VerificationCycle.sequence_no.desc())
            .first()
        )
        snapshot = (
            session.query(InputSnapshot)
            .filter_by(cycle_id=cycle.id, purpose="FORMAL")
            .order_by(InputSnapshot.created_at.desc())
            .first()
            if cycle
            else None
        )
        report = (
            session.query(ReportVersion)
            .filter_by(cycle_id=cycle.id)
            .order_by(ReportVersion.sequence_no.desc())
            .first()
            if cycle
            else None
        )
        record = session.query(PublishedRecord).filter_by(report_version_id=report.id).one_or_none() if report else None
        result.append(
            {
                "id": task.id,
                "project_id": task.project_id,
                "delivery_item_id": task.delivery_item_id,
                "title": task.title,
                "requirement_key": task.requirement_key,
                "cycle_id": cycle.id if cycle else None,
                "cycle_status": cycle.business_status if cycle else "UNKNOWN",
                "formal_snapshot_id": snapshot.id if snapshot else None,
                "formal_snapshot_hash": snapshot.snapshot_hash if snapshot else None,
                "report_id": report.id if report else None,
                "report_status": report.status if report else None,
                "published_record_id": record.id if record else None,
                "delivery_pull_request": pull_request,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )
    return result
