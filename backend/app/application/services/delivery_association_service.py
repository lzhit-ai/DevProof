"""Auditable links between source-derived delivery items, PRs, Git ranges and verification tasks."""

from datetime import UTC, datetime
import hashlib
import json
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.common import append_audit_event, require_project_role
from app.application.services.git_service import assert_delivery_item_repository_match
from app.application.services.repository_identity import github_repository_matches
from app.core.config import get_settings
from app.domain.enums import ExternalResourceType, ProjectRole
from app.domain.errors import DomainError
from app.infrastructure.github_source_client import GitHubSourceClient
from app.infrastructure.business_ownership import require_python_delivery_associations
from app.infrastructure.persistence.models import (
    AgentChangeProposalRun,
    DeliveryChangeLink,
    DeliveryItem,
    DeliveryItemSourceLink,
    ExternalConnection,
    ExternalResource,
    ExternalResourceRevision,
    GitRepository,
    GitSnapshot,
    PublishedRecord,
    SourceRevision,
    VerificationCycle,
    VerificationTask,
)


_AGENT_CHANGE_RULES_VERSION = "token-overlap-v1"


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _candidate_tokens(value: str) -> set[str]:
    text = value.lower()[:30_000]
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text))
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return tokens


def _latest_resource_revision(session: Session, resource_id: UUID) -> ExternalResourceRevision | None:
    return (
        session.query(ExternalResourceRevision)
        .filter_by(resource_id=resource_id)
        .order_by(ExternalResourceRevision.revision_no.desc())
        .first()
    )


def _item_for_project(session: Session, *, project_id: UUID, delivery_item_id: UUID) -> DeliveryItem:
    item = session.get(DeliveryItem, delivery_item_id)
    if item is None or item.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "代码交付不存在")
    resource = session.get(ExternalResource, item.external_resource_id)
    if resource is None or resource.resource_type != ExternalResourceType.PULL_REQUEST.value:
        raise DomainError("INPUT_INVALID", "核验任务只能归属当前项目已同步的 GitHub PR")
    return item


def _item_source_connection(session: Session, *, item: DeliveryItem) -> ExternalConnection:
    resource = session.get(ExternalResource, item.external_resource_id)
    connection = session.get(ExternalConnection, resource.connection_id) if resource else None
    if resource is None or connection is None or connection.project_id != item.project_id:
        raise DomainError("INPUT_INVALID", "研发事项缺少可核对的外部来源仓库")
    return connection


def _assert_pr_matches_item(session: Session, *, item: DeliveryItem, resource: ExternalResource) -> None:
    connection = _item_source_connection(session, item=item)
    if resource.connection_id != connection.id:
        raise DomainError("INPUT_INVALID", "研发事项只能关联同一来源仓库的 PR")


def bind_task_delivery_item(
    session: Session,
    *,
    project_id: UUID,
    task_id: UUID,
    delivery_item_id: UUID,
    actor_id: UUID,
    correlation_id: str,
) -> VerificationTask:
    from app.infrastructure.business_ownership import require_python_task_management
    require_python_task_management(session)
    task = session.get(VerificationTask, task_id)
    if task is None or task.project_id != project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "核验任务不存在")
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    if task.delivery_item_id != item.id and session.query(PublishedRecord).filter_by(task_id=task.id).first() is not None:
        raise DomainError("STATE_CONFLICT", "已固化正式记录的历史任务不可重新归属研发事项")
    snapshots = (
        session.query(GitSnapshot)
        .join(VerificationCycle, VerificationCycle.id == GitSnapshot.cycle_id)
        .filter(VerificationCycle.task_id == task.id)
        .all()
    )
    for snapshot in snapshots:
        repository = session.get(GitRepository, snapshot.repository_id)
        if repository is None:
            raise DomainError("INPUT_INVALID", "核验任务存在无法核对来源的 Git 范围")
        assert_delivery_item_repository_match(
            session,
            project_id=task.project_id,
            delivery_item_id=item.id,
            repository=repository,
        )
    task.delivery_item_id = item.id
    task.version += 1
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="VerificationTask",
        aggregate_id=task.id,
        action="TASK_DELIVERY_ITEM_BOUND",
        correlation_id=correlation_id,
        after_version=task.version,
        payload={"deliveryItemId": str(item.id)},
    )
    return task


