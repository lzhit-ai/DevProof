"""Frozen deterministic runs for non-delivery profiles.

These runs deliberately do not enter InputSnapshot -> AnalysisRun -> dual-core -> report.
They turn already frozen project/status/security inputs into separately traceable read-only
projections, without scanning a repository or asking a model to invent conclusions.
"""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.domain.enums import AssessmentProfile, ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.business_ownership import require_python_peripheral_profiles
from app.infrastructure.persistence.models import (
    PeripheralProfileRun,
    ProjectHealthSnapshot,
    SecurityBaselineSnapshot,
    SecurityFinding,
    SecurityScanArtifact,
)


_NON_DELIVERY_PROFILES = {
    AssessmentProfile.PROJECT_STATUS_SUMMARY.value,
    AssessmentProfile.SECURITY_BASELINE.value,
    AssessmentProfile.QUALITY_TREND.value,
}


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _as_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _health_snapshot(session: Session, *, project_id: UUID, snapshot_id: UUID) -> ProjectHealthSnapshot:
    snapshot = session.get(ProjectHealthSnapshot, snapshot_id)
    if snapshot is None or snapshot.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "项目态势快照不存在")
    return snapshot


def _security_baseline(session: Session, *, project_id: UUID, baseline_id: UUID) -> SecurityBaselineSnapshot:
    baseline = session.get(SecurityBaselineSnapshot, baseline_id)
    if baseline is None or baseline.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "安全基线不存在")
    return baseline


def _quality_artifacts(session: Session, *, project_id: UUID, artifact_ids: list[UUID]) -> list[SecurityScanArtifact]:
    if len(artifact_ids) < 2:
        raise DomainError("INPUT_INVALID", "质量趋势运行至少需要两个可比扫描工件")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise DomainError("INPUT_INVALID", "质量趋势运行不能重复选择扫描工件")
    artifacts = session.query(SecurityScanArtifact).filter(SecurityScanArtifact.id.in_(artifact_ids)).all()
    by_id = {artifact.id: artifact for artifact in artifacts}
    if len(by_id) != len(artifact_ids) or any(by_id[artifact_id].project_id != project_id for artifact_id in artifact_ids):
        raise DomainError("RESOURCE_NOT_FOUND", "质量趋势扫描工件不存在或不属于当前项目")
    ordered = [by_id[artifact_id] for artifact_id in artifact_ids]
    first = ordered[0]
    comparable_key = (
        first.repository_id,
        first.scan_type,
        first.scanner_name,
        first.scanner_version,
        first.rule_set_version,
    )
    if any(
        (artifact.repository_id, artifact.scan_type, artifact.scanner_name, artifact.scanner_version, artifact.rule_set_version)
        != comparable_key
        for artifact in ordered
    ):
        raise DomainError("INPUT_INVALID", "质量趋势只能比较同一仓库、扫描类型、扫描器版本与规则版本的工件")
    return sorted(ordered, key=lambda artifact: (artifact.created_at, str(artifact.id)))


def _project_status_projection(snapshot: ProjectHealthSnapshot) -> tuple[dict, dict, dict, list[str]]:
    limitations = list(snapshot.coverage.get("observabilityLimits", []))
    limitations.append("本次外围运行只复用该态势快照，不读取提交、PR 或仓库代码来补写项目完成结论。")
    manifest = {
        "profile": AssessmentProfile.PROJECT_STATUS_SUMMARY.value,
        "healthSnapshot": {
            "id": str(snapshot.id),
            "snapshotHash": snapshot.snapshot_hash,
            "inputHash": snapshot.input_hash,
            "asOf": _as_iso(snapshot.as_of),
        },
    }
    output = {"scope": snapshot.scope, "summary": snapshot.summary, "asOf": _as_iso(snapshot.as_of)}
    return manifest, output, snapshot.coverage, limitations


def _security_baseline_projection(baseline: SecurityBaselineSnapshot) -> tuple[dict, dict, dict, list[str]]:
    limitations = list(baseline.coverage.get("limitations", []))
    limitations.append("本次外围运行只复用该安全基线，不执行扫描器、不读取仓库，也不输出安全通过或发布通过结论。")
    manifest = {
        "profile": AssessmentProfile.SECURITY_BASELINE.value,
        "securityBaseline": {
            "id": str(baseline.id),
            "repositoryId": str(baseline.repository_id),
            "targetSha": baseline.target_sha,
            "snapshotHash": baseline.snapshot_hash,
            "inputHash": baseline.input_hash,
        },
    }
    output = {"targetSha": baseline.target_sha, "summary": baseline.summary, "coverage": baseline.coverage}
    return manifest, output, baseline.coverage, limitations


