from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("display_name")
    @classmethod
    def normalise_display_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("姓名不能为空")
        return name

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
            raise ValueError("请输入有效的邮箱地址")
        return email


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: UUID
    display_name: str
    email: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    # Optional: when present, the project is created and its GitHub source is
    # registered + a background sync queued in one step.
    repository_url: str | None = Field(default=None, max_length=2048)
    # Optional knowledge bases to mount to the new project.
    knowledge_base_ids: list[UUID] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    version: int
    created_at: datetime
    can_delete: bool = False


class ProjectDeleteRequest(BaseModel):
    confirmation_name: str = Field(min_length=1, max_length=200)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    requirement_key: str = Field(min_length=1, max_length=100)
    delivery_item_id: UUID
    orchestration_template_id: UUID | None = None


class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    delivery_item_id: UUID | None
    title: str
    requirement_key: str
    cycle_id: UUID
    cycle_status: str
    version: int


class DeliveryClaimInput(BaseModel):
    id: UUID | None = None
    text: str = Field(min_length=3, max_length=6000)


class DeliveryClaimProposalRequest(BaseModel):
    source_revision_ids: list[UUID] = Field(default_factory=list, max_length=20)


class DeliveryClaimConfirmRequest(BaseModel):
    claims: list[DeliveryClaimInput] = Field(min_length=1, max_length=12)


class DeliveryClaimResponse(BaseModel):
    id: UUID
    claim_key: str
    text: str
    rationale: str
    origin: str
    status: str
    source_manifest: dict
    created_at: datetime
    updated_at: datetime


class VerificationTaskListResponse(BaseModel):
    """A project-scoped task projection for the workbench list, never a new fact source."""

    id: UUID
    project_id: UUID
    delivery_item_id: UUID | None
    title: str
    requirement_key: str
    cycle_id: UUID | None
    cycle_status: str
    formal_snapshot_id: UUID | None
    formal_snapshot_hash: str | None
    report_id: UUID | None
    report_status: str | None
    published_record_id: UUID | None
    delivery_pull_request: dict | None = None
    created_at: datetime
    updated_at: datetime


class SourceResponse(BaseModel):
    id: UUID
    project_id: UUID
    logical_name: str
    revision_no: int
    content_hash: str
    processing_status: str
    parser_version: str | None
    ingestion_job_id: UUID
    knowledge_base_id: UUID | None = None
    force_ocr: bool = False


class SourceDetailResponse(BaseModel):
    id: UUID
    project_id: UUID
    logical_name: str
    source_role: str
    revision_no: int
    content_hash: str
    media_type: str
    original_filename: str
    processing_status: str
    parser_version: str | None
    failure_code: str | None
    ocr_confidence: float | None
    extraction_metadata: dict
    ingestion_job_status: str | None
    in_snapshot: bool
    knowledge_base_id: UUID | None = None
    force_ocr: bool = False
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseMountRequest(BaseModel):
    knowledge_base_id: UUID


class SourceContentResponse(BaseModel):
    content: str
    media_type: str
    logical_name: str
    original_filename: str
    locator_summary: dict


class ChunkItemResponse(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    locator: dict
    index_version: str


class RetrievalIndexResponse(BaseModel):
    id: UUID
    project_id: UUID
    index_version: str
    parser_version: str
    embedding_provider: str
    embedding_model: str
    dimensions: int
    status: str
    ready_source_count: int
    indexed_source_count: int
    indexed_chunk_count: int
    activated_at: datetime | None
    created_at: datetime


class RetrievalIndexRebuildResponse(RetrievalIndexResponse):
    build_run_id: UUID
    reindexed_source_count: int
    reindexed_chunk_count: int


class RetrievalIndexBuildRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    target_index_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    source_count: int
    reindexed_source_count: int
    reindexed_chunk_count: int
    error_code: str | None
    error_message: str | None


class SnapshotCreateRequest(BaseModel):
    source_revision_ids: list[UUID] = Field(min_length=1)


class FormalSnapshotCreateRequest(BaseModel):
    source_revision_ids: list[UUID] = Field(default_factory=list, max_length=100)
    git_snapshot_id: UUID
    external_evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)
    manual_evidence_ids: list[UUID] = Field(default_factory=list, max_length=100)


class SnapshotResponse(BaseModel):
    id: UUID
    cycle_id: UUID
    snapshot_hash: str
    purpose: str
    assessment_profile: str
    policy_version: str
    workflow_version: str
    created_at: datetime


class EvidenceResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    source_type: str
    evidence_kind: str
    excerpt_safe: str
    locator: dict
    locator_precision: str


class GitRepositoryCreateRequest(BaseModel):
    display_url: str = Field(min_length=8, max_length=2000)
    credential_ref: str | None = Field(default=None, max_length=160)


class GitRepositoryResponse(BaseModel):
    id: UUID
    project_id: UUID
    display_url: str
    read_only: bool


class GitSnapshotCreateRequest(BaseModel):
    repository_id: UUID
    base_ref: str = Field(min_length=1, max_length=255)
    target_ref: str = Field(min_length=1, max_length=255)
    diff_mode: str = Field(pattern="^(TWO_DOT|THREE_DOT)$")
    include_paths: list[str] = Field(default_factory=list, max_length=100)
    exclude_paths: list[str] = Field(default_factory=list, max_length=100)


class GitSnapshotResponse(BaseModel):
    id: UUID
    base_sha: str
    target_sha: str
    merge_base_sha: str
    diff_mode: str
    diff_hash: str
    coverage: dict


class GitSnapshotDiffResponse(BaseModel):
    snapshotId: UUID
    baseSha: str
    targetSha: str
    effectiveBaseSha: str
    diffMode: str
    diffHash: str
    diffArtifactId: UUID
    coverage: dict
    files: list[dict]


class AnalysisRunResponse(BaseModel):
    id: UUID
    snapshot_id: UUID
    assessment_profile: str
    run_status: str
    poll_url: str


class AnalysisResultResponse(BaseModel):
    id: UUID
    claim_id: UUID
    claim_key: str
    claim_text: str
    status: str
    reason: str
    requires_human_confirmation: bool
    evidence: list[dict]
    risks: list[dict] = Field(default_factory=list)
    human_decision: dict | None = None
    allowed_human_decisions: list[str] = Field(default_factory=list)
    evidence_assessments: list[dict] = Field(default_factory=list)


class HumanVerificationDecisionRequest(BaseModel):
    decision: str
    note: str = Field(default="", max_length=2000)


class CodeReviewResponse(BaseModel):
    gitSnapshotId: UUID | None = None
    findings: list[dict] = Field(default_factory=list)
    coverage: list[dict] = Field(default_factory=list)


class ReportResponse(BaseModel):
    id: UUID
    cycle_id: UUID
    sequence_no: int
    status: str
    record_type: str
    content_hash: str
    editorial_note: str
    version: int


class ProjectReportResponse(BaseModel):
    """Read model for a report in a project workbench or review queue."""

    id: UUID
    cycle_id: UUID
    sequence_no: int
    status: str
    record_type: str
    content_hash: str
    version: int
    snapshot_hash: str
    editorial_note: str
    submitted_at: datetime | None
    task_id: UUID
    task_title: str
    requirement_key: str
    delivery_item_id: UUID | None
    submitted_by_name: str | None
    latest_approval_action: str | None
    latest_approval_reason: str | None
    latest_approval_at: datetime | None


class ReportContentResponse(ProjectReportResponse):
    """Replayable report draft body for the task-level Notebook."""

    items: list[dict] = Field(default_factory=list)
    planBaseline: dict | None = None


class PublishedRecordResponse(BaseModel):
    """Immutable delivery record projection, including its originating report context."""

    id: UUID
    project_id: UUID
    task_id: UUID
    task_title: str
    requirement_key: str
    delivery_item_id: UUID | None
    cycle_id: UUID
    report_version_id: UUID
    report_sequence_no: int
    report_status: str
    snapshot_hash: str
    record_type: str
    record_no: str
    record_hash: str
    published_by_name: str | None
    published_at: datetime
    approval_action: str | None
    approval_reason: str | None
    approval_by_name: str | None
    approval_at: datetime | None


class ReportDraftUpdateRequest(BaseModel):
    editorial_note: str = Field(default="", max_length=8000)
    item_dispositions: dict[UUID, str | None] = Field(default_factory=dict, max_length=500)
    expected_version: int = Field(ge=1)


class ApprovalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class ProjectMemberCreateRequest(BaseModel):
    user_id: UUID | None = None
    user_email: str | None = Field(default=None, max_length=255)
    role: str = Field(pattern="^(SUBMITTER|REVIEWER|ADMIN)$")

    @model_validator(mode="after")
    def require_one_identity(self):
        if (self.user_id is None) == (self.user_email is None):
            raise ValueError("exactly one of user_id or user_email is required")
        return self


class EvidenceQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[UUID] = Field(min_length=1, max_length=20)


class EvidenceQuestionResponse(BaseModel):
    answer: str
    fact_status: str
    citations: list[dict]


class ExternalEvidenceCreateRequest(BaseModel):
    evidence_type: str = Field(pattern="^(TEST|BUILD)$")
    logical_name: str = Field(min_length=1, max_length=255)
    commit_sha: str = Field(pattern="^[0-9a-fA-F]{40}$")
    content: str = Field(min_length=1, max_length=2 * 1024 * 1024)
    exit_code: int | None = Field(default=None, ge=-255, le=255)


class ExternalEvidenceResponse(BaseModel):
    id: UUID
    project_id: UUID
    cycle_id: UUID
    evidence_type: str
    logical_name: str
    commit_sha: str
    content_hash: str
    exit_code: int | None


class ManualEvidenceCreateRequest(BaseModel):
    logical_name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2 * 1024 * 1024)


class ManualEvidenceResponse(BaseModel):
    id: UUID
    project_id: UUID
    cycle_id: UUID
    logical_name: str
    content_hash: str


class SnapshotSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    preferred_source_roles: list[str] = Field(default_factory=list, max_length=8)


class SnapshotSearchResponse(BaseModel):
    items: list[dict]


class AgentToolCreateRequest(BaseModel):
    key: str = Field(min_length=3, max_length=96)
    name: str = Field(min_length=1, max_length=160)
    tool_type: str = Field(pattern="^(DOCUMENT_RETRIEVAL|GIT_DIFF|CI_EVIDENCE|EVIDENCE_QUERY|HTTP_QUERY)$")
    endpoint_url: str | None = Field(default=None, max_length=2000)
    secret_ref: str | None = Field(default=None, max_length=160)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class AgentCapabilityCreateRequest(BaseModel):
    key: str = Field(min_length=3, max_length=96)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    core_scope: str = Field(pattern="^SHARED$")
    prompt_template: str = Field(default="", max_length=20_000)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    parameter_schema: dict = Field(default_factory=dict)
    tool_ids: list[UUID] = Field(default_factory=list, max_length=20)


class AgentCapabilityVersionCreateRequest(BaseModel):
    prompt_template: str = Field(default="", max_length=20_000)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    parameter_schema: dict = Field(default_factory=dict)
    tool_ids: list[UUID] = Field(default_factory=list, max_length=20)


class OrchestrationTemplateNodeInput(BaseModel):
    capability_version_id: UUID
    enabled: bool = True
    parameters: dict = Field(default_factory=dict)


class OrchestrationTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    assessment_profile: str = Field(
        default="DELIVERY_VERIFICATION",
        pattern="^(DELIVERY_VERIFICATION|PROJECT_STATUS_SUMMARY|SECURITY_BASELINE|QUALITY_TREND)$",
    )
    nodes: list[OrchestrationTemplateNodeInput] = Field(min_length=1, max_length=30)


class TaskOrchestrationBindingRequest(BaseModel):
    template_id: UUID


class ExternalConnectionCreateRequest(BaseModel):
    provider: str = Field(default="GITHUB", pattern="^GITHUB$")
    name: str = Field(min_length=1, max_length=160)
    repository_slug: str = Field(min_length=3, max_length=255)
    secret_ref: str | None = Field(default=None, max_length=160)


class ExternalConnectionResponse(BaseModel):
    id: UUID
    project_id: UUID
    provider: str
    name: str
    repository_slug: str
    secret_ref_configured: bool
    is_active: bool
    created_at: datetime


class SourceSyncRunResponse(BaseModel):
    id: UUID
    connection_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    changed_count: int
    page_count: int
    continuation_cursor: dict
    error_code: str | None
    error_message: str | None


class DeliveryItemResponse(BaseModel):
    id: UUID
    project_id: UUID
    external_key: str
    title: str
    planning_status: str
    verification_status: str
    source_updated_at: datetime | None
    provider: str
    repository_slug: str
    web_url: str
    milestone_key: str | None
    resource_revision: int
    resource_type: str
    pull_request: dict | None = None


class TaskDeliveryItemBindingRequest(BaseModel):
    delivery_item_id: UUID