def _pr_for_project(session: Session, *, project_id: UUID, pull_request_resource_id: UUID) -> ExternalResource:
    resource = session.get(ExternalResource, pull_request_resource_id)
    connection = session.get(ExternalConnection, resource.connection_id) if resource else None
    if resource is None or connection is None or connection.project_id != project_id or resource.resource_type != ExternalResourceType.PULL_REQUEST.value:
        raise DomainError("INPUT_INVALID", "关联目标必须是当前项目已同步的 GitHub PR")
    return resource


def _git_snapshot_for_item(session: Session, *, item: DeliveryItem, git_snapshot_id: UUID) -> GitSnapshot:
    snapshot = session.get(GitSnapshot, git_snapshot_id)
    cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
    task = session.get(VerificationTask, cycle.task_id) if cycle else None
    if task is None or task.project_id != item.project_id:
        raise DomainError("INPUT_INVALID", "Git 范围不存在或不属于当前项目")
    if task.delivery_item_id != item.id:
        raise DomainError("STATE_CONFLICT", "Git 范围所属核验任务尚未绑定当前研发事项")
    repository = session.get(GitRepository, snapshot.repository_id)
    connection = _item_source_connection(session, item=item)
    if repository is None or not github_repository_matches(
        repository_url=repository.display_url, repository_slug=connection.repository_slug
    ):
        raise DomainError("INPUT_INVALID", "研发事项只能关联同一来源仓库的 Git 范围")
    return snapshot


def _existing_link(
    session: Session,
    *,
    delivery_item_id: UUID,
    pull_request_resource_id: UUID | None,
    git_snapshot_id: UUID | None,
) -> DeliveryChangeLink | None:
    query = session.query(DeliveryChangeLink).filter_by(delivery_item_id=delivery_item_id)
    if pull_request_resource_id is not None:
        return query.filter_by(pull_request_resource_id=pull_request_resource_id).one_or_none()
    return query.filter_by(git_snapshot_id=git_snapshot_id).one_or_none()


def _upsert_link(
    session: Session,
    *,
    item: DeliveryItem,
    pull_request_resource_id: UUID | None,
    git_snapshot_id: UUID | None,
    link_status: str,
    link_source: str,
    confidence: float | None,
    reason: str,
    actor_id: UUID,
    agent_proposal_run_id: UUID | None = None,
) -> tuple[DeliveryChangeLink, bool]:
    existing = _existing_link(
        session,
        delivery_item_id=item.id,
        pull_request_resource_id=pull_request_resource_id,
        git_snapshot_id=git_snapshot_id,
    )
    is_confirmed = link_status == "CONFIRMED"
    if existing is None:
        link = DeliveryChangeLink(
            delivery_item_id=item.id,
            pull_request_resource_id=pull_request_resource_id,
            git_snapshot_id=git_snapshot_id,
            link_status=link_status,
            link_source=link_source,
            confidence=confidence,
            reason=reason,
            agent_proposal_run_id=agent_proposal_run_id,
            created_by=actor_id,
            confirmed_by=actor_id if is_confirmed else None,
            confirmed_at=datetime.now(UTC) if is_confirmed else None,
        )
        session.add(link)
        session.flush()
        return link, True
    if existing.link_status != "CONFIRMED" and is_confirmed:
        existing.link_status = "CONFIRMED"
        existing.link_source = link_source
        existing.confidence = confidence
        existing.reason = reason
        existing.confirmed_by = actor_id
        existing.confirmed_at = datetime.now(UTC)
        return existing, True
    return existing, False


