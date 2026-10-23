"""SHA-bound security evidence and baseline records; never an unbounded repository AI scan."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.business_ownership import require_python_security_baselines
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.persistence.models import (
    GitRepository,
    SecurityBaselineRecord,
    SecurityBaselineSnapshot,
    SecurityFinding,
    SecurityScanArtifact,
)


_REQUIRED_SCAN_TYPES = {"SAST", "DEPENDENCY", "SECRET", "CONFIG"}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _repository_for_project(session: Session, *, project_id: UUID, repository_id: UUID) -> GitRepository:
    repository = session.get(GitRepository, repository_id)
    if repository is None or repository.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "Git 仓库不存在或不属于当前项目")
    return repository


def _artifact_for_project(session: Session, *, project_id: UUID, artifact_id: UUID) -> SecurityScanArtifact:
    artifact = session.get(SecurityScanArtifact, artifact_id)
    if artifact is None or artifact.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "安全扫描输入不存在")
    return artifact


def _baseline_for_project(session: Session, *, project_id: UUID, baseline_id: UUID) -> SecurityBaselineSnapshot:
    baseline = session.get(SecurityBaselineSnapshot, baseline_id)
    if baseline is None or baseline.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "安全基线不存在")
    return baseline


def import_security_scan_artifact(
    session: Session,
    *,
    project_id: UUID,
    repository_id: UUID,
    target_sha: str,
    scan_type: str,
    scanner_name: str,
    scanner_version: str,
    rule_set_version: str,
    coverage: dict,
    content: str,
    findings: list[dict],
    actor_id: UUID,
    correlation_id: str,
) -> SecurityScanArtifact:
    require_python_security_baselines(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    _repository_for_project(session, project_id=project_id, repository_id=repository_id)
    if scan_type not in {"SAST", "DEPENDENCY", "SECRET", "CONFIG", "CI"}:
        raise DomainError("INPUT_INVALID", "不支持的安全扫描类型")
    fingerprint_values = [str(item["fingerprint"]).strip() for item in findings]
    if len(fingerprint_values) != len(set(fingerprint_values)):
        raise DomainError("INPUT_INVALID", "同一扫描输入中的风险指纹不能重复")
    encoded = content.encode("utf-8")
    artifact = SecurityScanArtifact(
        project_id=project_id,
        repository_id=repository_id,
        target_sha=target_sha.lower(),
        scan_type=scan_type,
        scanner_name=scanner_name.strip(),
        scanner_version=scanner_version.strip(),
        rule_set_version=rule_set_version.strip(),
        coverage=coverage,
        content_hash=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        artifact_uri="pending://artifact",
        imported_by=actor_id,
    )
    session.add(artifact)
    session.flush()
    artifact.artifact_uri = LocalArtifactStorage(get_settings().artifact_root).write_bytes(
        [str(project_id), "security-scan-artifacts", str(artifact.id)], "scan-result.txt", encoded
    )
    for item in findings:
        session.add(
            SecurityFinding(
                scan_artifact_id=artifact.id,
                fingerprint=str(item["fingerprint"]).strip(),
                severity=str(item["severity"]),
                category=str(item["category"]).strip(),
                title=str(item["title"]).strip(),
                locator=item.get("locator") or {},
            )
        )
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="SecurityScanArtifact",
        aggregate_id=artifact.id,
        action="SECURITY_SCAN_ARTIFACT_IMPORTED",
        correlation_id=correlation_id,
        payload={
            "targetSha": artifact.target_sha,
            "scanType": artifact.scan_type,
            "scanner": artifact.scanner_name,
            "ruleSetVersion": artifact.rule_set_version,
            "contentHash": artifact.content_hash,
            "findingCount": len(findings),
        },
    )
    return artifact


def list_security_scan_artifacts(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 100) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    artifacts = (
        session.query(SecurityScanArtifact)
        .filter_by(project_id=project_id)
        .order_by(SecurityScanArtifact.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "artifact": artifact,
            "finding_count": session.query(SecurityFinding).filter_by(scan_artifact_id=artifact.id).count(),
        }
        for artifact in artifacts
    ]


def list_security_findings(session: Session, *, project_id: UUID, artifact_id: UUID, actor_id: UUID) -> list[SecurityFinding]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    _artifact_for_project(session, project_id=project_id, artifact_id=artifact_id)
    return session.query(SecurityFinding).filter_by(scan_artifact_id=artifact_id).order_by(SecurityFinding.severity.desc(), SecurityFinding.category).all()


def explain_security_scan_artifact(session: Session, *, project_id: UUID, artifact_id: UUID, actor_id: UUID) -> dict:
    """Explain only facts already imported for one SHA-bound scanner artifact."""

    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    artifact = _artifact_for_project(session, project_id=project_id, artifact_id=artifact_id)
    findings = session.query(SecurityFinding).filter_by(scan_artifact_id=artifact.id).all()
    severity_counts = dict(sorted(Counter(finding.severity for finding in findings).items()))
    status_counts = dict(sorted(Counter(finding.finding_status for finding in findings).items()))
    category_counts = dict(sorted(Counter(finding.category for finding in findings).items()))
    high_risk_count = sum(1 for finding in findings if finding.severity in {"CRITICAL", "HIGH"})
    observations = [
        f"该说明只针对 {artifact.scan_type} 工件、目标 SHA {artifact.target_sha[:12]}…、扫描器 {artifact.scanner_name} {artifact.scanner_version} 与规则 {artifact.rule_set_version}。",
        f"导入结果包含 {len(findings)} 条风险，其中高/严重风险 {high_risk_count} 条。",
    ]
    if status_counts.get("REMEDIATION_CLAIMED", 0):
        observations.append("存在“已声明整改”的风险；该状态仍需要同范围的新扫描结果验证，不能描述为已修复。")
    if not findings:
        observations.append("该工件没有导入风险；这不等同于项目安全、代码已全部扫描或发布通过。")
    limitations = [
        "解释只读取这一份已导入扫描工件及其结构化风险，不读取仓库、分支或未导入的扫描输出。",
        "覆盖范围以扫描器声明为准；未纳入的路径、依赖、配置、规则或扫描类型不产生安全结论。",
        "风险处置状态是人工处置事实，不替代后续扫描验证。",
    ]
    return {
        "scope": {
            "artifactId": str(artifact.id),
            "repositoryId": str(artifact.repository_id),
            "targetSha": artifact.target_sha,
            "scanType": artifact.scan_type,
            "scannerName": artifact.scanner_name,
            "scannerVersion": artifact.scanner_version,
            "ruleSetVersion": artifact.rule_set_version,
            "coverage": artifact.coverage,
            "contentHash": artifact.content_hash,
        },
        "summary": {
            "findingCount": len(findings),
            "severityCounts": severity_counts,
            "statusCounts": status_counts,
            "categoryCounts": category_counts,
        },
        "observations": observations,
        "limitations": limitations,
    }


def list_quality_trend(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 300) -> dict:
    """Return comparable sequences of imported scanner results; never infer quality from commits."""

    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    artifacts = (
        session.query(SecurityScanArtifact)
        .filter_by(project_id=project_id)
        .order_by(SecurityScanArtifact.created_at.asc())
        .limit(limit)
        .all()
    )
    grouped: dict[tuple[UUID, str, str, str, str], list[dict]] = {}
    for artifact in artifacts:
        findings = session.query(SecurityFinding).filter_by(scan_artifact_id=artifact.id).all()
        key = (
            artifact.repository_id,
            artifact.scan_type,
            artifact.scanner_name,
            artifact.scanner_version,
            artifact.rule_set_version,
        )
        grouped.setdefault(key, []).append(
            {
                "artifact_id": str(artifact.id),
                "target_sha": artifact.target_sha,
                "created_at": artifact.created_at,
                "content_hash": artifact.content_hash,
                "finding_count": len(findings),
                "severity_counts": dict(sorted(Counter(finding.severity for finding in findings).items())),
                "status_counts": dict(sorted(Counter(finding.finding_status for finding in findings).items())),
                "coverage": artifact.coverage,
            }
        )
    series = [
        {
            "series_key": ":".join(str(part) for part in key),
            "repository_id": str(key[0]),
            "scan_type": key[1],
            "scanner_name": key[2],
            "scanner_version": key[3],
            "rule_set_version": key[4],
            "points": points,
        }
        for key, points in grouped.items()
    ]
    return {
        "series": series,
        "limitations": [
            "只比较同一仓库、扫描类型、扫描器、扫描器版本和规则版本的导入结果。",
            "扫描器或规则版本变更会形成新序列，不与旧序列解释为风险上升或下降。",
            "趋势来自导入扫描/CI 工件，不以提交数量、PR 关联、Agent 推断或未导入代码替代质量事实。",
        ],
    }


def update_security_finding_status(
    session: Session,
    *,
    project_id: UUID,
    finding_id: UUID,
    finding_status: str,
    reason: str,
    actor_id: UUID,
    correlation_id: str,
) -> SecurityFinding:
    require_python_security_baselines(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.REVIEWER, ProjectRole.ADMIN})
    finding = session.get(SecurityFinding, finding_id)
    artifact = session.get(SecurityScanArtifact, finding.scan_artifact_id) if finding else None
    if finding is None or artifact is None or artifact.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "安全风险不存在")
    if finding_status not in {"OPEN", "ACCEPTED_RISK", "REMEDIATION_CLAIMED"}:
        raise DomainError("INPUT_INVALID", "不支持的风险状态")
    finding.finding_status = finding_status
    finding.status_reason = reason.strip()
    finding.status_updated_by = actor_id
    finding.status_updated_at = datetime.now(UTC)
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="SecurityFinding",
        aggregate_id=finding.id,
        action="SECURITY_FINDING_STATUS_UPDATED",
        correlation_id=correlation_id,
        payload={"status": finding.finding_status, "reason": finding.status_reason, "scanArtifactId": str(artifact.id)},
    )
    return finding


def create_security_baseline(
    session: Session,
    *,
    project_id: UUID,
    repository_id: UUID,
    target_sha: str,
    scan_artifact_ids: list[UUID],
    actor_id: UUID,
    correlation_id: str,
) -> SecurityBaselineSnapshot:
    require_python_security_baselines(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    _repository_for_project(session, project_id=project_id, repository_id=repository_id)
    if len(scan_artifact_ids) != len(set(scan_artifact_ids)):
        raise DomainError("INPUT_INVALID", "安全基线不能重复选择同一扫描输入")
    artifacts = [_artifact_for_project(session, project_id=project_id, artifact_id=artifact_id) for artifact_id in scan_artifact_ids]
    normalized_sha = target_sha.lower()
    if any(artifact.repository_id != repository_id or artifact.target_sha != normalized_sha for artifact in artifacts):
        raise DomainError("INPUT_INVALID", "安全基线的所有扫描输入必须绑定同一仓库和目标 SHA")
    findings = (
        session.query(SecurityFinding)
        .filter(SecurityFinding.scan_artifact_id.in_(scan_artifact_ids))
        .order_by(SecurityFinding.scan_artifact_id, SecurityFinding.fingerprint)
        .all()
    )
    finding_manifest = [
        {
            "id": str(finding.id),
            "scanArtifactId": str(finding.scan_artifact_id),
            "fingerprint": finding.fingerprint,
            "severity": finding.severity,
            "category": finding.category,
            "status": finding.finding_status,
            "locator": finding.locator,
        }
        for finding in findings
    ]
    artifact_manifest = [
        {
            "id": str(artifact.id),
            "scanType": artifact.scan_type,
            "scannerName": artifact.scanner_name,
            "scannerVersion": artifact.scanner_version,
            "ruleSetVersion": artifact.rule_set_version,
            "coverage": artifact.coverage,
            "contentHash": artifact.content_hash,
        }
        for artifact in artifacts
    ]
    scan_types = {artifact.scan_type for artifact in artifacts}
    summary = {
        "findingCount": len(findings),
        "severityCounts": dict(sorted(Counter(finding.severity for finding in findings).items())),
        "statusCounts": dict(sorted(Counter(finding.finding_status for finding in findings).items())),
        "scanTypeCounts": dict(sorted(Counter(artifact.scan_type for artifact in artifacts).items())),
    }
    coverage = {
        "providedScanTypes": sorted(scan_types),
        "missingRecommendedScanTypes": sorted(_REQUIRED_SCAN_TYPES - scan_types),
        "scannerCoverage": [{"scanArtifactId": entry["id"], "scanType": entry["scanType"], "coverage": entry["coverage"]} for entry in artifact_manifest],
        "limitations": [
            "该基线只覆盖导入扫描器声明的路径、依赖、配置和规则版本。",
            "未导入扫描输入的范围不产生安全结论。",
            "风险状态为人工处置状态；REMEDIATION_CLAIMED 仍需新的扫描输入验证。",
        ],
    }
    manifest = {"repositoryId": str(repository_id), "targetSha": normalized_sha, "scanArtifacts": artifact_manifest, "findings": finding_manifest}
    input_hash = _canonical_hash(manifest)
    snapshot_hash = _canonical_hash({"inputHash": input_hash, "createdAt": datetime.now(UTC).isoformat()})
    baseline = SecurityBaselineSnapshot(
        project_id=project_id,
        repository_id=repository_id,
        target_sha=normalized_sha,
        input_manifest=manifest,
        input_hash=input_hash,
        snapshot_hash=snapshot_hash,
        summary=summary,
        coverage=coverage,
        created_by=actor_id,
    )
    session.add(baseline)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="SecurityBaselineSnapshot",
        aggregate_id=baseline.id,
        action="SECURITY_BASELINE_CREATED",
        correlation_id=correlation_id,
        payload={"targetSha": baseline.target_sha, "snapshotHash": baseline.snapshot_hash, "scanArtifactCount": len(artifacts)},
    )
    return baseline


def list_security_baselines(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[SecurityBaselineSnapshot]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return session.query(SecurityBaselineSnapshot).filter_by(project_id=project_id).order_by(SecurityBaselineSnapshot.created_at.desc()).limit(limit).all()


def confirm_security_baseline(
    session: Session,
    *,
    project_id: UUID,
    baseline_id: UUID,
    reason: str,
    actor_id: UUID,
    correlation_id: str,
) -> SecurityBaselineRecord:
    require_python_security_baselines(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.REVIEWER, ProjectRole.ADMIN})
    baseline = _baseline_for_project(session, project_id=project_id, baseline_id=baseline_id)
    existing = session.query(SecurityBaselineRecord).filter_by(baseline_snapshot_id=baseline.id).one_or_none()
    if existing is not None:
        return existing
    normalized_reason = reason.strip()
    record_hash = _canonical_hash({"snapshotHash": baseline.snapshot_hash, "reason": normalized_reason, "confirmation": "REVIEWER_OR_ADMIN"})
    record = SecurityBaselineRecord(
        project_id=project_id,
        baseline_snapshot_id=baseline.id,
        record_no=f"SB-{baseline.id.hex[:16].upper()}",
        record_hash=record_hash,
        confirmation_reason=normalized_reason,
        confirmed_by=actor_id,
    )
    session.add(record)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="SecurityBaselineRecord",
        aggregate_id=record.id,
        action="SECURITY_BASELINE_CONFIRMED",
        correlation_id=correlation_id,
        payload={"baselineId": str(baseline.id), "recordHash": record.record_hash},
    )
    return record


def list_security_baseline_records(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[SecurityBaselineRecord]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    return session.query(SecurityBaselineRecord).filter_by(project_id=project_id).order_by(SecurityBaselineRecord.confirmed_at.desc()).limit(limit).all()
