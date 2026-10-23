"""Versioned read-only Git computation. No business identifiers are looked up here."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from devproof_agent.compute.settings import digest


class GitSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)

    repository_cache_root: str = "/repository-cache"
    git_capture_timeout_seconds: int = Field(default=90, ge=10, le=600)
    git_command_timeout_seconds: int = Field(default=60, ge=5, le=300)
    git_ssh_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    git_diff_max_bytes: int = Field(default=16 * 1024 * 1024, ge=65536, le=67108864)
    git_tree_max_bytes: int = Field(default=8 * 1024 * 1024, ge=65536, le=33554432)
    git_credential_refs: str = "GITHUB_SOURCE_TOKEN"
    code_review_context_max_file_bytes: int = Field(default=262144, ge=4096, le=2097152)
    code_review_context_max_total_bytes: int = Field(default=1048576, ge=65536, le=8388608)
    code_review_context_max_related_symbols: int = Field(default=12, ge=1, le=50)

    def configuration(self) -> dict:
        from importlib.metadata import version
        return {"schemaVersion": "git-compute-configuration-v1", "captureVersion": "git-capture-v4",
            "syntaxVersion": "tree-sitter-language-pack:" + version("tree-sitter-language-pack") + "|tree-sitter:" + version("tree-sitter"),
            "syntaxLanguages": ["java", "python", "javascript", "typescript", "tsx"],
            "timeoutSeconds": self.git_capture_timeout_seconds, "commandTimeoutSeconds": self.git_command_timeout_seconds,
            "sshConnectTimeoutSeconds": self.git_ssh_connect_timeout_seconds,
            "diffMaxBytes": self.git_diff_max_bytes, "treeMaxBytes": self.git_tree_max_bytes,
            "contextMaxFileBytes": self.code_review_context_max_file_bytes,
            "contextMaxTotalBytes": self.code_review_context_max_total_bytes,
            "contextMaxRelatedSymbols": self.code_review_context_max_related_symbols}

    def configuration_hash(self) -> str:
        import json
        return digest(json.dumps(self.configuration(), ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8"))


class GitRange(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    configurationHash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    baseRef: str = Field(min_length=1, max_length=255)
    targetRef: str = Field(min_length=1, max_length=255)
    diffMode: Literal["TWO_DOT", "THREE_DOT"]
    includePaths: list[str] = Field(default_factory=list, max_length=100)
    excludePaths: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("baseRef", "targetRef")
    @classmethod
    def ref(cls, value: str) -> str:
        if value.startswith("-") or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid Git revision")
        return value

    @field_validator("includePaths", "excludePaths")
    @classmethod
    def paths(cls, values: list[str]) -> list[str]:
        if any(not path or len(path) > 1000 or any(c in path for c in ("\x00", "\n", "\r")) for path in values):
            raise ValueError("Invalid Git pathspec")
        return values


class GitCaptureRequest(GitRange):
    schemaVersion: Literal["git-capture-request-v1"]
    projectId: UUID
    repositoryId: UUID
    repositoryUrl: str = Field(min_length=8, max_length=2000)
    credentialRef: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,159}$")


class GitCaptureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schemaVersion: Literal["git-capture-result-v1"] = "git-capture-result-v1"
    requestHash: str
    configurationHash: str
    baseSha: str
    targetSha: str
    mergeBaseSha: str
    effectiveBaseSha: str
    diffHash: str
    diffBase64: str
    bundleJson: str
    bundleHash: str
    coverage: dict
