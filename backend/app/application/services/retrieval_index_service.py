"""Derived retrieval-index lifecycle; it never mutates source or snapshot facts."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.domain.enums import ProjectRole, SourceProcessingStatus
from app.domain.errors import DomainError
from app.domain.model_contracts import EmbeddingRequest, EmbeddingResult
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.document_parser import MarkdownTextDocumentParser
from app.infrastructure.embedding_model import (
    configured_embedding_index_version,
    create_embedding_model,
    embedding_index_version,
)
from app.infrastructure.persistence.models import DocumentChunk, ProjectRetrievalIndex, RetrievalIndexBuildRun, SourceRevision
from app.infrastructure.business_ownership import require_python_knowledge_sources


_ACTIVE = "ACTIVE"
_HISTORICAL = "HISTORICAL"
_CANONICAL_PARSER_VERSION = "knowledge-extraction-v1"


def active_index_version(session: Session, *, project_id: UUID) -> str | None:
    active = session.query(ProjectRetrievalIndex).filter_by(project_id=project_id, status=_ACTIVE).one_or_none()
    return active.index_version if active is not None else None


def ensure_initial_retrieval_index(
    session: Session,
    *,
    project_id: UUID,
    index_version: str,
    parser_version: str,
    embedding: EmbeddingResult,
    actor_id: UUID,
    correlation_id: str,
) -> None:
    """Seed an empty project's active index without silently switching an existing project."""
    require_python_knowledge_sources(session)

    active = session.query(ProjectRetrievalIndex).filter_by(project_id=project_id, status=_ACTIVE).one_or_none()
    if active is None:
        session.add(
            ProjectRetrievalIndex(
                project_id=project_id,
                index_version=index_version,
                parser_version=parser_version,
                embedding_provider=embedding.provider,
                embedding_model=embedding.model,
                dimensions=len(embedding.vector),
                status=_ACTIVE,
                created_by=actor_id,
                activated_at=datetime.now(UTC),
            )
        )
        return
    if active.index_version != index_version:
        append_audit_event(
            session,
            project_id=project_id,
            actor_id=actor_id,
            aggregate_type="ProjectRetrievalIndex",
            aggregate_id=active.id,
            action="SOURCE_INDEX_VERSION_REQUIRES_REBUILD",
            correlation_id=correlation_id,
            payload={"activeIndexVersion": active.index_version, "pendingIndexVersion": index_version},
        )


def list_project_retrieval_indexes(session: Session, *, project_id: UUID, actor_id: UUID) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    ready_source_count = session.query(SourceRevision).filter_by(project_id=project_id, processing_status=SourceProcessingStatus.READY).count()
    indexes = (
        session.query(ProjectRetrievalIndex)
        .filter_by(project_id=project_id)
        .order_by(ProjectRetrievalIndex.status.asc(), ProjectRetrievalIndex.activated_at.desc().nullslast(), ProjectRetrievalIndex.created_at.desc())
        .all()
    )
    response: list[dict] = []
    for item in indexes:
        source_count = (
            session.query(DocumentChunk.source_revision_id)
            .join(SourceRevision, SourceRevision.id == DocumentChunk.source_revision_id)
            .filter(SourceRevision.project_id == project_id, SourceRevision.processing_status == SourceProcessingStatus.READY)
            .filter(DocumentChunk.index_version == item.index_version)
            .distinct()
            .count()
        )
        chunk_count = (
            session.query(DocumentChunk)
            .join(SourceRevision, SourceRevision.id == DocumentChunk.source_revision_id)
            .filter(SourceRevision.project_id == project_id, DocumentChunk.index_version == item.index_version)
            .count()
        )
        response.append(
            {
                "id": item.id,
                "project_id": item.project_id,
                "index_version": item.index_version,
                "parser_version": item.parser_version,
                "embedding_provider": item.embedding_provider,
                "embedding_model": item.embedding_model,
                "dimensions": item.dimensions,
                "status": item.status,
                "ready_source_count": ready_source_count,
                "indexed_source_count": source_count,
                "indexed_chunk_count": chunk_count,
                "activated_at": item.activated_at,
                "created_at": item.created_at,
            }
        )
    return response


def start_retrieval_index_build_run(
    session: Session,
    *,
    project_id: UUID,
    actor_id: UUID,
) -> RetrievalIndexBuildRun:
    require_python_knowledge_sources(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.ADMIN})
    target_version = configured_embedding_index_version(get_settings(), _CANONICAL_PARSER_VERSION)
    run = RetrievalIndexBuildRun(
        project_id=project_id,
        target_index_version=target_version,
        status="RUNNING",
        created_by=actor_id,
    )
    session.add(run)
    session.flush()
    return run


def finish_retrieval_index_build_run(
    run: RetrievalIndexBuildRun,
    *,
    result: dict | None = None,
    error: DomainError | None = None,
) -> None:
    run.finished_at = datetime.now(UTC)
    if error is not None:
        run.status = "FAILED"
        run.error_code = error.code
        run.error_message = error.message[:500]
        return
    if result is None:
        raise ValueError("a successful retrieval-index run requires a result")
    run.status = "SUCCEEDED"
    run.source_count = result["ready_source_count"]
    run.reindexed_source_count = result["reindexed_source_count"]
    run.reindexed_chunk_count = result["reindexed_chunk_count"]


def list_retrieval_index_build_runs(session: Session, *, project_id: UUID, actor_id: UUID, limit: int = 50) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    runs = (
        session.query(RetrievalIndexBuildRun)
        .filter_by(project_id=project_id)
        .order_by(RetrievalIndexBuildRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": run.id,
            "project_id": run.project_id,
            "target_index_version": run.target_index_version,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "source_count": run.source_count,
            "reindexed_source_count": run.reindexed_source_count,
            "reindexed_chunk_count": run.reindexed_chunk_count,
            "error_code": run.error_code,
            "error_message": run.error_message,
        }
        for run in runs
    ]


