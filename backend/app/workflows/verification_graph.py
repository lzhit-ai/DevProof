"""Fixed delivery-verification orchestration without business persistence.

The caller supplies trusted step bindings. No database, model provider, artifact
store or application settings are imported by this module.
"""

from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.domain.verification_contracts import VerificationGraphState, VerificationSteps


def should_supplement_context(state: VerificationGraphState) -> str:
    return (
        "supplement_context"
        if state.get("context_requests") and state.get("context_request_round", 0) == 0
        else "run_custom_agents"
    )


def run_verification_graph(
    steps: VerificationSteps, *, run_id: UUID, snapshot_id: UUID
) -> VerificationGraphState:
    graph = StateGraph(VerificationGraphState)
    graph.add_node("load_snapshot", steps.load_snapshot)
    graph.add_node("collect_git_evidence", steps.collect_git_evidence)
    graph.add_node("create_claims", steps.create_claims)
    graph.add_node("review_code", steps.review_code)
    graph.add_node("challenge_code_findings", steps.challenge_code_findings)
    graph.add_node("summarize_code_coverage", steps.summarize_code_coverage)
    graph.add_node("link_deterministic", steps.link_deterministic)
    graph.add_node("propose_model_links", steps.propose_model_links)
    graph.add_node("supplement_context", steps.supplement_context)
    graph.add_node("run_custom_agents", steps.run_custom_agents)
    graph.add_node("reconcile", steps.reconcile)
    graph.add_edge(START, "load_snapshot")
    graph.add_edge("load_snapshot", "collect_git_evidence")
    graph.add_edge("collect_git_evidence", "create_claims")
    graph.add_edge("create_claims", "review_code")
    graph.add_edge("review_code", "challenge_code_findings")
    graph.add_edge("challenge_code_findings", "summarize_code_coverage")
    graph.add_edge("summarize_code_coverage", "link_deterministic")
    graph.add_edge("link_deterministic", "propose_model_links")
    graph.add_conditional_edges("propose_model_links", should_supplement_context, {
        "supplement_context": "supplement_context",
        "run_custom_agents": "run_custom_agents",
    })
    graph.add_edge("supplement_context", "propose_model_links")
    graph.add_edge("run_custom_agents", "reconcile")
    graph.add_edge("reconcile", END)
    return graph.compile().invoke({
        "analysis_run_id": str(run_id),
        "input_snapshot_id": str(snapshot_id),
        "workflow_schema_version": "delivery-context-v2",
        "node_errors": [],
        "context_request_round": 0,
        "context_requests": [],
        "context_artifact_ids": [],
    })
