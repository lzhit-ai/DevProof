"""Evidence-bound planning and validation for the delivery code-review core."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.code_review_contracts import ReviewClaim, ReviewEvidence, ReviewFinding
from app.workflows.code_review_inputs import (
    plan_code_review as build_code_review_input,
    plan_code_review_challenges as build_code_review_challenge_input,
)

from app.domain.model_contracts import CodeReviewFindingChallengeProposal, CodeReviewFindingProposal
from app.infrastructure.persistence.models import Claim, CodeReviewFinding, CodeReviewFindingChallenge, EvidenceItem


def plan_code_review(*, bundle: dict, evidence_by_locator: dict[tuple[str, str], str], claims: list[Claim], char_budget: int) -> tuple[list[dict], dict]:
    return build_code_review_input(
        bundle=bundle,
        evidence_by_locator=evidence_by_locator,
        claims=[ReviewClaim(id=item.id, text=item.text) for item in claims],
        char_budget=char_budget,
    )


def persist_validated_findings(
    session: Session,
    *,
    run_id: UUID,
    proposal_batch: list[CodeReviewFindingProposal],
    allowed_evidence_ids: set[UUID],
    allowed_claim_ids: set[UUID],
) -> tuple[list[CodeReviewFinding], int]:
    findings: list[CodeReviewFinding] = []
    rejected = 0
    for proposal in proposal_batch:
        if proposal.evidence_id not in allowed_evidence_ids or any(item not in allowed_claim_ids for item in proposal.related_claim_ids):
            rejected += 1
            continue
        evidence = session.get(EvidenceItem, proposal.evidence_id)
        if evidence is None or evidence.source_type != "CODE" or evidence.locator_precision != "EXACT":
            rejected += 1
            continue
        fingerprint_input = json.dumps({"evidence": str(proposal.evidence_id), "claims": sorted(str(item) for item in proposal.related_claim_ids), "kind": proposal.finding_kind, "title": proposal.title.strip().casefold(), "trigger": proposal.trigger_scenario.strip().casefold()}, sort_keys=True, ensure_ascii=False)
        fingerprint = f"sha256:{hashlib.sha256(fingerprint_input.encode('utf-8')).hexdigest()}"
        existing = session.query(CodeReviewFinding).filter_by(analysis_run_id=run_id, fingerprint=fingerprint).one_or_none()
        if existing is not None:
            findings.append(existing)
            continue
        finding = CodeReviewFinding(
            analysis_run_id=run_id,
            evidence_id=proposal.evidence_id,
            claim_id=proposal.related_claim_ids[0] if proposal.related_claim_ids else None,
            fingerprint=fingerprint,
            severity=proposal.severity,
            finding_kind=proposal.finding_kind,
            title=proposal.title,
            problem=proposal.problem,
            trigger_scenario=proposal.trigger_scenario,
            recommendation=proposal.recommendation,
            confidence=proposal.confidence,
            produced_by="MODEL",
            requires_human_confirmation=True,
            schema_version="code-review-finding-v1",
        )
        session.add(finding)
        findings.append(finding)
    session.flush()
    return findings, rejected


def plan_code_review_challenges(
    *,
    bundle: dict,
    findings: list[CodeReviewFinding],
    evidence_by_id: dict[UUID, EvidenceItem],
    claims_by_id: dict[UUID, Claim],
    char_budget: int,
    max_findings: int,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    return build_code_review_challenge_input(
        bundle=bundle,
        findings=[
            ReviewFinding(
                id=item.id,
                evidence_id=item.evidence_id,
                claim_id=item.claim_id,
                finding_kind=item.finding_kind,
                severity=item.severity,
                title=item.title,
                problem=item.problem,
                trigger_scenario=item.trigger_scenario,
                recommendation=item.recommendation,
                confidence=item.confidence,
            )
            for item in findings
        ],
        evidence_by_id={
            key: ReviewEvidence(id=item.id, locator=item.locator)
            for key, item in evidence_by_id.items()
        },
        claims_by_id={
            key: ReviewClaim(id=item.id, text=item.text)
            for key, item in claims_by_id.items()
        },
        char_budget=char_budget,
        max_findings=max_findings,
    )


def persist_validated_challenges(
    session: Session,
    *,
    run_id: UUID,
    proposal_batch: list[CodeReviewFindingChallengeProposal],
    allowed_findings: dict[UUID, CodeReviewFinding],
    allowed_evidence_ids: set[UUID],
    model_call_id: UUID | None,
) -> tuple[list[CodeReviewFindingChallenge], int]:
    """Persist only challenge proposals tied to the original finding Hunk in this run."""
    challenges: list[CodeReviewFindingChallenge] = []
    rejected = 0
    seen: set[UUID] = set()
    for proposal in proposal_batch:
        finding = allowed_findings.get(proposal.finding_id)
        evidence_ids = list(dict.fromkeys(proposal.evidence_ids))
        if finding is None or proposal.finding_id in seen or finding.evidence_id not in evidence_ids or any(item not in allowed_evidence_ids for item in evidence_ids):
            rejected += 1
            continue
        evidence_items = [session.get(EvidenceItem, item) for item in evidence_ids]
        if any(item is None or item.source_type != "CODE" or item.locator_precision != "EXACT" for item in evidence_items):
            rejected += 1
            continue
        seen.add(proposal.finding_id)
        fingerprint_input = json.dumps(
            {
                "finding": str(finding.id),
                "verdict": proposal.verdict,
                "evidence": sorted(str(item) for item in evidence_ids),
                "reason": proposal.reason.strip().casefold(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        fingerprint = f"sha256:{hashlib.sha256(fingerprint_input.encode('utf-8')).hexdigest()}"
        existing = session.query(CodeReviewFindingChallenge).filter_by(analysis_run_id=run_id, finding_id=finding.id).one_or_none()
        if existing is not None:
            challenges.append(existing)
            continue
        challenge = CodeReviewFindingChallenge(
            analysis_run_id=run_id,
            finding_id=finding.id,
            fingerprint=fingerprint,
            verdict=proposal.verdict,
            reason=proposal.reason,
            evidence_ids=[str(item) for item in evidence_ids],
            model_call_id=model_call_id,
            schema_version="code-review-challenge-v1",
        )
        session.add(challenge)
        challenges.append(challenge)
    session.flush()
    return challenges, rejected
