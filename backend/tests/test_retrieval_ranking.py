"""Regression coverage for deterministic hybrid retrieval fusion."""

import unittest
from uuid import uuid4

from app.application.services.retrieval_ranking import rank_candidates, ranking_reasons
from app.domain.ports import RetrievedChunk


class RetrievalRankingTests(unittest.TestCase):
    def test_rrf_rewards_a_chunk_found_by_both_retrievers(self) -> None:
        both = RetrievedChunk(
            chunk_id=uuid4(), source_revision_id=uuid4(), fts_rank=2, vector_rank=1
        )
        lexical_only = RetrievedChunk(chunk_id=uuid4(), source_revision_id=uuid4(), fts_rank=1)

        ranked = rank_candidates(
            [both, lexical_only],
            source_roles={},
            preferred_source_roles=[],
            evidence_metadata={
                both.chunk_id: ("EXACT", None),
                lexical_only.chunk_id: ("EXACT", None),
            },
        )

        self.assertGreater(
            ranked[both.chunk_id].rrf_score, ranked[lexical_only.chunk_id].rrf_score
        )
        self.assertGreater(
            ranked[both.chunk_id].final_score, ranked[lexical_only.chunk_id].final_score
        )

    def test_explicit_source_role_preference_can_break_a_close_rrf_tie(self) -> None:
        requirement_source = uuid4()
        design_source = uuid4()
        requirement = RetrievedChunk(
            chunk_id=uuid4(), source_revision_id=requirement_source, fts_rank=2
        )
        design = RetrievedChunk(chunk_id=uuid4(), source_revision_id=design_source, fts_rank=1)

        ranked = rank_candidates(
            [requirement, design],
            source_roles={requirement_source: "需求", design_source: "设计"},
            preferred_source_roles=["需求"],
            evidence_metadata={
                requirement.chunk_id: ("EXACT", None),
                design.chunk_id: ("EXACT", None),
            },
        )

        self.assertEqual(ranked[requirement.chunk_id].source_role_match, 1.0)
        self.assertEqual(ranked[design.chunk_id].source_role_match, 0.0)
        self.assertGreater(
            ranked[requirement.chunk_id].final_score,
            ranked[design.chunk_id].final_score,
        )

    def test_evidence_quality_uses_locator_precision_and_available_ocr_confidence(self) -> None:
        exact = RetrievedChunk(chunk_id=uuid4(), source_revision_id=uuid4(), fts_rank=1)
        approximate = RetrievedChunk(chunk_id=uuid4(), source_revision_id=uuid4(), fts_rank=1)

        ranked = rank_candidates(
            [exact, approximate],
            source_roles={},
            preferred_source_roles=[],
            evidence_metadata={
                exact.chunk_id: ("EXACT", None),
                approximate.chunk_id: ("APPROXIMATE", 0.5),
            },
        )

        self.assertEqual(ranked[exact.chunk_id].evidence_quality, 1.0)
        self.assertEqual(ranked[approximate.chunk_id].evidence_quality, 0.5)
        self.assertIn(
            "双路召回命中",
            ranking_reasons(
                candidate=RetrievedChunk(chunk_id=uuid4(), fts_rank=1, vector_rank=1),
                source_role="需求",
                preferred_source_roles=["需求"],
                precision="EXACT",
                ocr_confidence=None,
            ),
        )
