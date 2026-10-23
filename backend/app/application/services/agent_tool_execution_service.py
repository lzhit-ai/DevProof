import hashlib
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.infrastructure.business_ownership import require_python_evidence_materials
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.persistence.models import (
    AgentToolExecution,
    AnalysisRun,
    InputSnapshot,
    ManualEvidence,
    VerificationCycle,
    VerificationTask,
)


def _run_context(session: Session, *, run_id: UUID, actor_id: UUID, allowed_roles: set[ProjectRole]) -> tuple[AnalysisRun, InputSnapshot, VerificationCycle, VerificationTask]:
    run = session.get(AnalysisRun, run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or run is None or snapshot is None or cycle is None:
        raise DomainError("RESOURCE_NOT_FOUND", "分析运行不存在")
    require_project_role(session, task.project_id, actor_id, allowed_roles)
    return run, snapshot, cycle, task


def list_tool_executions(session: Session, *, run_id: UUID, actor_id: UUID) -> list[dict]:
    run, _, _, _ = _run_context(
        session,
        run_id=run_id,
        actor_id=actor_id,
        allowed_roles={ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN},
    )
    executions = (
        session.query(AgentToolExecution)
        .filter_by(analysis_run_id=run.id)
        .order_by(AgentToolExecution.created_at)
        .all()
    )
    imports = (
        session.query(ManualEvidence)
        .filter(ManualEvidence.source_tool_execution_id.in_([item.id for item in executions]))
        .all()
        if executions
        else []
    )
    imported_by_execution = {item.source_tool_execution_id: item for item in imports}
    return [
        {
            "id": item.id,
            "analysis_run_id": item.analysis_run_id,
            "capability_key": item.capability_key,
            "tool_key": item.tool_key,
            "tool_type": item.tool_type,
            "content_hash": item.content_hash,
            "excerpt_safe": item.excerpt_safe,
            "locator": item.locator,
            "status": item.status,
            "created_at": item.created_at,
            "imported_manual_evidence_id": imported_by_execution[item.id].id if item.id in imported_by_execution else None,
        }
        for item in executions
    ]


def import_tool_execution_as_manual_evidence(
    session: Session,
    *,
    run_id: UUID,
    execution_id: UUID,
    logical_name: str,
    actor_id: UUID,
    correlation_id: str,
) -> ManualEvidence:
    require_python_evidence_materials(session)
    run, _, cycle, task = _run_context(
        session,
        run_id=run_id,
        actor_id=actor_id,
        allowed_roles={ProjectRole.SUBMITTER, ProjectRole.ADMIN},
    )
    if run.run_status not in {"SUCCEEDED", "PARTIALLY_COMPLETED"}:
        raise DomainError("STATE_CONFLICT", "仅终态分析运行的工具结果可以被显式导入")
    if cycle.business_status not in {"DRAFT", "NEEDS_EVIDENCE", "NEEDS_CONFIRMATION"}:
        raise DomainError("STATE_CONFLICT", "当前轮次不能再导入工具结果；请在可补证轮次创建新的正式输入快照")
    execution = session.query(AgentToolExecution).filter_by(id=execution_id, analysis_run_id=run.id).one_or_none()
    if execution is None:
        raise DomainError("RESOURCE_NOT_FOUND", "临时工具结果不存在或不属于当前运行")
    imported = session.query(ManualEvidence).filter_by(source_tool_execution_id=execution.id).one_or_none()
    if imported is not None:
        return imported

    storage = LocalArtifactStorage(get_settings().artifact_root)
    content = storage.read_text(execution.artifact_uri)
    content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
    if content_hash != execution.content_hash:
        raise DomainError("INPUT_STALE", "临时工具结果的存储内容与运行哈希不一致，不能导入")

    evidence = ManualEvidence(
        project_id=task.project_id,
        cycle_id=cycle.id,
        logical_name=logical_name.strip(),
        content_hash=content_hash,
        artifact_uri="pending://artifact",
        submitted_by=actor_id,
        origin_type="AGENT_TOOL_IMPORT",
        origin_locator={
            "toolExecutionId": str(execution.id),
            "analysisRunId": str(run.id),
            "capabilityKey": execution.capability_key,
            "toolKey": execution.tool_key,
            "toolResponseHash": execution.content_hash,
        },
        source_tool_execution_id=execution.id,
    )
    session.add(evidence)
    session.flush()
    evidence.artifact_uri = storage.write_bytes(
        [str(task.project_id), "manual-evidence", str(evidence.id)],
        "imported-tool-result.txt",
        content.encode("utf-8"),
    )
    append_audit_event(
        session,
        project_id=task.project_id,
        actor_id=actor_id,
        aggregate_type="AgentToolExecution",
        aggregate_id=execution.id,
        action="AGENT_TOOL_RESULT_IMPORTED",
        correlation_id=correlation_id,
        payload={"manualEvidenceId": str(evidence.id), "contentHash": evidence.content_hash},
    )
    append_audit_event(
        session,
        project_id=task.project_id,
        actor_id=actor_id,
        aggregate_type="ManualEvidence",
        aggregate_id=evidence.id,
        action="MANUAL_EVIDENCE_SUBMITTED",
        correlation_id=correlation_id,
        payload={
            "contentHash": evidence.content_hash,
            "logicalName": evidence.logical_name,
            "originType": evidence.origin_type,
            "toolExecutionId": str(execution.id),
        },
    )
    return evidence
