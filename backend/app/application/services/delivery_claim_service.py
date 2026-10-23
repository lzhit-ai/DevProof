import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.generation_model import create_generation_model
from app.infrastructure.business_ownership import require_python_delivery_claims
from app.infrastructure.persistence.models import (
    DeliveryClaimDraft,
    DeliveryItem,
    ExternalResource,
    ExternalResourceRevision,
    InputSnapshot,
    SourceRevision,
    VerificationCycle,
    VerificationTask,
    ModelCall,
    ProjectKnowledgeBase,
)


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _task_cycle(session: Session, *, project_id: UUID, task_id: UUID, actor_id: UUID) -> tuple[VerificationTask, VerificationCycle]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN, ProjectRole.REVIEWER})
    task = session.get(VerificationTask, task_id)
    cycle = (
        session.query(VerificationCycle)
        .filter_by(task_id=task_id)
        .order_by(VerificationCycle.sequence_no.desc())
        .first()
        if task is not None
        else None
    )
    if task is None or task.project_id != project_id or cycle is None:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在或不属于当前项目")
    return task, cycle


def _assert_editable(session: Session, *, task: VerificationTask, cycle: VerificationCycle, actor_id: UUID) -> None:
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if cycle.business_status not in {"DRAFT", "NEEDS_EVIDENCE", "NEEDS_CONFIRMATION"}:
        raise DomainError("STATE_CONFLICT", "当前轮次已开始分析或进入审批，不能再修改交付主张")
    if session.query(InputSnapshot).filter_by(cycle_id=cycle.id, purpose="FORMAL").first() is not None:
        raise DomainError("STATE_CONFLICT", "正式快照已创建；如需修改交付主张，请创建新的核验轮次")


def _latest_pr_revision(session: Session, *, task: VerificationTask) -> tuple[DeliveryItem, ExternalResourceRevision]:
    item = session.get(DeliveryItem, task.delivery_item_id)
    resource = session.get(ExternalResource, item.external_resource_id) if item else None
    revision = (
        session.query(ExternalResourceRevision)
        .filter_by(resource_id=resource.id)
        .order_by(ExternalResourceRevision.revision_no.desc())
        .first()
        if resource else None
    )
    if item is None or resource is None or resource.resource_type != "PULL_REQUEST" or revision is None:
        raise DomainError("INPUT_INVALID", "当前核验任务缺少可用于提取主张的同步 Pull Request 版本")
    return item, revision


