from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class ParsedDocumentChunk:
    content: str
    locator: dict


class DocumentParserPort:
    def parse(self, text: str) -> list[ParsedDocumentChunk]:
        raise NotImplementedError


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmbeddingConfiguration(WireModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=255)
    baseUrl: str = Field(min_length=1)
    dimensions: int = Field(ge=1, le=8192)


class ParserConfiguration(WireModel):
    parserVersion: str
    mineruBaseUrl: str
    mineruModelVersion: str
    mineruLanguage: str
    mineruTimeoutSeconds: int
    mineruPollIntervalSeconds: int
    mineruResultMaxBytes: int


class ComputeConfiguration(WireModel):
    schemaVersion: Literal["compute-configuration-v1"] = "compute-configuration-v1"
    parser: ParserConfiguration
    embedding: EmbeddingConfiguration
    sourceMaxBytes: int
    resultMaxBytes: int
    timeoutSeconds: int


class ConfigurationResponse(WireModel):
    configuration: ComputeConfiguration
    configurationHash: str
    embeddingCredentialConfigured: bool
    mineruCredentialConfigured: bool
    supportedExtensions: list[str]


class DocumentInspection(WireModel):
    schemaVersion: Literal["document-inspection-v1"] = "document-inspection-v1"
    contentHash: str
    mediaType: str
    byteSize: int


class ChunkComputation(WireModel):
    chunkIndex: int = Field(ge=0)
    content: str
    textHash: str
    locator: dict[str, Any]
    embedding: list[float] | None


class IndexingOutcome(WireModel):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    code: str | None = None
    message: str | None = None


class DocumentComputation(WireModel):
    schemaVersion: Literal["document-computation-v1"] = "document-computation-v1"
    contentHash: str
    configurationHash: str
    mediaType: str
    parserVersion: str
    normalizedText: str
    normalizedTextHash: str
    metadata: dict[str, Any]
    ocrConfidence: None = None
    indexVersion: str
    indexing: IndexingOutcome
    chunks: list[ChunkComputation] = Field(min_length=1)


class EmbeddingBatchRequest(WireModel):
    schemaVersion: Literal["embedding-batch-request-v1"] = "embedding-batch-request-v1"
    configurationHash: str
    texts: list[str] = Field(min_length=1)


class EmbeddingBatchResult(WireModel):
    schemaVersion: Literal["embedding-batch-result-v1"] = "embedding-batch-result-v1"
    configurationHash: str
    textHashes: list[str]
    vectors: list[list[float]]


class NormalizedChunks(WireModel):
    schemaVersion: Literal["normalized-chunks-v1"] = "normalized-chunks-v1"
    configurationHash: str
    normalizedTextHash: str
    chunks: list[ChunkComputation] = Field(min_length=1)
