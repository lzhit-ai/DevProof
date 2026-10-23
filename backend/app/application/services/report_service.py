from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.application.services.citation_resolver import resolve_citation
from app.domain.enums import AssessmentProfile, ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import ApprovalAction, AnalysisRun, Claim, DeliveryItem, EvidenceItem, HumanVerificationDecision, InputSnapshot, PublishedRecord, ReportItem, ReportVersion, User, VerificationCycle, VerificationResult, VerificationTask
from app.infrastructure.report_renderer import CanonicalJsonReportRenderer
from app.infrastructure.business_ownership import require_python_reports


_DELIVERY_PROFILE = AssessmentProfile.DELIVERY_VERIFICATION.value


def _assert_cycle_open_for_report_write(cycle: VerificationCycle) -> None:
    """A published cycle is immutable, including any historical report drafts it contains."""
    if cycle.business_status == "PUBLISHED":
        raise DomainError("STATE_CONFLICT", "核验轮次已发布，历史报告版本不可再修改、提交、审批或发布")


def _locked_cycle_for_report(session: Session, *, report: ReportVersion) -> VerificationCycle:
    """Serialize report transitions at the verification-cycle boundary."""
    cycle = (
        session.query(VerificationCycle)
        .filter(VerificationCycle.id == report.cycle_id)
        .with_for_update()
        .one_or_none()
    )
    if cycle is None:
        raise DomainError("RESOURCE_NOT_FOUND", "报告所属核验轮次不存在")
    return cycle


def _assert_delivery_report_run(*, run: AnalysisRun, snapshot: InputSnapshot) -> None:
    if run.assessment_profile != _DELIVERY_PROFILE or snapshot.assessment_profile != _DELIVERY_PROFILE:
        raise DomainError("ASSESSMENT_PROFILE_NOT_ENABLED", "当前仅交付核验运行支持报告草稿、审批和正式记录")


def _content_hash(
    *,
    results: list[VerificationResult],
    editorial_note: str,
    dispositions: dict[str, str | None],
    human_decisions: dict[str, dict] | None = None,
) -> str:
    return CanonicalJsonReportRenderer().render(
        results=[
            {
                "id": str(item.id),
                "status": item.status,
                "evidence": item.evidence_ids,
                "humanDecision": (human_decisions or {}).get(str(item.id)),
            }
            for item in results
        ],
        editorial_note=editorial_note,
        dispositions=dispositions,
    ).content_hash


def _latest_human_decisions(session: Session, *, result_ids: list[UUID]) -> dict[UUID, HumanVerificationDecision]:
    if not result_ids:
        return {}
    rows = (
        session.query(HumanVerificationDecision)
        .filter(HumanVerificationDecision.result_id.in_(result_ids))
        .order_by(HumanVerificationDecision.result_id, HumanVerificationDecision.created_at.desc(), HumanVerificationDecision.id.desc())
        .all()
    )
    latest: dict[UUID, HumanVerificationDecision] = {}
    for item in rows:
        latest.setdefault(item.result_id, item)
    return latest


def _decision_snapshot(item: HumanVerificationDecision | None) -> dict | None:
    if item is None:
        return None
    return {
        "id": str(item.id),
        "decision": item.decision,
        "note": item.note,
        "actorId": str(item.actor_id),
        "createdAt": item.created_at.isoformat() if item.created_at else None,
    }


def _result_snapshot(result: VerificationResult, decision: HumanVerificationDecision | None) -> dict:
    return {
        "status": result.status,
        "reason": result.reason,
        "humanDecision": _decision_snapshot(decision),
    }


def _assert_all_required_decisions(session: Session, *, run_id: UUID) -> None:
    results = session.query(VerificationResult).filter_by(analysis_run_id=run_id).all()
    pending = [item.id for item in results if item.requires_human_confirmation]
    latest = _latest_human_decisions(session, result_ids=pending)
    unresolved = [str(result_id) for result_id in pending if result_id not in latest]
    if unresolved:
        raise DomainError("HUMAN_DECISIONS_REQUIRED", "仍有待人工确认的交付结论；请逐项完成裁决后再提交报告")


