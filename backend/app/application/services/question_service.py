from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.citation_resolver import resolve_citation
from app.core.config import get_settings
from app.domain.errors import DomainError
from app.domain.model_contracts import EvidenceAnswerRequest
from app.infrastructure.generation_model import create_generation_model
from app.infrastructure.persistence.models import ModelCall
from app.infrastructure.business_ownership import require_python_evidence_questions


def answer_evidence_question(session: Session, *, snapshot_id: UUID, question: str, evidence_ids: list[UUID], actor_id: UUID) -> dict:
    require_python_evidence_questions(session)
    evidence = [resolve_citation(session, evidence_id=item, snapshot_id=snapshot_id, actor_id=actor_id) for item in evidence_ids]
    request = EvidenceAnswerRequest(question=question, prompt_version="v1", schema_version="v1", evidence=[{"id": str(item.id), "excerpt": item.excerpt_safe, "locator": item.locator} for item in evidence])
    settings = get_settings()
    allowed_ids = [str(item.id) for item in evidence]
    try:
        result = create_generation_model(settings).answer_evidence(request)
        session.add(ModelCall(run_id=None, provider=result.provider, model=result.model, operation="EVIDENCE_QA", prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=allowed_ids, status="SUCCEEDED", latency_ms=result.latency_ms, attempts=result.attempts))
        return {"answer": result.payload.answer, "fact_status": result.payload.fact_status, "citations": [{"evidenceId": str(item.id), "locator": item.locator, "precision": item.locator_precision} for item in evidence]}
    except DomainError as exc:
        session.add(ModelCall(run_id=None, provider=settings.generation_provider, model=settings.generation_model, operation="EVIDENCE_QA", prompt_version=request.prompt_version, schema_version=request.schema_version, allowed_evidence_ids=allowed_ids, status="FAILED", attempts=2 if exc.code == "MODEL_SCHEMA_INVALID" else 1, error_code=exc.code, error_summary=exc.message[:500]))
        raise