class DeliveryChangeLinkCreateRequest(BaseModel):
    pull_request_resource_id: UUID | None = None
    git_snapshot_id: UUID | None = None
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def require_exactly_one_target(self):
        if (self.pull_request_resource_id is None) == (self.git_snapshot_id is None):
            raise ValueError("exactly one change target is required")
        return self


class DeliveryChangeLinkResponse(BaseModel):
    id: UUID
    delivery_item_id: UUID
    target_kind: str
    target_id: UUID
    target_label: str
    target_url: str | None
    link_status: str
    link_source: str
    confidence: float | None
    reason: str
    agent_proposal_run_id: UUID | None
    confirmed_at: datetime | None


class AgentChangeCandidateTargetResponse(BaseModel):
    target_kind: str
    target_id: UUID
    target_label: str
    input_ref: dict


class AgentChangeCandidateTargetInput(BaseModel):
    target_kind: str = Field(pattern="^(PULL_REQUEST|GIT_SNAPSHOT)$")
    target_id: UUID


class AgentChangeProposalRequest(BaseModel):
    targets: list[AgentChangeCandidateTargetInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_unique_targets(self):
        keys = {(target.target_kind, target.target_id) for target in self.targets}
        if len(keys) != len(self.targets):
            raise ValueError("candidate targets must be unique")
        return self


class AgentChangeProposalRunResponse(BaseModel):
    id: UUID
    input_hash: str
    rules_version: str
    candidate_target_count: int
    created_candidate_count: int
    created_at: datetime


class AgentChangeProposalResponse(BaseModel):
    proposal_run: AgentChangeProposalRunResponse
    links: list[DeliveryChangeLinkResponse]
    created_candidate_count: int
    skipped_existing_count: int
    skipped_no_overlap_count: int


class PlatformLinkDiscoveryResponse(BaseModel):
    changed_count: int
    skipped_count: int


class DeliveryItemDocumentSourceLinkCreateRequest(BaseModel):
    source_revision_id: UUID
    link_role: str = Field(pattern="^(ACCEPTANCE|DESIGN|PLAN)$")


class DeliveryItemSourceLinkResponse(BaseModel):
    id: UUID
    delivery_item_id: UUID
    source_kind: str
    source_id: UUID
    source_label: str
    link_role: str


class ProjectHealthSnapshotCreateRequest(BaseModel):
    milestone_key: str | None = Field(default=None, max_length=160)


class ProjectHealthSnapshotResponse(BaseModel):
    id: UUID
    project_id: UUID
    scope: dict
    input_manifest: dict
    input_hash: str
    snapshot_hash: str
    summary: dict
    coverage: dict
    as_of: datetime
    created_at: datetime


class ProjectSummaryDraftCreateRequest(BaseModel):
    health_snapshot_id: UUID
    period_type: str = Field(pattern="^(DAILY|WEEKLY|ITERATION)$")
    title: str | None = Field(default=None, max_length=300)


class ProjectSummaryDraftResponse(BaseModel):
    id: UUID
    project_id: UUID
    health_snapshot_id: UUID
    period_type: str
    title: str
    content: dict
    content_hash: str


class AgentToolExecutionResponse(BaseModel):
    id: UUID
    analysis_run_id: UUID
    capability_key: str
    tool_key: str
    tool_type: str
    content_hash: str
    excerpt_safe: str
    locator: dict
    status: str
    created_at: datetime
    imported_manual_evidence_id: UUID | None


class AgentToolExecutionImportRequest(BaseModel):
    logical_name: str = Field(min_length=1, max_length=255)


class AgentToolExecutionImportResponse(BaseModel):
    manual_evidence_id: UUID
    cycle_id: UUID
    content_hash: str
    origin_type: str
    draft_status: str
    created_at: datetime
    updated_at: datetime


class ProjectSummaryRecordResponse(BaseModel):
    id: UUID
    project_id: UUID
    health_snapshot_id: UUID
    summary_draft_id: UUID
    record_no: str
    record_hash: str
    confirmation_type: str
    published_at: datetime


class PeripheralProfileRunCreateRequest(BaseModel):
    assessment_profile: str = Field(pattern="^(PROJECT_STATUS_SUMMARY|SECURITY_BASELINE|QUALITY_TREND)$")
    health_snapshot_id: UUID | None = None
    security_baseline_id: UUID | None = None
    scan_artifact_ids: list[UUID] | None = Field(default=None, min_length=2, max_length=300)

    @model_validator(mode="after")
    def require_profile_specific_input(self):
        if self.assessment_profile == "PROJECT_STATUS_SUMMARY":
            valid = self.health_snapshot_id is not None and self.security_baseline_id is None and self.scan_artifact_ids is None
        elif self.assessment_profile == "SECURITY_BASELINE":
            valid = self.security_baseline_id is not None and self.health_snapshot_id is None and self.scan_artifact_ids is None
        else:
            valid = self.scan_artifact_ids is not None and self.health_snapshot_id is None and self.security_baseline_id is None
            if valid and len(self.scan_artifact_ids) != len(set(self.scan_artifact_ids)):
                raise ValueError("quality trend scan artifacts must be unique")
        if not valid:
            raise ValueError("profile must receive exactly its dedicated frozen input")
        return self


class PeripheralProfileRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    assessment_profile: str
    run_status: str
    input_manifest: dict
    input_hash: str
    output: dict
    coverage: dict
    limitations: list[str]
    created_at: datetime


class SecurityFindingInput(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=255)
    severity: str = Field(pattern="^(INFO|LOW|MEDIUM|HIGH|CRITICAL)$")
    category: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=4000)
    locator: dict = Field(default_factory=dict)


