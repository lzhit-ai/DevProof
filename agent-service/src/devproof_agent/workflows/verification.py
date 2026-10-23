"""Frozen-input analysis. The graph produces candidates and never writes business state."""

import hashlib
import asyncio
import json
from typing import TypedDict
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from langgraph.graph import END, START, StateGraph

from devproof_agent.agents.verification import RESULT
from devproof_agent.models import AgentError
from devproof_agent.runtime.core import RunContext
from devproof_agent.workflows.code_review_inputs import plan_code_review, plan_code_review_challenges
from devproof_agent.workflows.review_values import ReviewClaim, ReviewEvidence, ReviewFinding
from devproof_agent.workflows.symbol_context import extract_symbol_context

BUILT_IN = {"requirement-claim-core", "delivery-git-diff", "evidence-reconciliation", "ci-evidence-import", "risk-scan", "model-link-proposal", "report-draft"}
STOP_CODES = {"BUDGET_EXHAUSTED", "LEASE_EXPIRED", "RUN_CANCELLED", "ATTEMPT_STALE", "AUTH_REVOKED", "AGENT_CONFIG_CHANGED", "INPUT_STALE", "AGENT_FORBIDDEN"}


class State(TypedDict, total=False):
    materials: dict
    bundle: dict
    findings: list[dict]
    challenges: list[dict]
    links: list[dict]
    custom_results: list[dict]
    coverage: list[dict]
    errors: list[str]
    requests: list[dict]
    context_round: int