def refresh_draft_human_decisions(session: Session, *, run_id: UUID) -> None:
    """Refresh mutable draft snapshots after a new append-only human decision."""
    require_python_reports(session)
    reports = session.query(ReportVersion).filter_by(run_id=run_id, status="DRAFT").all()
    if not reports:
        return
    results = session.query(VerificationResult).filter_by(analysis_run_id=run_id).all()
    decisions = _latest_human_decisions(session, result_ids=[item.id for item in results])
    decision_payloads = {str(result_id): _decision_snapshot(item) for result_id, item in decisions.items()}
    by_id = {item.id: item for item in results}
    for report in reports:
        items = session.query(ReportItem).filter_by(report_version_id=report.id).all()
        for item in items:
            result = by_id.get(item.result_id)
            if result is not None:
                item.result_snapshot = _result_snapshot(result, decisions.get(result.id))
        report.content_hash = _content_hash(
            results=results,
            editorial_note=report.editorial_note,
            dispositions={str(item.id): item.disposition for item in items},
            human_decisions=decision_payloads,
        )
        report.version += 1


def _decision_payloads_from_items(items: list[ReportItem]) -> dict[str, dict]:
    return {
        str(item.result_id): item.result_snapshot["humanDecision"]
        for item in items
        if item.result_snapshot.get("humanDecision")
    }


def _draft_cycle_status(results: list[VerificationResult]) -> str:
    if not results or all(item.status in {"NOT_PROVEN", "NOT_ANALYZED"} for item in results):
        return "NEEDS_EVIDENCE"
    if any(item.requires_human_confirmation for item in results):
        return "NEEDS_CONFIRMATION"
    return "DRAFT_READY"


