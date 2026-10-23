"""Versioned Java/Worker wire contracts. These types confer no authorization.

    The receiving service must validate each reference against its current task,
    lease, frozen input and registered manifest before accepting an operation.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)
from pydantic.alias_generators import to_camel


ContentHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TaskKind = Literal["DELIVERY_VERIFY", "PLAN_DRAFT", "PLAN_REFINE", "DELIVERY_CLAIM_PROPOSE", "EVIDENCE_QUESTION"]


class WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class VerificationRunRef(WireModel):
    kind: Literal["ANALYSIS_RUN"]
    id: UUID


class PlanningRunRef(WireModel):
    kind: Literal["PLANNING_RUN"]
    id: UUID


class ClaimProposalRunRef(WireModel):
    kind: Literal["CLAIM_PROPOSAL_RUN"]
    id: UUID


class EvidenceQuestionRunRef(WireModel):
    kind: Literal["EVIDENCE_QUESTION_RUN"]
    id: UUID


BusinessRef = Annotated[
    VerificationRunRef | PlanningRunRef | ClaimProposalRunRef | EvidenceQuestionRunRef,
    Field(discriminator="kind"),
]


class FrozenInputRef(WireModel):
    kind: Literal["VERIFICATION", "PLANNING", "CLAIM_PROPOSAL", "EVIDENCE_QUESTION"]
    id: UUID
    content_hash: ContentHash
    schema_version: NonEmpty


class PlanVersionRef(WireModel):
    id: UUID
    content_hash: ContentHash


class RepositoryRef(WireModel):
    repository_id: UUID
    target_sha: GitSha


class RegisteredVersion(WireModel):
    key: NonEmpty
    version: NonEmpty


class FrozenModelConfiguration(WireModel):
    provider: NonEmpty
    model: NonEmpty
    base_url: NonEmpty


class FrozenConfigurationRef(WireModel):
    kind: Literal["ORCHESTRATION"]
    id: UUID
    content_hash: ContentHash
    schema_version: NonEmpty


class AgentManifest(WireModel):
    id: UUID
    content_hash: ContentHash
    agents: list[RegisteredVersion] = Field(min_length=1)
    tools: list[RegisteredVersion]
    prompt_versions: list[RegisteredVersion]
    model_config_ref: NonEmpty
    model_configuration: FrozenModelConfiguration
    prompt_definitions: dict[str, str]
    business_configuration_ref: FrozenConfigurationRef | None = None
    execution_configuration: dict[str, JsonValue] = Field(default_factory=dict)


class ExecutionBudget(WireModel):
    timeout_seconds: int = Field(gt=0)
    max_turns: int = Field(gt=0)
    max_tool_calls: int = Field(ge=0)
    max_child_agents: int = Field(ge=0)
    max_delegation_depth: int = Field(ge=0)


class AttemptContext(WireModel):
    contract_version: Literal["agent-task-v1"]
    task_id: UUID
    attempt_id: UUID
    fencing_token: int = Field(ge=1)
    worker_id: NonEmpty
    correlation_id: NonEmpty


class AgentTaskAssignment(AttemptContext):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [{
                "if": {"properties": {"taskKind": {"const": "DELIVERY_VERIFY"}}},
                "then": {"properties": {
                    "businessRef": {"properties": {"kind": {"const": "ANALYSIS_RUN"}}},
                    "inputSnapshotRef": {"properties": {"kind": {"const": "VERIFICATION"}}},
                }},
            }, {
                "if": {"properties": {"taskKind": {"enum": ["PLAN_DRAFT", "PLAN_REFINE"]}}},
                "then": {"properties": {
                    "businessRef": {"properties": {"kind": {"const": "PLANNING_RUN"}}},
                    "inputSnapshotRef": {"properties": {"kind": {"const": "PLANNING"}}},
                    "planVersionRef": {"type": "null"},
                }},
            }, {
                "if": {"properties": {"taskKind": {"const": "DELIVERY_CLAIM_PROPOSE"}}},
                "then": {"properties": {
                    "businessRef": {"properties": {"kind": {"const": "CLAIM_PROPOSAL_RUN"}}},
                    "inputSnapshotRef": {"properties": {"kind": {"const": "CLAIM_PROPOSAL"}}},
                    "planVersionRef": {"type": "null"},
                    "repositoryRefs": {"maxItems": 0}, "allowedEvidenceIds": {"maxItems": 0},
                }},
            }, {
                "if": {"properties": {"taskKind": {"const": "EVIDENCE_QUESTION"}}},
                "then": {"properties": {
                    "businessRef": {"properties": {"kind": {"const": "EVIDENCE_QUESTION_RUN"}}},
                    "inputSnapshotRef": {"properties": {"kind": {"const": "EVIDENCE_QUESTION"}}},
                    "planVersionRef": {"type": "null"}, "repositoryRefs": {"maxItems": 0},
                    "allowedEvidenceIds": {"minItems": 1, "maxItems": 20},
                }},
            }],
        },
    )

    project_id: UUID
    task_kind: TaskKind
    business_ref: BusinessRef
    lease_expires_at: AwareDatetime
    lease_duration_seconds: int = Field(ge=15, le=300)
    input_snapshot_ref: FrozenInputRef
    plan_version_ref: PlanVersionRef | None
    repository_refs: list[RepositoryRef]
    allowed_evidence_ids: list[UUID]
    agent_manifest: AgentManifest
    budget: ExecutionBudget

    @model_validator(mode="after")
    def check_run_scope(self) -> "AgentTaskAssignment":
        verification = self.task_kind == "DELIVERY_VERIFY"
        claim_proposal = self.task_kind == "DELIVERY_CLAIM_PROPOSE"
        question = self.task_kind == "EVIDENCE_QUESTION"
        expected_run, expected_input = {
            "DELIVERY_VERIFY": ("ANALYSIS_RUN", "VERIFICATION"),
            "PLAN_DRAFT": ("PLANNING_RUN", "PLANNING"), "PLAN_REFINE": ("PLANNING_RUN", "PLANNING"),
            "DELIVERY_CLAIM_PROPOSE": ("CLAIM_PROPOSAL_RUN", "CLAIM_PROPOSAL"),
            "EVIDENCE_QUESTION": ("EVIDENCE_QUESTION_RUN", "EVIDENCE_QUESTION"),
        }[self.task_kind]
        if self.business_ref.kind != expected_run:
            raise ValueError("task kind and business run kind must agree")
        if self.input_snapshot_ref.kind != expected_input:
            raise ValueError("task kind and frozen input kind must agree")
        if not verification and self.plan_version_ref is not None:
            raise ValueError("planning input does not bind a confirmed verification baseline")
        if claim_proposal and (self.repository_refs or self.allowed_evidence_ids):
            raise ValueError("claim extraction grants no repository or formal evidence access")
        if question and (self.repository_refs or not 1 <= len(self.allowed_evidence_ids) <= 20):
            raise ValueError("evidence questions grant selected evidence only")
        return self


class AgentTaskHeartbeat(AttemptContext):
    """The service owns the clock, lease extension and cancellation response."""


class AgentTaskResult(AttemptContext):
    input_snapshot_ref: FrozenInputRef
    result_schema_version: NonEmpty
    result_hash: ContentHash
    evidence_refs: list[UUID]
    # Digest the exact UTF-8 bytes of this JSON object, avoiding language-specific
    # float/Unicode reserialization when Java accepts a Python result.
    candidates_json: NonEmpty


class AgentTaskFailure(AttemptContext):
    error_code: NonEmpty
    message_redacted: NonEmpty
    reason: Literal["FAILED", "CANCELLED", "BUDGET_EXHAUSTED"]


class AgentTaskEvent(AttemptContext):
    event_seq: int = Field(ge=1)
    agent_instance_id: UUID
    parent_agent_instance_id: UUID | None
    tool_call_id: UUID | None
    occurred_at: AwareDatetime
    event_type: NonEmpty
    payload_redacted: dict[str, JsonValue]


class AgentToolCall(AttemptContext):
    tool_call_id: UUID
    tool: RegisteredVersion
    input_snapshot_ref: FrozenInputRef
    arguments: dict[str, JsonValue]


class ClaimProposalDocument(WireModel):
    source_revision_id: UUID
    name: str
    content_hash: ContentHash
    extracted_text_hash: ContentHash
    excerpt: str = Field(max_length=4000)
    excerpt_hash: ContentHash


class ClaimProposalInput(WireModel):
    schema_version: Literal["delivery-claim-input-v1"]
    project_id: UUID
    task_id: UUID
    cycle_id: UUID
    source_manifest: dict[str, JsonValue]
    documents: list[ClaimProposalDocument] = Field(max_length=20)


class QuestionEvidence(WireModel):
    evidence_id: UUID
    source_type: str
    evidence_kind: str
    excerpt: str
    locator: dict[str, JsonValue]
    precision: Literal["EXACT", "APPROXIMATE", "UNAVAILABLE"]


class EvidenceQuestionInput(WireModel):
    schema_version: Literal["evidence-question-input-v1"]
    project_id: UUID
    snapshot_id: UUID
    snapshot_hash: ContentHash
    question: str = Field(min_length=1, max_length=2000)
    evidence: list[QuestionEvidence] = Field(min_length=1, max_length=20)
