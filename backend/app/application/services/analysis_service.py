import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.domain.enums import AssessmentProfile, ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import (
    AnalysisJob,
    AnalysisRun,
    AnalysisRunManifest,
    AnalysisCoverage,
    CodeReviewFinding,
    CodeReviewFindingChallenge,
    InputSnapshot,
    InputSnapshotClaim,
    InputSnapshotGit,
    InputSnapshotPlan,
    Claim,
    ClaimEvidenceLink,
    EvidenceItem,
    HumanVerificationDecision,
    RiskFinding,
    VerificationResult,
    VerificationCycle,
    VerificationTask,
)
from app.application.services.orchestration_service import freeze_run_orchestration, orchestration_fingerprint
from app.infrastructure.business_ownership import require_python_verification


_DELIVERY_PROFILE = AssessmentProfile.DELIVERY_VERIFICATION.value

_HUMAN_DECISIONS_BY_STATUS = {
    "SUPPORTED": ("CONFIRM_SUPPORT", "CONFIRM_PARTIAL", "CONFIRM_INSUFFICIENT"),
    "PARTIALLY_SUPPORTED": ("CONFIRM_SUPPORT", "CONFIRM_PARTIAL", "CONFIRM_INSUFFICIENT"),
    "NOT_PROVEN": ("CONFIRM_INSUFFICIENT", "RETURN_FOR_EVIDENCE"),
    "NOT_ANALYZED": ("RETURN_FOR_EVIDENCE",),
    "CONFLICTING": ("RETURN_FOR_EVIDENCE",),
    "CONFLICT": ("RETURN_FOR_EVIDENCE",),
}


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


def _human_decision_projection(item: HumanVerificationDecision | None) -> dict | None:
    if item is None:
        return None
    return {
        "id": str(item.id),
        "decision": item.decision,
        "note": item.note,
        "actorId": str(item.actor_id),
        "createdAt": item.created_at.isoformat() if item.created_at else None,
    }