def confirm_change_link(
    session: Session,
    *,
    project_id: UUID,
    delivery_item_id: UUID,
    pull_request_resource_id: UUID | None,
    git_snapshot_id: UUID | None,
    reason: str,
    actor_id: UUID,
    correlation_id: str,
) -> DeliveryChangeLink:
    require_python_delivery_associations(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    if (pull_request_resource_id is None) == (git_snapshot_id is None):
        raise DomainError("INPUT_INVALID", "一次只能确认一个 PR 或 Git 范围关联")
    if pull_request_resource_id is not None:
        resource = _pr_for_project(session, project_id=project_id, pull_request_resource_id=pull_request_resource_id)
        _assert_pr_matches_item(session, item=item, resource=resource)
    if git_snapshot_id is not None:
        _git_snapshot_for_item(session, item=item, git_snapshot_id=git_snapshot_id)
    link, changed = _upsert_link(
        session,
        item=item,
        pull_request_resource_id=pull_request_resource_id,
        git_snapshot_id=git_snapshot_id,
        link_status="CONFIRMED",
        link_source="USER",
        confidence=1.0,
        reason=reason.strip(),
        actor_id=actor_id,
    )
    if changed:
        append_audit_event(
            session,
            project_id=project_id,
            actor_id=actor_id,
            aggregate_type="DeliveryChangeLink",
            aggregate_id=link.id,
            action="DELIVERY_CHANGE_LINK_CONFIRMED",
            correlation_id=correlation_id,
            payload={"deliveryItemId": str(item.id), "pullRequestResourceId": str(pull_request_resource_id) if pull_request_resource_id else None, "gitSnapshotId": str(git_snapshot_id) if git_snapshot_id else None},
        )
    return link


def _agent_target_for_item(session: Session, *, project_id: UUID, item: DeliveryItem, target_kind: str, target_id: UUID) -> dict:
    if target_kind == "PULL_REQUEST":
        resource = _pr_for_project(session, project_id=project_id, pull_request_resource_id=target_id)
        _assert_pr_matches_item(session, item=item, resource=resource)
        revision = _latest_resource_revision(session, resource.id)
        if revision is None:
            raise DomainError("STATE_CONFLICT", "候选 PR 尚未同步可用版本")
        return {
            "targetKind": "PULL_REQUEST",
            "targetId": resource.id,
            "targetLabel": f"PR #{resource.external_key} · {revision.title}",
            "inputRef": {"resourceRevisionId": str(revision.id), "contentHash": revision.content_hash},
            "text": f"{resource.external_key} {revision.title} {revision.body}",
            "pullRequestResourceId": resource.id,
            "gitSnapshotId": None,
        }
    if target_kind == "GIT_SNAPSHOT":
        snapshot = _git_snapshot_for_item(session, item=item, git_snapshot_id=target_id)
        cycle = session.get(VerificationCycle, snapshot.cycle_id)
        task = session.get(VerificationTask, cycle.task_id) if cycle else None
        if task is None:
            raise DomainError("INPUT_INVALID", "Git 范围所属核验任务不存在")
        return {
            "targetKind": "GIT_SNAPSHOT",
            "targetId": snapshot.id,
            "targetLabel": f"{snapshot.base_sha[:12]}..{snapshot.target_sha[:12]}",
            "inputRef": {"gitSnapshotId": str(snapshot.id), "diffHash": snapshot.diff_hash, "taskId": str(task.id)},
            "text": f"{task.title} {task.requirement_key} {snapshot.selected_base_ref} {snapshot.selected_target_ref}",
            "pullRequestResourceId": None,
            "gitSnapshotId": snapshot.id,
        }
    raise DomainError("INPUT_INVALID", "候选目标类型只支持已同步 PR 或已冻结 Git 范围")


def list_agent_candidate_targets(session: Session, *, project_id: UUID, delivery_item_id: UUID, actor_id: UUID) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    connection = _item_source_connection(session, item=item)
    targets: list[dict] = []
    resources = (
        session.query(ExternalResource)
        .join(ExternalConnection, ExternalConnection.id == ExternalResource.connection_id)
        .filter(
            ExternalConnection.id == connection.id,
            ExternalResource.resource_type == ExternalResourceType.PULL_REQUEST.value,
        )
        .order_by(ExternalResource.external_key.desc())
        .limit(100)
        .all()
    )
    for resource in resources:
        revision = _latest_resource_revision(session, resource.id)
        if revision is None:
            continue
        targets.append(
            {
                "target_kind": "PULL_REQUEST",
                "target_id": resource.id,
                "target_label": f"PR #{resource.external_key} · {revision.title}",
                "input_ref": {"resourceRevisionId": str(revision.id), "contentHash": revision.content_hash},
            }
        )
    snapshots = (
        session.query(GitSnapshot)
        .join(VerificationCycle, VerificationCycle.id == GitSnapshot.cycle_id)
        .join(VerificationTask, VerificationTask.id == VerificationCycle.task_id)
        .filter(VerificationTask.project_id == project_id, VerificationTask.delivery_item_id == item.id)
        .order_by(GitSnapshot.created_at.desc())
        .limit(100)
        .all()
    )
    for snapshot in snapshots:
        targets.append(
            {
                "target_kind": "GIT_SNAPSHOT",
                "target_id": snapshot.id,
                "target_label": f"冻结 Git 范围 · {snapshot.base_sha[:12]}..{snapshot.target_sha[:12]}",
                "input_ref": {"gitSnapshotId": str(snapshot.id), "diffHash": snapshot.diff_hash},
            }
        )
    return targets


def propose_agent_change_candidates(
    session: Session,
    *,
    project_id: UUID,
    delivery_item_id: UUID,
    targets: list[dict],
    actor_id: UUID,
    correlation_id: str,
) -> tuple[AgentChangeProposalRun, list[DeliveryChangeLink], dict]:
    require_python_delivery_associations(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    if not targets or len(targets) > 20:
        raise DomainError("INPUT_INVALID", "候选 Agent 每次必须在 1-20 个已选目标中工作")
    target_keys = {(str(target["target_kind"]), UUID(str(target["target_id"]))) for target in targets}
    if len(target_keys) != len(targets):
        raise DomainError("INPUT_INVALID", "候选目标不能重复")
    source_revision = _latest_resource_revision(session, item.external_resource_id)
    item_text = f"{item.external_key} {item.title} {source_revision.title if source_revision else ''} {source_revision.body if source_revision else ''}"
    item_tokens = _candidate_tokens(item_text)
    resolved_targets = [
        _agent_target_for_item(
            session,
            project_id=project_id,
            item=item,
            target_kind=str(target["target_kind"]),
            target_id=UUID(str(target["target_id"])),
        )
        for target in targets
    ]
    manifest = {
        "schemaVersion": "agent-change-link-candidate-v1",
        "deliveryItem": {
            "id": str(item.id),
            "externalKey": item.external_key,
            "primaryResourceRevisionId": str(source_revision.id) if source_revision else None,
            "primaryContentHash": source_revision.content_hash if source_revision else None,
        },
        "candidateTargets": [
            {
                "targetKind": target["targetKind"],
                "targetId": str(target["targetId"]),
                "targetLabel": target["targetLabel"],
                "inputRef": target["inputRef"],
            }
            for target in resolved_targets
        ],
    }
    proposal_run = AgentChangeProposalRun(
        project_id=project_id,
        delivery_item_id=item.id,
        input_manifest=manifest,
        input_hash=_hash(manifest),
        rules_version=_AGENT_CHANGE_RULES_VERSION,
        candidate_target_count=len(resolved_targets),
        created_by=actor_id,
    )
    session.add(proposal_run)
    session.flush()
    created_links: list[DeliveryChangeLink] = []
    skipped_existing = 0
    skipped_no_overlap = 0
    for target in resolved_targets:
        if _existing_link(
            session,
            delivery_item_id=item.id,
            pull_request_resource_id=target["pullRequestResourceId"],
            git_snapshot_id=target["gitSnapshotId"],
        ) is not None:
            skipped_existing += 1
            continue
        overlap = sorted(item_tokens & _candidate_tokens(target["text"]))
        if not overlap:
            skipped_no_overlap += 1
            continue
        confidence = round(min(0.8, 0.35 + 0.07 * min(len(overlap), 6)), 2)
        reason = (
            f"受控候选 Agent（{_AGENT_CHANGE_RULES_VERSION}）仅比较事项来源版本与用户选定目标的标题/元数据；"
            f"共享标识符：{'、'.join(overlap[:8])}。此为待人工确认的关联，不证明交付完成。"
        )
        link, changed = _upsert_link(
            session,
            item=item,
            pull_request_resource_id=target["pullRequestResourceId"],
            git_snapshot_id=target["gitSnapshotId"],
            link_status="CANDIDATE",
            link_source="AGENT",
            confidence=confidence,
            reason=reason,
            actor_id=actor_id,
            agent_proposal_run_id=proposal_run.id,
        )
        if changed:
            created_links.append(link)
    proposal_run.created_candidate_count = len(created_links)
    result = {
        "createdCandidateCount": len(created_links),
        "skippedExistingCount": skipped_existing,
        "skippedNoOverlapCount": skipped_no_overlap,
    }
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="AgentChangeProposalRun",
        aggregate_id=proposal_run.id,
        action="AGENT_DELIVERY_CHANGE_CANDIDATES_PROPOSED",
        correlation_id=correlation_id,
        payload={"deliveryItemId": str(item.id), "rulesVersion": _AGENT_CHANGE_RULES_VERSION, **result},
    )
    return proposal_run, created_links, result


def _primary_issue_resource(session: Session, *, item: DeliveryItem) -> tuple[ExternalResource, ExternalConnection] | None:
    link = (
        session.query(DeliveryItemSourceLink)
        .filter_by(delivery_item_id=item.id, link_role="PRIMARY")
        .filter(DeliveryItemSourceLink.external_resource_revision_id.is_not(None))
        .order_by(DeliveryItemSourceLink.created_at.desc())
        .first()
    )
    revision = session.get(ExternalResourceRevision, link.external_resource_revision_id) if link else None
    resource = session.get(ExternalResource, revision.resource_id) if revision else None
    connection = session.get(ExternalConnection, resource.connection_id) if resource else None
    if resource is None or connection is None or resource.resource_type != ExternalResourceType.ISSUE.value:
        return None
    return resource, connection


def _timeline_pr_events(events: list[dict]) -> list[tuple[str, str, str]]:
    relations: list[tuple[str, str, str]] = []
    for event in events:
        source = event.get("source") if isinstance(event, dict) else None
        issue = source.get("issue") if isinstance(source, dict) else None
        if not isinstance(issue, dict) or not isinstance(issue.get("pull_request"), dict):
            continue
        number = issue.get("number")
        if not isinstance(number, int):
            continue
        event_name = str(event.get("event") or "")
        if event_name == "cross-referenced":
            relations.append((str(number), "CONFIRMED", "GitHub Issue 时间线记录该 PR 对此事项的交叉引用"))
    return relations


def discover_platform_links(
    session: Session,
    *,
    project_id: UUID,
    delivery_item_id: UUID,
    actor_id: UUID,
    correlation_id: str,
) -> dict:
    require_python_delivery_associations(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    primary = _primary_issue_resource(session, item=item)
    if primary is None:
        raise DomainError("STATE_CONFLICT", "当前研发事项没有可用于发现 PR 关联的 GitHub Issue 来源")
    issue, connection = primary
    events = GitHubSourceClient(
        repository_slug=connection.repository_slug,
        api_base_url=connection.api_base_url,
        secret_ref=connection.secret_ref,
        settings=get_settings(),
    ).fetch_issue_timeline(issue.external_key)
    changed_count = 0
    skipped_count = 0
    for pr_number, link_status, reason in _timeline_pr_events(events):
        pr_resource = session.query(ExternalResource).filter_by(
            connection_id=connection.id,
            resource_type=ExternalResourceType.PULL_REQUEST.value,
            external_key=pr_number,
        ).one_or_none()
        if pr_resource is None:
            skipped_count += 1
            continue
        _, changed = _upsert_link(
            session,
            item=item,
            pull_request_resource_id=pr_resource.id,
            git_snapshot_id=None,
            link_status=link_status,
            link_source="PLATFORM",
            confidence=1.0 if link_status == "CONFIRMED" else 0.7,
            reason=reason,
            actor_id=actor_id,
        )
        changed_count += int(changed)
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="DeliveryItem",
        aggregate_id=item.id,
        action="DELIVERY_PLATFORM_LINKS_DISCOVERED",
        correlation_id=correlation_id,
        payload={"changedCount": changed_count, "skippedCount": skipped_count},
    )
    return {"changedCount": changed_count, "skippedCount": skipped_count}


def list_change_links(session: Session, *, project_id: UUID, delivery_item_id: UUID, actor_id: UUID) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    links = session.query(DeliveryChangeLink).filter_by(delivery_item_id=delivery_item_id).order_by(DeliveryChangeLink.created_at).all()
    result: list[dict] = []
    for link in links:
        if link.pull_request_resource_id is not None:
            resource = session.get(ExternalResource, link.pull_request_resource_id)
            revision = (
                session.query(ExternalResourceRevision)
                .filter_by(resource_id=resource.id)
                .order_by(ExternalResourceRevision.revision_no.desc())
                .first()
                if resource
                else None
            )
            target_kind = "PULL_REQUEST"
            target_id = link.pull_request_resource_id
            target_label = revision.title if revision else "已删除的 PR 来源"
            target_url = revision.web_url if revision else None
        else:
            snapshot = session.get(GitSnapshot, link.git_snapshot_id)
            target_kind = "GIT_SNAPSHOT"
            target_id = link.git_snapshot_id
            target_label = f"{snapshot.base_sha[:12]}..{snapshot.target_sha[:12]}" if snapshot else "已删除的 Git 范围"
            target_url = None
        result.append(
            {
                "id": link.id,
                "delivery_item_id": link.delivery_item_id,
                "target_kind": target_kind,
                "target_id": target_id,
                "target_label": target_label,
                "target_url": target_url,
                "link_status": link.link_status,
                "link_source": link.link_source,
                "confidence": link.confidence,
                "reason": link.reason,
                "agent_proposal_run_id": link.agent_proposal_run_id,
                "confirmed_at": link.confirmed_at,
            }
        )
    return result


def link_document_source(
    session: Session,
    *,
    project_id: UUID,
    delivery_item_id: UUID,
    source_revision_id: UUID,
    link_role: str,
    actor_id: UUID,
    correlation_id: str,
) -> DeliveryItemSourceLink:
    from app.infrastructure.business_ownership import require_python_github_sources
    require_python_github_sources(session)
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.ADMIN})
    item = _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    source = session.get(SourceRevision, source_revision_id)
    if source is None or source.project_id != project_id or source.processing_status != "READY":
        raise DomainError("INPUT_INVALID", "资料版本不存在、不属于当前项目或尚未完成处理")
    existing = session.query(DeliveryItemSourceLink).filter_by(
        delivery_item_id=item.id,
        source_revision_id=source.id,
        link_role=link_role,
    ).one_or_none()
    if existing is not None:
        return existing
    link = DeliveryItemSourceLink(
        delivery_item_id=item.id,
        source_revision_id=source.id,
        link_role=link_role,
        created_by=actor_id,
    )
    session.add(link)
    session.flush()
    append_audit_event(
        session,
        project_id=project_id,
        actor_id=actor_id,
        aggregate_type="DeliveryItemSourceLink",
        aggregate_id=link.id,
        action="DELIVERY_ITEM_DOCUMENT_SOURCE_LINKED",
        correlation_id=correlation_id,
        payload={"deliveryItemId": str(item.id), "sourceRevisionId": str(source.id), "linkRole": link_role},
    )
    return link


