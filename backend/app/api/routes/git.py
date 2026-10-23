from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import CurrentUserDep, SessionDep, correlation_id, idempotency_key
from app.api.schemas import (
    GitRepositoryCreateRequest,
    GitRepositoryResponse,
    GitSnapshotCreateRequest,
    GitSnapshotDiffResponse,
    GitSnapshotResponse,
)
from app.application.services.git_service import freeze_git_snapshot, get_git_snapshot_diff, list_repositories, register_repository
from app.domain.errors import DomainError
from app.infrastructure.credential_resolver import normalize_secret_ref
from app.infrastructure.git_reader import ReadOnlyGitReader

repository_router = APIRouter(prefix="/projects/{project_id}/git-repositories")
snapshot_router = APIRouter(prefix="/cycles/{cycle_id}/git-snapshots")
snapshot_read_router = APIRouter(prefix="/git-snapshots")


@repository_router.post("", response_model=GitRepositoryResponse, status_code=status.HTTP_201_CREATED)
def register(
    project_id: UUID,
    payload: GitRepositoryCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> GitRepositoryResponse:
    try:
        repository = register_repository(
            session,
            project_id=project_id,
            display_url=payload.display_url,
            credential_ref=normalize_secret_ref(payload.credential_ref),
            actor_id=user.id,
            correlation_id=correlation_id(request),
        )
        session.commit()
        return GitRepositoryResponse(id=repository.id, project_id=repository.project_id, display_url=repository.display_url, read_only=repository.read_only)
    except DomainError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})


@repository_router.get("", response_model=list[GitRepositoryResponse])
def list_registered_repositories(
    project_id: UUID,
    session: SessionDep,
    user: CurrentUserDep,
) -> list[GitRepositoryResponse]:
    try:
        repositories = list_repositories(session, project_id=project_id, actor_id=user.id)
        return [
            GitRepositoryResponse(
                id=repository.id,
                project_id=repository.project_id,
                display_url=repository.display_url,
                read_only=repository.read_only,
            )
            for repository in repositories
        ]
    except DomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        )


@snapshot_router.post("", response_model=GitSnapshotResponse, status_code=status.HTTP_201_CREATED)
def freeze(
    cycle_id: UUID,
    payload: GitSnapshotCreateRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
    _: str = Depends(idempotency_key),
) -> GitSnapshotResponse:
    try:
        snapshot = freeze_git_snapshot(session, cycle_id=cycle_id, repository_id=payload.repository_id, base_ref=payload.base_ref, target_ref=payload.target_ref, diff_mode=payload.diff_mode, include_paths=payload.include_paths, exclude_paths=payload.exclude_paths, actor_id=user.id, correlation_id=correlation_id(request), reader=ReadOnlyGitReader())
        session.commit()
        return GitSnapshotResponse(id=snapshot.id, base_sha=snapshot.base_sha, target_sha=snapshot.target_sha, merge_base_sha=snapshot.merge_base_sha, diff_mode=snapshot.diff_mode, diff_hash=snapshot.diff_hash, coverage=snapshot.coverage)
    except DomainError as exc:
        session.rollback()
        http_status = status.HTTP_403_FORBIDDEN if exc.code == "AUTH_FORBIDDEN" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})


@snapshot_read_router.get("/{snapshot_id}/diff", response_model=GitSnapshotDiffResponse)
def get_diff(snapshot_id: UUID, session: SessionDep, user: CurrentUserDep) -> GitSnapshotDiffResponse:
    try:
        return GitSnapshotDiffResponse(**get_git_snapshot_diff(session, snapshot_id=snapshot_id, actor_id=user.id))
    except DomainError as exc:
        http_status = status.HTTP_404_NOT_FOUND if exc.code == "RESOURCE_NOT_FOUND" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