def start_analysis_run(
    session: Session, *, snapshot_id: UUID, actor_id: UUID, idempotency_key: str, correlation_id: str
) -> AnalysisRun:
    snapshot = session.get(InputSnapshot, snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if snapshot is None or task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "输入快照不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if snapshot.purpose != "FORMAL":
        raise DomainError("INPUT_STALE", "只有正式输入快照可以启动分析")
    if snapshot.assessment_profile != _DELIVERY_PROFILE:
        raise DomainError("ASSESSMENT_PROFILE_NOT_ENABLED", f"运行配置 {snapshot.assessment_profile} 尚未开放执行")
    require_python_verification(session)
    git_binding = session.query(InputSnapshotGit).filter_by(snapshot_id=snapshot.id).one_or_none()
    if git_binding is None:
        raise DomainError("INPUT_STALE", "交付核验必须包含冻结 Git 范围")
    from app.infrastructure.persistence.models import GitSnapshot
    git_snapshot = session.get(GitSnapshot, git_binding.git_snapshot_id)
    if git_snapshot is None or not git_snapshot.diff_artifact_id or not git_snapshot.code_change_artifact_id:
        raise DomainError("GIT_ARTIFACT_MISSING", "交付核验的 Git 输入不具备可回放制品")
    if not session.query(InputSnapshotClaim).filter_by(snapshot_id=snapshot.id).first():
        raise DomainError("CLAIMS_NOT_CONFIRMED", "正式输入快照缺少已确认的交付主张，不能启动交付核验")
    if cycle.business_status not in {"DRAFT", "NEEDS_EVIDENCE", "NEEDS_CONFIRMATION"}:
        raise DomainError("STATE_CONFLICT", "当前轮次状态不允许启动新的分析运行")
    existing_job = session.query(AnalysisJob).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing_job is not None:
        return session.get(AnalysisRun, existing_job.run_id)
    settings = get_settings()
    config = {
        "assessmentProfile": snapshot.assessment_profile,
        "workflow": "delivery-context-v2",
        "rules": "delivery-verdict-v2",
        "prompt": "code-context-v2",
        "schema": "delivery-context-v2",
        "generationProvider": settings.generation_provider,
        "generationModel": settings.generation_model,
        "embeddingProvider": settings.embedding_provider,
        "embeddingModel": settings.embedding_model,
        "orchestrationHash": orchestration_fingerprint(session, task=task, actor_id=actor_id),
    }
    plan_binding = session.get(InputSnapshotPlan, snapshot.id)
    if plan_binding:
        config["planVersionRef"] = str(plan_binding.plan_version_id)
        config["planContentHash"] = plan_binding.plan_content_hash
        config["planBaselineHash"] = plan_binding.selection_hash
    config_hash = f"sha256:{hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}"
    existing_run = session.query(AnalysisRun).filter(AnalysisRun.snapshot_id == snapshot.id, AnalysisRun.analysis_config_hash == config_hash, AnalysisRun.run_status.in_(("QUEUED", "RUNNING"))).one_or_none()
    if existing_run is not None:
        return existing_run
    manifest_hash = f"sha256:{hashlib.sha256(json.dumps({**config, 'snapshot': snapshot.snapshot_hash}, sort_keys=True).encode()).hexdigest()}"
    run = AnalysisRun(snapshot_id=snapshot.id, assessment_profile=snapshot.assessment_profile, analysis_config_hash=config_hash, manifest_hash=manifest_hash, checkpoint_ns=f"run-{uuid4()}")
    if plan_binding:
        run.plan_version_id = plan_binding.plan_version_id
        run.plan_baseline_hash = plan_binding.selection_hash
    session.add(run)
    session.flush()
    orchestration_snapshot = freeze_run_orchestration(session, run=run, task=task, actor_id=actor_id)
    if config["orchestrationHash"] != orchestration_snapshot.content_hash:
        raise DomainError("ORCHESTRATION_CHANGED", "启动过程中编排模板发生变化，请重新发起分析")
    session.add(orchestration_snapshot)
    session.add(AnalysisRunManifest(run_id=run.id, workflow_version="delivery-context-v2", rule_set_version="delivery-verdict-v2", prompt_set_version="code-review-v1+challenge-v1+link-v2", generation_model=config["generationModel"], embedding_model=config["embeddingModel"], schema_version="delivery-context-v2"))
    session.add(AnalysisJob(run_id=run.id, idempotency_key=idempotency_key, max_attempts=settings.job_max_attempts))
    cycle.business_status = "ANALYZING"
    cycle.active_run_id = run.id
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="AnalysisRun", aggregate_id=run.id, action="ANALYSIS_RUN_QUEUED", correlation_id=correlation_id, payload={"snapshotHash": snapshot.snapshot_hash, "orchestrationHash": orchestration_snapshot.content_hash, "assessmentProfile": snapshot.assessment_profile})
    return run


def request_cancel(session: Session, *, run_id: UUID, actor_id: UUID, correlation_id: str) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "分析运行不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if run.assessment_profile == _DELIVERY_PROFILE:
        require_python_verification(session)
    if run.run_status not in {"QUEUED", "RUNNING"}:
        raise DomainError("STATE_CONFLICT", "当前运行不可取消")
    run.cancel_requested_at = datetime.now(UTC)
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="AnalysisRun", aggregate_id=run.id, action="ANALYSIS_CANCEL_REQUESTED", correlation_id=correlation_id)
    return run


def get_analysis_run(session: Session, *, run_id: UUID, actor_id: UUID) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id) if run else None
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "分析运行不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return run


