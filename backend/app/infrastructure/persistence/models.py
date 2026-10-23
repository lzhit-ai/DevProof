import os
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# The vector column dimension must match the configured embedding model output. It is
# read from the environment at import time because SQLAlchemy models are built eagerly.
_EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))


class TimestampedEntity:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampedEntity, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class Project(TimestampedEntity, Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectMember(TimestampedEntity, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        CheckConstraint("role IN ('SUBMITTER', 'REVIEWER', 'ADMIN')", name="ck_project_members_role"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class ExternalConnection(TimestampedEntity, Base):
    """A project-scoped read-only source connection; credentials stay in the environment."""

    __tablename__ = "external_connections"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "repository_slug", name="uq_external_connection_project_provider_repo"),
        CheckConstraint("provider IN ('GITHUB')", name="ck_external_connection_provider"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    repository_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    api_base_url: Mapped[str] = mapped_column(Text, nullable=False, default="https://api.github.com")
    secret_ref: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class SourceSyncRun(Base):
    __tablename__ = "source_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'PARTIALLY_SUCCEEDED', 'FAILED')",
            name="ck_source_sync_run_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("external_connections.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    executor_owner: Mapped[str] = mapped_column(String(16), nullable=False, default="PYTHON", server_default="PYTHON")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    continuation_cursor: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # Durable worker lease fields so a background lane can consume this run.
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)


class ExternalResource(TimestampedEntity, Base):
    __tablename__ = "external_resources"
    __table_args__ = (
        UniqueConstraint("connection_id", "resource_type", "external_key", name="uq_external_resource_connection_type_key"),
        CheckConstraint("resource_type IN ('ISSUE', 'PULL_REQUEST', 'MILESTONE')", name="ck_external_resource_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("external_connections.id", ondelete="CASCADE"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_key: Mapped[str] = mapped_column(String(160), nullable=False)
    logical_key: Mapped[str] = mapped_column(String(320), nullable=False)


class ExternalResourceRevision(Base):
    __tablename__ = "external_resource_revisions"
    __table_args__ = (UniqueConstraint("resource_id", "revision_no", name="uq_external_resource_revision"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    resource_id: Mapped[UUID] = mapped_column(ForeignKey("external_resources.id", ondelete="CASCADE"), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    web_url: Mapped[str] = mapped_column(Text, nullable=False)
    milestone_key: Mapped[str | None] = mapped_column(String(160))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryItem(TimestampedEntity, Base):
    """A source-derived development/delivery item; planning and verification status never overwrite each other."""

    __tablename__ = "delivery_items"
    __table_args__ = (
        UniqueConstraint("project_id", "external_key", name="uq_delivery_item_project_external_key"),
        CheckConstraint("planning_status IN ('OPEN', 'IN_PROGRESS', 'DECLARED_DONE', 'CANCELLED')", name="ck_delivery_item_planning_status"),
        CheckConstraint("verification_status IN ('NOT_ASSESSED', 'PARTIALLY_SUPPORTED', 'CONFIRMED', 'CONFLICT', 'INSUFFICIENT_EVIDENCE')", name="ck_delivery_item_verification_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    external_resource_id: Mapped[UUID] = mapped_column(ForeignKey("external_resources.id", ondelete="RESTRICT"), nullable=False)
    external_key: Mapped[str] = mapped_column(String(320), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    planning_status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_ASSESSED")
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryItemSourceLink(Base):
    __tablename__ = "delivery_item_source_links"
    __table_args__ = (
        CheckConstraint("link_role IN ('PRIMARY', 'ACCEPTANCE', 'DESIGN', 'PLAN')", name="ck_delivery_item_source_link_role"),
        CheckConstraint(
            "(external_resource_revision_id IS NOT NULL AND source_revision_id IS NULL) OR "
            "(external_resource_revision_id IS NULL AND source_revision_id IS NOT NULL)",
            name="ck_delivery_item_source_link_exactly_one_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    delivery_item_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False)
    external_resource_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("external_resource_revisions.id", ondelete="RESTRICT"))
    source_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_revisions.id", ondelete="RESTRICT"))
    link_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentChangeProposalRun(Base):
    """Frozen, controlled inputs and result counts for an Agent change-link proposal."""

    __tablename__ = "agent_change_proposal_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    delivery_item_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False)
    input_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryChangeLink(Base):
    __tablename__ = "delivery_change_links"
    __table_args__ = (
        CheckConstraint("link_status IN ('CANDIDATE', 'CONFIRMED')", name="ck_delivery_change_link_status"),
        CheckConstraint("link_source IN ('PLATFORM', 'USER', 'AGENT')", name="ck_delivery_change_link_source"),
        CheckConstraint(
            "(pull_request_resource_id IS NOT NULL AND git_snapshot_id IS NULL) OR "
            "(pull_request_resource_id IS NULL AND git_snapshot_id IS NOT NULL)",
            name="ck_delivery_change_link_exactly_one_target",
        ),
        UniqueConstraint("delivery_item_id", "pull_request_resource_id", name="uq_delivery_change_link_item_pr"),
        UniqueConstraint("delivery_item_id", "git_snapshot_id", name="uq_delivery_change_link_item_git_snapshot"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    delivery_item_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_items.id", ondelete="CASCADE"), nullable=False)
    pull_request_resource_id: Mapped[UUID | None] = mapped_column(ForeignKey("external_resources.id", ondelete="RESTRICT"))
    git_snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("git_snapshots.id", ondelete="RESTRICT"))
    link_status: Mapped[str] = mapped_column(String(24), nullable=False)
    link_source: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agent_proposal_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_change_proposal_runs.id", ondelete="RESTRICT"))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectHealthSnapshot(Base):
    """Immutable, evidence-scoped project-status input; not a delivery-verification run."""

    __tablename__ = "project_health_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectSummaryDraft(TimestampedEntity, Base):
    __tablename__ = "project_summary_drafts"
    __table_args__ = (
        CheckConstraint("period_type IN ('DAILY', 'WEEKLY', 'ITERATION')", name="ck_project_summary_draft_period_type"),
        CheckConstraint("draft_status IN ('DRAFT', 'PUBLISHED')", name="ck_project_summary_draft_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    health_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("project_health_snapshots.id", ondelete="RESTRICT"), nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    draft_status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class ProjectSummaryRecord(Base):
    __tablename__ = "project_summary_records"
    __table_args__ = (
        UniqueConstraint("summary_draft_id", name="uq_project_summary_record_draft"),
        CheckConstraint("confirmation_type IN ('PERSONAL_CONFIRMED')", name="ck_project_summary_record_confirmation_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    health_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("project_health_snapshots.id", ondelete="RESTRICT"), nullable=False)
    summary_draft_id: Mapped[UUID] = mapped_column(ForeignKey("project_summary_drafts.id", ondelete="RESTRICT"), nullable=False)
    record_no: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    confirmation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PERSONAL_CONFIRMED")
    published_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecurityScanArtifact(TimestampedEntity, Base):
    """An immutable scanner/CI result bound to one project repository SHA."""

    __tablename__ = "security_scan_artifacts"
    __table_args__ = (
        CheckConstraint("scan_type IN ('SAST', 'DEPENDENCY', 'SECRET', 'CONFIG', 'CI')", name="ck_security_scan_artifact_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("git_repositories.id", ondelete="RESTRICT"), nullable=False)
    target_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scanner_name: Mapped[str] = mapped_column(String(160), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(160), nullable=False)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    imported_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class SecurityFinding(TimestampedEntity, Base):
    __tablename__ = "security_findings"
    __table_args__ = (
        UniqueConstraint("scan_artifact_id", "fingerprint", name="uq_security_finding_artifact_fingerprint"),
        CheckConstraint("severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_security_finding_severity"),
        CheckConstraint("finding_status IN ('OPEN', 'ACCEPTED_RISK', 'REMEDIATION_CLAIMED')", name="ck_security_finding_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scan_artifact_id: Mapped[UUID] = mapped_column(ForeignKey("security_scan_artifacts.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    finding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status_updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SecurityBaselineSnapshot(Base):
    __tablename__ = "security_baseline_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("git_repositories.id", ondelete="RESTRICT"), nullable=False)
    target_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    input_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecurityBaselineRecord(Base):
    __tablename__ = "security_baseline_records"
    __table_args__ = (UniqueConstraint("baseline_snapshot_id", name="uq_security_baseline_record_snapshot"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    baseline_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("security_baseline_snapshots.id", ondelete="RESTRICT"), nullable=False)
    record_no: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    confirmation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PeripheralProfileRun(Base):
    """A frozen, deterministic run for one non-delivery profile; never a dual-core review run."""

    __tablename__ = "peripheral_profile_runs"
    __table_args__ = (
        CheckConstraint(
            "assessment_profile IN ('PROJECT_STATUS_SUMMARY', 'SECURITY_BASELINE', 'QUALITY_TREND')",
            name="ck_peripheral_profile_run_profile",
        ),
        CheckConstraint("run_status IN ('SUCCEEDED')", name="ck_peripheral_profile_run_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    assessment_profile: Mapped[str] = mapped_column(String(48), nullable=False)
    run_status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCEEDED")
    input_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    limitations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerificationTask(TimestampedEntity, Base):
    __tablename__ = "verification_tasks"
    __table_args__ = (UniqueConstraint("project_id", "requirement_key", name="uq_task_project_requirement"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    delivery_item_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_items.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class VerificationCycle(TimestampedEntity, Base):
    __tablename__ = "verification_cycles"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_no", name="uq_cycle_task_sequence"),
        CheckConstraint(
            "business_status IN ('DRAFT', 'ANALYZING', 'DRAFT_READY', 'NEEDS_EVIDENCE', "
            "'NEEDS_CONFIRMATION', 'PENDING_REVIEW', 'REJECTED', 'APPROVED', 'PUBLISHED')",
            name="ck_cycle_business_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("verification_tasks.id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    business_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    created_from_cycle_id: Mapped[UUID | None] = mapped_column(ForeignKey("verification_cycles.id"))
    active_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class KnowledgeBase(TimestampedEntity, Base):
    """A standalone knowledge library that projects can mount (share)."""

    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class ProjectKnowledgeBase(TimestampedEntity, Base):
    """Mount relation: a project can use a knowledge base shared by another project."""

    __tablename__ = "project_knowledge_bases"
    __table_args__ = (
        UniqueConstraint("project_id", "knowledge_base_id", name="uq_project_knowledge_base"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_base_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class SourceRevision(TimestampedEntity, Base):
    __tablename__ = "source_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "logical_name", "revision_no", name="uq_source_revision"),
        CheckConstraint(
            "processing_status IN ('UPLOADED', 'PARSING', 'OCR_CHECKING', 'CHUNKING', 'INDEXING', 'READY', 'FAILED')",
            name="ck_source_processing_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_role: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extracted_artifact_uri: Mapped[str | None] = mapped_column(Text)
    normalized_text_hash: Mapped[str | None] = mapped_column(String(80))
    extraction_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UPLOADED")
    parser_version: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    knowledge_base_id: Mapped[UUID | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True)
    force_ocr: Mapped[bool] = mapped_column(default=False, nullable=False)


class SourceIngestionJob(TimestampedEntity, Base):
    """Durable document processing job; deliberately separate from analysis runs."""

    __tablename__ = "source_ingestion_jobs"
    executor_owner: Mapped[str] = mapped_column(String(16),nullable=False,server_default="PYTHON")
    compute_configuration: Mapped[dict | None] = mapped_column(JSONB)
    configuration_hash: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("job_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_source_ingestion_job_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_revision_id: Mapped[UUID] = mapped_column(ForeignKey("source_revisions.id", ondelete="CASCADE"), unique=True, nullable=False)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("source_revision_id", "chunk_index", "index_version", name="uq_document_chunk_version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_revision_id: Mapped[UUID] = mapped_column(ForeignKey("source_revisions.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    index_version: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIMENSIONS))


class ProjectRetrievalIndex(TimestampedEntity, Base):
    """A project selects one derived vector index; source and snapshot facts stay immutable."""

    __tablename__ = "project_retrieval_indexes"
    __table_args__ = (
        UniqueConstraint("project_id", "index_version", name="uq_project_retrieval_index_version"),
        CheckConstraint("status IN ('ACTIVE', 'HISTORICAL')", name="ck_project_retrieval_index_status"),
        Index(
            "uq_project_retrieval_active_index",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    index_version: Mapped[str] = mapped_column(String(512), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="HISTORICAL")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetrievalIndexBuildRun(Base):
    """Durable outcome for a derived-index rebuild, including a safe failure summary."""

    __tablename__ = "retrieval_index_build_runs"
    executor_owner: Mapped[str] = mapped_column(String(16),nullable=False,server_default="PYTHON")
    compute_configuration: Mapped[dict | None] = mapped_column(JSONB)
    configuration_hash: Mapped[str | None] = mapped_column(String(80))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_no: Mapped[int] = mapped_column(Integer,nullable=False,server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer,nullable=False,server_default="3")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    input_manifest: Mapped[list | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED')", name="ck_retrieval_index_build_run_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    target_index_version: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reindexed_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reindexed_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class GitRepository(TimestampedEntity, Base):
    __tablename__ = "git_repositories"
    __table_args__ = (UniqueConstraint("project_id", "canonical_url_hash", name="uq_project_git_repository"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    canonical_url_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    display_url: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(255))
    read_only: Mapped[bool] = mapped_column(nullable=False, default=True)


class ArtifactObject(TimestampedEntity, Base):
    __tablename__ = "artifact_objects"
    __table_args__ = (UniqueConstraint("project_id", "kind", "content_hash", name="uq_artifact_project_kind_hash"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)


class GitSnapshot(TimestampedEntity, Base):
    __tablename__ = "git_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("git_repositories.id"), nullable=False)
    selected_base_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    selected_target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    target_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    merge_base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    diff_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    include_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    exclude_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    diff_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    effective_base_sha: Mapped[str | None] = mapped_column(String(64))
    capture_version: Mapped[str | None] = mapped_column(String(64))
    diff_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifact_objects.id"))
    code_change_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifact_objects.id"))


class Claim(TimestampedEntity, Base):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("analysis_run_id", "claim_key", name="uq_claim_run_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    claim_key: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    authority_level: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_revisions.id"))
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint("locator_precision IN ('EXACT', 'APPROXIMATE', 'UNAVAILABLE')", name="ck_evidence_locator_precision"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_revisions.id"))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    excerpt_safe: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False)
    locator_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    requires_human_confirmation: Mapped[bool] = mapped_column(nullable=False, default=False)


class ClaimEvidenceLink(Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", "relation", name="uq_claim_evidence_relation"),
        CheckConstraint("relation IN ('SUPPORTS', 'CONTRADICTS', 'CONTEXT_ONLY')", name="ck_claim_evidence_relation"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    produced_by: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_human_confirmation: Mapped[bool] = mapped_column(nullable=False, default=False)


class VerificationResult(Base):
    __tablename__ = "verification_results"
    __table_args__ = (UniqueConstraint("analysis_run_id", "claim_id", name="uq_result_run_claim"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    requires_human_confirmation: Mapped[bool] = mapped_column(nullable=False, default=False)
    produced_by: Mapped[str] = mapped_column(String(32), nullable=False)


class HumanVerificationDecision(Base):
    """Append-only human adjudications for an immutable system verification result."""

    __tablename__ = "human_verification_decisions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    result_id: Mapped[UUID] = mapped_column(
        ForeignKey("verification_results.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    supersedes_decision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("human_verification_decisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NodeAttempt(Base):
    __tablename__ = "node_attempts"
    __table_args__ = (UniqueConstraint("analysis_run_id", "node_id", "attempt_no", name="uq_node_attempt"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskFinding(Base):
    __tablename__ = "risk_findings"
    __table_args__ = (UniqueConstraint("analysis_run_id", "claim_id", "evidence_id", "category", name="uq_risk_finding"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_items.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)


class CodeReviewFinding(Base):
    __tablename__ = "code_review_findings"
    __table_args__ = (UniqueConstraint("analysis_run_id", "fingerprint", name="uq_code_review_finding_run_fingerprint"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_items.id"), nullable=False)
    claim_id: Mapped[UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"))
    fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    finding_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_scenario: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    produced_by: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_human_confirmation: Mapped[bool] = mapped_column(nullable=False, default=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodeReviewFindingChallenge(Base):
    __tablename__ = "code_review_finding_challenges"
    __table_args__ = (UniqueConstraint("analysis_run_id", "finding_id", name="uq_code_review_challenge_run_finding"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    finding_id: Mapped[UUID] = mapped_column(ForeignKey("code_review_findings.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_call_id: Mapped[UUID | None] = mapped_column(ForeignKey("model_calls.id", ondelete="SET NULL"))
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisCoverage(Base):
    __tablename__ = "analysis_coverages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_ref: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ReportVersion(TimestampedEntity, Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("cycle_id", "sequence_no", name="uq_report_cycle_sequence"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    parent_report_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("report_versions.id"))
    record_type: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    submitted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    editorial_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ReportItem(Base):
    __tablename__ = "report_items"
    __table_args__ = (UniqueConstraint("report_version_id", "display_order", name="uq_report_item_order"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    report_version_id: Mapped[UUID] = mapped_column(ForeignKey("report_versions.id", ondelete="CASCADE"), nullable=False)
    result_id: Mapped[UUID] = mapped_column(ForeignKey("verification_results.id"), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    citation_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    disposition: Mapped[str | None] = mapped_column(Text)


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    report_version_id: Mapped[UUID] = mapped_column(ForeignKey("report_versions.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishedRecord(Base):
    __tablename__ = "published_records"
    __table_args__ = (UniqueConstraint("report_version_id", name="uq_published_report"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("verification_tasks.id"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id"), nullable=False)
    report_version_id: Mapped[UUID] = mapped_column(ForeignKey("report_versions.id"), nullable=False)
    record_type: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")
    record_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    published_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishedReportBody(Base):
    __tablename__ = "published_report_bodies"

    report_version_id: Mapped[UUID] = mapped_column(ForeignKey("report_versions.id"), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    body_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InputSnapshot(TimestampedEntity, Base):
    __tablename__ = "input_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="PREPARATION")
    assessment_profile: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")


class DeliveryClaimDraft(TimestampedEntity, Base):
    __tablename__ = "delivery_claim_drafts"
    __table_args__ = (
        UniqueConstraint("cycle_id", "claim_key", name="uq_delivery_claim_draft_cycle_key"),
        CheckConstraint("origin IN ('MODEL', 'HUMAN')", name="ck_delivery_claim_draft_origin"),
        CheckConstraint("claim_status IN ('CANDIDATE', 'CONFIRMED', 'DISCARDED')", name="ck_delivery_claim_draft_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    claim_key: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_status: Mapped[str] = mapped_column(String(16), nullable=False, default="CANDIDATE")
    source_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InputSnapshotClaim(Base):
    __tablename__ = "input_snapshot_claims"
    __table_args__ = (UniqueConstraint("snapshot_id", "claim_key", name="uq_input_snapshot_claim_key"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    delivery_claim_draft_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_claim_drafts.id"), nullable=False)
    claim_key: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)


class InputSnapshotPlan(Base):
    """Read/freeze bridge to the Java-owned, immutable plan selection aggregate."""

    __tablename__ = "input_snapshot_plans"

    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id"), primary_key=True)
    # Cross-service tables are migration-owned; no duplicate ORM table declarations.
    selection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    selection_hash: Mapped[str] = mapped_column(String(80), nullable=False)


class InputSnapshotSource(Base):
    __tablename__ = "input_snapshot_sources"
    __table_args__ = (UniqueConstraint("snapshot_id", "source_revision_id", name="uq_snapshot_source"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(ForeignKey("source_revisions.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)


class InputSnapshotGit(Base):
    __tablename__ = "input_snapshot_git"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), unique=True, nullable=False)
    git_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("git_snapshots.id"), nullable=False)
    diff_hash: Mapped[str] = mapped_column(String(80), nullable=False)


class ExternalEvidence(TimestampedEntity, Base):
    __tablename__ = "external_evidence"
    __table_args__ = (CheckConstraint("evidence_type IN ('TEST', 'BUILD')", name="ck_external_evidence_type"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    submitted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class InputSnapshotExternalEvidence(Base):
    __tablename__ = "input_snapshot_external_evidence"
    __table_args__ = (UniqueConstraint("snapshot_id", "external_evidence_id", name="uq_snapshot_external_evidence"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    external_evidence_id: Mapped[UUID] = mapped_column(ForeignKey("external_evidence.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)


class ManualEvidence(TimestampedEntity, Base):
    """A submitter-provided note or attachment preserved outside the report draft."""

    __tablename__ = "manual_evidence"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("verification_cycles.id", ondelete="CASCADE"), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    origin_locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_tool_execution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_tool_executions.id", ondelete="RESTRICT"), unique=True
    )


class InputSnapshotManualEvidence(Base):
    __tablename__ = "input_snapshot_manual_evidence"
    __table_args__ = (UniqueConstraint("snapshot_id", "manual_evidence_id", name="uq_snapshot_manual_evidence"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    manual_evidence_id: Mapped[UUID] = mapped_column(ForeignKey("manual_evidence.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)


class AnalysisRun(TimestampedEntity, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index(
            "uq_active_run_config",
            "snapshot_id",
            "analysis_config_hash",
            unique=True,
            postgresql_where=text("run_status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    assessment_profile: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")
    analysis_config_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    run_status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    executor_owner: Mapped[str] = mapped_column(String(16), nullable=False, default="PYTHON", server_default="PYTHON")
    manifest_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    plan_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    plan_baseline_hash: Mapped[str | None] = mapped_column(String(80))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentToolExecution(Base):
    """A bounded tool response used only inside one Agent run until a person imports it."""

    __tablename__ = "agent_tool_executions"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "capability_key", "tool_key", name="uq_agent_tool_execution_run_tool"),
        CheckConstraint("tool_type = 'HTTP_QUERY'", name="ck_agent_tool_execution_type"),
        CheckConstraint("status IN ('SUCCEEDED')", name="ck_agent_tool_execution_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    input_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("input_snapshots.id", ondelete="CASCADE"), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(96), nullable=False)
    tool_key: Mapped[str] = mapped_column(String(96), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False, default="HTTP_QUERY")
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_safe: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCEEDED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRunManifest(Base):
    __tablename__ = "analysis_run_manifests"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), unique=True, nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    degradation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AnalysisRunContextArtifact(Base):
    """Immutable, run-scoped context captured by the single controlled supplement round."""

    __tablename__ = "analysis_run_context_artifacts"
    __table_args__ = (UniqueConstraint("analysis_run_id", "round_no", name="uq_run_context_artifact_round"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("artifact_objects.id", ondelete="RESTRICT"), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"))
    agent_task_attempt_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("principal_hash", "request_method", "request_path", "idempotency_key", name="uq_idempotency_request"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    principal_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="IN_PROGRESS")
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisJob(TimestampedEntity, Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    job_status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before_version: Mapped[int | None] = mapped_column(Integer)
    after_version: Mapped[int | None] = mapped_column(Integer)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentTool(TimestampedEntity, Base):
    """A project-scoped, read-only tool that may be granted to an Agent capability."""

    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_agent_tool_project_key"),
        CheckConstraint(
            "tool_type IN ('DOCUMENT_RETRIEVAL', 'GIT_DIFF', 'CI_EVIDENCE', 'EVIDENCE_QUERY', 'HTTP_QUERY')",
            name="ck_agent_tool_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    secret_ref: Mapped[str | None] = mapped_column(String(160))
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class AgentCapability(TimestampedEntity, Base):
    """A core or user-defined Agent. Runtime behaviour always comes from a version."""

    __tablename__ = "agent_capabilities"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_agent_capability_project_key"),
        CheckConstraint("core_scope IN ('REQUIREMENT', 'DELIVERY', 'SHARED')", name="ck_agent_capability_core_scope"),
        CheckConstraint("kind IN ('SYSTEM', 'CUSTOM')", name="ck_agent_capability_kind"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    core_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    is_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_default_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class AgentCapabilityVersion(Base):
    __tablename__ = "agent_capability_versions"
    __table_args__ = (UniqueConstraint("capability_id", "version_no", name="uq_agent_capability_version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    capability_id: Mapped[UUID] = mapped_column(ForeignKey("agent_capabilities.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tool_bindings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    parameter_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrchestrationTemplate(TimestampedEntity, Base):
    __tablename__ = "orchestration_templates"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_orchestration_template_project_name"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessment_profile: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_system: Mapped[bool] = mapped_column(nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class OrchestrationTemplateNode(Base):
    __tablename__ = "orchestration_template_nodes"
    __table_args__ = (
        UniqueConstraint("template_id", "display_order", name="uq_orchestration_template_node_order"),
        UniqueConstraint("template_id", "capability_version_id", name="uq_orchestration_template_capability"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("orchestration_templates.id", ondelete="CASCADE"), nullable=False)
    capability_version_id: Mapped[UUID] = mapped_column(ForeignKey("agent_capability_versions.id"), nullable=False)
    core_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class TaskOrchestrationBinding(Base):
    __tablename__ = "task_orchestration_bindings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("verification_tasks.id", ondelete="CASCADE"), unique=True, nullable=False)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("orchestration_templates.id"), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    bound_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRunOrchestrationSnapshot(Base):
    __tablename__ = "analysis_run_orchestration_snapshots"
    raw_body: Mapped[str | None] = mapped_column(Text)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), unique=True, nullable=False)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("orchestration_templates.id"), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assessment_profile: Mapped[str] = mapped_column(String(48), nullable=False, default="DELIVERY_VERIFICATION")
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    template_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    nodes_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
