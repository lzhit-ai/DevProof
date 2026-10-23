import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from devproof_agent.compute.types import ComputeConfiguration, EmbeddingConfiguration, ParserConfiguration

PARSER_VERSION = "knowledge-extraction-v1"


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class ComputeSettings(BaseSettings):
    # Read only declared compute settings from process environment. No .env/DB access.
    model_config = SettingsConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)

    compute_service_token: str = Field(min_length=32, repr=False)
    compute_timeout_seconds: int = Field(default=1800, ge=60, le=7200)
    compute_result_max_bytes: int = Field(default=256 * 1024 * 1024, ge=1048576, le=1073741824)
    compute_concurrency: int = Field(default=1, ge=1, le=8)
    source_max_bytes: int = Field(default=100 * 1024 * 1024, ge=1048576, le=524288000)
    embedding_provider: str = Field(default="dashscope", min_length=1, max_length=64)
    embedding_model: str = Field(default="text-embedding-v4", min_length=1, max_length=255)
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str | None = Field(default=None, repr=False)
    embedding_dimensions: int = Field(default=768, ge=1, le=8192)
    mineru_api_base_url: str = "https://mineru.net"
    mineru_api_token: str | None = Field(default=None, repr=False)
    mineru_model_version: Literal["pipeline", "vlm", "MinerU-HTML"] = "pipeline"
    mineru_force_ocr: bool = True
    mineru_language: str = "ch"
    mineru_timeout_seconds: int = Field(default=300, ge=60, le=1800)
    mineru_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    mineru_result_max_bytes: int = Field(default=32 * 1024 * 1024, ge=1048576, le=134217728)

    @field_validator("embedding_base_url", "mineru_api_base_url")
    @classmethod
    def provider_url(cls, value: str) -> str:
        from urllib.parse import urlsplit
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Compute provider URL must be HTTPS without credentials/query/fragment")
        return value.rstrip("/")

    def configuration(self) -> ComputeConfiguration:
        return ComputeConfiguration(
            parser=ParserConfiguration(parserVersion=PARSER_VERSION, mineruBaseUrl=self.mineru_api_base_url,
                mineruModelVersion=self.mineru_model_version, mineruLanguage=self.mineru_language,
                mineruTimeoutSeconds=self.mineru_timeout_seconds,
                mineruPollIntervalSeconds=self.mineru_poll_interval_seconds, mineruResultMaxBytes=self.mineru_result_max_bytes),
            embedding=EmbeddingConfiguration(provider=self.embedding_provider, model=self.embedding_model,
                baseUrl=self.embedding_base_url, dimensions=self.embedding_dimensions),
            sourceMaxBytes=self.source_max_bytes, resultMaxBytes=self.compute_result_max_bytes,
            timeoutSeconds=self.compute_timeout_seconds,
        )

    def configuration_hash(self) -> str:
        raw = json.dumps(self.configuration().model_dump(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")
        return digest(raw)

    def index_version(self) -> str:
        return f"{PARSER_VERSION}|embedding:{self.embedding_provider}:{self.embedding_model}:d{self.embedding_dimensions}"
