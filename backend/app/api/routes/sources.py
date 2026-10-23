from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import ChunkItemResponse, KnowledgeBaseCreateRequest, KnowledgeBaseMountRequest, KnowledgeBaseResponse, SourceContentResponse, SourceDetailResponse, SourceResponse
from app.application.services.source_service import create_knowledge_base, create_source_revision, delete_source, list_all_knowledge_bases, list_project_knowledge_bases, list_project_sources, list_source_chunks, mount_knowledge_base, read_source_content, read_source_download, unmount_knowledge_base
from app.domain.errors import DomainError


def _failure(exc: DomainError) -> HTTPException:
    if exc.code == "AUTH_FORBIDDEN":
        code = status.HTTP_403_FORBIDDEN
    elif exc.code in {"INPUT_INVALID", "SOURCE_MEDIA_UNSUPPORTED", "SOURCE_TOO_LARGE"}:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif exc.code in {"SOURCE_FROZEN_IN_SNAPSHOT", "SOURCE_NOT_READY", "BUSINESS_OWNER_MISMATCH"}:
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message})


sources_router = APIRouter(prefix="/projects/{project_id}/sources")
knowledge_bases_router = APIRouter(prefix="/projects/{project_id}/knowledge-bases")
all_knowledge_bases_router = APIRouter(prefix="/knowledge-bases")


@all_knowledge_bases_router.get("", response_model=list[KnowledgeBaseResponse])
def get_all_knowledge_bases(session: SessionDep, user: CurrentUserDep) -> list[KnowledgeBaseResponse]:
    try:
        items = list_all_knowledge_bases(session, actor_id=user.id)
        return [
            KnowledgeBaseResponse(
                id=item.id, project_id=item.project_id, name=item.name,
                created_at=item.created_at, updated_at=item.updated_at,
            )
            for item in items
        ]
    except DomainError as exc:
        raise _failure(exc)


@sources_router.get("", response_model=list[SourceDetailResponse])
def list_sources(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[SourceDetailResponse]:
    try:
        return [SourceDetailResponse(**item) for item in list_project_sources(session, project_id=project_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@sources_router.get("/{source_id}", response_model=SourceContentResponse)
def read_content(project_id: UUID, source_id: UUID, session: SessionDep, user: CurrentUserDep) -> SourceContentResponse:
    try:
        return SourceContentResponse(**read_source_content(session, project_id=project_id, source_id=source_id, actor_id=user.id))
    except DomainError as exc:
        raise _failure(exc)


@sources_router.get("/{source_id}/download")
def download_source(project_id: UUID, source_id: UUID, session: SessionDep, user: CurrentUserDep) -> FileResponse:
    try:
        item = read_source_download(session, project_id=project_id, source_id=source_id, actor_id=user.id)
        return FileResponse(item["path"], media_type=item["media_type"], filename=item["filename"])
    except DomainError as exc:
        raise _failure(exc)


@sources_router.get("/{source_id}/chunks", response_model=list[ChunkItemResponse])
def list_chunks(project_id: UUID, source_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[ChunkItemResponse]:
    try:
        return [ChunkItemResponse(**item) for item in list_source_chunks(session, project_id=project_id, source_id=source_id, actor_id=user.id)]
    except DomainError as exc:
        raise _failure(exc)


@sources_router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def upload(
    project_id: UUID,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(...),
    source_role: str = Form(..., max_length=64),
    logical_name: str = Form(..., max_length=255),
    knowledge_base_id: UUID | None = Form(None),
    force_ocr: bool = Form(False),
    _: str = Depends(idempotency_key),
) -> SourceResponse:
    try:
        source, job = create_source_revision(
            session,
            project_id=project_id,
            source_role=source_role,
            logical_name=logical_name,
            original_filename=file.filename or logical_name,
            claimed_media_type=file.content_type,
            content=await file.read(),
            actor_id=user.id,
            correlation_id=correlation_id(request),
            knowledge_base_id=knowledge_base_id,
            force_ocr=force_ocr,
        )
        session.commit()
        return SourceResponse(
            id=source.id,
            project_id=source.project_id,
            logical_name=source.logical_name,
            revision_no=source.revision_no,
            content_hash=source.content_hash,
            processing_status=source.processing_status,
            parser_version=source.parser_version,
            ingestion_job_id=job.id,
            knowledge_base_id=source.knowledge_base_id,
            force_ocr=source.force_ocr,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@sources_router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source_endpoint(project_id: UUID, source_id: UUID, session: SessionDep, user: CurrentUserDep) -> None:
    try:
        delete_source(session, project_id=project_id, source_id=source_id, actor_id=user.id)
        session.commit()
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@knowledge_bases_router.get("", response_model=list[KnowledgeBaseResponse])
def get_knowledge_bases(project_id: UUID, session: SessionDep, user: CurrentUserDep) -> list[KnowledgeBaseResponse]:
    try:
        items = list_project_knowledge_bases(session, project_id=project_id, actor_id=user.id)
        return [
            KnowledgeBaseResponse(
                id=item.id, project_id=item.project_id, name=item.name,
                created_at=item.created_at, updated_at=item.updated_at,
            )
            for item in items
        ]
    except DomainError as exc:
        raise _failure(exc)


@knowledge_bases_router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base_endpoint(
    project_id: UUID,
    payload: KnowledgeBaseCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> KnowledgeBaseResponse:
    try:
        item = create_knowledge_base(
            session,
            project_id=project_id,
            name=payload.name,
            actor_id=user.id,
        )
        session.commit()
        return KnowledgeBaseResponse(
            id=item.id, project_id=item.project_id, name=item.name,
            created_at=item.created_at, updated_at=item.updated_at,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@knowledge_bases_router.post("/mount", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
def mount_knowledge_base_endpoint(
    project_id: UUID,
    payload: KnowledgeBaseMountRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> KnowledgeBaseResponse:
    try:
        item = mount_knowledge_base(
            session,
            project_id=project_id,
            knowledge_base_id=payload.knowledge_base_id,
            actor_id=user.id,
        )
        session.commit()
        return KnowledgeBaseResponse(
            id=item.id, project_id=item.project_id, name=item.name,
            created_at=item.created_at, updated_at=item.updated_at,
        )
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)


@knowledge_bases_router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmount_knowledge_base_endpoint(project_id: UUID, knowledge_base_id: UUID, session: SessionDep, user: CurrentUserDep) -> None:
    try:
        unmount_knowledge_base(session, project_id=project_id, knowledge_base_id=knowledge_base_id, actor_id=user.id)
        session.commit()
    except DomainError as exc:
        session.rollback()
        raise _failure(exc)
