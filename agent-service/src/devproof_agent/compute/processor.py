"""Compute actual document chunks/vectors without owning any source/job state."""

import math
import time
from collections.abc import Callable

import httpx

from devproof_agent.compute.document_parser import DocumentExtractionError, MarkdownTextDocumentParser, detect_media_type, extract_document
from devproof_agent.compute.settings import PARSER_VERSION, ComputeSettings, digest
from devproof_agent.compute.types import (
    ChunkComputation, DocumentComputation, EmbeddingBatchResult, IndexingOutcome, NormalizedChunks,
)
from devproof_agent.models import AgentError


class Computation:
    def __init__(self, settings: ComputeSettings, cancelled: Callable[[], bool]):
        self.settings = settings
        self.deadline = time.monotonic() + settings.compute_timeout_seconds
        self.cancelled = cancelled

    def remaining(self) -> float:
        if self.cancelled():
            raise AgentError("COMPUTE_CANCELLED", "调用方已停止资料计算")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentError("COMPUTE_TIMEOUT", "资料计算超过配置的时间上限")
        return remaining

    def vectors(self, texts: list[str]) -> list[list[float]]:
        settings = self.settings
        if not settings.embedding_api_key or not settings.embedding_api_key.strip():
            raise AgentError("MODEL_NOT_CONFIGURED", f"{settings.embedding_provider} Embedding 尚未配置 API Key")
        result = []
        with httpx.Client(follow_redirects=False) as client:
            for text in texts:
                timeout = min(30.0, self.remaining())
                try:
                    with client.stream("POST", settings.embedding_base_url + "/embeddings",
                        json={"model": settings.embedding_model, "input": text,
                            "dimensions": settings.embedding_dimensions, "encoding_format": "float"},
                        headers={"Authorization": "Bearer " + settings.embedding_api_key}, timeout=timeout) as response:
                        if response.is_redirect or response.is_error:
                            raise AgentError("MODEL_UNAVAILABLE", f"Embedding 调用失败（HTTP {response.status_code}）")
                        raw = bytearray()
                        for part in response.iter_bytes():
                            self.remaining()
                            raw.extend(part)
                            if len(raw) > 2 * 1024 * 1024:
                                raise AgentError("MODEL_SCHEMA_INVALID", "Embedding 响应超过允许大小")
                    import json
                    vector = json.loads(raw)["data"][0]["embedding"]
                    if (not isinstance(vector, list) or len(vector) != settings.embedding_dimensions
                        or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                            and math.isfinite(value) for value in vector)):
                        raise ValueError
                    result.append([float(value) for value in vector])
                except httpx.RequestError:
                    raise AgentError("MODEL_UNAVAILABLE", "Embedding 请求超时或连接失败") from None
                except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError):
                    raise AgentError("MODEL_SCHEMA_INVALID", "Embedding 向量维度或响应格式不兼容") from None
        self.remaining()
        return result

    def extract(self, content: bytes, filename: str, force_ocr: bool) -> DocumentComputation:
        self.remaining()
        try:
            media = detect_media_type(filename=filename, claimed_media_type=None, content=content)
            extraction = extract_document(content=content, filename=filename, media_type=media,
                force_ocr=force_ocr, settings=self.settings, remaining=self.remaining)
        except DocumentExtractionError as exc:
            raise AgentError(exc.code, exc.message) from None
        self.remaining()
        if not extraction.chunks:
            raise AgentError("SOURCE_EMPTY", "资料未能解析出可索引内容")
        metadata = {**extraction.metadata, "extractorVersion": extraction.parser_version}
        chunks = [ChunkComputation(chunkIndex=index, content=chunk.content,
            textHash=digest(chunk.content.encode("utf-8")), locator=chunk.locator, embedding=None)
            for index, chunk in enumerate(extraction.chunks)]
        outcome = IndexingOutcome(status="AVAILABLE")
        index_version = self.settings.index_version()
        try:
            vectors = self.vectors([chunk.content for chunk in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector
        except AgentError as exc:
            if exc.code not in {"MODEL_UNAVAILABLE", "MODEL_NOT_CONFIGURED"}:
                raise
            outcome = IndexingOutcome(status="UNAVAILABLE", code=exc.code, message=exc.message)
            metadata["indexing"] = outcome.model_dump()
            index_version = f"{PARSER_VERSION}|embedding:unavailable"
        return DocumentComputation(contentHash=digest(content), configurationHash=self.settings.configuration_hash(),
            mediaType=media, parserVersion=PARSER_VERSION, normalizedText=extraction.normalized_text,
            normalizedTextHash=digest(extraction.normalized_text.encode("utf-8")), metadata=metadata,
            indexVersion=index_version, indexing=outcome, chunks=chunks)

    def embed(self, texts: list[str]) -> EmbeddingBatchResult:
        return EmbeddingBatchResult(configurationHash=self.settings.configuration_hash(),
            textHashes=[digest(text.encode("utf-8")) for text in texts], vectors=self.vectors(texts))

    def rechunk(self, raw: bytes) -> NormalizedChunks:
        self.remaining()
        try:
            normalized = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise AgentError("SOURCE_ENCODING_INVALID", "规范化资料不是 UTF-8 文本") from None
        chunks = MarkdownTextDocumentParser().parse(normalized)
        self.remaining()
        if not chunks:
            raise AgentError("SOURCE_EMPTY", "资料未能解析出可重建内容")
        return NormalizedChunks(configurationHash=self.settings.configuration_hash(), normalizedTextHash=digest(raw),
            chunks=[ChunkComputation(chunkIndex=i, content=chunk.content, textHash=digest(chunk.content.encode("utf-8")),
                locator=chunk.locator, embedding=None) for i,chunk in enumerate(chunks)])
