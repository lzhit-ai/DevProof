"""Transitional Python business bindings; ownership moves to Java by aggregate."""

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.errors import DomainError
from app.domain.verification_contracts import VerificationGraphState, VerificationSteps
from app.domain.model_contracts import CodeReviewChallengeRequest, CodeReviewRequest, GenerationRequest
from app.application.services.code_review_service import persist_validated_challenges, persist_validated_findings, plan_code_review, plan_code_review_challenges
from app.infrastructure.agent_tool_runner import execute_http_query
from app.infrastructure.code_context import extract_symbol_context
from app.infrastructure.generation_model import create_generation_model
from app.infrastructure.git_reader import ReadOnlyGitReader
from app.infrastructure.persistence.models import (
    AnalysisCoverage,
    AnalysisRun,
    AnalysisRunManifest,
    AnalysisRunOrchestrationSnapshot,
    AnalysisRunContextArtifact,
    AgentToolExecution,
    ArtifactObject,
    Claim,
    ClaimEvidenceLink,
    CodeReviewFinding,
    CodeReviewFindingChallenge,
    EvidenceItem,
    GitRepository,
    GitSnapshot,
    InputSnapshot,
    InputSnapshotClaim,
    InputSnapshotGit,
    ModelCall,
    NodeAttempt,
    RiskFinding,
    RunEvent,
    SourceRevision,
    VerificationCycle,
    VerificationResult,
    VerificationTask,
)
from app.infrastructure.artifact_storage import LocalArtifactStorage


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|password|passwd|secret|token)\b(\s*[:=]\s*)([^\s,;]+)"
)
_ASCII_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_KEY_TOKEN = re.compile(r"[A-Za-z]{2,}-\d+")
_CJK_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,}")
_STOP_WORDS = {"this", "that", "with", "from", "true", "false", "none", "null", "return", "class", "function", "const", "import", "async", "await"}


def _safe_excerpt(text: str, limit: int = 1600) -> str:
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)[:limit]


def _tokens(text: str) -> set[str]:
    ascii_tokens = {item.lower() for item in _ASCII_TOKEN.findall(text)}
    key_tokens = {item.lower() for item in _KEY_TOKEN.findall(text)}
    cjk_tokens = set(_CJK_TOKEN.findall(text))
    return (ascii_tokens | key_tokens | cjk_tokens) - _STOP_WORDS


def _claim_authority(source_role: str) -> int:
    return {"ACCEPTANCE": 4, "REQUIREMENT": 4, "DESIGN": 3, "MEETING": 2}.get(source_role.upper(), 1)


def _parse_hunks(diff: str) -> list[tuple[str, str, int | None, int | None, str]]:
    """Return path, header, new start/end and the immutable hunk payload."""
    hunks: list[tuple[str, str, int | None, int | None, str]] = []
    path: str | None = None
    header: str | None = None
    new_start: int | None = None
    new_line: int | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal lines
        if path and header and lines:
            added = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
            payload = "\n".join(added or lines)
            end = (new_line - 1) if new_line is not None else None
            hunks.append((path, header, new_start, end, payload))
        lines = []

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            flush()
            path = None
            header = None
            new_start = None
            new_line = None
        elif line.startswith("+++ "):
            candidate = line[4:].strip()
            path = candidate[2:] if candidate.startswith("b/") else (None if candidate == "/dev/null" else candidate)
        elif line.startswith("@@ "):
            flush()
            header = line
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            new_start = int(match.group(1)) if match else None
            new_line = new_start
        elif header is not None:
            lines.append(line)
            if new_line is not None and (line.startswith("+") or line.startswith(" ")) and not line.startswith("+++"):
                new_line += 1
    flush()
    return hunks