def get_latest_task_analysis_run(session: Session, *, task_id: UUID, actor_id: UUID) -> AnalysisRun:
    task = session.get(VerificationTask, task_id)
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    run = (
        session.query(AnalysisRun)
        .join(InputSnapshot, InputSnapshot.id == AnalysisRun.snapshot_id)
        .join(VerificationCycle, VerificationCycle.id == InputSnapshot.cycle_id)
        .filter(VerificationCycle.task_id == task.id)
        .order_by(AnalysisRun.created_at.desc())
        .first()
    )
    if run is None:
        raise DomainError("RESOURCE_NOT_FOUND", "该核验任务尚未创建分析运行")
    return run


def get_analysis_results(session: Session, *, run_id: UUID, actor_id: UUID) -> list[dict]:
    """Read model for the workbench; every returned citation stays in the run snapshot."""
    run = get_analysis_run(session, run_id=run_id, actor_id=actor_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id)
    results = (
        session.query(VerificationResult, Claim)
        .join(Claim, Claim.id == VerificationResult.claim_id)
        .filter(VerificationResult.analysis_run_id == run.id)
        .order_by(Claim.claim_key)
        .all()
    )
    decisions = _latest_human_decisions(session, result_ids=[result.id for result, _ in results])
    items: list[dict] = []
    for result, claim in results:
        evidence_ids = [UUID(item) for item in result.evidence_ids]
        evidence = (
            session.query(EvidenceItem)
            .filter(
                EvidenceItem.id.in_(evidence_ids),
                EvidenceItem.snapshot_id == snapshot.id,
                EvidenceItem.source_type != "TOOL",
                EvidenceItem.evidence_kind != "HTTP_QUERY",
            )
            .all()
            if evidence_ids
            else []
        )
        risks = session.query(RiskFinding).filter_by(analysis_run_id=run.id, claim_id=claim.id).all()
        assessments = (
            session.query(ClaimEvidenceLink)
            .filter(
                ClaimEvidenceLink.claim_id == claim.id,
                ClaimEvidenceLink.evidence_id.in_([item.id for item in evidence]),
                ClaimEvidenceLink.produced_by.in_(["MODEL", "DETERMINISTIC", "HUMAN"]),
            )
            .order_by(ClaimEvidenceLink.id)
            .all()
            if evidence else []
        )
        items.append({
            "id": result.id,
            "claim_id": claim.id,
            "claim_key": claim.claim_key,
            "claim_text": claim.text,
            "status": result.status,
            "reason": result.reason,
            "requires_human_confirmation": result.requires_human_confirmation,
            "human_decision": _human_decision_projection(decisions.get(result.id)),
            "allowed_human_decisions": list(_HUMAN_DECISIONS_BY_STATUS.get(result.status, ())),
            "evidence_assessments": [
                {"evidenceId": str(link.evidence_id), "relation": link.relation,
                 "reason": link.reason, "producedBy": link.produced_by}
                for link in assessments
            ],
            "evidence": [
                {
                    "id": str(item.id),
                    "sourceType": item.source_type,
                    "excerpt": item.excerpt_safe,
                    "locator": item.locator,
                    "precision": item.locator_precision,
                }
                for item in evidence
            ],
            "risks": [
                {
                    "id": str(item.id),
                    "severity": item.severity,
                    "category": item.category,
                    "findingKind": item.finding_kind,
                    "recommendation": item.recommendation,
                }
                for item in risks
            ],
        })
    return items


