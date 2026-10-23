from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行时配置；密钥采用注入方式，而非提交入库。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DevProof"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://ai_codereview:ai_codereview@postgres:5432/ai_codereview"
    artifact_root: str = "/artifacts"
    jwt_secret: str = Field(min_length=32)
    jwt_access_ttl_seconds: int = Field(default=28800, ge=300, le=86_400)
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    worker_id: str = "worker-1"
    job_lease_seconds: int = Field(default=60, ge=15, le=300)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    generation_provider: str = "deepseek"
    generation_model: str = "deepseek-v4-flash"
    generation_base_url: str = "https://api.deepseek.com"
    generation_api_key: str | None = None
    embedding_provider: str = "dashscope"
    embedding_model: str = "text-embedding-v4"
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str | None = None
    embedding_dimensions: int = Field(default=768, ge=1, le=8192)
    agent_tool_allowed_hosts: list[str] = Field(default_factory=list)
    agent_tool_timeout_seconds: int = Field(default=10, ge=1, le=30)
    agent_tool_response_limit_bytes: int = Field(default=262_144, ge=4_096, le=1_048_576)
    github_sync_timeout_seconds: int = Field(default=15, ge=1, le=30)
    github_sync_response_limit_bytes: int = Field(default=2_097_152, ge=65_536, le=8_388_608)
    source_max_bytes: int = Field(default=100 * 1024 * 1024, ge=1_048_576, le=524_288_000)
    # MinerU 在线解析。
    mineru_api_base_url: str = "https://mineru.net"
    mineru_api_token: str | None = None
    mineru_model_version: str = "pipeline"  # 模型版本：pipeline | vlm | MinerU-HTML
    mineru_force_ocr: bool = True  # 是否强制 OCR（is_ocr）
    mineru_language: str = "ch"
    mineru_timeout_seconds: int = Field(default=300, ge=60, le=1800)
    mineru_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    mineru_result_max_bytes: int = Field(default=32 * 1024 * 1024, ge=1_048_576, le=128 * 1024 * 1024)
    code_review_context_max_file_bytes: int = Field(default=262_144, ge=4_096, le=2_097_152)
    code_review_context_max_total_bytes: int = Field(default=1_048_576, ge=65_536, le=8_388_608)
    code_review_context_max_related_symbols: int = Field(default=12, ge=1, le=50)
    code_review_context_max_supplement_requests: int = Field(default=5, ge=1, le=20)
    git_command_timeout_seconds: int = Field(default=60, ge=5, le=300)
    git_ssh_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    git_repository_cache_ttl_hours: int = Field(default=168, ge=1, le=2_160)
    git_repository_cache_max_usage_percent: int = Field(default=80, ge=50, le=95)
    code_review_input_char_budget: int = Field(default=96_000, ge=8_000, le=400_000)
    code_review_challenge_max_findings: int = Field(default=30, ge=1, le=100)
    code_review_challenge_input_char_budget: int = Field(default=64_000, ge=8_000, le=400_000)
    code_review_challenge_timeout_seconds: int = Field(default=60, ge=5, le=180)


@lru_cache
def get_settings() -> Settings:
    return Settings()