def _quality_trend_projection(session: Session, artifacts: list[SecurityScanArtifact]) -> tuple[dict, dict, dict, list[str]]:
    points: list[dict] = []
    for artifact in artifacts:
        findings = session.query(SecurityFinding).filter_by(scan_artifact_id=artifact.id).all()
        points.append(
            {
                "artifactId": str(artifact.id),
                "targetSha": artifact.target_sha,
                "createdAt": _as_iso(artifact.created_at),
                "contentHash": artifact.content_hash,
                "findingCount": len(findings),
                "severityCounts": dict(sorted(Counter(finding.severity for finding in findings).items())),
                "statusCounts": dict(sorted(Counter(finding.finding_status for finding in findings).items())),
                "coverage": artifact.coverage,
            }
        )
    first = artifacts[0]
    comparable = {
        "repositoryId": str(first.repository_id),
        "scanType": first.scan_type,
        "scannerName": first.scanner_name,
        "scannerVersion": first.scanner_version,
        "ruleSetVersion": first.rule_set_version,
    }
    manifest = {
        "profile": AssessmentProfile.QUALITY_TREND.value,
        "comparability": comparable,
        "scanArtifacts": [
            {
                "id": point["artifactId"],
                "targetSha": point["targetSha"],
                "createdAt": point["createdAt"],
                "contentHash": point["contentHash"],
                "findingCount": point["findingCount"],
                "severityCounts": point["severityCounts"],
                "statusCounts": point["statusCounts"],
                "coverage": point["coverage"],
            }
            for point in points
        ],
    }
    output = {"comparability": comparable, "points": points}
    coverage = {"pointCount": len(points), "scannerCoverage": [{"artifactId": point["artifactId"], "coverage": point["coverage"]} for point in points]}
    limitations = [
        "只比较本次冻结的同一仓库、扫描类型、扫描器名称与版本、规则版本工件。",
        "提交数量、PR 关联、Agent 推断与未导入代码均不参与质量趋势。",
        "发现数的变化只描述这组可比工件的导入结果，不等同于整体项目质量或安全状态。",
    ]
    return manifest, output, coverage, limitations


def create_peripheral_profile_run(
    session: Session,
    *,
    project_id: UUID,
    assessment_profile: str,
    health_snapshot_id: UUID | None,
    security_baseline_id: UUID | None,
    scan_artifact_ids: list[UUID] | None,
    actor_id: UUID,
    correlation_id: str,
) -> PeripheralProfileRun:
    require_python_peripheral_profiles(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if assessment_profile not in _NON_DELIVERY_PROFILES:
        raise DomainError("INPUT_INVALID", "外围运行只支持项目态势、安全基线或质量趋势配置")
    if assessment_profile == AssessmentProfile.PROJECT_STATUS_SUMMARY.value:
        if health_snapshot_id is None or security_baseline_id is not None or scan_artifact_ids:
            raise DomainError("INPUT_INVALID", "项目态势运行只能选择一个项目态势快照")
        manifest, output, coverage, limitations = _project_status_projection(
            _health_snapshot(session, project_id=project_id, snapshot_id=health_snapshot_id)
        )
    elif assessment_profile == AssessmentProfile.SECURITY_BASELINE.value:
        if security_baseline_id is None or health_snapshot_id is not None or scan_artifact_ids:
            raise DomainError("INPUT_INVALID", "安全基线运行只能选择一个安全基线快照")
        manifest, output, coverage, limitations = _security_baseline_projection(
            _security_baseline(session, project_id=project_id, baseline_id=security_baseline_id)
        )
    else:
        if health_snapshot_id is not None or security_baseline_id is not None or not scan_artifact_ids:
            raise DomainError("INPUT_INVALID", "质量趋势运行只能选择多个可比扫描工件")
        manifest, output, coverage, limitations = _quality_trend_projection(
            session, _quality_artifacts(session, project_id=project_id, artifact_ids=scan_artifact_ids)
        )
    run = PeripheralProfileRun(
        project_id=project_id,
        assessment_profile=assessment_profile,
        input_manifest=manifest,
        input_hash=_canonical_hash(manifest),
        output=output,
        coverage=coverage,
        limitations=limitations,
        created_by=actor_id,
    )
    session.add(run)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="PeripheralProfileRun",
        aggregate_id=run.id,
        action="PERIPHERAL_PROFILE_RUN_CREATED",
        correlation_id=correlation_id,
        payload={"assessmentProfile": run.assessment_profile, "inputHash": run.input_hash, "runStatus": run.run_status},
    )
    return run


def list_peripheral_profile_runs(
    session: Session, *, project_id: UUID, actor_id: UUID, assessment_profile: str | None = None, limit: int = 100
) -> list[PeripheralProfileRun]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    query = session.query(PeripheralProfileRun).filter_by(project_id=project_id)
    if assessment_profile is not None:
        if assessment_profile not in _NON_DELIVERY_PROFILES:
            raise DomainError("INPUT_INVALID", "不支持的外围运行配置")
        query = query.filter_by(assessment_profile=assessment_profile)
    return query.order_by(PeripheralProfileRun.created_at.desc()).limit(limit).all()