async def run_verification(registry, assignment: dict, gateway, context: RunContext) -> dict:
    limits = assignment["agentManifest"]["executionConfiguration"]
    async def tool(key, arguments):
        context.budget.tool()
        await context.emit("TOOL_STARTED", {"name": key}, context)
        try:
            value = await gateway.tool(key, arguments)
            await context.emit("TOOL_COMPLETED", {"name": key, "ok": True}, context)
            return value
        except AgentError as exc:
            await context.emit("TOOL_COMPLETED", {"name": key, "ok": False, "errorCode": exc.code}, context)
            raise

    async def event(kind, stage, **values):
        await context.emit(kind, {"stage": stage, **values}, context)

    async def call(stage, key, payload):
        await event("STAGE_STARTED", stage)
        async def emit(kind, values, instance):
            await context.emit(kind, {"stage": stage, **values}, instance)
        actual = RunContext(context.budget, emit)
        try:
            value = await registry.run(key, json.dumps(payload, ensure_ascii=False, allow_nan=False), assignment, gateway, actual)
            await event("STAGE_COMPLETED", stage)
            return value, None
        except AgentError as exc:
            if exc.code in STOP_CODES:
                raise
            await event("STAGE_FAILED", stage, errorCode=exc.code)
            return None, exc.code

    def covered(state, kind, reference, status, reason=None, details=None):
        return [*state.get("coverage", []), {"scopeKind": kind, "scopeRef": reference, "state": status, "reasonCode": reason, "details": details or {}}]

    def code_evidence(state):
        return [item for item in state["materials"]["evidence"] if item["sourceType"] == "CODE" and item["kind"] == "GIT_DIFF_HUNK" and item["precision"] == "EXACT"]

    def acceptance(state, claims):
        bound = {item["id"]: item.get("planAcceptance") for item in state["materials"]["claims"]}
        return [{**item, **({"planAcceptance": bound[item["id"]]} if bound.get(item["id"]) else {})} for item in claims]

    async def load(state):
        materials = await tool("read_delivery_input", {})
        manifest = assignment["agentManifest"]
        frozen = manifest.get("businessConfigurationRef") or {}
        raw = materials.get("orchestrationRawJson", "")
        digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if digest != frozen.get("contentHash") or digest != materials.get("orchestrationHash") or json.loads(raw) != materials.get("orchestration"):
            raise AgentError("INPUT_STALE", "核验编排正文与任务冻结版本不一致")
        if any(item["id"] not in assignment["allowedEvidenceIds"] for item in materials["evidence"]):
            raise AgentError("INPUT_STALE", "材料包含授权范围以外的证据")
        for node in materials["orchestration"]["nodes"]:
            if node["enabled"] and node["capabilityKey"] not in BUILT_IN:
                key, prompt = "custom:" + node["capabilityKey"], node["promptTemplate"]
                if manifest["promptDefinitions"].get(key) != prompt or {"key": key, "version": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()} not in manifest["promptVersions"]:
                    raise AgentError("AGENT_CONFIG_CHANGED", "自定义能力提示词与任务冻结版本不一致")
        return {"materials": materials, "bundle": materials.get("bundle") or {}, "findings": [], "challenges": [], "links": [], "custom_results": [],
            "coverage": [], "errors": [materials["captureError"]] if materials.get("captureError") else [], "requests": [], "context_round": 0}

    async def review(state):
        evidence = code_evidence(state)
        changes, coverage = plan_code_review(bundle=state["bundle"],
            evidence_by_locator={(item["locator"].get("path", ""), item["locator"].get("hunk", "")): item["id"] for item in evidence},
            claims=[ReviewClaim(UUID(item["id"]), item["text"]) for item in state["materials"]["claims"]], char_budget=limits["reviewInputCharBudget"])
        if not changes:
            reason = state["materials"].get("captureError") or "NO_CITABLE_CODE_EVIDENCE"
            await event("STAGE_SKIPPED", "review_code", reasonCode=reason)
            return {"coverage": covered(state, "CODE_REVIEW", "delivery-git-diff", "UNAVAILABLE" if state["materials"].get("captureError") else "PARTIAL", reason, coverage["details"])}
        result, error = await call("review_code", "delivery-review-agent", {"claims": acceptance(state, coverage["details"]["claims"]), "codeChanges": changes})
        allowed_evidence, allowed_claims = {item["id"] for item in evidence}, {item["id"] for item in state["materials"]["claims"]}
        findings, seen = [], set()
        for item in result["findings"] if result is not None else []:
            if item["findingKey"] not in seen and item["evidenceId"] in allowed_evidence and set(item["relatedClaimIds"]) <= allowed_claims:
                findings.append(item); seen.add(item["findingKey"])
        details = {**coverage["details"], "modelFindingCount": len(result["findings"]) if result is not None else 0, "rejectedFindingCount": len(result["findings"]) - len(findings) if result is not None else 0}
        return {"findings": findings, "coverage": covered(state, "CODE_REVIEW", "delivery-git-diff", "UNAVAILABLE" if error else coverage["state"], error, details),
            "errors": [*state["errors"], error] if error else state["errors"]}

    async def challenge(state):
        if not state["findings"]:
            await event("STAGE_SKIPPED", "challenge_code_findings", reasonCode="NO_CODE_REVIEW_FINDINGS")
            return {"coverage": covered(state, "FINDING_CHALLENGE", "delivery-git-diff", "NOT_APPLICABLE", "NO_CODE_REVIEW_FINDINGS", {"eligibleFindingCount": 0})}
        findings = [ReviewFinding(item["findingKey"], UUID(item["evidenceId"]), UUID(item["relatedClaimIds"][0]) if item["relatedClaimIds"] else None,
            item["findingKind"], item["severity"], item["title"], item["problem"], item["triggerScenario"], item["recommendation"], item["confidence"]) for item in state["findings"]]
        selected, changes, claims, coverage = plan_code_review_challenges(bundle=state["bundle"], findings=findings,
            evidence_by_id={UUID(item["id"]): ReviewEvidence(UUID(item["id"]), item["locator"]) for item in code_evidence(state)},
            claims_by_id={UUID(item["id"]): ReviewClaim(UUID(item["id"]), item["text"]) for item in state["materials"]["claims"]}, char_budget=limits["challengeInputCharBudget"], max_findings=limits["challengeMaxFindings"])
        if not selected:
            await event("STAGE_SKIPPED", "challenge_code_findings", reasonCode="FINDING_CHALLENGE_BUDGET_EXHAUSTED")
            return {"coverage": covered(state, "FINDING_CHALLENGE", "delivery-git-diff", "PARTIAL", "FINDING_CHALLENGE_BUDGET_EXHAUSTED", coverage["details"])}
        result, error = await call("challenge_code_findings", "finding-challenge-agent", {"findings": [{**item, "findingKey": item["findingId"]} for item in selected], "codeChanges": changes, "claims": acceptance(state, claims)})
        actual = {item["findingId"]: item for item in selected}; allowed = {item["id"] for item in code_evidence(state)}; challenges, seen = [], set()
        for item in result["challenges"] if result is not None else []:
            finding = actual.get(item["findingKey"])
            if finding and item["findingKey"] not in seen and finding["evidenceId"] in item["evidenceIds"] and set(item["evidenceIds"]) <= allowed:
                challenges.append(item); seen.add(item["findingKey"])
        details = {**coverage["details"], "challengedFindingCount": len(challenges), "unchallengedFindingIds": sorted(set(actual) - seen)}
        return {"challenges": challenges, "coverage": covered(state, "FINDING_CHALLENGE", "delivery-git-diff", "UNAVAILABLE" if error else "PARTIAL" if set(actual) - seen else coverage["state"], error, details),
            "errors": [*state["errors"], error] if error else state["errors"]}

    async def link(state):
        enabled = {item["capabilityKey"] for item in state["materials"]["orchestration"]["nodes"] if item["enabled"]}
        if "model-link-proposal" not in enabled:
            await event("STAGE_SKIPPED", "propose_model_links", reasonCode="DISABLED_BY_TEMPLATE")
            return {"requests": [], "coverage": covered(state, "MODEL", "link-proposal", "SKIPPED", "DISABLED_BY_TEMPLATE")}
        evidence = [item for item in state["materials"]["evidence"] if item in code_evidence(state) or item["sourceType"] in {"TEST", "BUILD", "MANUAL"}]
        existing = {(item.get("path"), item.get("symbol")) for item in state["bundle"].get("contexts", [])}
        candidates = [item for item in state["bundle"].get("contextCandidates", []) if (item.get("path"), item.get("symbol")) not in existing] if state["context_round"] == 0 else []
        contexts, remaining = [], limits["reviewInputCharBudget"] // 2
        for item in state["bundle"].get("contexts", []):
            actual = {**item, "evidenceRole": "CONTEXT_ONLY"}; size = len(json.dumps(actual, ensure_ascii=False))
            if size > remaining:
                break
            contexts.append(actual); remaining -= size
        result, error = await call("propose_model_links", "evidence-link-agent", {"claims": state["materials"]["claims"], "evidence": evidence,
            "contextOnly": contexts, "contextCandidates": candidates, "contextRound": state["context_round"]})
        requests, proposals = [], []
        if result is not None:
            claims, allowed, candidate_ids = {item["id"] for item in state["materials"]["claims"]}, {item["id"] for item in evidence}, {item["candidateId"] for item in candidates}
            proposals = [item for item in result["proposals"] if item["claimId"] in claims and item["evidenceId"] in allowed]
            requests = [item for item in result["contextRequests"] if item["claimId"] in claims and item["candidateId"] in candidate_ids]
        return {"links": [*state["links"], *proposals], "requests": requests, "coverage": covered(state, "MODEL", "link-proposal", "UNAVAILABLE" if error else "ANALYZED", error, {"contextRound": state["context_round"], "contextRequestCount": len(requests)}),
            "errors": [*state["errors"], error] if error else state["errors"]}

    async def supplement(state):
        await event("STAGE_STARTED", "supplement_context")
        try:
            requests = state["requests"][:limits["contextMaxSupplementRequests"]]
            sources = await tool("read_context_candidate", {"requests": requests})
            if "recorded" in sources:
                result = sources["recorded"]
            else:
                extracted, skipped = [], []
                for source in sources["sources"]:
                    context.budget.check()
                    value = await asyncio.to_thread(extract_symbol_context, source["path"], source["source"], source["symbol"])
                    if value is None:
                        skipped.append({"candidateId": source["candidateId"], "reasonCode": "SYMBOL_DEFINITION_NOT_FOUND"})
                    else:
                        extracted.append({"candidateId": source["candidateId"], **value})
                result = await tool("record_context_supplement", {"requests": requests, "contexts": extracted, "skipped": skipped})
            contexts = result["contexts"]
            if any(item.get("evidenceRole") != "CONTEXT_ONLY" or "evidenceId" in item for item in contexts):
                raise AgentError("INPUT_STALE", "补充上下文不能形成正式证据")
            await event("STAGE_COMPLETED", "supplement_context")
            return {"bundle": {**state["bundle"], "contexts": [*state["bundle"].get("contexts", []), *contexts]}, "context_round": 1, "requests": [],
                "coverage": covered(state, "CONTEXT_SUPPLEMENT", "frozen-sha", "ANALYZED" if contexts else "PARTIAL", None if contexts else "NO_SUPPLEMENT_CONTEXT", result.get("details", {}))}
        except AgentError as exc:
            if exc.code in STOP_CODES:
                raise
            await event("STAGE_FAILED", "supplement_context", errorCode=exc.code)
            return {"context_round": 1, "requests": [], "errors": [*state["errors"], exc.code], "coverage": covered(state, "CONTEXT_SUPPLEMENT", "frozen-sha", "UNAVAILABLE", exc.code)}

    async def custom(state):
        coverage, errors, results = state["coverage"], state["errors"], []
        nodes = [item for item in state["materials"]["orchestration"]["nodes"] if item["enabled"] and item["capabilityKey"] not in BUILT_IN]
        if not nodes:
            await event("STAGE_SKIPPED", "run_custom_agents", reasonCode="NO_CUSTOM_AGENTS")
        for node in nodes:
            key, temporary = node["capabilityKey"], []
            for registered in node["tools"]:
                if registered.get("type") == "HTTP_QUERY":
                    try:
                        temporary.append(await tool("query_registered_tool", {"capabilityKey": key, "toolKey": registered["key"]}))
                    except AgentError as exc:
                        if exc.code in STOP_CODES:
                            raise
                        await event("STAGE_FAILED", "run_custom_agents", capabilityKey=key, errorCode=exc.code)
                        errors = [*errors, f"{key}:{exc.code}"]
            result, error = await call("run_custom_agents", "custom-evidence-agent", {"capabilityKey": key, "capabilityInstruction": node["promptTemplate"], "claims": state["materials"]["claims"], "evidence": state["materials"]["evidence"], "temporaryContext": temporary})
            claims, evidence = {item["id"] for item in state["materials"]["claims"]}, {item["id"] for item in state["materials"]["evidence"]}
            if result is not None:
                results.append({"capabilityKey": key, "links": [item for item in result["proposals"] if item["claimId"] in claims and item["evidenceId"] in evidence]})
            coverage = covered({"coverage": coverage}, "AGENT", key, "UNAVAILABLE" if error else "ANALYZED", error)
            if error:
                errors = [*errors, f"{key}:{error}"]
        return {"custom_results": results, "coverage": coverage, "errors": errors}

    graph = StateGraph(State)
    for key, implementation in {"load": load, "review": review, "challenge": challenge, "link": link, "supplement": supplement, "custom": custom}.items():
        graph.add_node(key, implementation)
    graph.add_edge(START, "load"); graph.add_edge("load", "review"); graph.add_edge("review", "challenge"); graph.add_edge("challenge", "link")
    graph.add_conditional_edges("link", lambda state: "supplement" if state["requests"] and state["context_round"] == 0 else "custom", {"supplement": "supplement", "custom": "custom"})
    graph.add_edge("supplement", "link"); graph.add_edge("custom", END)
    final = await graph.compile().ainvoke({})
    result = {"schemaVersion": "verification-result-v1", "findings": final["findings"], "challenges": final["challenges"], "links": final["links"],
        "customResults": final["custom_results"], "coverage": final["coverage"], "nodeErrors": list(dict.fromkeys(final["errors"]))}
    Draft202012Validator(RESULT, format_checker=FormatChecker()).validate(result)
    return result
