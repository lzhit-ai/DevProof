"""Read Java-owned selections and freeze their provenance with legacy formal input.

The caller locks the cycle before selecting a baseline. This module never edits
plans, selections or the current-selection pointer.
"""

import hashlib
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.services.repository_identity import github_repository_slug_from_git_url
from app.domain.errors import DomainError
from app.infrastructure.persistence.models import DeliveryClaimDraft, GitRepository, GitSnapshot, InputSnapshotPlan


def _hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def selected_plan_for_freeze(
    session: Session, *, cycle_id: UUID, project_id: UUID, git: GitSnapshot, claims: list[DeliveryClaimDraft]
) -> dict | None:
    row = session.execute(text("""
        SELECT p.*,v.body_json AS plan_body,v.content_hash AS actual_plan_hash,v.status,v.confirmed_at,
               i.project_id,rs.repository_id,rs.target_sha
        FROM cycle_plan_selection_current c JOIN cycle_plan_selections p ON p.id=c.selection_id
        JOIN plan_versions v ON v.id=p.plan_version_id JOIN idea_revisions ir ON ir.id=v.idea_revision_id
        JOIN ideas i ON i.id=ir.idea_id JOIN planning_runs pr ON pr.id=v.planning_run_id
        JOIN planning_input_snapshots ps ON ps.id=pr.snapshot_id JOIN repository_snapshots rs ON rs.id=ps.repository_snapshot_id
        WHERE c.cycle_id=:cycle
    """), {"cycle": cycle_id}).mappings().one_or_none()
    if row is None:
        return None
    if row["project_id"] != project_id or row["status"] not in {"CONFIRMED", "SUPERSEDED"} or row["confirmed_at"] is None:
        raise DomainError("INPUT_STALE", "所选计划不属于当前项目或尚未人工确认")
    if _hash(row["body_json"]) != row["content_hash"] or _hash(row["plan_body"]) != row["plan_content_hash"] or row["actual_plan_hash"] != row["plan_content_hash"]:
        raise DomainError("INPUT_STALE", "计划基线正文与内容摘要不一致")
    body = json.loads(row["body_json"])
    if (body.get("cycleId") != str(cycle_id) or body.get("planVersionId") != str(row["plan_version_id"])
            or body.get("planContentHash") != row["plan_content_hash"] or body.get("planningRepositoryId") != str(row["repository_id"])
            or body.get("planningTargetSha") != row["target_sha"]):
        raise DomainError("INPUT_STALE", "计划基线引用与确认记录不一致")
    if git.repository_id != row["repository_id"]:
        planned_repo = session.get(GitRepository, row["repository_id"])
        actual_repo = session.get(GitRepository, git.repository_id)
        planned_slug = github_repository_slug_from_git_url(planned_repo.display_url) if planned_repo else None
        actual_slug = github_repository_slug_from_git_url(actual_repo.display_url) if actual_repo else None
        if not planned_slug or planned_slug != actual_slug:
            raise DomainError("INPUT_STALE", "开发代码与所选计划必须来自同一仓库")
    criteria = {
        (issue["key"], criterion["key"]): criterion
        for issue in json.loads(row["plan_body"])["issues"] for criterion in issue["acceptanceCriteria"]
    }
    claims_by_id = {str(claim.id): claim for claim in claims}
    mappings = body.get("mappings", [])
    seen: set[tuple[str, str]] = set()
    seen_claims: set[str] = set()
    if not mappings or len(mappings) > 12:
        raise DomainError("INPUT_STALE", "计划基线必须包含实际验收绑定")
    for mapping in mappings:
        key = (mapping["issueKey"], mapping["acceptanceKey"])
        claim = claims_by_id.get(mapping["claimId"])
        criterion = criteria.get(key)
        if (key in seen or mapping["claimId"] in seen_claims or claim is None or criterion is None or criterion != mapping["criterion"]
                or claim.claim_key != mapping["claimKey"] or _hash(claim.text) != mapping["claimTextHash"]
                or claim.text.strip() != criterion["condition"].strip()):
            raise DomainError("INPUT_STALE", "交付主张已变化，请重新应用计划验收项后再冻结")
        seen.add(key)
        seen_claims.add(mapping["claimId"])
    return {
        "selectionId": str(row["id"]), "selectionHash": row["content_hash"],
        "planVersionId": str(row["plan_version_id"]), "planContentHash": row["plan_content_hash"],
        "body": body,
    }


def frozen_plan_baseline(session: Session, *, snapshot_id: UUID) -> dict | None:
    binding = session.get(InputSnapshotPlan, snapshot_id)
    if binding is None:
        return None
    row = session.execute(text("SELECT body_json,content_hash FROM cycle_plan_selections WHERE id=:id"),
                          {"id": binding.selection_id}).mappings().one_or_none()
    if row is None or row["content_hash"] != binding.selection_hash or _hash(row["body_json"]) != binding.selection_hash:
        raise DomainError("INPUT_STALE", "冻结的计划绑定缺失或摘要不一致")
    return {
        "selectionId": str(binding.selection_id), "selectionHash": binding.selection_hash,
        "planVersionId": str(binding.plan_version_id), "planContentHash": binding.plan_content_hash,
        "body": json.loads(row["body_json"]),
    }