def _assert_publishable_citations(session: Session, *, report: ReportVersion, actor_id: UUID) -> None:
    """Published report references are re-resolved against the immutable run snapshot."""
    run = session.get(AnalysisRun, report.run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    if snapshot is None or snapshot.snapshot_hash != report.snapshot_hash:
        raise DomainError("INPUT_STALE", "报告绑定的输入快照不存在或哈希不一致")
    for item in session.query(ReportItem).filter_by(report_version_id=report.id).all():
        for evidence_id in item.citation_snapshot.get("evidenceIds", []):
            resolve_citation(session, evidence_id=UUID(str(evidence_id)), snapshot_id=snapshot.id, actor_id=actor_id)


def _formal_citation_ids(session: Session, *, snapshot_id: UUID, evidence_ids: list) -> list[str]:
    """A runtime tool response may never be copied into a report citation snapshot."""

    requested = [UUID(str(item)) for item in evidence_ids]
    if not requested:
        return []
    allowed = {
        str(item.id)
        for item in session.query(EvidenceItem)
        .filter(
            EvidenceItem.id.in_(requested),
            EvidenceItem.snapshot_id == snapshot_id,
            EvidenceItem.source_type != "TOOL",
            EvidenceItem.evidence_kind != "HTTP_QUERY",
        )
        .all()
    }
    return [str(item) for item in evidence_ids if str(item) in allowed]


def _delivery_item_verification_status(session: Session, *, report: ReportVersion) -> str:
    statuses = []
    for item in session.query(ReportItem).filter_by(report_version_id=report.id).all():
        decision = (item.result_snapshot.get("humanDecision") or {}).get("decision")
        statuses.append(
            "CONFIRMED" if decision == "CONFIRM_SUPPORT"
            else "PARTIALLY_SUPPORTED" if decision == "CONFIRM_PARTIAL"
            else "INSUFFICIENT_EVIDENCE" if decision in {"CONFIRM_INSUFFICIENT", "RETURN_FOR_EVIDENCE"}
            else item.result_snapshot.get("status")
        )
    if statuses and all(status in {"SUPPORTED", "CONFIRMED"} for status in statuses):
        return "CONFIRMED"
    if any(status in {"CONFLICT", "CONFLICTING"} for status in statuses):
        return "CONFLICT"
    if not statuses or all(status in {"INSUFFICIENT_EVIDENCE", "NOT_PROVEN", "NOT_ANALYZED"} for status in statuses):
        return "INSUFFICIENT_EVIDENCE"
    return "PARTIALLY_SUPPORTED"


def _report_projection(session: Session, *, report: ReportVersion, cycle: VerificationCycle, task: VerificationTask) -> dict:
    latest_approval = (
        session.query(ApprovalAction)
        .filter_by(report_version_id=report.id)
        .order_by(ApprovalAction.created_at.desc())
        .first()
    )
    submitter = session.get(User, report.submitted_by) if report.submitted_by else None
    return {
        "id": report.id,
        "cycle_id": cycle.id,
        "sequence_no": report.sequence_no,
        "status": report.status,
        "record_type": report.record_type,
        "content_hash": report.content_hash,
        "version": report.version,
        "snapshot_hash": report.snapshot_hash,
        "editorial_note": report.editorial_note,
        "submitted_at": report.submitted_at,
        "task_id": task.id,
        "task_title": task.title,
        "requirement_key": task.requirement_key,
        "delivery_item_id": task.delivery_item_id,
        "submitted_by_name": submitter.display_name if submitter else None,
        "latest_approval_action": latest_approval.action if latest_approval else None,
        "latest_approval_reason": latest_approval.reason if latest_approval else None,
        "latest_approval_at": latest_approval.created_at if latest_approval else None,
    }


def list_project_reports(
    session: Session, *, project_id: UUID, actor_id: UUID, report_status: str | None = None, limit: int = 100
) -> list[dict]:
    """List project-scoped report versions for the review workbench."""

    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    query = (
        session.query(ReportVersion, VerificationCycle, VerificationTask)
        .join(VerificationCycle, VerificationCycle.id == ReportVersion.cycle_id)
        .join(VerificationTask, VerificationTask.id == VerificationCycle.task_id)
        .filter(VerificationTask.project_id == project_id)
    )
    if report_status:
        query = query.filter(ReportVersion.status == report_status)
    rows = (
        query.order_by(ReportVersion.submitted_at.desc().nullslast(), ReportVersion.sequence_no.desc())
        .limit(limit)
        .all()
    )
    return [_report_projection(session, report=report, cycle=cycle, task=task) for report, cycle, task in rows]


def get_project_report(session: Session, *, project_id: UUID, report_id: UUID, actor_id: UUID) -> dict:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    row = (
        session.query(ReportVersion, VerificationCycle, VerificationTask)
        .join(VerificationCycle, VerificationCycle.id == ReportVersion.cycle_id)
        .join(VerificationTask, VerificationTask.id == VerificationCycle.task_id)
        .filter(ReportVersion.id == report_id, VerificationTask.project_id == project_id)
        .one_or_none()
    )
    if row is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验报告不存在或不属于当前项目")
    report, cycle, task = row
    return _report_projection(session, report=report, cycle=cycle, task=task)


def get_report_content(session: Session, *, project_id: UUID, report_id: UUID, actor_id: UUID) -> dict:
    """Return the stored draft body rather than recomputing a view from live results."""
    projection = get_project_report(session, project_id=project_id, report_id=report_id, actor_id=actor_id)
    report = session.get(ReportVersion, report_id)
    run = session.get(AnalysisRun, report.run_id) if report else None
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    if report is None or snapshot is None:
        raise DomainError("INPUT_STALE", "报告绑定的正式输入快照不存在")
    rows = (
        session.query(ReportItem, Claim)
        .join(VerificationResult, VerificationResult.id == ReportItem.result_id)
        .join(Claim, Claim.id == VerificationResult.claim_id)
        .filter(ReportItem.report_version_id == report.id)
        .order_by(ReportItem.display_order)
        .all()
    )
    evidence_ids = [UUID(str(evidence_id)) for item, _ in rows for evidence_id in item.citation_snapshot.get("evidenceIds", [])]
    evidence_by_id = {
        str(item.id): item
        for item in session.query(EvidenceItem)
        .filter(EvidenceItem.id.in_(evidence_ids), EvidenceItem.snapshot_id == snapshot.id)
        .all()
    } if evidence_ids else {}
    projection["items"] = [
        {
            "id": str(item.id),
            "claimText": claim.text,
            "result": item.result_snapshot,
            "disposition": item.disposition,
            "citations": [
                {
                    "id": str(evidence_id),
                    "sourceType": evidence_by_id[str(evidence_id)].source_type,
                    "excerpt": evidence_by_id[str(evidence_id)].excerpt_safe,
                    "locator": evidence_by_id[str(evidence_id)].locator,
                }
                for evidence_id in item.citation_snapshot.get("evidenceIds", [])
                if str(evidence_id) in evidence_by_id
            ],
        }
        for item, claim in rows
    ]
    from app.application.services.plan_baseline_service import frozen_plan_baseline

    baseline = frozen_plan_baseline(session, snapshot_id=snapshot.id)
    if baseline:
        projection["planBaseline"] = baseline
    return projection


def _published_record_projection(
    session: Session, *, record: PublishedRecord, report: ReportVersion, cycle: VerificationCycle, task: VerificationTask
) -> dict:
    latest_approval = (
        session.query(ApprovalAction)
        .filter_by(report_version_id=report.id)
        .order_by(ApprovalAction.created_at.desc())
        .first()
    )
    publisher = session.get(User, record.published_by)
    approver = session.get(User, latest_approval.actor_id) if latest_approval else None
    return {
        "id": record.id,
        "project_id": task.project_id,
        "task_id": task.id,
        "task_title": task.title,
        "requirement_key": task.requirement_key,
        "delivery_item_id": task.delivery_item_id,
        "cycle_id": cycle.id,
        "report_version_id": report.id,
        "report_sequence_no": report.sequence_no,
        "report_status": report.status,
        "snapshot_hash": report.snapshot_hash,
        "record_type": record.record_type,
        "record_no": record.record_no,
        "record_hash": record.record_hash,
        "published_by_name": publisher.display_name if publisher else None,
        "published_at": record.published_at,
        "approval_action": latest_approval.action if latest_approval else None,
        "approval_reason": latest_approval.reason if latest_approval else None,
        "approval_by_name": approver.display_name if approver else None,
        "approval_at": latest_approval.created_at if latest_approval else None,
    }


def list_published_records(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 100) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    rows = (
        session.query(PublishedRecord, ReportVersion, VerificationCycle, VerificationTask)
        .join(ReportVersion, ReportVersion.id == PublishedRecord.report_version_id)
        .join(VerificationCycle, VerificationCycle.id == PublishedRecord.cycle_id)
        .join(VerificationTask, VerificationTask.id == PublishedRecord.task_id)
        .filter(VerificationTask.project_id == project_id)
        .order_by(PublishedRecord.published_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _published_record_projection(session, record=record, report=report, cycle=cycle, task=task)
        for record, report, cycle, task in rows
    ]


def get_published_record(session: Session, *, project_id: UUID, record_id: UUID, actor_id: UUID) -> dict:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    row = (
        session.query(PublishedRecord, ReportVersion, VerificationCycle, VerificationTask)
        .join(ReportVersion, ReportVersion.id == PublishedRecord.report_version_id)
        .join(VerificationCycle, VerificationCycle.id == PublishedRecord.cycle_id)
        .join(VerificationTask, VerificationTask.id == PublishedRecord.task_id)
        .filter(PublishedRecord.id == record_id, VerificationTask.project_id == project_id)
        .one_or_none()
    )
    if row is None:
        raise DomainError("RESOURCE_NOT_FOUND", "正式交付记录不存在或不属于当前项目")
    record, report, cycle, task = row
    return _published_record_projection(session, record=record, report=report, cycle=cycle, task=task)


def create_draft(session: Session, *, cycle_id: UUID, run_id: UUID, actor_id: UUID, correlation_id: str) -> ReportVersion:
    require_python_reports(session)
    cycle = session.get(VerificationCycle, cycle_id); run = session.get(AnalysisRun, run_id); task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or run is None or run.run_status not in {"SUCCEEDED", "PARTIALLY_COMPLETED"}:
        raise DomainError("STATE_CONFLICT", "仅终态分析运行可生成报告草稿")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    snapshot = session.get(InputSnapshot, run.snapshot_id)
    if snapshot is None or snapshot.cycle_id != cycle.id or snapshot.purpose != "FORMAL":
        raise DomainError("INPUT_STALE", "报告草稿必须绑定当前轮次的正式输入快照")
    _assert_delivery_report_run(run=run, snapshot=snapshot)
    results = session.query(VerificationResult).filter_by(analysis_run_id=run.id).all()
    decisions = _latest_human_decisions(session, result_ids=[item.id for item in results])
    decision_payloads = {str(result_id): _decision_snapshot(item) for result_id, item in decisions.items()}
    content_hash = _content_hash(results=results, editorial_note="", dispositions={}, human_decisions=decision_payloads)
    next_no = session.query(func.coalesce(func.max(ReportVersion.sequence_no), 0)).filter_by(cycle_id=cycle.id).scalar() + 1
    report = ReportVersion(cycle_id=cycle.id, sequence_no=next_no, status="DRAFT", record_type=run.assessment_profile, content_hash=content_hash, snapshot_hash=snapshot.snapshot_hash, run_id=run.id)
    session.add(report); session.flush()
    for order, result in enumerate(results, start=1):
        session.add(ReportItem(report_version_id=report.id, result_id=result.id, display_order=order, result_snapshot={"status": result.status, "reason": result.reason}, citation_snapshot={"evidenceIds": _formal_citation_ids(session, snapshot_id=snapshot.id, evidence_ids=result.evidence_ids)}))
    for item in session.query(ReportItem).filter_by(report_version_id=report.id).all():
        item.result_snapshot = _result_snapshot(
            next(result for result in results if result.id == item.result_id),
            decisions.get(item.result_id),
        )
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_DRAFT_CREATED", correlation_id=correlation_id)
    return report


def create_automatic_draft(session: Session, *, run_id: UUID, correlation_id: str) -> ReportVersion:
    """Create the enabled report-draft block's output without bypassing review or publish gates."""
    require_python_reports(session)
    run = session.get(AnalysisRun, run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or run is None or snapshot is None:
        raise DomainError("RESOURCE_NOT_FOUND", "分析运行或其正式输入快照不存在")
    _assert_cycle_open_for_report_write(cycle)
    if run.run_status not in {"SUCCEEDED", "PARTIALLY_COMPLETED"} or snapshot.purpose != "FORMAL":
        raise DomainError("STATE_CONFLICT", "仅终态正式分析运行可自动生成报告草稿")
    _assert_delivery_report_run(run=run, snapshot=snapshot)
    existing = session.query(ReportVersion).filter_by(run_id=run.id).order_by(ReportVersion.sequence_no).first()
    if existing is not None:
        return existing
    results = session.query(VerificationResult).filter_by(analysis_run_id=run.id).all()
    decisions = _latest_human_decisions(session, result_ids=[item.id for item in results])
    decision_payloads = {str(result_id): _decision_snapshot(item) for result_id, item in decisions.items()}
    content_hash = _content_hash(results=results, editorial_note="", dispositions={}, human_decisions=decision_payloads)
    next_no = session.query(func.coalesce(func.max(ReportVersion.sequence_no), 0)).filter_by(cycle_id=cycle.id).scalar() + 1
    report = ReportVersion(
        cycle_id=cycle.id,
        sequence_no=next_no,
        status="DRAFT",
        record_type=run.assessment_profile,
        content_hash=content_hash,
        snapshot_hash=snapshot.snapshot_hash,
        run_id=run.id,
    )
    session.add(report)
    session.flush()
    for order, result in enumerate(results, start=1):
        session.add(ReportItem(
            report_version_id=report.id,
            result_id=result.id,
            display_order=order,
            result_snapshot={"status": result.status, "reason": result.reason},
            citation_snapshot={"evidenceIds": _formal_citation_ids(session, snapshot_id=snapshot.id, evidence_ids=result.evidence_ids)},
        ))
    for item in session.query(ReportItem).filter_by(report_version_id=report.id).all():
        item.result_snapshot = _result_snapshot(
            next(result for result in results if result.id == item.result_id),
            decisions.get(item.result_id),
        )
    append_audit_event(
        session,
        project_id=task.project_id,
        actor_id=task.created_by,
        aggregate_type="ReportVersion",
        aggregate_id=report.id,
        action="REPORT_DRAFT_CREATED",
        correlation_id=correlation_id,
        payload={"createdBy": "REPORT_DRAFT_BLOCK", "runId": str(run.id)},
    )
    return report


def update_draft(
    session: Session,
    *,
    report_id: UUID,
    editorial_note: str,
    item_dispositions: dict[UUID, str | None],
    expected_version: int,
    actor_id: UUID,
    correlation_id: str,
) -> ReportVersion:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id)
    cycle = _locked_cycle_for_report(session, report=report) if report else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "DRAFT":
        raise DomainError("STATE_CONFLICT", "仅草稿报告可编辑")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if report.version != expected_version:
        raise DomainError("VERSION_CONFLICT", "报告草稿已被其他操作更新，请重新读取后再保存")
    items = session.query(ReportItem).filter_by(report_version_id=report.id).all()
    item_by_id = {item.id: item for item in items}
    if not set(item_dispositions).issubset(item_by_id):
        raise DomainError("INPUT_INVALID", "处置项不属于当前报告版本")
    for item_id, disposition in item_dispositions.items():
        item_by_id[item_id].disposition = disposition
    results = session.query(VerificationResult).filter_by(analysis_run_id=report.run_id).all()
    report.editorial_note = editorial_note
    report.content_hash = _content_hash(
        results=results,
        editorial_note=editorial_note,
        dispositions={str(item.id): item.disposition for item in items},
        human_decisions=_decision_payloads_from_items(items),
    )
    report.version += 1
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_DRAFT_UPDATED", correlation_id=correlation_id, payload={"version": report.version})
    return report


def submit_for_review(session: Session, *, report_id: UUID, actor_id: UUID, correlation_id: str) -> ReportVersion:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id); cycle = _locked_cycle_for_report(session, report=report) if report else None; task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "DRAFT": raise DomainError("STATE_CONFLICT", "仅草稿可提交审核")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    _assert_all_required_decisions(session, run_id=report.run_id)
    report.status = "SUBMITTED"; report.submitted_by = actor_id; report.submitted_at = datetime.now(UTC)
    cycle.business_status = "PENDING_REVIEW"
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_SUBMITTED", correlation_id=correlation_id)
    return report


def approve(session: Session, *, report_id: UUID, actor_id: UUID, reason: str, correlation_id: str) -> ReportVersion:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id); cycle = _locked_cycle_for_report(session, report=report) if report else None; task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "SUBMITTED": raise DomainError("STATE_CONFLICT", "仅已提交报告可批准")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.REVIEWER, ProjectRole.ADMIN})
    if report.submitted_by == actor_id: raise DomainError("AUTH_FORBIDDEN", "提交者不能审批自己的报告")
    report.status = "APPROVED"; cycle.business_status = "APPROVED"
    session.add(ApprovalAction(report_version_id=report.id, action="APPROVED", actor_id=actor_id, reason=reason, report_hash=report.content_hash, snapshot_hash=report.snapshot_hash, run_id=report.run_id))
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_APPROVED", correlation_id=correlation_id)
    return report


