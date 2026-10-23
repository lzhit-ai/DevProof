import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.core.config import Settings
from app.domain.errors import DomainError
from app.domain.model_contracts import EmbeddingRequest, EmbeddingResult
from app.domain.ports import EmbeddingModelPort


class OpenAICompatibleEmbeddingAdapter(EmbeddingModelPort):
    """Bounded OpenAI-compatible adapter for any provider exposing POST /embeddings."""

    def __init__(self, api_key: str, model: str, base_url: str, provider: str, dimensions: int) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise DomainError("MODEL_NOT_CONFIGURED", f"{provider} Embedding 地址必须是 HTTPS URL")
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._dimensions = dimensions
        self._endpoint = f"{base_url.rstrip('/')}/embeddings"

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        payload = {
            "model": self._model,
            "input": request.text,
            "dimensions": self._dimensions,
            "encoding_format": "float",
        }
        http_request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            vector = body["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DomainError("MODEL_SCHEMA_INVALID", f"{self._provider} Embedding 返回格式无效") from exc
        except HTTPError as exc:
            raise DomainError("MODEL_UNAVAILABLE", f"{self._provider} Embedding 调用失败（HTTP {exc.code}）") from exc
        except (URLError, TimeoutError) as exc:
            raise DomainError("MODEL_UNAVAILABLE", f"{self._provider} Embedding 当前不可用") from exc
        if (
            not isinstance(vector, list)
            or len(vector) != self._dimensions
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector)
        ):
            raise DomainError("MODEL_SCHEMA_INVALID", "Embedding 向量维度或数据类型与 pgvector 索引不兼容")
        return EmbeddingResult(provider=self._provider, model=self._model, vector=[float(value) for value in vector])


def embedding_index_version(parser_version: str, result: EmbeddingResult) -> str:
    return f"{parser_version}|embedding:{result.provider}:{result.model}:d{len(result.vector)}"


def configured_embedding_index_version(settings: Settings, parser_version: str) -> str:
    """The only vector index version a configured runtime may activate."""

    return f"{parser_version}|embedding:{settings.embedding_provider}:{settings.embedding_model}:d{settings.embedding_dimensions}"


def create_embedding_model(settings: Settings) -> EmbeddingModelPort:
    if not settings.embedding_api_key:
        raise DomainError("MODEL_NOT_CONFIGURED", f"{settings.embedding_provider} Embedding 尚未配置 API Key")
    return OpenAICompatibleEmbeddingAdapter(
        settings.embedding_api_key,
        settings.embedding_model,
        settings.embedding_base_url,
        settings.embedding_provider,
        settings.embedding_dimensions,
    )
