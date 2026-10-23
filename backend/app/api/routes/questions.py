from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.schemas import EvidenceQuestionRequest, EvidenceQuestionResponse
from app.application.services.question_service import answer_evidence_question
from app.domain.errors import DomainError


router = APIRouter(prefix="/input-snapshots/{snapshot_id}/questions")


@router.post("", response_model=EvidenceQuestionResponse)
def ask(snapshot_id: UUID, payload: EvidenceQuestionRequest, session: SessionDep, user: CurrentUserDep) -> EvidenceQuestionResponse:
    try:
        result = answer_evidence_question(session, snapshot_id=snapshot_id, question=payload.question, evidence_ids=payload.evidence_ids, actor_id=user.id)
        session.commit()
        return EvidenceQuestionResponse(**result)
    except DomainError as exc:
        session.rollback()
        status_code = 422 if exc.code == "CITATION_INVALID" else 424 if exc.code in {"MODEL_NOT_CONFIGURED", "MODEL_UNAVAILABLE", "MODEL_SCHEMA_INVALID"} else 403
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})