def rebuild_project_retrieval_index(
    session: Session,
    *,
    project_id: UUID,
    actor_id: UUID,
    correlation_id: str,
) -> dict:
    """Build a new derived index atomically and activate it only after every source succeeds."""
    require_python_knowledge_sources(session)

    require_project_role(session, project_id, actor_id, {ProjectRole.ADMIN})
    parser = MarkdownTextDocumentParser()
    settings = get_settings()
    target_version = configured_embedding_index_version(settings, _CANONICAL_PARSER_VERSION)
    sources = (
        session.query(SourceRevision)
        .filter_by(project_id=project_id, processing_status=SourceProcessingStatus.READY)
        .with_for_update()
        .all()
    )
    if not sources:
        raise DomainError("SOURCE_NOT_READY", "当前项目没有可重建索引的 READY 资料")
    if False:  # Normalized artifacts provide a rebuildable text projection for all supported formats.
        raise DomainError("INDEX_REBUILD_UNSUPPORTED", "项目包含当前解析器版本无法重建的资料")

    storage = LocalArtifactStorage(settings.artifact_root)
    parsed_sources: list[tuple[SourceRevision, list]] = []
    for source in sources:
        try:
            parsed = parser.parse(storage.read_text(source.extracted_artifact_uri or source.artifact_uri))
        except (OSError, ValueError) as exc:
            raise DomainError("SOURCE_ARTIFACT_UNAVAILABLE", "资料原文不可读取，不能重建索引") from exc
        if not parsed:
            raise DomainError("SOURCE_EMPTY", "资料未能解析出可重建内容")
        parsed_sources.append((source, parsed))

    current_rows = (
        session.query(DocumentChunk)
        .filter(DocumentChunk.source_revision_id.in_([source.id for source in sources]), DocumentChunk.index_version == target_version)
        .all()
    )
    existing = {(row.source_revision_id, row.chunk_index): row for row in current_rows}
    missing: list[tuple[SourceRevision, int, object]] = []
    for source, chunks in parsed_sources:
        seen_indexes = set()
        for chunk_index, chunk in enumerate(chunks):
            seen_indexes.add(chunk_index)
            text_hash = f"sha256:{hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()}"
            prior = existing.get((source.id, chunk_index))
            if prior is not None:
                if prior.text_hash != text_hash or prior.content != chunk.content or prior.locator != chunk.locator:
                    raise DomainError("INDEX_STATE_INVALID", "已有派生索引与不可变资料内容不一致")
                continue
            missing.append((source, chunk_index, chunk))
        unexpected = [key for key in existing if key[0] == source.id and key[1] not in seen_indexes]
        if unexpected:
            raise DomainError("INDEX_STATE_INVALID", "已有派生索引与当前解析结果的分块数量不一致")

    reindexed_sources: set[UUID] = set()
    if missing:
        model = create_embedding_model(settings)
        for source, chunk_index, chunk in missing:
            embedding = model.embed(EmbeddingRequest(text=chunk.content, model=settings.embedding_model))
            if embedding_index_version(_CANONICAL_PARSER_VERSION, embedding) != target_version:
                raise DomainError("MODEL_SCHEMA_INVALID", "Embedding 返回的索引版本与当前运行配置不一致")
            session.add(
                DocumentChunk(
                    source_revision_id=source.id,
                    chunk_index=chunk_index,
                    content=chunk.content,
                    text_hash=f"sha256:{hashlib.sha256(chunk.content.encode('utf-8')).hexdigest()}",
                    locator=chunk.locator,
                    index_version=target_version,
                    embedding=embedding.vector,
                )
            )
            reindexed_sources.add(source.id)

    active = (
        session.query(ProjectRetrievalIndex)
        .filter_by(project_id=project_id, status=_ACTIVE)
        .with_for_update()
        .one_or_none()
    )
    target = (
        session.query(ProjectRetrievalIndex)
        .filter_by(project_id=project_id, index_version=target_version)
        .one_or_none()
    )
    if target is None:
        target = ProjectRetrievalIndex(
            project_id=project_id,
            index_version=target_version,
            parser_version=_CANONICAL_PARSER_VERSION,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            status=_HISTORICAL,
            created_by=actor_id,
        )
        session.add(target)
        session.flush()
    if active is not None and active.id != target.id:
        active.status = _HISTORICAL
        # The database guarantees one active index per project; release the old row first.
        session.flush()
    target.status = _ACTIVE
    target.activated_at = datetime.now(UTC)
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="ProjectRetrievalIndex",
        aggregate_id=target.id,
        action="PROJECT_RETRIEVAL_INDEX_REBUILT",
        correlation_id=correlation_id,
        payload={
            "indexVersion": target_version,
            "sourceCount": len(sources),
            "reindexedSourceCount": len(reindexed_sources),
            "reindexedChunkCount": len(missing),
        },
    )
    return {
        "id": target.id,
        "project_id": target.project_id,
        "index_version": target.index_version,
        "parser_version": target.parser_version,
        "embedding_provider": target.embedding_provider,
        "embedding_model": target.embedding_model,
        "dimensions": target.dimensions,
        "status": target.status,
        "ready_source_count": len(sources),
        "indexed_source_count": len(sources),
        "indexed_chunk_count": len(current_rows) + len(missing),
        "activated_at": target.activated_at,
        "created_at": target.created_at,
        "reindexed_source_count": len(reindexed_sources),
        "reindexed_chunk_count": len(missing),
    }
