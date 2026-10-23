from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.ports import RetrievedChunk, RetrieverPort
from app.infrastructure.persistence.models import DocumentChunk


class PostgresHybridRetriever(RetrieverPort):
    """PostgreSQL FTS plus pgvector adapter, constrained by source revision IDs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, *, source_revision_ids, query: str, limit: int, query_embedding: list[float] | None, embedding_index_version: str | None = None) -> list[RetrievedChunk]:
        tsquery = func.websearch_to_tsquery("simple", query)
        tsvector = func.to_tsvector("simple", DocumentChunk.content)
        rank = func.ts_rank_cd(tsvector, tsquery).label("fts_rank")
        candidates: dict[tuple, RetrievedChunk] = {}
        fts_rows = self._session.query(DocumentChunk, rank).filter(
            DocumentChunk.source_revision_id.in_(source_revision_ids),
            tsvector.op("@@")(tsquery),
        ).order_by(rank.desc()).limit(limit * 12).all()
        for chunk, score in fts_rows:
            identity = (chunk.source_revision_id, chunk.chunk_index)
            if identity in candidates:
                continue
            candidates[identity] = RetrievedChunk(
                chunk_id=chunk.id,
                source_revision_id=chunk.source_revision_id,
                chunk_index=chunk.chunk_index,
                fts_rank=len(candidates) + 1,
                fts_score=float(score or 0),
            )
            if len(candidates) >= limit * 3:
                break

        if query_embedding is not None:
            distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
            vector_query = self._session.query(DocumentChunk, distance).filter(
                DocumentChunk.source_revision_id.in_(source_revision_ids),
                DocumentChunk.embedding.is_not(None),
            )
            if embedding_index_version is not None:
                vector_query = vector_query.filter(DocumentChunk.index_version == embedding_index_version)
            vector_rows = vector_query.order_by(distance).limit(limit * 12).all()
            vector_position = 0
            for chunk, score in vector_rows:
                identity = (chunk.source_revision_id, chunk.chunk_index)
                prior = candidates.get(identity)
                if prior is not None and prior.vector_rank is not None:
                    continue
                vector_position += 1
                candidates[identity] = RetrievedChunk(
                    chunk_id=chunk.id,
                    source_revision_id=chunk.source_revision_id,
                    chunk_index=chunk.chunk_index,
                    fts_rank=prior.fts_rank if prior else None,
                    fts_score=prior.fts_score if prior else None,
                    vector_rank=vector_position,
                    vector_score=1 - float(score or 1),
                )
                if vector_position >= limit * 3:
                    break

        if not candidates:
            needle = query.lower()
            for chunk in self._session.query(DocumentChunk).filter(DocumentChunk.source_revision_id.in_(source_revision_ids)).all():
                if needle in chunk.content.lower():
                    identity = (chunk.source_revision_id, chunk.chunk_index)
                    candidates.setdefault(
                        identity,
                        RetrievedChunk(
                            chunk_id=chunk.id,
                            source_revision_id=chunk.source_revision_id,
                            chunk_index=chunk.chunk_index,
                            fts_rank=1,
                            fts_score=0.0,
                        ),
                    )
        return list(candidates.values())