def request_changes(session: Session, *, report_id: UUID, actor_id: UUID, reason: str, correlation_id: str) -> ReportVersion:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id); cycle = _locked_cycle_for_report(session, report=report) if report else None; task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "SUBMITTED": raise DomainError("STATE_CONFLICT", "仅已提交报告可要求补证")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.REVIEWER, ProjectRole.ADMIN})
    if report.submitted_by == actor_id: raise DomainError("AUTH_FORBIDDEN", "提交者不能审核自己的报告")
    report.status = "CHANGES_REQUESTED"
    session.add(ApprovalAction(report_version_id=report.id, action="CHANGES_REQUESTED", actor_id=actor_id, reason=reason, report_hash=report.content_hash, snapshot_hash=report.snapshot_hash, run_id=report.run_id))
    next_no = session.query(func.coalesce(func.max(ReportVersion.sequence_no), 0)).filter_by(cycle_id=cycle.id).scalar() + 1
    draft = ReportVersion(cycle_id=cycle.id, sequence_no=next_no, status="DRAFT", parent_report_version_id=report.id, record_type=report.record_type, content_hash=report.content_hash, snapshot_hash=report.snapshot_hash, run_id=report.run_id, editorial_note=report.editorial_note)
    session.add(draft); session.flush()
    for item in session.query(ReportItem).filter_by(report_version_id=report.id).all():
        session.add(ReportItem(report_version_id=draft.id, result_id=item.result_id, display_order=item.display_order, result_snapshot=item.result_snapshot, citation_snapshot=item.citation_snapshot, disposition=item.disposition))
    cycle.business_status = _draft_cycle_status(session.query(VerificationResult).filter_by(analysis_run_id=report.run_id).all())
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_CHANGES_REQUESTED", correlation_id=correlation_id, payload={"newDraftId": str(draft.id)})
    return draft