def list_item_source_links(session: Session, *, project_id: UUID, delivery_item_id: UUID, actor_id: UUID) -> list[dict]:
    require_project_role(session, project_id, actor_id, {ProjectRole.SUBMITTER, ProjectRole.REVIEWER, ProjectRole.ADMIN})
    _item_for_project(session, project_id=project_id, delivery_item_id=delivery_item_id)
    links = session.query(DeliveryItemSourceLink).filter_by(delivery_item_id=delivery_item_id).order_by(DeliveryItemSourceLink.created_at).all()
    result: list[dict] = []
    for link in links:
        if link.source_revision_id is not None:
            source = session.get(SourceRevision, link.source_revision_id)
            result.append(
                {
                    "id": link.id,
                    "delivery_item_id": link.delivery_item_id,
                    "source_kind": "DOCUMENT",
                    "source_id": link.source_revision_id,
                    "source_label": f"{source.logical_name} r{source.revision_no}" if source else "已删除的资料版本",
                    "link_role": link.link_role,
                }
            )
        else:
            revision = session.get(ExternalResourceRevision, link.external_resource_revision_id)
            result.append(
                {
                    "id": link.id,
                    "delivery_item_id": link.delivery_item_id,
                    "source_kind": "EXTERNAL_RESOURCE",
                    "source_id": link.external_resource_revision_id,
                    "source_label": revision.title if revision else "已删除的外部来源版本",
                    "link_role": link.link_role,
                }
            )
    return result
