import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.core.config import get_settings
from app.application.services.repository_identity import github_repository_matches
from app.domain.enums import ProjectRole
from app.domain.errors import DomainError
from app.domain.ports import GitReaderPort
from app.infrastructure.artifact_storage import LocalArtifactStorage
from app.infrastructure.business_ownership import require_python_git_inputs
from app.infrastructure.persistence.models import ArtifactObject, DeliveryItem, ExternalConnection, ExternalResource, GitRepository, GitSnapshot, VerificationCycle, VerificationTask


def _persist_artifact(
    session: Session,
    *,
    project_id: UUID,
    kind: str,
    content: bytes,
    media_type: str,
    schema_version: str,
) -> ArtifactObject:
    content_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
    existing = session.query(ArtifactObject).filter_by(project_id=project_id, kind=kind, content_hash=content_hash).one_or_none()
    if existing is not None:
        return existing
    artifact = ArtifactObject(
        project_id=project_id,
        kind=kind,
        content_hash=content_hash,
        byte_size=len(content),
        media_type=media_type,
        schema_version=schema_version,
        storage_uri="pending://artifact",
    )
    session.add(artifact)
    session.flush()
    try:
        artifact.storage_uri = LocalArtifactStorage(get_settings().artifact_root).write_bytes(
            [str(project_id), "git-snapshots", str(artifact.id)],
            "payload.diff" if kind == "GIT_DIFF" else "code-change-bundle.json",
            content,
        )
    except (OSError, ValueError) as exc:
        raise DomainError("GIT_ARTIFACT_WRITE_FAILED", "冻结 Git 输入制品写入失败") from exc
    return artifact


