"""Regression coverage for project-scoped derived retrieval-index activation."""

import unittest
from uuid import uuid4

from app.application.services.retrieval_index_service import (
    active_index_version,
    ensure_initial_retrieval_index,
    finish_retrieval_index_build_run,
)
from app.core.config import Settings
from app.domain.errors import DomainError
from app.domain.model_contracts import EmbeddingResult
from app.infrastructure.embedding_model import configured_embedding_index_version
from app.infrastructure.persistence.models import AuditEvent, ProjectRetrievalIndex, RetrievalIndexBuildRun


class _Query:
    def __init__(self, result):
        self._result = result

    def filter_by(self, **_kwargs):
        return self

    def one_or_none(self):
        return self._result


class _Session:
    def __init__(self, active=None):
        self.active = active
        self.added = []

    def query(self, _model):
        return _Query(self.active)

    def add(self, item):
        self.added.append(item)


class RetrievalIndexPolicyTests(unittest.TestCase):
    def test_runtime_index_version_uses_the_configured_provider_model_and_dimension(self) -> None:
        settings = Settings(
            jwt_secret="test-only-jwt-secret-with-at-least-32-characters",
            embedding_provider="dashscope",
            embedding_model="text-embedding-v4",
        )
        self.assertEqual(
            configured_embedding_index_version(settings, "markdown-text-v1"),
            "markdown-text-v1|embedding:dashscope:text-embedding-v4:d768",
        )

    def test_first_ready_source_seeds_the_active_index(self) -> None:
        session = _Session()
        project_id = uuid4()
        actor_id = uuid4()
        ensure_initial_retrieval_index(
            session,
            project_id=project_id,
            index_version="markdown-text-v1|embedding:dashscope:text-embedding-v4:d768",
            parser_version="markdown-text-v1",
            embedding=EmbeddingResult(provider="dashscope", model="text-embedding-v4", vector=[0.0] * 768),
            actor_id=actor_id,
            correlation_id="test-correlation",
        )

        index = session.added[0]
        self.assertIsInstance(index, ProjectRetrievalIndex)
        self.assertEqual(index.status, "ACTIVE")
        self.assertEqual(index.project_id, project_id)
        self.assertEqual(index.dimensions, 768)

    def test_new_provider_does_not_silently_replace_an_existing_active_index(self) -> None:
        active = ProjectRetrievalIndex(
            id=uuid4(),
            project_id=uuid4(),
            index_version="markdown-text-v1|embedding:siliconflow:BAAI/bge-m3:d768",
            parser_version="markdown-text-v1",
            embedding_provider="siliconflow",
            embedding_model="BAAI/bge-m3",
            dimensions=768,
            status="ACTIVE",
            created_by=uuid4(),
        )
        session = _Session(active)
        ensure_initial_retrieval_index(
            session,
            project_id=active.project_id,
            index_version="markdown-text-v1|embedding:dashscope:text-embedding-v4:d768",
            parser_version="markdown-text-v1",
            embedding=EmbeddingResult(provider="dashscope", model="text-embedding-v4", vector=[0.0] * 768),
            actor_id=uuid4(),
            correlation_id="test-correlation",
        )

        self.assertEqual(active.status, "ACTIVE")
        self.assertEqual(len([item for item in session.added if isinstance(item, ProjectRetrievalIndex)]), 0)
        self.assertIsInstance(session.added[0], AuditEvent)
        self.assertEqual(session.added[0].action, "SOURCE_INDEX_VERSION_REQUIRES_REBUILD")
        self.assertEqual(active_index_version(session, project_id=active.project_id), active.index_version)

    def test_rebuild_run_keeps_a_safe_failure_or_success_summary(self) -> None:
        failed = RetrievalIndexBuildRun(project_id=uuid4(), target_index_version="index-v1", created_by=uuid4())
        finish_retrieval_index_build_run(failed, error=DomainError("MODEL_UNAVAILABLE", "模型当前不可用"))
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.error_code, "MODEL_UNAVAILABLE")

        succeeded = RetrievalIndexBuildRun(project_id=uuid4(), target_index_version="index-v2", created_by=uuid4())
        finish_retrieval_index_build_run(
            succeeded,
            result={"ready_source_count": 2, "reindexed_source_count": 1, "reindexed_chunk_count": 3},
        )
        self.assertEqual(succeeded.status, "SUCCEEDED")
        self.assertEqual((succeeded.source_count, succeeded.reindexed_source_count, succeeded.reindexed_chunk_count), (2, 1, 3))
