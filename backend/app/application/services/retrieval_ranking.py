"""Deterministic, explainable ranking for frozen-document retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.ports import RetrievedChunk


RRF_K = 60
RRF_WEIGHT = 0.75
SOURCE_ROLE_WEIGHT = 0.15
EVIDENCE_QUALITY_WEIGHT = 0.10


@dataclass(frozen=True)
class RankingSignals:
    rrf_score: float
    normalized_rrf_score: float
    source_role_match: float
    evidence_quality: float
    final_score: float


def rank_candidates(
    candidates: list[RetrievedChunk],
    *,
    source_roles: dict[UUID, str],
    preferred_source_roles: list[str],
    evidence_metadata: dict[UUID, tuple[str, float | None]],
) -> dict[UUID, RankingSignals]:
    """Combine rank-only retrieval with auditable metadata signals.

    The raw FTS/vector scores are intentionally not mixed: they are generated
    on different scales.  RRF consumes only their positions, then the small
    business layer adds explicit source-role and evidence-quality signals.
    """
    rrf_scores = {candidate.chunk_id: _rrf_score(candidate) for candidate in candidates}
    max_rrf = max(rrf_scores.values(), default=0.0)
    requested_roles = {
        _normalize_role(role) for role in preferred_source_roles if _normalize_role(role)
    }
    ranked: dict[UUID, RankingSignals] = {}
    for candidate in candidates:
        rrf_score = rrf_scores[candidate.chunk_id]
        normalized_rrf = rrf_score / max_rrf if max_rrf else 0.0
        source_role = source_roles.get(candidate.source_revision_id, "")
        role_match = (
            1.0 if requested_roles and _normalize_role(source_role) in requested_roles else 0.0
        )
        precision, ocr_confidence = evidence_metadata.get(
            candidate.chunk_id, ("UNAVAILABLE", None)
        )
        evidence_quality = _evidence_quality(precision, ocr_confidence)
        final_score = (
            RRF_WEIGHT * normalized_rrf
            + SOURCE_ROLE_WEIGHT * role_match
            + EVIDENCE_QUALITY_WEIGHT * evidence_quality
        )
        ranked[candidate.chunk_id] = RankingSignals(
            rrf_score=rrf_score,
            normalized_rrf_score=normalized_rrf,
            source_role_match=role_match,
            evidence_quality=evidence_quality,
            final_score=final_score,
        )
    return ranked


def ranking_reasons(
    *,
    candidate: RetrievedChunk,
    source_role: str,
    preferred_source_roles: list[str],
    precision: str,
    ocr_confidence: float | None,
) -> list[str]:
    reasons = [
        "双路召回命中" if candidate.fts_rank and candidate.vector_rank else "单路召回命中"
    ]
    requested_roles = {
        _normalize_role(role) for role in preferred_source_roles if _normalize_role(role)
    }
    if requested_roles:
        reasons.append(
            "匹配指定资料角色"
            if _normalize_role(source_role) in requested_roles
            else "未匹配指定资料角色"
        )
    precision_label = {
        "EXACT": "精确定位",
        "APPROXIMATE": "近似定位",
        "UNAVAILABLE": "定位不可用",
    }.get(precision, "定位不可用")
    extraction_label = (
        "未提供 OCR 置信度，不降权"
        if ocr_confidence is None
        else f"OCR 置信度 {max(0.0, min(1.0, ocr_confidence)):.2f}"
    )
    reasons.append(f"证据质量：{precision_label}；{extraction_label}")
    return reasons


def _rrf_score(candidate: RetrievedChunk) -> float:
    return sum(
        1 / (RRF_K + rank)
        for rank in (candidate.fts_rank, candidate.vector_rank)
        if rank is not None
    )


def _evidence_quality(precision: str, ocr_confidence: float | None) -> float:
    precision_score = {"EXACT": 1.0, "APPROXIMATE": 0.5, "UNAVAILABLE": 0.0}.get(
        precision, 0.0
    )
    extraction_score = 1.0 if ocr_confidence is None else max(0.0, min(1.0, ocr_confidence))
    return 0.6 * precision_score + 0.4 * extraction_score


def _normalize_role(role: str) -> str:
    return role.strip().casefold()