def register_repository(
    session: Session, *, project_id: UUID, display_url: str, credential_ref: str | None, actor_id: UUID, correlation_id: str
) -> GitRepository:
    require_python_git_inputs(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    canonical_hash = f"sha256:{hashlib.sha256(display_url.strip().encode('utf-8')).hexdigest()}"
    existing = session.query(GitRepository).filter_by(project_id=project_id, canonical_url_hash=canonical_hash).one_or_none()
    if existing is not None:
        if existing.credential_ref != credential_ref:
            existing.credential_ref = credential_ref
            append_audit_event(
                session,
                project_id=project_id,
                actor_id=actor_id,
                aggregate_type="GitRepository",
                aggregate_id=existing.id,
                action="GIT_REPOSITORY_CREDENTIAL_REF_UPDATED",
                correlation_id=correlation_id,
                payload={"credentialRefConfigured": credential_ref is not None},
            )
        return existing
    repository = GitRepository(
        project_id=project_id,
        canonical_url_hash=canonical_hash,
        display_url=display_url.strip(),
        credential_ref=credential_ref,
    )
    session.add(repository)
    session.flush()
    append_audit_event(session, project_id=project_id, actor_id=actor_id, aggregate_type="GitRepository", aggregate_id=repository.id, action="GIT_REPOSITORY_REGISTERED", correlation_id=correlation_id)
    return repository


def list_repositories(session: Session, *, project_id: UUID, actor_id: UUID) -> list[GitRepository]:
    """Return project-owned read-only repositories for input-range selection."""
    require_project_role(
        session,
        project_id,
        actor_id,
        {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN},
    )
    return (
        session.query(GitRepository)
        .filter_by(project_id=project_id)
        .order_by(GitRepository.created_at.desc())
        .all()
    )


def get_git_snapshot_diff(session: Session, *, snapshot_id: UUID, actor_id: UUID) -> dict:
    snapshot = session.get(GitSnapshot, snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Git 快照不存在")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    if not snapshot.diff_artifact_id or not snapshot.code_change_artifact_id:
        raise DomainError("GIT_ARTIFACT_MISSING", "该历史 Git 快照未保存可回放 Diff 制品")
    diff_artifact = session.get(ArtifactObject, snapshot.diff_artifact_id)
    bundle_artifact = session.get(ArtifactObject, snapshot.code_change_artifact_id)
    try:
        storage = LocalArtifactStorage(get_settings().artifact_root)
        raw = storage.read_bytes(diff_artifact.storage_uri) if diff_artifact else b""
        bundle_bytes = storage.read_bytes(bundle_artifact.storage_uri) if bundle_artifact else b""
        if not diff_artifact or f"sha256:{hashlib.sha256(raw).hexdigest()}" != diff_artifact.content_hash:
            raise DomainError("GIT_ARTIFACT_HASH_MISMATCH", "冻结 Git Diff 制品哈希不一致")
        if not bundle_artifact or f"sha256:{hashlib.sha256(bundle_bytes).hexdigest()}" != bundle_artifact.content_hash:
            raise DomainError("GIT_ARTIFACT_HASH_MISMATCH", "代码变更制品哈希不一致")
        bundle = json.loads(bundle_bytes.decode("utf-8"))
    except (DomainError, OSError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError("GIT_ARTIFACT_UNAVAILABLE", "冻结 Git 制品当前不可读取") from exc
    return {
        "snapshotId": str(snapshot.id), "baseSha": snapshot.base_sha, "targetSha": snapshot.target_sha,
        "effectiveBaseSha": snapshot.effective_base_sha or snapshot.base_sha, "diffMode": snapshot.diff_mode,
        "diffHash": snapshot.diff_hash, "diffArtifactId": str(diff_artifact.id),
        "coverage": {"capture": snapshot.coverage, "bundle": bundle.get("coverage", {})},
        "files": bundle.get("files", []),
        "contexts": bundle.get("contexts", []),
    }


def assert_delivery_item_repository_match(
    session: Session, *, project_id: UUID, delivery_item_id: UUID | None, repository: GitRepository
) -> None:
    """A task bound to an external delivery item may only freeze its source repository."""
    if delivery_item_id is None:
        return
    item = session.get(DeliveryItem, delivery_item_id)
    resource = session.get(ExternalResource, item.external_resource_id) if item else None
    connection = session.get(ExternalConnection, resource.connection_id) if resource else None
    if item is None or resource is None or connection is None or connection.project_id != project_id:
        raise DomainError("INPUT_INVALID", "代码交付缺少可核对的 Pull Request 来源仓库")
    if not github_repository_matches(repository_url=repository.display_url, repository_slug=connection.repository_slug):
        raise DomainError("GIT_RANGE_INVALID", "本次代码交付的 Git 范围必须来自该 Pull Request 的同一来源仓库")


def freeze_git_snapshot(
    session: Session, *, cycle_id: UUID, repository_id: UUID, base_ref: str, target_ref: str, diff_mode: str, include_paths: list[str], exclude_paths: list[str], actor_id: UUID, correlation_id: str, reader: GitReaderPort
) -> GitSnapshot:
    require_python_git_inputs(session)
    cycle = session.get(VerificationCycle, cycle_id)
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    repository = session.get(GitRepository, repository_id)
    if task is None or repository is None or repository.project_id != task.project_id:
        raise DomainError("GIT_RANGE_INVALID", "轮次或仓库不存在，或不属于同一项目")
    require_project_role(session, task.project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    if cycle.business_status not in {"DRAFT", "NEEDS_EVIDENCE", "NEEDS_CONFIRMATION"}:
        raise DomainError("STATE_CONFLICT", "当前轮次不能再冻结新的 Git 范围")
    assert_delivery_item_repository_match(
        session,
        project_id=task.project_id,
        delivery_item_id=task.delivery_item_id,
        repository=repository,
    )
    frozen = reader.freeze_range(
        repository.display_url,
        base_ref,
        target_ref,
        diff_mode,
        include_paths,
        exclude_paths,
        credential_ref=repository.credential_ref,
    )
    if not frozen.diff:
        raise DomainError("GIT_DIFF_EMPTY", "指定范围没有可冻结的 Git Diff")
    diff_artifact = _persist_artifact(
        session,
        project_id=task.project_id,
        kind="GIT_DIFF",
        content=frozen.diff,
        media_type="text/x-diff",
        schema_version="git-diff-v2",
    )
    bundle_bytes = json.dumps(frozen.code_change_bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    bundle_artifact = _persist_artifact(
        session,
        project_id=task.project_id,
        kind="CODE_CHANGE_BUNDLE",
        content=bundle_bytes,
        media_type="application/json",
        schema_version=str(frozen.code_change_bundle.get("schemaVersion", "code-change-bundle-v2")),
    )
    snapshot = GitSnapshot(
        cycle_id=cycle_id,
        repository_id=repository_id,
        selected_base_ref=base_ref,
        selected_target_ref=target_ref,
        base_sha=frozen.base_sha,
        target_sha=frozen.target_sha,
        merge_base_sha=frozen.merge_base_sha,
        effective_base_sha=frozen.base_sha if diff_mode == "TWO_DOT" else frozen.merge_base_sha,
        capture_version="git-capture-v3",
        diff_mode=diff_mode,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        diff_hash=frozen.diff_hash,
        coverage=frozen.coverage,
        diff_artifact_id=diff_artifact.id,
        code_change_artifact_id=bundle_artifact.id,
    )
    session.add(snapshot)
    session.flush()
    append_audit_event(session, project_id=task.project_id, actor_id=actor_id, aggregate_type="GitSnapshot", aggregate_id=snapshot.id, action="GIT_SNAPSHOT_FROZEN", correlation_id=correlation_id, payload={"baseSha": frozen.base_sha, "targetSha": frozen.target_sha, "diffHash": frozen.diff_hash, "diffArtifactId": str(diff_artifact.id), "codeChangeArtifactId": str(bundle_artifact.id)})
    return snapshot