def record_human_verification_decision(
    session: Session,
    *,
    run_id: UUID,
    result_id: UUID,
    decision: str,
    note: str,
    actor_id: UUID,
    correlation_id: str,
) -> dict:
    """Append a human adjudication without mutating the system-generated result."""
    from app.infrastructure.business_ownership import require_python_reports

    require_python_reports(session)
    run = get_analysis_run(session, run_id=run_id, actor_id=actor_id)
    snapshot = session.get(InputSnapshot, run.snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    result = session.query(VerificationResult).filter_by(id=result_id, analysis_run_id=run.id).one_or_none()
    if task is None or result is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验结论不存在或不属于当前运行")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if run.run_status not in {"SUCCEEDED", "PARTIALLY_COMPLETED"}:
        raise DomainError("STATE_CONFLICT", "仅已结束的分析运行可以进行人工裁决")
    if cycle.business_status in {"PUBLISHED", "PENDING_REVIEW", "APPROVED"}:
        raise DomainError("STATE_CONFLICT", "报告已进入审核或发布阶段，不能修改本轮人工裁决")
    allowed = _HUMAN_DECISIONS_BY_STATUS.get(result.status, ())
    if decision not in allowed:
        raise DomainError("INPUT_INVALID", "该系统结论不允许采用此人工裁决")
    clean_note = note.strip()
    if decision == "RETURN_FOR_EVIDENCE" and not clean_note:
        raise DomainError("INPUT_INVALID", "退回补证时必须说明需要补充的内容")
    previous = _latest_human_decisions(session, result_ids=[result.id]).get(result.id)
    recorded = HumanVerificationDecision(
        result_id=result.id,
        decision=decision,
        note=clean_note,
        actor_id=actor_id,
        supersedes_decision_id=previous.id if previous else None,
    )
    session.add(recorded)
    session.flush()
    from app.application.services.report_service import refresh_draft_human_decisions

    refresh_draft_human_decisions(session, run_id=run.id)
    append_audit_event(
        session,
        project_id=task.project_id,
        actor_id=actor_id,
        aggregate_type="HumanVerificationDecision",
        aggregate_id=recorded.id,
        action="HUMAN_VERIFICATION_DECIDED",
        correlation_id=correlation_id,
        payload={"runId": str(run.id), "resultId": str(result.id), "decision": decision},
    )
    return _human_decision_projection(recorded) or {}


def get_code_review(session: Session, *, run_id: UUID, actor_id: UUID) -> dict:
    run = get_analysis_run(session, run_id=run_id, actor_id=actor_id)
    binding = session.query(InputSnapshotGit).filter_by(snapshot_id=run.snapshot_id).one_or_none()
    findings = session.query(CodeReviewFinding).filter_by(analysis_run_id=run.id).order_by(CodeReviewFinding.created_at).all()
    challenges = session.query(CodeReviewFindingChallenge).filter_by(analysis_run_id=run.id).all()
    challenge_by_finding = {item.finding_id: item for item in challenges}
    coverage = (
        session.query(AnalysisCoverage)
        .filter_by(analysis_run_id=run.id)
        .filter(AnalysisCoverage.scope_kind.in_(("GIT_CAPTURE", "CODE_REVIEW", "FINDING_CHALLENGE", "STANDARD_VERIFICATION", "CONTEXT_SUPPLEMENT")))
        .order_by(AnalysisCoverage.id)
        .all()
    )
    return {
        "gitSnapshotId": str(binding.git_snapshot_id) if binding else None,
        "findings": [
            {
                "id": str(item.id),
                "claimId": str(item.claim_id) if item.claim_id else None,
                "evidenceId": str(item.evidence_id),
                "severity": item.severity,
                "findingKind": item.finding_kind,
                "title": item.title,
                "problem": item.problem,
                "triggerScenario": item.trigger_scenario,
                "recommendation": item.recommendation,
                "confidence": item.confidence,
                "requiresHumanConfirmation": item.requires_human_confirmation,
                "challenge": (
                    {
                        "state": "COMPLETED",
                        "verdict": challenge_by_finding[item.id].verdict,
                        "reason": challenge_by_finding[item.id].reason,
                        "evidenceIds": challenge_by_finding[item.id].evidence_ids,
                    }
                    if item.id in challenge_by_finding
                    else {"state": "NOT_STARTED", "verdict": None, "reason": None, "evidenceIds": []}
                ),
            }
            for item in findings
        ],
        "coverage": [
            {"scopeKind": item.scope_kind, "scopeRef": item.scope_ref, "state": item.state, "reasonCode": item.reason_code, "details": item.details}
            for item in coverage
        ],
    }
