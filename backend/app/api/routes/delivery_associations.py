from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    AgentChangeCandidateTargetResponse,
    AgentChangeProposalRequest,
    AgentChangeProposalResponse,
    AgentChangeProposalRunResponse,
    DeliveryChangeLinkCreateRequest,
    DeliveryChangeLinkResponse,
    DeliveryItemDocumentSourceLinkCreateRequest,
    DeliveryItemSourceLinkResponse,
    PlatformLinkDiscoveryResponse,
)
from app.application.services.delivery_association_service import (
    confirm_change_link,
    discover_platform_links,
    link_document_source,
    list_agent_candidate_targets,
    list_change_links,
    list_item_source_links,
    propose_agent_change_candidates,
)
from app.domain.errors import DomainError


router = APIRouter(prefix="/projects/{project_id}/delivery-items")


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == "RESOURCE_NOT_FOUND":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {"INPUT_INVALID", "SOURCE_RESPONSE_INVALID"}:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


@router.get("/{delivery_item_id}/change-links", response_model=list[DeliveryChangeLinkResponse])
def get_change_links(project_id: UUID, delivery_item_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[DeliveryChangeLinkResponse]:
    try:
        return [
            DeliveryChangeLinkResponse(**item)
            for item in list_change_links(session, project_id=project_id, delivery_item_id=delivery_item_id, actor_id=user.id)
        ]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/{delivery_item_id}/change-links", response_model=DeliveryChangeLinkResponse, status_code=status.HTTP_201_CREATED)
def create_confirmed_change_link(
    project_id: UUID,
    delivery_item_id: UUID,
    payload: DeliveryChangeLinkCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> DeliveryChangeLinkResponse:
    try:
        link = confirm_change_link(
            session,
            project_id=project_id,
            delivery_item_id=delivery_item_id,
            pull_request_resource_id=payload.pull_request_resource_id,
            git_snapshot_id=payload.git_snapshot_id,
            reason=payload.reason,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        items = list_change_links(session, project_id=project_id, delivery_item_id=delivery_item_id, actor_id=user.id)
        item = next(entry for entry in items if entry["id"] == link.id)
        return DeliveryChangeLinkResponse(**item)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/{delivery_item_id}/agent-change-candidate-targets", response_model=list[AgentChangeCandidateTargetResponse])
def get_agent_candidate_targets(project_id: UUID, delivery_item_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[AgentChangeCandidateTargetResponse]:
    try:
        return [
            AgentChangeCandidateTargetResponse(**item)
            for item in list_agent_candidate_targets(
                session,
                project_id=project_id,
                delivery_item_id=delivery_item_id,
                actor_id=user.id,
            )
        ]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/{delivery_item_id}/agent-change-candidates", response_model=AgentChangeProposalResponse, status_code=status.HTTP_201_CREATED)
def propose_change_candidates(
    project_id: UUID,
    delivery_item_id: UUID,
    payload: AgentChangeProposalRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> AgentChangeProposalResponse:
    try:
        proposal_run, links, result = propose_agent_change_candidates(
            session,
            project_id=project_id,
            delivery_item_id=delivery_item_id,
            targets=[target.model_dump() for target in payload.targets],
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        all_links = list_change_links(session, project_id=project_id, delivery_item_id=delivery_item_id, actor_id=user.id)
        created_link_ids = {link.id for link in links}
        return AgentChangeProposalResponse(
            proposal_run=AgentChangeProposalRunResponse(
                id=proposal_run.id,
                input_hash=proposal_run.input_hash,
                rules_version=proposal_run.rules_version,
                candidate_target_count=proposal_run.candidate_target_count,
                created_candidate_count=proposal_run.created_candidate_count,
                created_at=proposal_run.created_at,
            ),
            links=[DeliveryChangeLinkResponse(**item) for item in all_links if item["id"] in created_link_ids],
            created_candidate_count=result["createdCandidateCount"],
            skipped_existing_count=result["skippedExistingCount"],
            skipped_no_overlap_count=result["skippedNoOverlapCount"],
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.post("/{delivery_item_id}/discover-platform-links", response_model=PlatformLinkDiscoveryResponse)
def discover_links(
    project_id: UUID,
    delivery_item_id: UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> PlatformLinkDiscoveryResponse:
    try:
        result = discover_platform_links(
            session,
            project_id=project_id,
            delivery_item_id=delivery_item_id,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return PlatformLinkDiscoveryResponse(**result)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@router.get("/{delivery_item_id}/source-links", response_model=list[DeliveryItemSourceLinkResponse])
def get_source_links(project_id: UUID, delivery_item_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[DeliveryItemSourceLinkResponse]:
    try:
        return [
            DeliveryItemSourceLinkResponse(**item)
            for item in list_item_source_links(session, project_id=project_id, delivery_item_id=delivery_item_id, actor_id=user.id)
        ]
    except DomainError as exc:
        raise _failure(exc)


@router.post("/{delivery_item_id}/source-links", response_model=DeliveryItemSourceLinkResponse, status_code=status.HTTP_201_CREATED)
def create_document_source_link(
    project_id: UUID,
    delivery_item_id: UUID,
    payload: DeliveryItemDocumentSourceLinkCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> DeliveryItemSourceLinkResponse:
    try:
        link = link_document_source(
            session,
            project_id=project_id,
            delivery_item_id=delivery_item_id,
            source_revision_id=payload.source_revision_id,
            link_role=payload.link_role,
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        items = list_item_source_links(session, project_id=project_id, delivery_item_id=delivery_item_id, actor_id=user.id)
        item = next(entry for entry in items if entry["id"] == link.id)
        return DeliveryItemSourceLinkResponse(**item)
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)
