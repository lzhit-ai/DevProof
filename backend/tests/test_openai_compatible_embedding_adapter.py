"""Unit coverage for the config-driven OpenAI-compatible embedding adapter."""

import json
import unittest
from unittest import mock

from app.domain.errors import DomainError
from app.domain.model_contracts import EmbeddingRequest
from app.infrastructure.embedding_model import (
    OpenAICompatibleEmbeddingAdapter,
    create_embedding_model,
)
from app.core.config import Settings


class _Response:
    def __init__(self, body: dict) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return json.dumps(self._body, ensure_ascii=False).encode("utf-8")


class OpenAICompatibleEmbeddingAdapterTests(unittest.TestCase):
    def _request(self) -> EmbeddingRequest:
        return EmbeddingRequest(text="示例文本 sample text", model="text-embedding-v4")

    def test_valid_dimension_vector_is_returned(self) -> None:
        with mock.patch("app.infrastructure.embedding_model.urlopen", return_value=_Response({"data": [{"embedding": [0.0] * 768}]})):
            adapter = OpenAICompatibleEmbeddingAdapter("sk-test", "text-embedding-v4", "https://example.com/v1", "dashscope", 768)
            result = adapter.embed(self._request())
        self.assertEqual(result.provider, "dashscope")
        self.assertEqual(result.model, "text-embedding-v4")
        self.assertEqual(len(result.vector), 768)

    def test_wrong_dimension_vector_is_rejected(self) -> None:
        with mock.patch("app.infrastructure.embedding_model.urlopen", return_value=_Response({"data": [{"embedding": [0.0] * 1024}]})):
            adapter = OpenAICompatibleEmbeddingAdapter("sk-test", "BAAI/bge-m3", "https://example.com/v1", "siliconflow", 768)
            with self.assertRaises(DomainError) as ctx:
                adapter.embed(self._request())
        self.assertEqual(ctx.exception.code, "MODEL_SCHEMA_INVALID")

    def test_non_https_base_url_is_rejected_at_construction(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            OpenAICompatibleEmbeddingAdapter("sk-test", "x", "http://example.com/v1", "siliconflow", 768)
        self.assertEqual(ctx.exception.code, "MODEL_NOT_CONFIGURED")

    def test_create_unknown_provider_without_key_is_rejected(self) -> None:
        settings = Settings(
            jwt_secret="test-only-jwt-secret-with-at-least-32-characters",
            embedding_provider="siliconflow",
            embedding_api_key=None,
        )
        with self.assertRaises(DomainError) as ctx:
            create_embedding_model(settings)
        self.assertEqual(ctx.exception.code, "MODEL_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
