"""In-process workflow contracts, independent of persistence and model vendors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict


class VerificationGraphState(TypedDict, total=False):
    analysis_run_id: str
    input_snapshot_id: str
    evidence_ids: list[str]
    git_evidence_ids: list[str]
    code_change_bundle: dict
    external_evidence_ids: list[str]
    manual_evidence_ids: list[str]
    claim_ids: list[str]
    verification_result_ids: list[str]
    coverage_id: str
    node_errors: list[str]
    workflow_schema_version: str
    context_request_round: int
    context_requests: list[dict]
    context_artifact_ids: list[str]


VerificationStep = Callable[[VerificationGraphState], VerificationGraphState]


@dataclass(frozen=True)
class VerificationSteps:
    """Trusted host bindings for the fixed workflow; never selected by the model.

    Each handler returns a state update. The host owns authorization, frozen
    business reads, candidate validation, persistence and execution observation.
    The graph owns ordering and its single context-supplement branch.
    """

    load_snapshot: VerificationStep
    collect_git_evidence: VerificationStep
    create_claims: VerificationStep
    review_code: VerificationStep
    challenge_code_findings: VerificationStep
    summarize_code_coverage: VerificationStep
    link_deterministic: VerificationStep
    propose_model_links: VerificationStep
    supplement_context: VerificationStep
    run_custom_agents: VerificationStep
    reconcile: VerificationStep
