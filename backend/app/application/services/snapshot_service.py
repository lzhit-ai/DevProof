import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.application.services.redaction import safe_excerpt
from app.core.config import get_settings
from app.domain.enums import AssessmentProfile, ProjectRole, SourceProcessingStatus
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import (
    DocumentChunk,
    EvidenceItem,
    InputSnapshot,
    InputSnapshotClaim,
    InputSnapshotSource,
    InputSnapshotGit,
    InputSnapshotExternalEvidence,
    InputSnapshotManualEvidence,
    InputSnapshotPlan,
    GitSnapshot,
    ExternalEvidence,
    DeliveryItemSourceLink,
    DeliveryItem,
    DeliveryClaimDraft,
    ExternalResource,
    ExternalResourceRevision,
    ManualEvidence,
    VerificationCycle,
    VerificationTask,
    SourceRevision,
    ProjectKnowledgeBase,
)
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.application.services.retrieval_index_service import active_index_version
from app.infrastructure.business_ownership import require_python_inputs


_DELIVERY_PROFILE = AssessmentProfile.DELIVERY_VERIFICATION.value


def _project_visible_source_ids(session: Session, *, project_id: UUID) -> set:
    """Source ids a project may reference: those in any knowledge base it mounted.

    A project can use sources from knowledge bases it created (auto-mounted)
    as well as knowledge bases shared/mounted by another project.
    """
    kb_ids = [
        row[0]
        for row in session.query(ProjectKnowledgeBase.knowledge_base_id)
        .filter(ProjectKnowledgeBase.project_id == project_id)
        .all()
    ]
    if not kb_ids:
        return set()
    return {
        row[0]
        for row in session.query(SourceRevision.id)
        .filter(SourceRevision.knowledge_base_id.in_(kb_ids))
        .all()
    }


def _document_chunks_for_snapshot(session: Session, *, source_id: UUID, active_version: str | None) -> list[DocumentChunk]:
    query = session.query(DocumentChunk).filter_by(source_revision_id=source_id)
    if active_version is not None:
        active_chunks = query.filter_by(index_version=active_version).order_by(DocumentChunk.chunk_index).all()
        if active_chunks:
            return active_chunks
    # Legacy sources may not yet have an active derived index. Freeze one stable raw-evidence copy per chunk.
    selected: dict[int, DocumentChunk] = {}
    for chunk in query.order_by(DocumentChunk.chunk_index, DocumentChunk.index_version).all():
        selected.setdefault(chunk.chunk_index, chunk)
    return [selected[index] for index in sorted(selected)]


def freeze_preparation_snapshot(
    session: Session,
    *,
    cycle_id: UUID,
    source_revision_ids: list[UUID],
    actor_id: UUID,
    correlation_id: str,
) -> InputSnapshot:
    require_python_inputs(session)
    cycle = session.get(VerificationCycle, cycle_id)
    if cycle is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验轮次不存在")
    task = session.get(VerificationTask, cycle.task_id)
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if cycle.business_status != "DRAFT":
        raise DomainError("STATE_CONFLICT", "只有草稿轮次可以冻结准备快照")
    if not source_revision_ids or len(set(source_revision_ids)) != len(source_revision_ids):
        raise DomainError("INPUT_INVALID", "至少选择一份且不重复的资料版本")

    visible = _project_visible_source_ids(session, project_id=task.project_id)
    sources = (
        session.query(SourceRevision)
        .filter(SourceRevision.id.in_(source_revision_ids))
        .all()
    )
    if len(sources) != len(source_revision_ids) or any(source.id not in visible for source in sources):
        raise DomainError("INPUT_INVALID", "资料版本不存在或不属于当前项目可用的知识库")
    not_ready = [source.id for source in sources if source.processing_status != SourceProcessingStatus.READY]
    if not_ready:
        raise DomainError("SOURCE_NOT_READY", "所选资料尚未完成处理")

    normalized = {
        "cycleId": str(cycle.id),
        "purpose": "PREPARATION",
        "assessmentProfile": _DELIVERY_PROFILE,
        "policyVersion": "v1",
        "workflowVersion": "v1",
        "sources": sorted(
            [
                {
                    "id": str(source.id),
                    "contentHash": source.content_hash,
                    "parserVersion": source.parser_version,
                }
                for source in sources
            ],
            key=lambda item: item["id"],
        ),
    }
    canonical = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    snapshot_hash = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    existing = session.query(InputSnapshot).filter_by(snapshot_hash=snapshot_hash).one_or_none()
    if existing is not None:
        return existing

    snapshot = InputSnapshot(
        cycle_id=cycle.id,
        snapshot_hash=snapshot_hash,
        policy_version="v1",
        workflow_version="v1",
        created_by=actor_id,
        purpose="PREPARATION",
        assessment_profile=_DELIVERY_PROFILE,
    )
    session.add(snapshot)
    session.flush()
    active_version = active_index_version(session, project_id=task.project_id)
    for source in sources:
        session.add(
            InputSnapshotSource(
                snapshot_id=snapshot.id,
                source_revision_id=source.id,
                content_hash=source.content_hash,
                parser_version=source.parser_version or "unknown",
            )
        )
        chunks = _document_chunks_for_snapshot(session, source_id=source.id, active_version=active_version)
        for chunk in chunks:
            session.add(
                EvidenceItem(
                    project_id=task.project_id,
                    snapshot_id=snapshot.id,
                    source_type="DOCUMENT",
                    evidence_kind="RAW_FACT",
                    source_revision_id=source.id,
                    content_hash=chunk.text_hash,
                    excerpt_safe=safe_excerpt(chunk.content),
                    locator={
                        "sourceRevisionId": str(source.id),
                        "chunkId": str(chunk.id),
                        "chunkIndex": chunk.chunk_index,
                        **chunk.locator,
                    },
                    locator_precision="EXACT",
                    extractor_version=source.parser_version or "markdown-text-v1",
                )
            )
    append_audit_event(
        session,
        project_id=task.project_id,
        actor_id=actor_id,
        aggregate_type="InputSnapshot",
        aggregate_id=snapshot.id,
        action="PREPARATION_SNAPSHOT_FROZEN",
        correlation_id=correlation_id,
        payload={"snapshotHash": snapshot.snapshot_hash, "sourceRevisionIds": [str(x) for x in source_revision_ids]},
    )
    return snapshot


