from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import require_project_role
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import EvidenceItem, InputSnapshot, VerificationCycle, VerificationTask


def resolve_citation(
    session: Session, *, evidence_id: UUID, snapshot_id: UUID, actor_id: UUID
) -> EvidenceItem:
    """Resolve only evidence belonging to the caller's project and requested snapshot."""

    snapshot = session.get(InputSnapshot, snapshot_id)
    if snapshot is None:
        raise DomainError("RESOURCE_NOT_FOUND", "输入快照不存在")
    cycle = session.get(VerificationCycle, snapshot.cycle_id)
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    evidence = session.get(EvidenceItem, evidence_id)
    if evidence is None or evidence.project_id != task.project_id or evidence.snapshot_id != snapshot.id:
        raise DomainError("CITATION_INVALID", "证据不存在、无权访问或不属于当前快照")
    if evidence.source_type == "TOOL" or evidence.evidence_kind == "HTTP_QUERY":
        raise DomainError("CITATION_INVALID", "运行期工具结果不是正式证据；请先显式导入并冻结到新的输入快照")
    if evidence.locator_precision not in {"EXACT", "APPROXIMATE", "UNAVAILABLE"}:
        raise DomainError("CITATION_INVALID", "证据定位器无效")
    return evidence