def _serialize(draft: DeliveryClaimDraft) -> dict:
    return {
        "id": draft.id,
        "claim_key": draft.claim_key,
        "text": draft.text,
        "rationale": draft.rationale,
        "origin": draft.origin,
        "status": draft.claim_status,
        "source_manifest": draft.source_manifest,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def list_delivery_claims(session: Session, *, project_id: UUID, task_id: UUID, actor_id: UUID) -> list[dict]:
    _, cycle = _task_cycle(session, project_id=project_id, task_id=task_id, actor_id=actor_id)
    return [
        _serialize(item)
        for item in session.query(DeliveryClaimDraft)
        .filter(DeliveryClaimDraft.cycle_id == cycle.id, DeliveryClaimDraft.claim_status != "DISCARDED")
        .order_by(DeliveryClaimDraft.created_at, DeliveryClaimDraft.claim_key)
        .all()
    ]


def propose_delivery_claims(
    session: Session,
    *,
    project_id: UUID,
    task_id: UUID,
    source_revision_ids: list[UUID],
    actor_id: UUID,
    correlation_id: str,
) -> list[dict]:
    require_python_delivery_claims(session)
    task, cycle = _task_cycle(session, project_id=project_id, task_id=task_id, actor_id=actor_id)
    _assert_editable(session, task=task, cycle=cycle, actor_id=actor_id)
    if session.query(DeliveryClaimDraft).filter_by(cycle_id=cycle.id, claim_status="CONFIRMED").first() is not None:
        raise DomainError("STATE_CONFLICT", "本轮交付内容已确认；如需调整，请编辑后重新确认，或创建新的核验轮次")
    if len(source_revision_ids) != len(set(source_revision_ids)):
        raise DomainError("INPUT_INVALID", "资料版本不能重复选择")
    item, revision = _latest_pr_revision(session, task=task)
    kb_ids = [
        row[0]
        for row in session.query(ProjectKnowledgeBase.knowledge_base_id)
        .filter(ProjectKnowledgeBase.project_id == project_id)
        .all()
    ]
    visible = (
        {
            row[0]
            for row in session.query(SourceRevision.id)
            .filter(SourceRevision.knowledge_base_id.in_(kb_ids))
            .all()
        }
        if kb_ids
        else set()
    )
    sources = (
        session.query(SourceRevision).filter(SourceRevision.id.in_(source_revision_ids)).all()
        if source_revision_ids else []
    )
    if len(sources) != len(source_revision_ids) or any(source.id not in visible or source.processing_status != "READY" for source in sources):
        raise DomainError("SOURCE_NOT_READY", "候选主张只能引用当前项目可用的知识库中已就绪的资料版本")
    storage = LocalArtifactStorage(get_settings().artifact_root)
    documents = []
    for source in sources:
        try:
            raw = storage.read_text(source.extracted_artifact_uri or source.artifact_uri)
        except OSError as exc:
            raise DomainError("ARTIFACT_MISSING", f"无法读取资料 {source.logical_name} 的已提取文本") from exc
        documents.append({"sourceRevisionId": str(source.id), "name": source.logical_name, "contentHash": source.content_hash, "excerpt": raw[:4000]})
    manifest = {
        "pullRequest": {"deliveryItemId": str(item.id), "revisionId": str(revision.id), "contentHash": revision.content_hash, "title": revision.title, "body": revision.body, "webUrl": revision.web_url},
        "documents": [{"sourceRevisionId": item["sourceRevisionId"], "name": item["name"], "contentHash": item["contentHash"]} for item in documents],
    }
    settings = get_settings()
    call = ModelCall(
        provider=settings.generation_provider,
        model=settings.generation_model,
        operation="DELIVERY_CLAIM_PROPOSAL",
        prompt_version="delivery-claim-proposal-v1",
        schema_version="delivery-claim-proposal-v1",
        allowed_evidence_ids=[],
        status="RUNNING",
    )
    session.add(call)
    try:
        result = create_generation_model(settings).propose_delivery_claims({**manifest, "documents": documents})
        call.provider = result.provider
        call.model = result.model
        call.attempts = result.attempts
        call.latency_ms = result.latency_ms
        call.status = "SUCCEEDED"
    except DomainError as exc:
        call.status = "FAILED"
        call.error_code = exc.code
        call.error_summary = exc.message[:500]
        append_audit_event(session, project_id=project_id, actor_id=actor_id, aggregate_type="VerificationCycle", aggregate_id=cycle.id, action="DELIVERY_CLAIM_PROPOSAL_FAILED", correlation_id=correlation_id, payload={"code": exc.code})
        raise
    for draft in session.query(DeliveryClaimDraft).filter_by(cycle_id=cycle.id, claim_status="CANDIDATE").all():
        draft.claim_status = "DISCARDED"
    created: list[DeliveryClaimDraft] = []
    for index, candidate in enumerate(result.claims.claims, start=1):
        key = f"MODEL-{index}-{hashlib.sha256(candidate.text.encode()).hexdigest()[:12]}"
        draft = DeliveryClaimDraft(
            cycle_id=cycle.id,
            claim_key=key,
            text=candidate.text.strip(),
            rationale=candidate.rationale.strip(),
            origin="MODEL",
            claim_status="CANDIDATE",
            source_manifest=manifest,
            created_by=actor_id,
        )
        session.add(draft)
        created.append(draft)
    session.flush()
    append_audit_event(session, project_id=project_id, actor_id=actor_id, aggregate_type="VerificationCycle", aggregate_id=cycle.id, action="DELIVERY_CLAIM_CANDIDATES_PROPOSED", correlation_id=correlation_id, payload={"count": len(created), "modelCallId": str(call.id), "inputHash": _hash(manifest)})
    return [_serialize(item) for item in created]


def confirm_delivery_claims(
    session: Session,
    *,
    project_id: UUID,
    task_id: UUID,
    claims: list[dict],
    actor_id: UUID,
    correlation_id: str,
) -> list[dict]:
    require_python_delivery_claims(session)
    task, cycle = _task_cycle(session, project_id=project_id, task_id=task_id, actor_id=actor_id)
    cycle = session.query(VerificationCycle).filter_by(id=cycle.id).populate_existing().with_for_update().one()
    _assert_editable(session, task=task, cycle=cycle, actor_id=actor_id)
    if not claims:
        raise DomainError("INPUT_INVALID", "至少确认一条交付主张后才能进入冻结步骤")
    existing = {item.id: item for item in session.query(DeliveryClaimDraft).filter_by(cycle_id=cycle.id).all()}
    existing_by_key = {item.claim_key: item for item in existing.values()}
    for item in existing.values():
        if item.claim_status == "CONFIRMED":
            item.claim_status = "DISCARDED"
    confirmed: list[DeliveryClaimDraft] = []
    selected_ids: set[UUID] = set()
    now = datetime.now(UTC)
    for index, payload in enumerate(claims, start=1):
        text = str(payload.get("text") or "").strip()
        if len(text) < 3:
            raise DomainError("INPUT_INVALID", "交付主张至少需要 3 个字符")
        raw_id = payload.get("id")
        draft = existing.get(UUID(str(raw_id))) if raw_id else None
        if raw_id and draft is None:
            raise DomainError("INPUT_INVALID", "交付主张不存在或不属于本轮")
        manual_key = f"HUMAN-{index}-{hashlib.sha256(text.encode()).hexdigest()[:12]}"
        if draft is None:
            # Reapplying a plan or retrying a lost response keeps the same real claim identity.
            draft = existing_by_key.get(manual_key)
        if draft is not None:
            if draft.id in selected_ids:
                raise DomainError("INPUT_INVALID", "同一交付主张不能重复确认")
            draft.text = text
            draft.claim_status = "CONFIRMED"
        else:
            draft = DeliveryClaimDraft(
                cycle_id=cycle.id,
                claim_key=manual_key,
                text=text,
                rationale="提交人补充的交付主张",
                origin="HUMAN",
                claim_status="CONFIRMED",
                source_manifest={"source": "USER_CONFIRMED"},
                created_by=actor_id,
            )
            session.add(draft)
        draft.confirmed_by = actor_id
        draft.confirmed_at = now
        if draft.id:
            selected_ids.add(draft.id)
        confirmed.append(draft)
    session.flush()
    append_audit_event(session, project_id=project_id, actor_id=actor_id, aggregate_type="VerificationCycle", aggregate_id=cycle.id, action="DELIVERY_CLAIMS_CONFIRMED", correlation_id=correlation_id, payload={"count": len(confirmed)})
    return [_serialize(item) for item in confirmed]
