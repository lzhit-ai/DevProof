from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ModelLinkProposal(BaseModel):
    claim_id: UUID
    evidence_id: UUID
    relation: Literal["SUPPORTS", "CONTRADICTS", "CONTEXT_ONLY"]
    rationale: str = Field(min_length=1, max_length=1000)


class CodeContextRequestProposal(BaseModel):
    """A request can select only a deterministic, SHA-bound candidate prepared by the program."""

    claim_id: UUID
    candidate_id: str = Field(min_length=8, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class ModelProposalBatch(BaseModel):
    proposals: list[ModelLinkProposal] = Field(default_factory=list, max_length=100)
    context_requests: list[CodeContextRequestProposal] = Field(default_factory=list, max_length=20)


class CodeReviewFindingProposal(BaseModel):
    evidence_id: UUID
    related_claim_ids: list[UUID] = Field(default_factory=list, max_length=20)
    finding_kind: Literal["BUG", "SECURITY", "PERFORMANCE", "RELIABILITY", "MAINTAINABILITY", "TEST_GAP"]
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    title: str = Field(min_length=1, max_length=240)
    problem: str = Field(min_length=1, max_length=4000)
    trigger_scenario: str = Field(min_length=1, max_length=3000)
    recommendation: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)


class CodeReviewFindingBatch(BaseModel):
    findings: list[CodeReviewFindingProposal] = Field(default_factory=list, max_length=100)


class CodeReviewFindingChallengeProposal(BaseModel):
    finding_id: UUID
    verdict: Literal["SUPPORTED", "UNSUPPORTED", "NEEDS_HUMAN"]
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=20)


class CodeReviewFindingChallengeBatch(BaseModel):
    challenges: list[CodeReviewFindingChallengeProposal] = Field(default_factory=list, max_length=100)


class DeliveryClaimCandidate(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)


class DeliveryClaimCandidateBatch(BaseModel):
    claims: list[DeliveryClaimCandidate] = Field(default_factory=list, max_length=12)


@dataclass(frozen=True)
class GenerationRequest:
    run_id: UUID
    prompt_version: str
    schema_version: str
    claims: list[dict]
    evidence: list[dict]
    instruction: str = ""
    operation: str = "LINK_PROPOSAL"
    temporary_context: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    model: str
    attempts: int
    latency_ms: int
    proposals: ModelProposalBatch


@dataclass(frozen=True)
class CodeReviewRequest:
    run_id: UUID
    prompt_version: str
    schema_version: str
    claims: list[dict]
    code_changes: list[dict]


@dataclass(frozen=True)
class CodeReviewResult:
    provider: str
    model: str
    attempts: int
    latency_ms: int
    findings: CodeReviewFindingBatch


@dataclass(frozen=True)
class CodeReviewChallengeRequest:
    run_id: UUID
    prompt_version: str
    schema_version: str
    claims: list[dict]
    code_changes: list[dict]
    findings: list[dict]
    timeout_seconds: int = 60


@dataclass(frozen=True)
class CodeReviewChallengeResult:
    provider: str
    model: str
    attempts: int
    latency_ms: int
    challenges: CodeReviewFindingChallengeBatch


@dataclass(frozen=True)
class DeliveryClaimProposalResult:
    provider: str
    model: str
    attempts: int
    latency_ms: int
    claims: DeliveryClaimCandidateBatch


@dataclass(frozen=True)
class EmbeddingRequest:
    text: str
    model: str


@dataclass(frozen=True)
class EmbeddingResult:
    provider: str
    model: str
    vector: list[float]


class EvidenceAnswerPayload(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    fact_status: Literal["CONFIRMED", "PARTIALLY_SUPPORTED", "CONFLICTING", "INSUFFICIENT_EVIDENCE", "INFERENCE_REQUIRES_CONFIRMATION"]


@dataclass(frozen=True)
class EvidenceAnswerRequest:
    question: str
    prompt_version: str
    schema_version: str
    evidence: list[dict]


@dataclass(frozen=True)
class EvidenceAnswerResult:
    provider: str
    model: str
    attempts: int
    latency_ms: int
    payload: EvidenceAnswerPayload
