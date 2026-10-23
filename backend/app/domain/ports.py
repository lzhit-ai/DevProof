from dataclasses import dataclass
from uuid import UUID

from app.domain.model_contracts import CodeReviewChallengeRequest, CodeReviewChallengeResult, CodeReviewRequest, CodeReviewResult, DeliveryClaimProposalResult, EmbeddingRequest, EmbeddingResult, EvidenceAnswerRequest, EvidenceAnswerResult, GenerationRequest, GenerationResult


@dataclass(frozen=True)
class FrozenGitRange:
    base_sha: str
    target_sha: str
    merge_base_sha: str
    diff_hash: str
    coverage: dict
    diff: bytes
    code_change_bundle: dict


@dataclass(frozen=True)
class FrozenGitDiff:
    """The exact, already-frozen diff read again by immutable commit SHA."""

    diff: str
    coverage: dict


@dataclass(frozen=True)
class ParsedDocumentChunk:
    content: str
    locator: dict


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    source_revision_id: UUID | None = None
    chunk_index: int | None = None
    fts_rank: int | None = None
    fts_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None


@dataclass(frozen=True)
class RenderedReport:
    content_hash: str


class GitReaderPort:
    """Read-only Git boundary; it never executes repository content or hooks."""

    def freeze_range(self, repository_url: str, base_ref: str, target_ref: str, diff_mode: str, include_paths: list[str], exclude_paths: list[str], credential_ref: str | None = None) -> FrozenGitRange:
        raise NotImplementedError

    def read_frozen_diff(
        self,
        repository_url: str,
        *,
        base_sha: str,
        target_sha: str,
        merge_base_sha: str,
        diff_mode: str,
        include_paths: list[str],
        exclude_paths: list[str],
        expected_diff_hash: str,
        credential_ref: str | None = None,
    ) -> FrozenGitDiff:
        """Read only an immutable SHA range and reject a changed diff payload."""
        raise NotImplementedError

    def read_frozen_blobs(
        self,
        repository_url: str,
        *,
        target_sha: str,
        paths: list[str],
        credential_ref: str | None = None,
    ) -> dict[str, bytes]:
        """Read already-cached paths from a frozen commit without any network fetch."""
        raise NotImplementedError


class GenerationModelPort:
    """Generation boundary: implementations may propose links but never final results."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise NotImplementedError

    def answer_evidence(self, request: EvidenceAnswerRequest) -> EvidenceAnswerResult:
        raise NotImplementedError

    def review_code(self, request: CodeReviewRequest) -> CodeReviewResult:
        raise NotImplementedError

    def challenge_code_findings(self, request: CodeReviewChallengeRequest) -> CodeReviewChallengeResult:
        raise NotImplementedError

    def propose_delivery_claims(self, payload: dict) -> DeliveryClaimProposalResult:
        raise NotImplementedError


class EmbeddingModelPort:
    """Embedding boundary remains independent from the generation provider."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise NotImplementedError


class DocumentParserPort:
    """Parses an allowed document format into immutable, locatable chunks."""

    def parse(self, content: str) -> list[ParsedDocumentChunk]:
        raise NotImplementedError


class ArtifactStoragePort:
    """Controlled raw-artifact boundary; database rows retain only the returned URI."""

    def write_bytes(self, namespace: list[str], filename: str, content: bytes) -> str:
        raise NotImplementedError

    def read_text(self, uri: str) -> str:
        raise NotImplementedError


class RetrieverPort:
    """Performs scoped hybrid retrieval without leaking ORM concerns to callers."""

    def search(self, *, source_revision_ids: list[UUID], query: str, limit: int, query_embedding: list[float] | None) -> list[RetrievedChunk]:
        raise NotImplementedError


class ReportRendererPort:
    """Creates a canonical, hashable representation of a report draft."""

    def render(self, *, results: list[dict], editorial_note: str, dispositions: dict[str, str | None]) -> RenderedReport:
        raise NotImplementedError
