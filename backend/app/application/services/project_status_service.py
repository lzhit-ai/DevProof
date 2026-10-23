"""Evidence-grounded project-health snapshots and personal development-summary records."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.business_ownership import require_python_project_status
from app.infrastructure.persistence.models import (
    DeliveryChangeLink,
    DeliveryItem,
    DeliveryItemSourceLink,
    ExternalConnection,
    ExternalResourceRevision,
    GitSnapshot,
    InputSnapshot,
    ProjectHealthSnapshot,
    ProjectSummaryDraft,
    ProjectSummaryRecord,
    PublishedRecord,
    RiskFinding,
    SourceSyncRun,
    VerificationCycle,
    VerificationTask,
    AnalysisRun,
)


_SUMMARY_PERIOD_LABELS = {"DAILY": "日报", "WEEKLY": "周报", "ITERATION": "迭代总结"}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _as_iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def _project_health_snapshot(session: Session, *, project_id: UUID, health_snapshot_id: UUID) -> ProjectHealthSnapshot:
    snapshot = session.get(ProjectHealthSnapshot, health_snapshot_id)
    if snapshot is None or snapshot.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "项目态势快照不存在")
    return snapshot


def _latest_item_revision(session: Session, item: DeliveryItem) -> ExternalResourceRevision | None:
    return (
        session.query(ExternalResourceRevision)
        .filter_by(resource_id=item.external_resource_id)
        .order_by(ExternalResourceRevision.revision_no.desc())
        .first()
    )


def _scope_items(session: Session, *, project_id: UUID, milestone_key: str | None) -> tuple[list[DeliveryItem], list[dict]]:
    items = session.query(DeliveryItem).filter_by(project_id=project_id).order_by(DeliveryItem.created_at).all()
    scoped_items: list[DeliveryItem] = []
    input_items: list[dict] = []
    for item in items:
        revision = _latest_item_revision(session, item)
        item_milestone = revision.milestone_key if revision else None
        if milestone_key is not None and item_milestone != milestone_key:
            continue
        scoped_items.append(item)
        input_items.append(
            {
                "id": str(item.id),
                "externalKey": item.external_key,
                "title": item.title,
                "planningStatus": item.planning_status,
                "verificationStatus": item.verification_status,
                "milestoneKey": item_milestone,
                "sourceUpdatedAt": _as_iso(item.source_updated_at),
                "externalRevision": revision.revision_no if revision else None,
                "externalContentHash": revision.content_hash if revision else None,
                "externalWebUrl": revision.web_url if revision else None,
            }
        )
    return scoped_items, input_items


def _status_counts(items: list[DeliveryItem]) -> tuple[dict[str, int], dict[str, int]]:
    return dict(sorted(Counter(item.planning_status for item in items).items())), dict(sorted(Counter(item.verification_status for item in items).items()))


def _item_ids_with_formal_records(session: Session, *, project_id: UUID, item_ids: set[UUID]) -> set[UUID]:
    if not item_ids:
        return set()
    rows = (
        session.query(VerificationTask.delivery_item_id)
        .join(PublishedRecord, PublishedRecord.task_id == VerificationTask.id)
        .filter(VerificationTask.project_id == project_id, VerificationTask.delivery_item_id.in_(item_ids))
        .distinct()
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _item_ids_with_confirmed_changes(session: Session, *, item_ids: set[UUID]) -> set[UUID]:
    if not item_ids:
        return set()
    rows = (
        session.query(DeliveryChangeLink.delivery_item_id)
        .filter(DeliveryChangeLink.delivery_item_id.in_(item_ids), DeliveryChangeLink.link_status == "CONFIRMED")
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _item_ids_with_document_sources(session: Session, *, item_ids: set[UUID]) -> set[UUID]:
    if not item_ids:
        return set()
    rows = (
        session.query(DeliveryItemSourceLink.delivery_item_id)
        .filter(
            DeliveryItemSourceLink.delivery_item_id.in_(item_ids),
            DeliveryItemSourceLink.source_revision_id.is_not(None),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _unattributed_activity_counts(session: Session, *, project_id: UUID) -> dict[str, int]:
    task_query = session.query(VerificationTask.id).filter(
        VerificationTask.project_id == project_id,
        VerificationTask.delivery_item_id.is_(None),
    )
    task_ids = [row[0] for row in task_query.all()]
    if not task_ids:
        return {"taskCount": 0, "gitSnapshotCount": 0}
    git_snapshot_count = (
        session.query(func.count(GitSnapshot.id))
        .join(VerificationCycle, VerificationCycle.id == GitSnapshot.cycle_id)
        .filter(VerificationCycle.task_id.in_(task_ids))
        .scalar()
        or 0
    )
    return {"taskCount": len(task_ids), "gitSnapshotCount": int(git_snapshot_count)}


def _observed_risks(session: Session, *, project_id: UUID) -> tuple[dict[str, int], list[dict]]:
    rows = (
        session.query(RiskFinding.id, RiskFinding.analysis_run_id, RiskFinding.severity, RiskFinding.category, RiskFinding.finding_kind)
        .join(AnalysisRun, AnalysisRun.id == RiskFinding.analysis_run_id)
        .join(InputSnapshot, InputSnapshot.id == AnalysisRun.snapshot_id)
        .join(VerificationCycle, VerificationCycle.id == InputSnapshot.cycle_id)
        .join(VerificationTask, VerificationTask.id == VerificationCycle.task_id)
        .filter(VerificationTask.project_id == project_id)
        .order_by(RiskFinding.severity, RiskFinding.category, RiskFinding.id)
        .all()
    )
    manifest = [
        {
            "riskFindingId": str(risk_id),
            "analysisRunId": str(run_id),
            "severity": severity,
            "category": category,
            "findingKind": finding_kind,
        }
        for risk_id, run_id, severity, category, finding_kind in rows
    ]
    return dict(sorted(Counter(entry["severity"] for entry in manifest).items())), manifest


def _source_freshness(session: Session, *, project_id: UUID) -> dict:
    latest_success = (
        session.query(SourceSyncRun)
        .join(ExternalConnection, ExternalConnection.id == SourceSyncRun.connection_id)
        .filter(
            ExternalConnection.project_id == project_id,
            SourceSyncRun.status.in_(["SUCCEEDED", "PARTIALLY_SUCCEEDED"]),
        )
        .order_by(SourceSyncRun.finished_at.desc())
        .first()
    )
    latest_attempt = (
        session.query(SourceSyncRun)
        .join(ExternalConnection, ExternalConnection.id == SourceSyncRun.connection_id)
        .filter(ExternalConnection.project_id == project_id)
        .order_by(SourceSyncRun.started_at.desc())
        .first()
    )
    latest_item_update = session.query(func.max(DeliveryItem.source_updated_at)).filter_by(project_id=project_id).scalar()
    return {
        "latestSuccessfulSync": {
            "id": str(latest_success.id),
            "status": latest_success.status,
            "finishedAt": _as_iso(latest_success.finished_at),
        }
        if latest_success
        else None,
        "latestSyncAttempt": {
            "id": str(latest_attempt.id),
            "status": latest_attempt.status,
            "finishedAt": _as_iso(latest_attempt.finished_at),
            "errorCode": latest_attempt.error_code,
        }
        if latest_attempt
        else None,
        "latestItemSourceUpdatedAt": _as_iso(latest_item_update),
    }


def create_project_health_snapshot(
    session: Session,
    *,
    project_id: UUID,
    milestone_key: str | None,
    actor_id: UUID,
    correlation_id: str,
) -> ProjectHealthSnapshot:
    require_python_project_status(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    normalized_milestone = milestone_key.strip() if milestone_key else None
    if normalized_milestone == "":
        normalized_milestone = None
    items, item_input = _scope_items(session, project_id=project_id, milestone_key=normalized_milestone)
    item_ids = {item.id for item in items}
    planning_counts, verification_counts = _status_counts(items)
    active_items = [item for item in items if item.planning_status != "CANCELLED"]
    declared_done_unverified = sum(
        item.planning_status == "DECLARED_DONE" and item.verification_status != "CONFIRMED" for item in active_items
    )
    formal_record_item_ids = _item_ids_with_formal_records(session, project_id=project_id, item_ids=item_ids)
    confirmed_change_item_ids = _item_ids_with_confirmed_changes(session, item_ids=item_ids)
    document_source_item_ids = _item_ids_with_document_sources(session, item_ids=item_ids)
    unattributed_activity = _unattributed_activity_counts(session, project_id=project_id)
    source_freshness = _source_freshness(session, project_id=project_id)
    risk_counts, risk_manifest = _observed_risks(session, project_id=project_id)
    as_of = datetime.now(UTC)
    scope = {"milestoneKey": normalized_milestone, "assessmentProfile": "PROJECT_STATUS_SUMMARY"}
    summary = {
        "plannedItemCount": len(active_items),
        "cancelledItemCount": len(items) - len(active_items),
        "planningStatusCounts": planning_counts,
        "verificationStatusCounts": verification_counts,
        "declaredDoneButNotVerifiedCount": int(declared_done_unverified),
        "formalRecordItemCount": len(formal_record_item_ids),
        "confirmedChangeLinkedItemCount": len(confirmed_change_item_ids),
        "documentSourceLinkedItemCount": len(document_source_item_ids),
        "unattributedActivity": unattributed_activity,
        "observedRiskCounts": risk_counts,
        "sourceFreshness": source_freshness,
    }
    data_gaps: list[str] = []
    if not active_items:
        data_gaps.append("NO_ACTIVE_PLAN_BASELINE")
    if source_freshness["latestSuccessfulSync"] is None:
        data_gaps.append("SOURCE_NOT_SYNCED")
    if unattributed_activity["gitSnapshotCount"]:
        data_gaps.append("UNATTRIBUTED_GIT_ACTIVITY")
    coverage = {
        "planBaselineAvailable": bool(active_items),
        "completionRate": None,
        "verificationCoverage": {
            "numerator": verification_counts.get("CONFIRMED", 0),
            "denominator": len(active_items),
        }
        if active_items
        else None,
        "dataGaps": data_gaps,
        "observabilityLimits": [
            "未关联研发事项的 Git 范围只计为待归属开发活动。",
            "历史风险为已记录发现，不等同于当前未关闭风险。",
            "项目态势不以提交数量、PR 数量或外部关闭状态推断完成。",
        ],
    }
    input_payload = {"scope": scope, "items": item_input, "risks": risk_manifest, "summary": summary, "coverage": coverage}
    input_hash = _canonical_hash(input_payload)
    snapshot_hash = _canonical_hash({"inputHash": input_hash, "asOf": _as_iso(as_of)})
    snapshot = ProjectHealthSnapshot(
        project_id=project_id,
        scope=scope,
        input_manifest=input_payload,
        input_hash=input_hash,
        snapshot_hash=snapshot_hash,
        summary=summary,
        coverage=coverage,
        as_of=as_of,
        created_by=actor_id,
    )
    session.add(snapshot)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="ProjectHealthSnapshot",
        aggregate_id=snapshot.id,
        action="PROJECT_HEALTH_SNAPSHOT_CREATED",
        correlation_id=correlation_id,
        payload={"snapshotHash": snapshot.snapshot_hash, "scope": scope, "dataGaps": data_gaps},
    )
    return snapshot


def list_project_health_snapshots(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[ProjectHealthSnapshot]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return (
        session.query(ProjectHealthSnapshot)
        .filter_by(project_id=project_id)
        .order_by(ProjectHealthSnapshot.as_of.desc())
        .limit(limit)
        .all()
    )


def get_project_health_snapshot(session: Session, *, project_id: UUID, health_snapshot_id: UUID, actor_id: UUID) -> ProjectHealthSnapshot:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return _project_health_snapshot(session, project_id=project_id, health_snapshot_id=health_snapshot_id)


def _draft_content(snapshot: ProjectHealthSnapshot, *, period_type: str) -> dict:
    summary = snapshot.summary
    coverage = snapshot.coverage
    period_label = _SUMMARY_PERIOD_LABELS[period_type]
    facts = [
        f"纳入态势口径的未取消事项：{summary['plannedItemCount']}；外部已声明完成：{summary['planningStatusCounts'].get('DECLARED_DONE', 0)}；本系统核验已确认：{summary['verificationStatusCounts'].get('CONFIRMED', 0)}。三项口径彼此独立。",
        f"已有正式交付记录覆盖事项：{summary['formalRecordItemCount']}；已确认 PR/Git 变更归属的事项：{summary['confirmedChangeLinkedItemCount']}；已关联验收/设计/计划资料的事项：{summary['documentSourceLinkedItemCount']}。",
    ]
    attention: list[str] = []
    if summary["declaredDoneButNotVerifiedCount"]:
        attention.append(f"外部已声明完成但尚未核验确认的事项：{summary['declaredDoneButNotVerifiedCount']}。")
    if summary["unattributedActivity"]["gitSnapshotCount"]:
        attention.append(f"待归属开发活动：{summary['unattributedActivity']['gitSnapshotCount']} 个冻结 Git 范围，来自 {summary['unattributedActivity']['taskCount']} 个未关联事项的核验任务。")
    if summary["observedRiskCounts"]:
        risk_text = "，".join(f"{key} {value}" for key, value in sorted(summary["observedRiskCounts"].items()))
        attention.append(f"历史交付核验中记录的风险发现：{risk_text}；其是否仍未关闭需要安全基线或人工状态确认。")
    if not attention:
        attention.append("当前快照没有新增的待归属开发活动或已声明完成但未核验确认事项。")
    return {
        "kind": "PROJECT_STATUS_SUMMARY",
        "periodType": period_type,
        "periodLabel": period_label,
        "healthSnapshotId": str(snapshot.id),
        "healthSnapshotHash": snapshot.snapshot_hash,
        "asOf": _as_iso(snapshot.as_of),
        "scope": snapshot.scope,
        "facts": facts,
        "attention": attention,
        "dataGaps": coverage["dataGaps"],
        "boundary": "本草稿描述已记录事实、数据缺口与待确认项；不将提交、PR 或外部关闭状态写成已完成结论。",
    }


def create_project_summary_draft(
    session: Session,
    *,
    project_id: UUID,
    health_snapshot_id: UUID,
    period_type: str,
    title: str | None,
    actor_id: UUID,
    correlation_id: str,
) -> ProjectSummaryDraft:
    require_python_project_status(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if period_type not in _SUMMARY_PERIOD_LABELS:
        raise DomainError("INPUT_INVALID", "总结类型必须是 DAILY、WEEKLY 或 ITERATION")
    snapshot = _project_health_snapshot(session, project_id=project_id, health_snapshot_id=health_snapshot_id)
    content = _draft_content(snapshot, period_type=period_type)
    normalized_title = title.strip() if title else ""
    if not normalized_title:
        normalized_title = f"{content['periodLabel']}项目态势总结（截至 {snapshot.as_of.date().isoformat()}）"
    draft = ProjectSummaryDraft(
        project_id=project_id,
        health_snapshot_id=snapshot.id,
        period_type=period_type,
        title=normalized_title,
        content=content,
        content_hash=_canonical_hash({"title": normalized_title, "content": content}),
        created_by=actor_id,
    )
    session.add(draft)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="ProjectSummaryDraft",
        aggregate_id=draft.id,
        action="PROJECT_SUMMARY_DRAFT_CREATED",
        correlation_id=correlation_id,
        payload={"healthSnapshotId": str(snapshot.id), "periodType": period_type, "contentHash": draft.content_hash},
    )
    return draft


def list_project_summary_drafts(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[ProjectSummaryDraft]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return (
        session.query(ProjectSummaryDraft)
        .filter_by(project_id=project_id)
        .order_by(ProjectSummaryDraft.created_at.desc())
        .limit(limit)
        .all()
    )


def publish_project_summary_draft(
    session: Session,
    *,
    project_id: UUID,
    draft_id: UUID,
    actor_id: UUID,
    correlation_id: str,
) -> ProjectSummaryRecord:
    require_python_project_status(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    draft = session.get(ProjectSummaryDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "项目总结草稿不存在")
    existing = session.query(ProjectSummaryRecord).filter_by(summary_draft_id=draft.id).one_or_none()
    if existing is not None:
        return existing
    snapshot = _project_health_snapshot(session, project_id=project_id, health_snapshot_id=draft.health_snapshot_id)
    record_hash = _canonical_hash(
        {
            "summaryDraftId": str(draft.id),
            "contentHash": draft.content_hash,
            "healthSnapshotHash": snapshot.snapshot_hash,
            "confirmationType": "PERSONAL_CONFIRMED",
        }
    )
    record = ProjectSummaryRecord(
        project_id=project_id,
        health_snapshot_id=snapshot.id,
        summary_draft_id=draft.id,
        record_no=f"PS-{draft.id.hex[:16].upper()}",
        record_hash=record_hash,
        confirmation_type="PERSONAL_CONFIRMED",
        published_by=actor_id,
    )
    session.add(record)
    draft.draft_status = "PUBLISHED"
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="ProjectSummaryRecord",
        aggregate_id=record.id,
        action="PROJECT_SUMMARY_PERSONALLY_CONFIRMED",
        correlation_id=correlation_id,
        payload={"draftId": str(draft.id), "healthSnapshotId": str(snapshot.id), "recordHash": record.record_hash},
    )
    return record


def list_project_summary_records(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[ProjectSummaryRecord]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return (
        session.query(ProjectSummaryRecord)
        .filter_by(project_id=project_id)
        .order_by(ProjectSummaryRecord.published_at.desc())
        .limit(limit)
        .all()
    )
