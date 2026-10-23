import hashlib
import json
from datetime import UTC, datetime

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.infrastructure.persistence.models import IdempotencyRecord


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hash(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _error(request: Request, *, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=409, content={"code": code, "message": message, "correlationId": request.headers.get("X-Correlation-Id"), "details": None})


async def replay_or_reserve(request: Request) -> Response | tuple[IdempotencyRecord, str] | None:
    """Reserve one command before its handler and replay only an identical completed request."""
    key = request.headers.get("Idempotency-Key")
    if request.method not in WRITE_METHODS or not key or request.url.path.endswith("/auth/login"):
        return None
    body = await request.body()
    principal = _hash(request.headers.get("Authorization", "anonymous").encode())
    request_hash = _hash(body)
    scope = {
        "principal_hash": principal,
        "request_method": request.method,
        "request_path": request.url.path,
        "idempotency_key": key,
    }
    with SessionLocal.begin() as session:
        existing = session.query(IdempotencyRecord).filter_by(**scope).one_or_none()
        if existing is not None:
            if existing.request_hash != request_hash:
                return _error(request, code="IDEMPOTENCY_CONFLICT", message="同一幂等键不能对应不同请求内容")
            if existing.state == "COMPLETED":
                return JSONResponse(status_code=existing.response_status or 200, content=existing.response_body or {})
            return _error(request, code="IDEMPOTENCY_IN_PROGRESS", message="相同命令正在处理中")
        record = IdempotencyRecord(**scope, request_hash=request_hash)
        session.add(record)
        try:
            session.flush()
        except IntegrityError:
            # A concurrent request claimed the key after the first lookup.
            return _error(request, code="IDEMPOTENCY_IN_PROGRESS", message="相同命令正在处理中")
        session.expunge(record)
    return record, request_hash


def complete(record_id, request_hash: str, response: Response, body: bytes) -> Response:
    """Persist only JSON response data; commands in this API all use JSON envelopes."""
    try:
        response_body = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        response_body = {"detail": {"code": "SYSTEM_ERROR", "message": "命令响应不是可重放 JSON"}}
    with SessionLocal.begin() as session:
        record = session.get(IdempotencyRecord, record_id)
        if record is not None and record.request_hash == request_hash:
            record.state = "COMPLETED"
            record.response_status = response.status_code
            record.response_body = response_body
            record.completed_at = datetime.now(UTC)
    headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-type"}}
    return Response(content=body, status_code=response.status_code, media_type=response.media_type or "application/json", headers=headers)


def abort(record_id, request_hash: str) -> None:
    """Do not leave a failed handler permanently reserving a client retry key."""
    with SessionLocal.begin() as session:
        record = session.get(IdempotencyRecord, record_id)
        if record is not None and record.request_hash == request_hash and record.state == "IN_PROGRESS":
            session.delete(record)