def freeze_formal_snapshot(
    session: Session,
    *,
    cycle_id: UUID,
    source_revision_ids: list[UUID],
    git_snapshot_id: UUID,
    external_evidence_ids: list[UUID],
    manual_evidence_ids: list[UUID],
    actor_id: UUID,
    correlation_id: str,
) -> InputSnapshot:
    require_python_inputs(session)
    # Serialize formal freezing with Java plan selection and claim confirmation.
    cycle = session.query(VerificationCycle).filter_by(id=cycle_id).with_for_update().one_or_none()
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    git = session.get(GitSnapshot, git_snapshot_id)
    if task is None or git is None or git.cycle_id != cycle_id:
        raise DomainError("GIT_RANGE_INVALID", "正式快照必须绑定当前轮次已冻结的 Git 范围")
    if not git.diff_artifact_id or not git.code_change_artifact_id:
        raise DomainError("GIT_ARTIFACT_MISSING", "正式快照必须使用已保存且可回放的 Git Diff 制品")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if cycle.business_status not in {"DRAFT", "NEEDS_EVIDENCE", "NEEDS_CONFIRMATION"}:
        raise DomainError("STATE_CONFLICT", "当前轮次不能再冻结新的正式输入快照")
    confirmed_claims = (
        session.query(DeliveryClaimDraft)
        .filter_by(cycle_id=cycle.id, claim_status="CONFIRMED")
        .order_by(DeliveryClaimDraft.claim_key)
        .all()
    )
    if not confirmed_claims:
        raise DomainError("CLAIMS_NOT_CONFIRMED", "请先确认本次 Pull Request 的交付主张，再创建正式快照")
    primary_link = (
        session.query(DeliveryItemSourceLink)
        .filter_by(delivery_item_id=task.delivery_item_id, link_role="PRIMARY")
        .filter(DeliveryItemSourceLink.external_resource_revision_id.is_not(None))
        .order_by(DeliveryItemSourceLink.created_at.desc())
        .first()
    )
    requirement_revision = session.get(ExternalResourceRevision, primary_link.external_resource_revision_id) if primary_link else None
    if requirement_revision is None:
        raise DomainError("INPUT_INVALID", "正式快照缺少本次 Pull Request 的同步版本")
    item = session.get(DeliveryItem, task.delivery_item_id)
    resource = session.get(ExternalResource, item.external_resource_id) if item else None
    if resource is None or resource.resource_type != "PULL_REQUEST":
        raise DomainError("INPUT_INVALID", "正式快照只能从当前项目已同步的 Pull Request 创建")
    if len(source_revision_ids) != len(set(source_revision_ids)):
        raise DomainError("INPUT_INVALID", "正式快照的资料版本不能重复选择")
    visible = _project_visible_source_ids(session, project_id=task.project_id)
    sources = session.query(SourceRevision).filter(SourceRevision.id.in_(source_revision_ids)).all()
    if len(sources) != len(source_revision_ids) or any(source.id not in visible for source in sources):
        raise DomainError("SOURCE_NOT_READY", "正式快照的资料必须属于当前项目可用的知识库")
    selected_source_ids = {str(source.id) for source in sources}
    referenced_source_ids = {
        str(item.get("sourceRevisionId"))
        for claim in confirmed_claims
        for item in claim.source_manifest.get("documents", [])
        if isinstance(item, dict) and item.get("sourceRevisionId")
    }
    if not referenced_source_ids.issubset(selected_source_ids):
        raise DomainError("INPUT_STALE", "候选交付主张引用的资料版本未被纳入本次正式快照；请重新选择资料或重新提取候选")
    if len(external_evidence_ids) != len(set(external_evidence_ids)):
        raise DomainError("INPUT_INVALID", "external evidence cannot be selected twice")
    external_evidence = session.query(ExternalEvidence).filter(ExternalEvidence.id.in_(external_evidence_ids), ExternalEvidence.project_id == task.project_id, ExternalEvidence.cycle_id == cycle.id).all() if external_evidence_ids else []
    if len(external_evidence) != len(external_evidence_ids):
        raise DomainError("INPUT_INVALID", "external evidence does not belong to this verification cycle")
    if any(item.commit_sha != git.target_sha for item in external_evidence):
        raise DomainError("INPUT_STALE", "external evidence must bind the frozen target commit")
    if len(manual_evidence_ids) != len(set(manual_evidence_ids)):
        raise DomainError("INPUT_INVALID", "manual evidence cannot be selected twice")
    manual_evidence = session.query(ManualEvidence).filter(
        ManualEvidence.id.in_(manual_evidence_ids),
        ManualEvidence.project_id == task.project_id,
        ManualEvidence.cycle_id == cycle.id,
    ).all() if manual_evidence_ids else []
    if len(manual_evidence) != len(manual_evidence_ids):
        raise DomainError("INPUT_INVALID", "manual evidence does not belong to this verification cycle")
    storage = LocalArtifactStorage(get_settings().artifact_root)
    from app.application.services.plan_baseline_service import selected_plan_for_freeze

    plan_baseline = selected_plan_for_freeze(session, cycle_id=cycle.id, project_id=task.project_id, git=git, claims=confirmed_claims)
    planned_claims = {item["claimId"]: item for item in plan_baseline["body"]["mappings"]} if plan_baseline else {}
    delivery_claims = [
        {
            "id": str(claim.id),
            "key": claim.claim_key,
            "text": claim.text,
            "origin": claim.origin,
            "sourceManifest": claim.source_manifest,
            "contentHash": f"sha256:{hashlib.sha256(claim.text.encode()).hexdigest()}",
        }
        for claim in confirmed_claims
    ]
    for payload in delivery_claims:
        mapping = planned_claims.get(payload["id"])
        if mapping:
            payload["sourceManifest"] = {
                **payload["sourceManifest"],
                "planAcceptance": {
                    "planVersionId": plan_baseline["planVersionId"], "planContentHash": plan_baseline["planContentHash"],
                    "selectionHash": plan_baseline["selectionHash"], "issueKey": mapping["issueKey"],
                    "acceptanceKey": mapping["acceptanceKey"], "criterion": mapping["criterion"],
                },
            }
    normalized = {"purpose": "FORMAL", "assessmentProfile": _DELIVERY_PROFILE, "cycleId": str(cycle.id), "policyVersion": "v1", "workflowVersion": "v1", "requirement": {"deliveryItemId": str(task.delivery_item_id), "externalResourceRevisionId": str(requirement_revision.id), "hash": requirement_revision.content_hash, "title": requirement_revision.title, "body": requirement_revision.body, "webUrl": requirement_revision.web_url}, "deliveryClaims": delivery_claims, "git": {"baseSha": git.base_sha, "targetSha": git.target_sha, "mergeBaseSha": git.merge_base_sha, "effectiveBaseSha": git.effective_base_sha, "diffMode": git.diff_mode, "diffHash": git.diff_hash, "diffArtifactId": str(git.diff_artifact_id), "codeChangeArtifactId": str(git.code_change_artifact_id)}, "sources": sorted([{"id": str(x.id), "hash": x.content_hash, "parser": x.parser_version} for x in sources], key=lambda x: x["id"]), "externalEvidence": sorted([{"id": str(x.id), "hash": x.content_hash, "commitSha": x.commit_sha, "type": x.evidence_type} for x in external_evidence], key=lambda x: x["id"]), "manualEvidence": sorted([{"id": str(x.id), "hash": x.content_hash, "submittedBy": str(x.submitted_by)} for x in manual_evidence], key=lambda x: x["id"])}
    if plan_baseline:
        normalized["planBaseline"] = {key: value for key, value in plan_baseline.items() if key != "body"}
    snapshot_hash = f"sha256:{hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}"
    existing = session.query(InputSnapshot).filter_by(snapshot_hash=snapshot_hash).one_or_none()
    if existing is not None: return existing
    snapshot = InputSnapshot(cycle_id=cycle.id, snapshot_hash=snapshot_hash, policy_version="v1", workflow_version="v1", created_by=actor_id, purpose="FORMAL", assessment_profile=_DELIVERY_PROFILE)
    session.add(snapshot); session.flush()
    if plan_baseline:
        session.add(InputSnapshotPlan(snapshot_id=snapshot.id, selection_id=UUID(plan_baseline["selectionId"]),
            plan_version_id=UUID(plan_baseline["planVersionId"]), plan_content_hash=plan_baseline["planContentHash"],
            selection_hash=plan_baseline["selectionHash"]))
    for claim, payload in zip(confirmed_claims, delivery_claims, strict=True):
        session.add(InputSnapshotClaim(snapshot_id=snapshot.id, delivery_claim_draft_id=claim.id, claim_key=claim.claim_key, text=claim.text, origin=claim.origin, source_manifest=payload["sourceManifest"], content_hash=payload["contentHash"]))
    requirement_content = f"{requirement_revision.title}\n\n{requirement_revision.body}".strip()
    session.add(EvidenceItem(project_id=task.project_id, snapshot_id=snapshot.id, source_type="PULL_REQUEST", evidence_kind="RAW_FACT", content_hash=requirement_revision.content_hash, excerpt_safe=safe_excerpt(requirement_content), locator={"deliveryItemId": str(task.delivery_item_id), "externalResourceRevisionId": str(requirement_revision.id), "webUrl": requirement_revision.web_url}, locator_precision="EXACT", extractor_version="github-pr-v1"))
    active_version = active_index_version(session, project_id=task.project_id)
    for source in sources:
        session.add(InputSnapshotSource(snapshot_id=snapshot.id, source_revision_id=source.id, content_hash=source.content_hash, parser_version=source.parser_version or "unknown"))
        chunks = _document_chunks_for_snapshot(session, source_id=source.id, active_version=active_version)
        for chunk in chunks:
            session.add(EvidenceItem(project_id=task.project_id, snapshot_id=snapshot.id, source_type="DOCUMENT", evidence_kind="RAW_FACT", source_revision_id=source.id, content_hash=chunk.text_hash, excerpt_safe=safe_excerpt(chunk.content), locator={"sourceRevisionId": str(source.id), "chunkId": str(chunk.id), "chunkIndex": chunk.chunk_index, **chunk.locator}, locator_precision="EXACT", extractor_version=source.parser_version or "markdown-text-v1"))
    for item in external_evidence:
        session.add(InputSnapshotExternalEvidence(snapshot_id=snapshot.id, external_evidence_id=item.id, content_hash=item.content_hash, commit_sha=item.commit_sha))
        content = storage.read_text(item.artifact_uri)
        session.add(EvidenceItem(project_id=task.project_id, snapshot_id=snapshot.id, source_type=item.evidence_type, evidence_kind="RAW_FACT", commit_sha=item.commit_sha, content_hash=item.content_hash, excerpt_safe=safe_excerpt(content), locator={"externalEvidenceId": str(item.id), "logicalName": item.logical_name, "commitSha": item.commit_sha, "exitCode": item.exit_code}, locator_precision="EXACT", extractor_version="external-evidence-v1"))
    for item in manual_evidence:
        session.add(InputSnapshotManualEvidence(snapshot_id=snapshot.id, manual_evidence_id=item.id, content_hash=item.content_hash))
        content = storage.read_text(item.artifact_uri)
        session.add(EvidenceItem(
            project_id=task.project_id,
            snapshot_id=snapshot.id,
            source_type="MANUAL",
            evidence_kind="HUMAN_NOTE",
            content_hash=item.content_hash,
            excerpt_safe=safe_excerpt(content),
            locator={
                "manualEvidenceId": str(item.id),
                "logicalName": item.logical_name,
                "submittedBy": str(item.submitted_by),
                "originType": item.origin_type,
                "origin": item.origin_locator,
            },
            locator_precision="EXACT",
            extractor_version="manual-evidence-v1",
            requires_human_confirmation=True,
        ))
    session.add(InputSnapshotGit(snapshot_id=snapshot.id, git_snapshot_id=git.id, diff_hash=git.diff_hash))
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="InputSnapshot", aggregate_id=snapshot.id, action="FORMAL_SNAPSHOT_FROZEN", correlation_id=correlation_id, payload={"snapshotHash": snapshot.snapshot_hash, "gitSnapshotId": str(git.id), "deliveryClaimCount": len(delivery_claims), "assessmentProfile": _DELIVERY_PROFILE})
    return snapshot