class SecurityScanArtifactCreateRequest(BaseModel):
    repository_id: UUID
    target_sha: str = Field(pattern="^[0-9a-fA-F]{40}$")
    scan_type: str = Field(pattern="^(SAST|DEPENDENCY|SECRET|CONFIG|CI)$")
    scanner_name: str = Field(min_length=1, max_length=160)
    scanner_version: str = Field(min_length=1, max_length=160)
    rule_set_version: str = Field(min_length=1, max_length=160)
    coverage: dict = Field(default_factory=dict)
    content: str = Field(min_length=1, max_length=2 * 1024 * 1024)
    findings: list[SecurityFindingInput] = Field(default_factory=list, max_length=2000)


class SecurityScanArtifactResponse(BaseModel):
    id: UUID
    project_id: UUID
    repository_id: UUID
    target_sha: str
    scan_type: str
    scanner_name: str
    scanner_version: str
    rule_set_version: str
    coverage: dict
    content_hash: str
    finding_count: int
    created_at: datetime


class SecurityFindingStatusUpdateRequest(BaseModel):
    finding_status: str = Field(pattern="^(OPEN|ACCEPTED_RISK|REMEDIATION_CLAIMED)$")
    reason: str = Field(min_length=1, max_length=4000)


class SecurityFindingResponse(BaseModel):
    id: UUID
    scan_artifact_id: UUID
    fingerprint: str
    severity: str
    category: str
    title: str
    locator: dict
    finding_status: str
    status_reason: str
    status_updated_at: datetime | None


class SecurityArtifactExplanationResponse(BaseModel):
    scope: dict
    summary: dict
    observations: list[str]
    limitations: list[str]


class QualityTrendPointResponse(BaseModel):
    artifact_id: UUID
    target_sha: str
    created_at: datetime
    content_hash: str
    finding_count: int
    severity_counts: dict
    status_counts: dict
    coverage: dict


class QualityTrendSeriesResponse(BaseModel):
    series_key: str
    repository_id: UUID
    scan_type: str
    scanner_name: str
    scanner_version: str
    rule_set_version: str
    points: list[QualityTrendPointResponse]


class QualityTrendResponse(BaseModel):
    series: list[QualityTrendSeriesResponse]
    limitations: list[str]


class SecurityBaselineCreateRequest(BaseModel):
    repository_id: UUID
    target_sha: str = Field(pattern="^[0-9a-fA-F]{40}$")
    scan_artifact_ids: list[UUID] = Field(min_length=1, max_length=100)


class SecurityBaselineSnapshotResponse(BaseModel):
    id: UUID
    project_id: UUID
    repository_id: UUID
    target_sha: str
    input_manifest: dict
    input_hash: str
    snapshot_hash: str
    summary: dict
    coverage: dict
    created_at: datetime


class SecurityBaselineConfirmRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class SecurityBaselineRecordResponse(BaseModel):
    id: UUID
    project_id: UUID
    baseline_snapshot_id: UUID
    record_no: str
    record_hash: str
    confirmation_reason: str
    confirmed_at: datetime