def reject(session: Session, *, report_id: UUID, actor_id: UUID, reason: str, correlation_id: str) -> ReportVersion:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id); cycle = _locked_cycle_for_report(session, report=report) if report else None; task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "SUBMITTED": raise DomainError("STATE_CONFLICT", "仅已提交报告可驳回")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.REVIEWER, ProjectRole.ADMIN})
    if report.submitted_by == actor_id: raise DomainError("AUTH_FORBIDDEN", "提交者不能审核自己的报告")
    report.status = "REJECTED"; cycle.business_status = "REJECTED"
    session.add(ApprovalAction(report_version_id=report.id, action="REJECTED", actor_id=actor_id, reason=reason, report_hash=report.content_hash, snapshot_hash=report.snapshot_hash, run_id=report.run_id))
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="ReportVersion", aggregate_id=report.id, action="REPORT_REJECTED", correlation_id=correlation_id)
    return report


def publish(session: Session, *, report_id: UUID, actor_id: UUID, correlation_id: str) -> PublishedRecord:
    require_python_reports(session)
    report = session.get(ReportVersion, report_id); cycle = _locked_cycle_for_report(session, report=report) if report else None; task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or report.status != "APPROVED": raise DomainError("STATE_CONFLICT", "仅已批准报告可发布")
    _assert_cycle_open_for_report_write(cycle)
    require_project_role(session, task.project_id, actor_id, {ProjectRole.ADMIN})
    run = session.get(AnalysisRun, report.run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    if run is None or snapshot is None or report.record_type != run.assessment_profile:
        raise DomainError("INPUT_STALE", "正式记录的运行配置与报告不一致")
    _assert_delivery_report_run(run=run, snapshot=snapshot)
    approval = session.query(ApprovalAction).filter_by(
        report_version_id=report.id,
        action="APPROVED",
        report_hash=report.content_hash,
        snapshot_hash=report.snapshot_hash,
        run_id=report.run_id,
    ).order_by(ApprovalAction.created_at.desc()).first()
    if approval is None:
        raise DomainError("STATE_CONFLICT", "批准记录未绑定当前报告哈希、快照哈希和分析运行")
    _assert_publishable_citations(session, report=report, actor_id=actor_id)
    existing = session.query(PublishedRecord).filter_by(report_version_id=report.id).one_or_none()
    if existing: return existing
    record_hash = CanonicalJsonReportRenderer().render(
        results=[{"reportContentHash": report.content_hash, "snapshotHash": report.snapshot_hash}],
        editorial_note="published-record-v1",
        dispositions={},
    ).content_hash
    record = PublishedRecord(task_id=task.id, cycle_id=cycle.id, report_version_id=report.id, record_type=report.record_type, record_no=f"{task.requirement_key}-{cycle.sequence_no}-{report.sequence_no}", record_hash=record_hash, published_by=actor_id)
    from app.application.services.published_body_service import freeze_published_body
    freeze_published_body(session, report=report, project_id=task.project_id, actor_id=actor_id)
    session.add(record); session.flush(); report.status = "PUBLISHED"; cycle.business_status = "PUBLISHED"
    if task.delivery_item_id is not None:
        item = session.get(DeliveryItem, task.delivery_item_id)
        if item is not None and item.project_id == task.project_id:
            item.verification_status = _delivery_item_verification_status(session, report=report)
            append_audit_event(
                session,
                project_id=task.project_id,
                actor_id=actor_id,
                aggregate_type="DeliveryItem",
                aggregate_id=item.id,
                action="DELIVERY_ITEM_VERIFICATION_STATUS_UPDATED",
                correlation_id=correlation_id,
                payload={"verificationStatus": item.verification_status, "publishedRecordId": str(record.id)},
            )
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="PublishedRecord", aggregate_id=record.id, action="REPORT_PUBLISHED", correlation_id=correlation_id)
    return record
