from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import require_project_role
from app.core.config import get_settings
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.domain.model_contracts import EmbeddingRequest
from app.infrastructure.document_parser import MarkdownTextDocumentParser
from app.infrastructure.embedding_model import configured_embedding_index_version, create_embedding_model
from app.infrastructure.persistence.models import EvidenceItem, InputSnapshot, InputSnapshotSource, KnowledgeBase, SourceRevision, VerificationCycle, VerificationTask
from app.infrastructure.retriever import PostgresHybridRetriever
from app.application.services.retrieval_index_service import active_index_version
from app.application.services.retrieval_ranking import rank_candidates, ranking_reasons
from app.infrastructure.business_ownership import require_python_knowledge_sources


def _business_source_role(source: SourceRevision, knowledge_base_names: dict[UUID, str]) -> str:
    """Prefer a knowledge-base name when upload flow uses the generic role."""
    if source.source_role.strip() != "知识库":
        return source.source_role
    return knowledge_base_names.get(source.knowledge_base_id, source.source_role)


def search_snapshot(
    session: Session,
    *,
    snapshot_id: UUID,
    query: str,
    limit: int,
    actor_id: UUID,
    preferred_source_roles: list[str] | None = None,
) -> list[dict]:
    require_python_knowledge_sources(session)
    snapshot = session.get(InputSnapshot, snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "输入快照不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    source_ids = [item.source_revision_id for item in session.query(InputSnapshotSource).filter_by(snapshot_id=snapshot.id).all()]
    if not source_ids:
        return []
    active_version = active_index_version(session, project_id=task.project_id)
    settings = get_settings()
    configured_version = configured_embedding_index_version(settings, MarkdownTextDocumentParser().version)
    try:
        if active_version is not None and active_version != configured_version:
            raise DomainError("MODEL_INDEX_UNAVAILABLE", "当前 Embedding 配置与项目活动索引不一致")
        embedding = create_embedding_model(settings).embed(EmbeddingRequest(text=query, model=settings.embedding_model))
        candidates = PostgresHybridRetriever(session).search(
            source_revision_ids=source_ids,
            query=query,
            limit=limit,
            query_embedding=embedding.vector,
            embedding_index_version=active_version or configured_version,
        )
    except DomainError:
        # Retrieval still serves exact lexical evidence when a cloud embedding model is unavailable.
        candidates = PostgresHybridRetriever(session).search(source_revision_ids=source_ids, query=query, limit=limit, query_embedding=None)

    evidence = session.query(EvidenceItem).filter_by(snapshot_id=snapshot.id, source_type="DOCUMENT").all()
    evidence_by_identity = {
        (str(item.locator.get("sourceRevisionId")), item.locator.get("chunkIndex")): item
        for item in evidence
    }
    evidence_by_chunk = {str(item.locator.get("chunkId")): item for item in evidence}
    source_by_id = {
        source.id: source
        for source in session.query(SourceRevision).filter(SourceRevision.id.in_(source_ids)).all()
    }
    knowledge_base_names = {
        knowledge_base.id: knowledge_base.name
        for knowledge_base in session.query(KnowledgeBase)
        .filter(KnowledgeBase.id.in_({source.knowledge_base_id for source in source_by_id.values() if source.knowledge_base_id}))
        .all()
    }
    business_roles = {
        source_id: _business_source_role(source, knowledge_base_names)
        for source_id, source in source_by_id.items()
    }
    matched: list[tuple] = []
    for candidate in candidates:
        item = evidence_by_identity.get((str(candidate.source_revision_id), candidate.chunk_index)) or evidence_by_chunk.get(str(candidate.chunk_id))
        if item is None:
            continue
        matched.append((candidate, item))

    preferred_source_roles = preferred_source_roles or []
    evidence_metadata = {}
    for candidate, item in matched:
        source = source_by_id.get(candidate.source_revision_id)
        evidence_metadata[candidate.chunk_id] = (
            item.locator_precision,
            source.ocr_confidence if source else None,
        )
    signals_by_chunk = rank_candidates(
        [candidate for candidate, _ in matched],
        source_roles=business_roles,
        preferred_source_roles=preferred_source_roles,
        evidence_metadata=evidence_metadata,
    )
    fused: list[dict] = []
    for candidate, item in matched:
        source = source_by_id.get(candidate.source_revision_id)
        signals = signals_by_chunk[candidate.chunk_id]
        fused.append({
            "evidenceId": str(item.id),
            "excerpt": item.excerpt_safe,
            "locator": item.locator,
            "precision": item.locator_precision,
            "score": round(signals.final_score, 6),
            "retrieval": {key: value for key, value in {"ftsRank": candidate.fts_rank, "ftsScore": candidate.fts_score, "vectorRank": candidate.vector_rank, "vectorScore": candidate.vector_score}.items() if value is not None},
            "ranking": {
                "rrfScore": round(signals.rrf_score, 6),
                "normalizedRrfScore": round(signals.normalized_rrf_score, 6),
                "sourceRole": source.source_role if source else None,
                "businessRole": business_roles.get(candidate.source_revision_id),
                "sourceRoleMatch": round(signals.source_role_match, 6),
                "evidenceQuality": round(signals.evidence_quality, 6),
                "finalScore": round(signals.final_score, 6),
                "weights": {"rrf": 0.75, "sourceRole": 0.15, "evidenceQuality": 0.10},
            },
            "whySelected": ranking_reasons(
                candidate=candidate,
                source_role=business_roles.get(candidate.source_revision_id, ""),
                preferred_source_roles=preferred_source_roles,
                precision=item.locator_precision,
                ocr_confidence=source.ocr_confidence if source else None,
            ),
        })
    return sorted(fused, key=lambda item: item["score"], reverse=True)[:limit]
