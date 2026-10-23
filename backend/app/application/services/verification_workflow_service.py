"""Compose the existing business implementation with the isolated workflow."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.verification_contracts import VerificationGraphState
from app.infrastructure.legacy_verification import create_legacy_verification_steps
from app.workflows.verification_graph import run_verification_graph as execute_graph
from app.infrastructure.business_ownership import require_python_verification


def run_verification_graph(
    session: Session, run_id: UUID, snapshot_id: UUID
) -> VerificationGraphState:
    require_python_verification(session)
    steps = create_legacy_verification_steps(session, run_id)
    return execute_graph(steps, run_id=run_id, snapshot_id=snapshot_id)