def create_legacy_verification_steps(session: Session, run_id: UUID) -> VerificationSteps:
    """Bind the existing business steps without executing them during composition."""

    orchestration = session.query(AnalysisRunOrchestrationSnapshot).filter_by(run_id=run_id).one_or_none()
    if orchestration is None:
        raise DomainError("ORCHESTRATION_SNAPSHOT_MISSING", "analysis run has no frozen orchestration snapshot")
    enabled_nodes = [item for item in orchestration.nodes_snapshot if item.get("enabled")]
    enabled_keys = {str(item.get("capabilityKey")) for item in enabled_nodes}
    required_keys = {"requirement-claim-core", "delivery-git-diff", "evidence-reconciliation"}
    if not required_keys.issubset(enabled_keys):
        raise DomainError("ORCHESTRATION_INVALID", "frozen orchestration is missing a required dual-core node")
    built_in_keys = {
        "requirement-claim-core",
        "delivery-git-diff",
        "ci-evidence-import",
        "risk-scan",
        "model-link-proposal",
        "evidence-reconciliation",
        "report-draft",
    }
    custom_agent_nodes = [item for item in enabled_nodes if item.get("capabilityKey") not in built_in_keys]

    def with_plan_acceptance(payloads: list[dict]) -> list[dict]:
        """Supply the exact acceptance contract as requirements, never as evidence."""
        run = session.get(AnalysisRun, run_id)
        if run is None or run.plan_version_id is None:
            return payloads
        frozen = {item.claim_key: item.source_manifest.get("planAcceptance") for item in
                  session.query(InputSnapshotClaim).filter_by(snapshot_id=run.snapshot_id).all()}
        for payload in payloads:
            claim = session.get(Claim, UUID(payload["id"]))
            acceptance = frozen.get(claim.claim_key) if claim else None
            if acceptance:
                payload["planAcceptance"] = {**acceptance, "role": "ACCEPTANCE_REQUIREMENT",
                    "rules": "按 condition、verificationMethod 和 requiredEvidence 核验；这些字段描述要求，不是已经存在的证据，不能作为 Evidence ID 引用。"}
        return payloads

    def ensure_not_cancelled() -> None:
        run = session.get(AnalysisRun, run_id)
        if run is not None and run.cancel_requested_at is not None:
            raise DomainError("RUN_CANCELLED", "analysis run was cancelled at a workflow boundary")

    def observed(node_id: str, handler):
        def invoke(state: VerificationGraphState) -> VerificationGraphState:
            attempt_no = session.query(NodeAttempt).filter_by(analysis_run_id=run_id, node_id=node_id).count() + 1
            attempt = NodeAttempt(analysis_run_id=run_id, node_id=node_id, attempt_no=attempt_no, status="RUNNING")
            session.add(attempt)
            session.add(RunEvent(run_id=run_id, node_id=node_id, event_type="NODE_EXECUTION", status="RUNNING", correlation_id=str(run_id), payload_redacted={"workflowVersion": state.get("workflow_schema_version", "v1")}))
            try:
                result = handler(state)
                attempt.status = "SUCCEEDED"
                attempt.finished_at = datetime.now(UTC)
                session.add(RunEvent(run_id=run_id, node_id=node_id, event_type="NODE_EXECUTION", status="SUCCEEDED", correlation_id=str(run_id), payload_redacted={"outputKeys": sorted(result.keys())}))
                return result
            except DomainError as exc:
                attempt.status = "FAILED"
                attempt.error_code = exc.code
                attempt.finished_at = datetime.now(UTC)
                session.add(RunEvent(run_id=run_id, node_id=node_id, event_type="NODE_EXECUTION", status="FAILED", correlation_id=str(run_id), payload_redacted={"errorCode": exc.code}))
                raise
            except Exception:
                attempt.status = "FAILED"
                attempt.error_code = "SYSTEM_ERROR"
                attempt.finished_at = datetime.now(UTC)
                session.add(RunEvent(run_id=run_id, node_id=node_id, event_type="NODE_EXECUTION", status="FAILED", correlation_id=str(run_id), payload_redacted={"errorCode": "SYSTEM_ERROR"}))
                raise
        return invoke

    def load_snapshot(state: VerificationGraphState) -> VerificationGraphState:
        ensure_not_cancelled()
        document_evidence = session.query(EvidenceItem).filter(EvidenceItem.snapshot_id == UUID(state["input_snapshot_id"]), EvidenceItem.source_type.in_(("DOCUMENT", "REQUIREMENT", "PULL_REQUEST"))).all()
        external_evidence = session.query(EvidenceItem).filter(EvidenceItem.snapshot_id == UUID(state["input_snapshot_id"]), EvidenceItem.source_type.in_(("TEST", "BUILD"))).all()
        manual_evidence = session.query(EvidenceItem).filter_by(snapshot_id=UUID(state["input_snapshot_id"]), source_type="MANUAL").all()
        return {
            "evidence_ids": [str(item.id) for item in document_evidence],
            "external_evidence_ids": [str(item.id) for item in external_evidence],
            "manual_evidence_ids": [str(item.id) for item in manual_evidence],
        }

    def collect_git_evidence(state: VerificationGraphState) -> VerificationGraphState:
        """Read immutable local artifacts; remote Git is never consulted during analysis."""
        ensure_not_cancelled()
        snapshot = session.get(InputSnapshot, UUID(state["input_snapshot_id"]))
        binding = session.query(InputSnapshotGit).filter_by(snapshot_id=snapshot.id).one_or_none() if snapshot else None
        git_snapshot = session.get(GitSnapshot, binding.git_snapshot_id) if binding else None
        cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
        task = session.get(VerificationTask, cycle.task_id) if cycle else None
        if not all((snapshot, binding, git_snapshot, task, git_snapshot.diff_artifact_id, git_snapshot.code_change_artifact_id)):
            coverage = AnalysisCoverage(analysis_run_id=run_id, scope_kind="GIT_CAPTURE", scope_ref="formal-snapshot", state="UNAVAILABLE", reason_code="GIT_ARTIFACT_MISSING", details={})
            session.add(coverage)
            return {"coverage_id": str(coverage.id), "node_errors": [*state.get("node_errors", []), "GIT_ARTIFACT_MISSING"]}
        diff_artifact = session.get(ArtifactObject, git_snapshot.diff_artifact_id)
        bundle_artifact = session.get(ArtifactObject, git_snapshot.code_change_artifact_id)
        try:
            storage = LocalArtifactStorage(get_settings().artifact_root)
            diff_bytes = storage.read_bytes(diff_artifact.storage_uri) if diff_artifact else b""
            bundle_bytes = storage.read_bytes(bundle_artifact.storage_uri) if bundle_artifact else b""
            if (f"sha256:{hashlib.sha256(diff_bytes).hexdigest()}" != binding.diff_hash or not diff_artifact or diff_artifact.content_hash != binding.diff_hash):
                raise DomainError("GIT_ARTIFACT_HASH_MISMATCH", "冻结 Git Diff 制品哈希不一致")
            if not bundle_artifact or f"sha256:{hashlib.sha256(bundle_bytes).hexdigest()}" != bundle_artifact.content_hash:
                raise DomainError("GIT_ARTIFACT_HASH_MISMATCH", "代码变更制品哈希不一致")
            bundle = json.loads(bundle_bytes.decode("utf-8"))
        except (DomainError, OSError, ValueError, json.JSONDecodeError) as exc:
            code = exc.code if isinstance(exc, DomainError) else "GIT_ARTIFACT_UNAVAILABLE"
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="GIT_CAPTURE", scope_ref="formal-snapshot", state="UNAVAILABLE", reason_code=code, details={}))
            return {"node_errors": [*state.get("node_errors", []), code]}

        evidence_ids: list[str] = []
        for file in bundle.get("files", []):
            for hunk in file.get("hunks", []):
                path, header, payload = str(file.get("path", "")), str(hunk.get("header", "")), str(hunk.get("payload", ""))
                identity = json.dumps({"artifact": str(diff_artifact.id), "path": path, "header": header, "payload": payload}, ensure_ascii=False, sort_keys=True)
                content_hash = f"sha256:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
                evidence = session.query(EvidenceItem).filter_by(snapshot_id=snapshot.id, source_type="CODE", content_hash=content_hash).one_or_none()
                if evidence is None:
                    evidence = EvidenceItem(project_id=task.project_id, snapshot_id=snapshot.id, source_type="CODE", evidence_kind="GIT_DIFF_HUNK", commit_sha=git_snapshot.target_sha, content_hash=content_hash, excerpt_safe=_safe_excerpt(payload), locator={"artifactId": str(diff_artifact.id), "commitSha": git_snapshot.target_sha, "path": path, "oldPath": file.get("old_path"), "hunk": header, "oldLineStart": hunk.get("old_start"), "oldLineEnd": hunk.get("old_end"), "newLineStart": hunk.get("new_start"), "newLineEnd": hunk.get("new_end")}, locator_precision="EXACT", extractor_version="git-diff-v2")
                    session.add(evidence)
                    session.flush()
                evidence_ids.append(str(evidence.id))
        details = {"capture": git_snapshot.coverage, "bundle": bundle.get("coverage", {}), "diffArtifactId": str(diff_artifact.id), "codeChangeArtifactId": str(bundle_artifact.id)}
        coverage = AnalysisCoverage(analysis_run_id=run_id, scope_kind="GIT_CAPTURE", scope_ref="formal-snapshot", state="ANALYZED" if evidence_ids else "PARTIAL", reason_code=None if evidence_ids else "NO_TEXT_HUNKS", details=details)
        session.add(coverage)
        session.flush()
        return {"git_evidence_ids": evidence_ids, "coverage_id": str(coverage.id), "code_change_bundle": bundle}

    def create_claims(state: VerificationGraphState) -> VerificationGraphState:
        ensure_not_cancelled()
        snapshot = session.get(InputSnapshot, UUID(state["input_snapshot_id"]))
        frozen_claims = (
            session.query(InputSnapshotClaim).filter_by(snapshot_id=snapshot.id).order_by(InputSnapshotClaim.claim_key).all()
            if snapshot is not None
            else []
        )
        if not frozen_claims:
            raise DomainError("CLAIMS_NOT_CONFIRMED", "正式快照缺少已确认的交付主张，不能生成交付核验结论")
        claims: list[str] = []
        for frozen in frozen_claims:
            claim = session.query(Claim).filter_by(analysis_run_id=run_id, claim_key=frozen.claim_key).one_or_none()
            if claim is None:
                claim = Claim(
                    analysis_run_id=run_id,
                    claim_key=frozen.claim_key,
                    claim_type="USER_CONFIRMED_DELIVERY",
                    text=frozen.text,
                    authority_level=3,
                )
                session.add(claim)
                session.flush()
            claims.append(str(claim.id))
        return {"claim_ids": claims}

    def review_code(state: VerificationGraphState) -> VerificationGraphState:
        """Run the DELIVERY core against frozen Hunk evidence; model failures are controlled degradation."""
        ensure_not_cancelled()
        bundle = state.get("code_change_bundle")
        claims = [session.get(Claim, UUID(item)) for item in state.get("claim_ids", [])]
        claims = [item for item in claims if item is not None]
        evidence_by_locator: dict[tuple[str, str], str] = {}
        allowed_evidence_ids: set[UUID] = set()
        for evidence_id in state.get("git_evidence_ids", []):
            evidence = session.get(EvidenceItem, UUID(evidence_id))
            if evidence is None:
                continue
            evidence_by_locator[(str(evidence.locator.get("path", "")), str(evidence.locator.get("hunk", "")))] = str(evidence.id)
            allowed_evidence_ids.add(evidence.id)
        if not bundle or not allowed_evidence_ids:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CODE_REVIEW", scope_ref="delivery-git-diff", state="PARTIAL", reason_code="NO_CITABLE_CODE_EVIDENCE", details={}))
            return {}
        settings = get_settings()
        changes, coverage_payload = plan_code_review(bundle=bundle, evidence_by_locator=evidence_by_locator, claims=claims, char_budget=settings.code_review_input_char_budget)
        if not changes:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CODE_REVIEW", scope_ref="delivery-git-diff", state=coverage_payload["state"], reason_code="CODE_REVIEW_BUDGET_EXHAUSTED", details=coverage_payload["details"]))
            return {}
        request = CodeReviewRequest(run_id=run_id, prompt_version="code-review-v1", schema_version="code-review-finding-v1", claims=with_plan_acceptance(coverage_payload["details"]["claims"]), code_changes=changes)
        try:
            generated = create_generation_model(settings).review_code(request)
            _, rejected = persist_validated_findings(session, run_id=run_id, proposal_batch=generated.findings.findings, allowed_evidence_ids=allowed_evidence_ids, allowed_claim_ids={item.id for item in claims})
            session.add(ModelCall(run_id=run_id, provider=generated.provider, model=generated.model, operation="CODE_REVIEW", prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=sorted(str(item) for item in allowed_evidence_ids), status="SUCCEEDED", latency_ms=generated.latency_ms, attempts=generated.attempts))
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CODE_REVIEW", scope_ref="delivery-git-diff", state=coverage_payload["state"], reason_code="MODEL_FINDING_INVALID" if rejected else None, details={**coverage_payload["details"], "modelFindingCount": len(generated.findings.findings), "rejectedFindingCount": rejected}))
            session.flush()
            return {}
        except DomainError as exc:
            manifest = session.query(AnalysisRunManifest).filter_by(run_id=run_id).one_or_none()
            if manifest is not None:
                manifest.degradation = {**manifest.degradation, "codeReview": {"code": exc.code, "promptVersion": request.prompt_version, "schemaVersion": request.schema_version}}
            session.add(ModelCall(run_id=run_id, provider=settings.generation_provider, model=settings.generation_model, operation="CODE_REVIEW", prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=sorted(str(item) for item in allowed_evidence_ids), status="FAILED", attempts=1, error_code=exc.code, error_summary=exc.message[:500]))
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CODE_REVIEW", scope_ref="delivery-git-diff", state="UNAVAILABLE", reason_code=exc.code, details=coverage_payload["details"]))
            return {"node_errors": [*state.get("node_errors", []), exc.code]}

    def challenge_code_findings(state: VerificationGraphState) -> VerificationGraphState:
        """Challenge persisted Findings using only their original frozen Hunk evidence."""
        ensure_not_cancelled()
        findings = session.query(CodeReviewFinding).filter_by(analysis_run_id=run_id).order_by(CodeReviewFinding.created_at, CodeReviewFinding.id).all()
        if not findings:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="FINDING_CHALLENGE", scope_ref="delivery-git-diff", state="NOT_APPLICABLE", reason_code="NO_CODE_REVIEW_FINDINGS", details={"eligibleFindingCount": 0}))
            return {}
        bundle = state.get("code_change_bundle")
        allowed_evidence: dict[UUID, EvidenceItem] = {}
        for evidence_id in state.get("git_evidence_ids", []):
            evidence = session.get(EvidenceItem, UUID(evidence_id))
            if evidence is not None and evidence.source_type == "CODE" and evidence.locator_precision == "EXACT":
                allowed_evidence[evidence.id] = evidence
        claims = {item.id: item for item in (session.get(Claim, UUID(item)) for item in state.get("claim_ids", [])) if item is not None}
        settings = get_settings()
        if not bundle or not allowed_evidence:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="FINDING_CHALLENGE", scope_ref="delivery-git-diff", state="PARTIAL", reason_code="NO_CITABLE_CODE_EVIDENCE", details={"eligibleFindingCount": len(findings)}))
            return {}
        selected, changes, claim_payload, coverage_payload = plan_code_review_challenges(
            bundle=bundle,
            findings=findings,
            evidence_by_id=allowed_evidence,
            claims_by_id=claims,
            char_budget=settings.code_review_challenge_input_char_budget,
            max_findings=settings.code_review_challenge_max_findings,
        )
        if not selected:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="FINDING_CHALLENGE", scope_ref="delivery-git-diff", state=coverage_payload["state"], reason_code="FINDING_CHALLENGE_BUDGET_EXHAUSTED", details=coverage_payload["details"]))
            return {}
        request = CodeReviewChallengeRequest(
            run_id=run_id,
            prompt_version="code-review-challenge-v1",
            schema_version="code-review-challenge-v1",
            claims=with_plan_acceptance(claim_payload),
            code_changes=changes,
            findings=selected,
            timeout_seconds=settings.code_review_challenge_timeout_seconds,
        )
        allowed_ids = set(allowed_evidence)
        try:
            generated = create_generation_model(settings).challenge_code_findings(request)
            model_call = ModelCall(
                run_id=run_id,
                provider=generated.provider,
                model=generated.model,
                operation="CODE_REVIEW_CHALLENGE",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                allowed_evidence_ids=sorted(str(item) for item in allowed_ids),
                status="SUCCEEDED",
                latency_ms=generated.latency_ms,
                attempts=generated.attempts,
            )
            session.add(model_call)
            session.flush()
            persisted, rejected = persist_validated_challenges(
                session,
                run_id=run_id,
                proposal_batch=generated.challenges.challenges,
                allowed_findings={item.id: item for item in findings},
                allowed_evidence_ids=allowed_ids,
                model_call_id=model_call.id,
            )
            reviewed_ids = {item.finding_id for item in persisted}
            missing = [item["findingId"] for item in selected if UUID(item["findingId"]) not in reviewed_ids]
            reason_code = "MODEL_CHALLENGE_INVALID" if rejected else ("MODEL_CHALLENGE_INCOMPLETE" if missing else None)
            session.add(AnalysisCoverage(
                analysis_run_id=run_id,
                scope_kind="FINDING_CHALLENGE",
                scope_ref="delivery-git-diff",
                state="ANALYZED" if not reason_code and coverage_payload["state"] == "ANALYZED" else "PARTIAL",
                reason_code=reason_code,
                details={
                    **coverage_payload["details"],
                    "modelChallengeCount": len(generated.challenges.challenges),
                    "persistedChallengeCount": len(persisted),
                    "rejectedChallengeCount": rejected,
                    "missingChallengeFindingIds": missing,
                },
            ))
            session.flush()
            return {}
        except DomainError as exc:
            manifest = session.query(AnalysisRunManifest).filter_by(run_id=run_id).one_or_none()
            if manifest is not None:
                manifest.degradation = {**manifest.degradation, "findingChallenge": {"code": exc.code, "promptVersion": request.prompt_version, "schemaVersion": request.schema_version}}
            session.add(ModelCall(run_id=run_id, provider=settings.generation_provider, model=settings.generation_model, operation="CODE_REVIEW_CHALLENGE", prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=sorted(str(item) for item in allowed_ids), status="FAILED", attempts=1, error_code=exc.code, error_summary=exc.message[:500]))
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="FINDING_CHALLENGE", scope_ref="delivery-git-diff", state="UNAVAILABLE", reason_code=exc.code, details=coverage_payload["details"]))
            return {"node_errors": [*state.get("node_errors", []), exc.code]}

    def summarize_code_coverage(state: VerificationGraphState) -> VerificationGraphState:
        """Summarize fixed standard-verification scope without asking a model for a completion verdict."""
        ensure_not_cancelled()
        bundle = state.get("code_change_bundle") or {}
        files = bundle.get("files", [])
        review = session.query(AnalysisCoverage).filter_by(analysis_run_id=run_id, scope_kind="CODE_REVIEW").order_by(AnalysisCoverage.id.desc()).first()
        challenge = session.query(AnalysisCoverage).filter_by(analysis_run_id=run_id, scope_kind="FINDING_CHALLENGE").order_by(AnalysisCoverage.id.desc()).first()
        challenges = session.query(CodeReviewFindingChallenge).filter_by(analysis_run_id=run_id).all()
        verdict_counts = {key: 0 for key in ("SUPPORTED", "UNSUPPORTED", "NEEDS_HUMAN")}
        for item in challenges:
            verdict_counts[item.verdict] = verdict_counts.get(item.verdict, 0) + 1
        reviewed_hunks = int((review.details or {}).get("analysedHunks", 0)) if review else 0
        reasons = [item.reason_code for item in (review, challenge) if item is not None and item.reason_code]
        state_name = "ANALYZED" if review and review.state == "ANALYZED" and challenge and challenge.state in {"ANALYZED", "NOT_APPLICABLE"} else "PARTIAL"
        session.add(AnalysisCoverage(
            analysis_run_id=run_id,
            scope_kind="STANDARD_VERIFICATION",
            scope_ref="delivery-git-diff",
            state=state_name,
            reason_code=reasons[0] if reasons else None,
            details={
                "totalFiles": len(files),
                "binaryFiles": sum(1 for item in files if item.get("binary")),
                "totalHunks": sum(len(item.get("hunks", [])) for item in files),
                "reviewedHunks": reviewed_hunks,
                "findingCount": session.query(CodeReviewFinding).filter_by(analysis_run_id=run_id).count(),
                "challengeVerdicts": verdict_counts,
                "uncoveredReasonCodes": reasons,
            },
        ))
        session.flush()
        return {}

    def link_deterministic(state: VerificationGraphState) -> VerificationGraphState:
        ensure_not_cancelled()
        actual_evidence = [session.get(EvidenceItem, UUID(item)) for item in [*state.get("git_evidence_ids", []), *state.get("external_evidence_ids", [])]]
        actual_evidence = [item for item in actual_evidence if item is not None]
        manual_evidence = [session.get(EvidenceItem, UUID(item)) for item in state.get("manual_evidence_ids", [])]
        manual_evidence = [item for item in manual_evidence if item is not None]
        for claim_id in state.get("claim_ids", []):
            claim = session.get(Claim, UUID(claim_id))
            if claim is None:
                continue
            claim_tokens = _tokens(claim.text)
            supporting: list[EvidenceItem] = []
            for evidence in actual_evidence:
                overlap = claim_tokens & _tokens(evidence.excerpt_safe)
                if not overlap:
                    continue
                supporting.append(evidence)
                exit_code = evidence.locator.get("exitCode") if evidence.source_type in {"TEST", "BUILD"} else None
                relation = "CONTRADICTS" if isinstance(exit_code, int) and exit_code != 0 else "SUPPORTS"
                link = session.query(ClaimEvidenceLink).filter_by(claim_id=claim.id, evidence_id=evidence.id, relation=relation).one_or_none()
                if link is None:
                    session.add(ClaimEvidenceLink(
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                        relation=relation,
                        reason=(f"外部 {evidence.source_type} 的非零退出码与目标冲突；标识符命中：" if relation == "CONTRADICTS" else "确定性标识符命中：") + ", ".join(sorted(overlap)[:5]),
                        confidence=0.75,
                        produced_by="DETERMINISTIC",
                        requires_human_confirmation=relation == "CONTRADICTS",
                    ))
            for evidence in manual_evidence:
                overlap = claim_tokens & _tokens(evidence.excerpt_safe)
                if not overlap:
                    continue
                link = session.query(ClaimEvidenceLink).filter_by(
                    claim_id=claim.id,
                    evidence_id=evidence.id,
                    relation="SUPPORTS",
                ).one_or_none()
                if link is None:
                    session.add(ClaimEvidenceLink(
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                        relation="SUPPORTS",
                        reason="人工补证包含与核验目标重叠的标识符：" + ", ".join(sorted(overlap)[:5]),
                        confidence=0.5,
                        produced_by="HUMAN",
                        requires_human_confirmation=False,
                    ))
        # The next node validates uniqueness against persisted links, including these ones.
        session.flush()
        return {}

    def propose_model_links(state: VerificationGraphState) -> VerificationGraphState:
        ensure_not_cancelled()
        if "model-link-proposal" not in enabled_keys:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="MODEL", scope_ref="link-proposal", state="SKIPPED", reason_code="DISABLED_BY_TEMPLATE"))
            return {}
        actual_evidence = [session.get(EvidenceItem, UUID(item)) for item in [*state.get("git_evidence_ids", []), *state.get("external_evidence_ids", []), *state.get("manual_evidence_ids", [])]]
        actual_evidence = [item for item in actual_evidence if item is not None]
        claims = [session.get(Claim, UUID(item)) for item in state.get("claim_ids", [])]
        claims = [item for item in claims if item is not None]
        allowed_ids = {str(item.id) for item in actual_evidence}
        bundle = state.get("code_change_bundle") or {}
        existing_context_symbols = {(str(item.get("path")), str(item.get("symbol"))) for item in bundle.get("contexts", [])}
        supplement_candidates = [
            item for item in bundle.get("contextCandidates", [])
            if (str(item.get("path")), str(item.get("symbol"))) not in existing_context_symbols
        ]
        context_payload: list[dict] = []
        remaining_context_chars = get_settings().code_review_input_char_budget // 2
        for context in bundle.get("contexts", []):
            candidate = {
                "contextId": context.get("contextId"),
                "path": context.get("path"),
                "symbol": context.get("symbol"),
                "relation": context.get("relation"),
                "content": context.get("content"),
                "evidenceRole": "CONTEXT_ONLY",
            }
            size = len(json.dumps(candidate, ensure_ascii=False))
            if size > remaining_context_chars:
                break
            context_payload.append(candidate)
            remaining_context_chars -= size
        request = GenerationRequest(
            run_id=run_id,
            prompt_version="v2",
            schema_version="v2",
            claims=with_plan_acceptance([
                {
                    "id": str(claim.id),
                    "text": claim.text,
                    "candidateEvidenceIds": [
                        str(evidence.id) for evidence in actual_evidence if _tokens(claim.text) & _tokens(evidence.excerpt_safe)
                    ],
                }
                for claim in claims
            ]),
            evidence=[{"id": str(item.id), "excerpt": item.excerpt_safe, "locator": item.locator} for item in actual_evidence],
            temporary_context=[{
                "kind": "FROZEN_CODE_CONTEXT",
                "contexts": context_payload,
                "contextCandidates": supplement_candidates,
                "rules": "CONTEXT_ONLY; never cite it as Diff evidence. A supplemental request may select only a candidateId.",
            }],
        )
        settings = get_settings()
        try:
            model = create_generation_model(settings)
            generated = model.generate(request)
            session.add(ModelCall(
                run_id=run_id,
                provider=generated.provider,
                model=generated.model,
                operation="LINK_PROPOSAL",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                allowed_evidence_ids=sorted(allowed_ids),
                status="SUCCEEDED",
                latency_ms=generated.latency_ms,
                attempts=generated.attempts,
            ))
            claim_ids = {str(item.id) for item in claims}
            for proposal in generated.proposals.proposals:
                if str(proposal.claim_id) not in claim_ids or str(proposal.evidence_id) not in allowed_ids:
                    continue
                existing = session.query(ClaimEvidenceLink).filter_by(
                    claim_id=proposal.claim_id,
                    evidence_id=proposal.evidence_id,
                    relation=proposal.relation,
                ).one_or_none()
                if existing is None:
                    session.add(ClaimEvidenceLink(
                        claim_id=proposal.claim_id,
                        evidence_id=proposal.evidence_id,
                        relation=proposal.relation,
                        reason=proposal.rationale,
                        confidence=0.5,
                        produced_by="MODEL",
                        requires_human_confirmation=proposal.relation == "CONTRADICTS",
                    ))
            valid_requests: list[dict] = []
            candidate_ids = {str(item.get("candidateId")) for item in supplement_candidates}
            if state.get("context_request_round", 0) == 0:
                for proposal in generated.proposals.context_requests:
                    if str(proposal.claim_id) in claim_ids and proposal.candidate_id in candidate_ids:
                        valid_requests.append({
                            "claimId": str(proposal.claim_id),
                            "candidateId": proposal.candidate_id,
                            "reason": proposal.reason,
                        })
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="MODEL", scope_ref="link-proposal", state="ANALYZED", details={"contextRequestCount": len(valid_requests), "contextRound": state.get("context_request_round", 0)}))
            session.flush()
            return {"context_requests": valid_requests}
        except DomainError as exc:
            manifest = session.query(AnalysisRunManifest).filter_by(run_id=run_id).one_or_none()
            if manifest is not None:
                manifest.degradation = {**manifest.degradation, "generation": {"code": exc.code, "promptVersion": request.prompt_version, "schemaVersion": request.schema_version}}
            session.add(ModelCall(
                run_id=run_id,
                provider=settings.generation_provider,
                model=settings.generation_model,
                operation="LINK_PROPOSAL",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                allowed_evidence_ids=sorted(allowed_ids),
                status="FAILED",
                attempts=2 if exc.code == "MODEL_SCHEMA_INVALID" else 1,
                error_code=exc.code,
                error_summary=exc.message[:500],
            ))
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="MODEL", scope_ref="link-proposal", state="UNAVAILABLE", reason_code=exc.code))
            return {"node_errors": [*state.get("node_errors", []), exc.code]}

    def supplement_context(state: VerificationGraphState) -> VerificationGraphState:
        """Capture one agent-requested, SHA-bound context artifact without fetching remote Git."""
        ensure_not_cancelled()
        if state.get("context_request_round", 0) >= 1:
            return {"context_requests": []}
        bundle = state.get("code_change_bundle") or {}
        candidates = {str(item.get("candidateId")): item for item in bundle.get("contextCandidates", [])}
        selected: list[dict] = []
        seen: set[str] = set()
        for request in state.get("context_requests", []):
            candidate = candidates.get(str(request.get("candidateId")))
            if candidate is None or candidate["candidateId"] in seen:
                continue
            seen.add(candidate["candidateId"])
            selected.append({**candidate, "claimId": request.get("claimId"), "reason": request.get("reason", "")})
            if len(selected) >= get_settings().code_review_context_max_supplement_requests:
                break
        if not selected:
            return {"context_request_round": 1, "context_requests": []}

        snapshot = session.get(InputSnapshot, UUID(state["input_snapshot_id"]))
        binding = session.query(InputSnapshotGit).filter_by(snapshot_id=snapshot.id).one_or_none() if snapshot else None
        git_snapshot = session.get(GitSnapshot, binding.git_snapshot_id) if binding else None
        cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
        task = session.get(VerificationTask, cycle.task_id) if cycle else None
        repository = session.get(GitRepository, git_snapshot.repository_id) if git_snapshot else None
        if not all((snapshot, git_snapshot, task, repository)):
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CONTEXT_SUPPLEMENT", scope_ref="frozen-sha", state="UNAVAILABLE", reason_code="GIT_ARTIFACT_MISSING", details={}))
            return {"context_request_round": 1, "context_requests": [], "node_errors": [*state.get("node_errors", []), "GIT_ARTIFACT_MISSING"]}
        try:
            blobs = ReadOnlyGitReader().read_frozen_blobs(
                repository.display_url,
                target_sha=git_snapshot.target_sha,
                paths=[item["path"] for item in selected],
                credential_ref=repository.credential_ref,
            )
        except DomainError as exc:
            session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CONTEXT_SUPPLEMENT", scope_ref="frozen-sha", state="UNAVAILABLE", reason_code=exc.code, details={"requestedCandidateIds": [item["candidateId"] for item in selected]}))
            return {"context_request_round": 1, "context_requests": [], "node_errors": [*state.get("node_errors", []), exc.code]}

        new_contexts: list[dict] = []
        skipped: list[dict] = []
        for item in selected:
            source = blobs.get(item["path"], b"").decode("utf-8", errors="replace")
            extracted = extract_symbol_context(item["path"], source, item["symbol"])
            if extracted is None:
                skipped.append({"candidateId": item["candidateId"], "reasonCode": "SYMBOL_DEFINITION_NOT_FOUND"})
                continue
            context_id = f"ctx-supplement-{hashlib.sha256((item['candidateId'] + extracted['content']).encode('utf-8')).hexdigest()[:20]}"
            new_contexts.append({
                "contextId": context_id,
                "path": item["path"],
                "commitSha": git_snapshot.target_sha,
                "language": item.get("language"),
                "symbol": extracted["symbol"],
                "symbolKind": extracted["symbolKind"],
                "kind": "SYMBOL",
                "relation": "SUPPLEMENTAL_DIRECT_IMPORT",
                "startLine": extracted["startLine"],
                "endLine": extracted["endLine"],
                "content": extracted["content"],
                "contentHash": f"sha256:{hashlib.sha256(extracted['content'].encode('utf-8')).hexdigest()}",
                "evidenceRole": "CONTEXT_ONLY",
                "requestedForClaimId": item.get("claimId"),
            })

        payload = {"schemaVersion": "run-context-v1", "targetSha": git_snapshot.target_sha, "requests": selected, "contexts": new_contexts, "skipped": skipped}
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        content_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        artifact = session.query(ArtifactObject).filter_by(project_id=task.project_id, kind="CODE_CONTEXT_SUPPLEMENT", content_hash=content_hash).one_or_none()
        if artifact is None:
            artifact = ArtifactObject(project_id=task.project_id, kind="CODE_CONTEXT_SUPPLEMENT", content_hash=content_hash, byte_size=len(raw), media_type="application/json", schema_version="run-context-v1", storage_uri="pending://artifact")
            session.add(artifact)
            session.flush()
            artifact.storage_uri = LocalArtifactStorage(get_settings().artifact_root).write_bytes([str(task.project_id), "analysis-runs", str(run_id), "contexts"], f"{artifact.id}.json", raw)
        request_hash = f"sha256:{hashlib.sha256(json.dumps(selected, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()}"
        if session.query(AnalysisRunContextArtifact).filter_by(analysis_run_id=run_id, round_no=1).one_or_none() is None:
            session.add(AnalysisRunContextArtifact(analysis_run_id=run_id, artifact_id=artifact.id, round_no=1, request_hash=request_hash))
        merged_contexts = [*bundle.get("contexts", []), *[item for item in new_contexts if item["contextId"] not in {entry.get("contextId") for entry in bundle.get("contexts", [])}]]
        updated_bundle = {**bundle, "contexts": merged_contexts, "coverage": {**(bundle.get("coverage") or {}), "supplementRound": 1, "supplementedContextCount": len(new_contexts), "supplementSkipped": skipped}}
        session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="CONTEXT_SUPPLEMENT", scope_ref="frozen-sha", state="ANALYZED" if new_contexts else "PARTIAL", reason_code=None if new_contexts else "NO_SUPPLEMENT_CONTEXT", details={"artifactId": str(artifact.id), "requestedCandidateIds": [item["candidateId"] for item in selected], "contextCount": len(new_contexts), "skipped": skipped}))
        session.flush()
        return {"code_change_bundle": updated_bundle, "context_request_round": 1, "context_requests": [], "context_artifact_ids": [*state.get("context_artifact_ids", []), str(artifact.id)]}


    def run_custom_agents(state: VerificationGraphState) -> VerificationGraphState:
        """Outer Agents may use temporary hints, but only frozen evidence can be cited."""
        ensure_not_cancelled()
        if not custom_agent_nodes:
            return {}
        evidence = [
            session.get(EvidenceItem, UUID(item))
            for item in [
                *state.get("evidence_ids", []),
                *state.get("git_evidence_ids", []),
                *state.get("external_evidence_ids", []),
                *state.get("manual_evidence_ids", []),
            ]
        ]
        evidence = [item for item in evidence if item is not None]
        claims = [session.get(Claim, UUID(item)) for item in state.get("claim_ids", [])]
        claims = [item for item in claims if item is not None]
        snapshot = session.get(InputSnapshot, UUID(state["input_snapshot_id"]))
        cycle = session.get(VerificationCycle, snapshot.cycle_id) if snapshot else None
        task = session.get(VerificationTask, cycle.task_id) if cycle else None
        if snapshot is None or task is None:
            raise DomainError("INPUT_STALE", "自定义 Agent 缺少正式输入快照")
        settings = get_settings()
        node_errors = [*state.get("node_errors", [])]
        for node in custom_agent_nodes:
            key = str(node.get("capabilityKey"))
            agent_evidence = [*evidence]
            temporary_tool_context: list[dict] = []
            for tool in node.get("tools", []):
                if tool.get("type") != "HTTP_QUERY":
                    continue
                tool_id = str(tool.get("toolId", "unknown"))
                event_node_id = f"tool:{tool_id}"[:64]
                try:
                    tool_key = str(tool.get("key", tool_id))
                    execution = session.query(AgentToolExecution).filter_by(
                        analysis_run_id=run_id,
                        capability_key=key,
                        tool_key=tool_key,
                    ).one_or_none()
                    reused = execution is not None
                    if execution is None:
                        outcome = execute_http_query(
                            tool,
                            analysis_run_id=str(run_id),
                            input_snapshot_id=str(snapshot.id),
                            capability_key=key,
                            settings=settings,
                        )
                        execution = AgentToolExecution(
                            project_id=task.project_id,
                            analysis_run_id=run_id,
                            input_snapshot_id=snapshot.id,
                            capability_key=key,
                            tool_key=tool_key,
                            tool_type="HTTP_QUERY",
                            content_hash=outcome.content_hash,
                            artifact_uri="pending://artifact",
                            excerpt_safe=_safe_excerpt(outcome.excerpt),
                            locator={**outcome.locator, "capabilityKey": key, "analysisRunId": str(run_id)},
                        )
                        session.add(execution)
                        session.flush()
                        execution.artifact_uri = LocalArtifactStorage(get_settings().artifact_root).write_bytes(
                            [str(task.project_id), "agent-tool-executions", str(execution.id)],
                            "response.txt",
                            outcome.content.encode("utf-8"),
                        )
                    temporary_tool_context.append({
                        "kind": "TEMPORARY_AGENT_TOOL_RESULT",
                        "toolExecutionId": str(execution.id),
                        "toolKey": execution.tool_key,
                        "locator": execution.locator,
                        "excerpt": execution.excerpt_safe,
                        "rule": "Only a review hint. It cannot be cited or become a formal delivery conclusion until a person explicitly imports it into a later formal input snapshot.",
                    })
                    session.add(AnalysisCoverage(
                        analysis_run_id=run_id,
                        scope_kind="AGENT_TOOL",
                        scope_ref=f"{key}:{tool_key}",
                        state="TEMPORARY",
                    ))
                    session.add(RunEvent(
                        run_id=run_id,
                        node_id=event_node_id,
                        event_type="TOOL_EXECUTION",
                        status="SUCCEEDED",
                        correlation_id=str(run_id),
                        payload_redacted={
                            "toolKey": tool_key,
                            "capabilityKey": key,
                            "toolExecutionId": str(execution.id),
                            "contentHash": execution.content_hash,
                            "evidenceState": "TEMPORARY_ONLY",
                            "reused": reused,
                        },
                    ))
                except DomainError as exc:
                    node_errors.append(f"{key}:{tool.get('key', tool_id)}:{exc.code}")
                    session.add(AnalysisCoverage(
                        analysis_run_id=run_id,
                        scope_kind="AGENT_TOOL",
                        scope_ref=f"{key}:{tool.get('key', tool_id)}",
                        state="UNAVAILABLE",
                        reason_code=exc.code,
                    ))
                    session.add(RunEvent(
                        run_id=run_id,
                        node_id=event_node_id,
                        event_type="TOOL_EXECUTION",
                        status="FAILED",
                        correlation_id=str(run_id),
                        payload_redacted={"toolKey": tool.get("key"), "capabilityKey": key, "errorCode": exc.code},
                    ))
            allowed_ids = {str(item.id) for item in agent_evidence}
            request = GenerationRequest(
                run_id=run_id,
                prompt_version=f"agent-{node.get('capabilityVersion', 1)}",
                schema_version="v1",
                instruction=str(node.get("promptTemplate", ""))[:20_000],
                operation=f"CUSTOM_AGENT:{key}",
                claims=with_plan_acceptance([{"id": str(claim.id), "text": claim.text, "candidateEvidenceIds": sorted(allowed_ids)} for claim in claims]),
                evidence=[{"id": str(item.id), "excerpt": item.excerpt_safe, "locator": item.locator} for item in agent_evidence],
                temporary_context=temporary_tool_context,
            )
            try:
                generated = create_generation_model(settings).generate(request)
                session.add(ModelCall(run_id=run_id, provider=generated.provider, model=generated.model, operation=request.operation, prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=sorted(allowed_ids), status="SUCCEEDED", latency_ms=generated.latency_ms, attempts=generated.attempts))
                claim_ids = {str(claim.id) for claim in claims}
                for proposal in generated.proposals.proposals:
                    if str(proposal.claim_id) not in claim_ids or str(proposal.evidence_id) not in allowed_ids:
                        continue
                    existing = session.query(ClaimEvidenceLink).filter_by(claim_id=proposal.claim_id, evidence_id=proposal.evidence_id, relation=proposal.relation).one_or_none()
                    if existing is None:
                        session.add(ClaimEvidenceLink(claim_id=proposal.claim_id, evidence_id=proposal.evidence_id, relation=proposal.relation, reason=proposal.rationale, confidence=0.5, produced_by="CUSTOM_AGENT", requires_human_confirmation=proposal.relation == "CONTRADICTS"))
                session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="AGENT", scope_ref=key, state="ANALYZED"))
            except DomainError as exc:
                session.add(ModelCall(run_id=run_id, provider=settings.generation_provider, model=settings.generation_model, operation=request.operation, prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=sorted(allowed_ids), status="FAILED", attempts=1, error_code=exc.code, error_summary=exc.message[:500]))
                session.add(AnalysisCoverage(analysis_run_id=run_id, scope_kind="AGENT", scope_ref=key, state="UNAVAILABLE", reason_code=exc.code))
                node_errors.append(f"{key}:{exc.code}")
        session.flush()
        return {"node_errors": node_errors}

    def reconcile(state: VerificationGraphState) -> VerificationGraphState:
        ensure_not_cancelled()
        results: list[str] = []
        for claim_id in state.get("claim_ids", []):
            claim = session.get(Claim, UUID(claim_id))
            if claim is None:
                continue
            links = [
                item
                for item in session.query(ClaimEvidenceLink).filter_by(claim_id=claim.id).all()
                if (linked_evidence := session.get(EvidenceItem, item.evidence_id)) is not None
                and linked_evidence.source_type != "TOOL"
                and linked_evidence.evidence_kind != "HTTP_QUERY"
            ]
            deterministic_supports = [item for item in links if item.relation == "SUPPORTS" and item.produced_by == "DETERMINISTIC"]
            human_supports = [item for item in links if item.relation == "SUPPORTS" and item.produced_by == "HUMAN"]
            model_supports = [item for item in links if item.relation == "SUPPORTS" and item.produced_by == "MODEL"]
            conflicts = [item for item in links if item.relation == "CONTRADICTS" and item.produced_by in {"DETERMINISTIC", "MODEL"}]
            exact_model_supports = [
                item for item in model_supports
                if (evidence := session.get(EvidenceItem, item.evidence_id)) is not None
                and evidence.source_type == "CODE"
                and evidence.evidence_kind == "GIT_DIFF_HUNK"
                and evidence.locator_precision == "EXACT"
            ]
            evidence_ids = [str(item.evidence_id) for item in [*deterministic_supports, *conflicts, *human_supports, *model_supports]]
            capture_unavailable = any(code in {"GIT_ARTIFACT_MISSING", "GIT_ARTIFACT_UNAVAILABLE", "GIT_ARTIFACT_HASH_MISMATCH"} for code in state.get("node_errors", []))
            model_unavailable = any(code.startswith("MODEL_") for code in state.get("node_errors", []))
            if conflicts:
                for conflict in conflicts:
                    if "risk-scan" not in enabled_keys:
                        continue
                    existing_finding = session.query(RiskFinding).filter_by(
                        analysis_run_id=run_id,
                        claim_id=claim.id,
                        evidence_id=conflict.evidence_id,
                        category="EVIDENCE_CONFLICT",
                    ).one_or_none()
                    if existing_finding is None:
                        session.add(RiskFinding(
                            analysis_run_id=run_id,
                            claim_id=claim.id,
                            evidence_id=conflict.evidence_id,
                            severity="HIGH" if claim.authority_level >= 3 else "MEDIUM",
                            category="EVIDENCE_CONFLICT",
                            finding_kind="DETERMINISTIC",
                            recommendation="复核冲突证据并补充与冻结提交绑定的可追溯材料",
                        ))
                status = "CONFLICTING"
                reason = "存在与冻结代码证据关联的反驳结论，需要核对业务语义"
                needs_confirmation = True
            elif exact_model_supports:
                status = "SUPPORTED"
                reason = "模型分析结果已绑定到当前冻结 Diff Hunk；必要代码上下文仅用于解释，不作为独立证据"
                needs_confirmation = False
            elif deterministic_supports:
                status = "PARTIALLY_SUPPORTED"
                reason = "已发现冻结 Git 范围内的直接代码标识符命中，但尚未形成足以证明完整目标的语义证据"
                needs_confirmation = False
            elif human_supports:
                status = "PARTIALLY_SUPPORTED"
                reason = "已关联人工补证；该补证不能单独证明本次冻结 PR 的代码交付范围"
                needs_confirmation = False
            elif capture_unavailable or (model_unavailable and not deterministic_supports):
                status = "NOT_ANALYZED"
                reason = "冻结代码输入或必要模型分析不可用，当前不能完成该目标的核验"
                needs_confirmation = False
            else:
                status = "NOT_PROVEN"
                reason = "已完成当前冻结代码范围分析，但没有足够的直接证据证明该交付目标"
                needs_confirmation = False
            result = session.query(VerificationResult).filter_by(analysis_run_id=run_id, claim_id=claim.id).one_or_none()
            if result is None:
                result = VerificationResult(
                    analysis_run_id=run_id,
                    claim_id=claim.id,
                    protocol_version="v1",
                    status=status,
                    reason=reason,
                    evidence_ids=evidence_ids,
                    requires_human_confirmation=needs_confirmation,
                    produced_by="DETERMINISTIC",
                )
                session.add(result)
                session.flush()
            results.append(str(result.id))
        return {"verification_result_ids": results}

    return VerificationSteps(
        load_snapshot=observed("load_snapshot", load_snapshot),
        collect_git_evidence=observed("collect_git_evidence", collect_git_evidence),
        create_claims=observed("create_claims", create_claims),
        review_code=observed("review_code", review_code),
        challenge_code_findings=observed("challenge_code_findings", challenge_code_findings),
        summarize_code_coverage=observed("summarize_code_coverage", summarize_code_coverage),
        link_deterministic=observed("link_deterministic", link_deterministic),
        propose_model_links=observed("propose_model_links", propose_model_links),
        supplement_context=observed("supplement_context", supplement_context),
        run_custom_agents=observed("run_custom_agents", run_custom_agents),
        reconcile=observed("reconcile", reconcile),
    )
