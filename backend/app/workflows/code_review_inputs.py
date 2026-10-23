"""Build bounded review inputs from materialized frozen data, without I/O."""

from __future__ import annotations

import json
from uuid import UUID

from app.domain.code_review_contracts import ReviewClaim, ReviewEvidence, ReviewFinding


def plan_code_review(*, bundle: dict, evidence_by_locator: dict[tuple[str, str], str], claims: list[ReviewClaim], char_budget: int) -> tuple[list[dict], dict]:
    """Create deterministic review inputs and an explicit unanalysed-range record."""
    claim_payload = [{"id": str(item.id), "text": item.text} for item in claims]
    selected: list[dict] = []
    skipped: list[dict] = []
    used = 0
    for file in bundle.get("files", []):
        path = str(file.get("path", ""))
        if file.get("binary") or file.get("context_state") == "SKIPPED":
            skipped.append({"path": path, "reasonCode": file.get("context_reason_code") or "NON_TEXT_CHANGE"})
            continue
        hunks: list[dict] = []
        for hunk in file.get("hunks", []):
            key = (path, str(hunk.get("header", "")))
            evidence_id = evidence_by_locator.get(key)
            if evidence_id is None:
                continue
            candidate = {"evidenceId": evidence_id, "header": hunk.get("header"), "oldStart": hunk.get("old_start"), "oldEnd": hunk.get("old_end"), "newStart": hunk.get("new_start"), "newEnd": hunk.get("new_end"), "payload": hunk.get("payload", "")}
            size = len(json.dumps(candidate, ensure_ascii=False))
            if used + size > char_budget:
                skipped.append({"path": path, "hunk": hunk.get("header"), "reasonCode": "CODE_REVIEW_BUDGET_EXHAUSTED"})
                continue
            hunks.append(candidate)
            used += size
        if hunks:
            context = {"base": file.get("base_context"), "target": file.get("target_context")}
            context_size = len(json.dumps(context, ensure_ascii=False))
            include_context = context_size <= max(char_budget - used, 0)
            if include_context:
                used += context_size
            elif context["base"] or context["target"]:
                skipped.append({"path": path, "reasonCode": "CODE_CONTEXT_BUDGET_EXHAUSTED"})
            selected.append({
                "path": path,
                "oldPath": file.get("old_path"),
                "editType": file.get("edit_type"),
                "hunks": hunks,
                "contextOnly": context if include_context else {"base": None, "target": None},
            })
    related_contexts: list[dict] = []
    for context in bundle.get("contexts", []):
        candidate = {
            "contextId": context.get("contextId"),
            "path": context.get("path"),
            "symbol": context.get("symbol"),
            "symbolKind": context.get("symbolKind"),
            "relation": context.get("relation"),
            "startLine": context.get("startLine"),
            "endLine": context.get("endLine"),
            "content": context.get("content"),
            "evidenceRole": "CONTEXT_ONLY",
        }
        size = len(json.dumps(candidate, ensure_ascii=False))
        if used + size > char_budget:
            skipped.append({"path": context.get("path"), "symbol": context.get("symbol"), "reasonCode": "RELATED_CONTEXT_BUDGET_EXHAUSTED"})
            continue
        related_contexts.append(candidate)
        used += size
    if selected and related_contexts:
        # Context is provided once for the review batch and never has an evidenceId.
        selected[0]["relatedContexts"] = related_contexts
    return selected, {"state": "ANALYZED" if selected else "PARTIAL", "details": {"inputCharBudget": char_budget, "inputCharsUsed": used, "analysedFiles": len(selected), "analysedHunks": sum(len(item["hunks"]) for item in selected), "unanalysed": skipped, "claims": claim_payload}}



def plan_code_review_challenges(
    *,
    bundle: dict,
    findings: list[ReviewFinding],
    evidence_by_id: dict[UUID, ReviewEvidence],
    claims_by_id: dict[UUID, ReviewClaim],
    char_budget: int,
    max_findings: int,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Build only the frozen Hunk/context payload required to challenge persisted findings."""
    hunk_by_locator: dict[tuple[str, str], tuple[dict, dict]] = {}
    for file in bundle.get("files", []):
        path = str(file.get("path", ""))
        for hunk in file.get("hunks", []):
            hunk_by_locator[(path, str(hunk.get("header", "")))] = (file, hunk)

    selected_findings: list[dict] = []
    code_changes: list[dict] = []
    selected_claim_ids: set[UUID] = set()
    skipped: list[dict] = []
    used = 0
    for finding in findings[:max_findings]:
        evidence = evidence_by_id.get(finding.evidence_id)
        if evidence is None:
            skipped.append({"findingId": str(finding.id), "reasonCode": "FINDING_EVIDENCE_MISSING"})
            continue
        path = str(evidence.locator.get("path", ""))
        header = str(evidence.locator.get("hunk", ""))
        source = hunk_by_locator.get((path, header))
        if source is None:
            skipped.append({"findingId": str(finding.id), "reasonCode": "FINDING_HUNK_MISSING"})
            continue
        file, hunk = source
        hunk_payload = {
            "evidenceId": str(evidence.id),
            "header": header,
            "oldStart": hunk.get("old_start"),
            "oldEnd": hunk.get("old_end"),
            "newStart": hunk.get("new_start"),
            "newEnd": hunk.get("new_end"),
            "payload": hunk.get("payload", ""),
        }
        finding_payload = {
            "findingId": str(finding.id),
            "evidenceId": str(finding.evidence_id),
            "claimId": str(finding.claim_id) if finding.claim_id else None,
            "findingKind": finding.finding_kind,
            "severity": finding.severity,
            "title": finding.title,
            "problem": finding.problem,
            "triggerScenario": finding.trigger_scenario,
            "recommendation": finding.recommendation,
            "confidence": finding.confidence,
        }
        context = {"base": file.get("base_context"), "target": file.get("target_context")}
        code_change = {
            "path": path,
            "oldPath": file.get("old_path"),
            "editType": file.get("edit_type"),
            "hunks": [hunk_payload],
            "contextOnly": context,
        }
        related_contexts = [
            {
                "contextId": item.get("contextId"),
                "path": item.get("path"),
                "symbol": item.get("symbol"),
                "relation": item.get("relation"),
                "content": item.get("content"),
                "evidenceRole": "CONTEXT_ONLY",
            }
            for item in bundle.get("contexts", [])
            if item.get("path") in {path, file.get("old_path")}
        ]
        if related_contexts:
            code_change["relatedContexts"] = related_contexts
        candidate_size = len(json.dumps({"finding": finding_payload, "codeChange": code_change}, ensure_ascii=False))
        if used + candidate_size > char_budget:
            skipped.append({"findingId": str(finding.id), "path": path, "hunk": header, "reasonCode": "FINDING_CHALLENGE_BUDGET_EXHAUSTED"})
            continue
        used += candidate_size
        selected_findings.append(finding_payload)
        code_changes.append(code_change)
        if finding.claim_id is not None:
            selected_claim_ids.add(finding.claim_id)

    claims = [
        {"id": str(claim_id), "text": claims_by_id[claim_id].text}
        for claim_id in sorted(selected_claim_ids, key=str)
        if claim_id in claims_by_id
    ]
    return selected_findings, code_changes, claims, {
        "state": "ANALYZED" if selected_findings else "PARTIAL",
        "details": {
            "inputCharBudget": char_budget,
            "inputCharsUsed": used,
            "eligibleFindingCount": len(findings),
            "selectedFindingCount": len(selected_findings),
            "selectedFindingIds": [item["findingId"] for item in selected_findings],
            "unanalysed": skipped,
        },
    }
