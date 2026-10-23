from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.application.security import decode_access_token
from app.core.db import get_session
from app.infrastructure.persistence.models import User

bearer = HTTPBearer(auto_error=False)
SessionDep = Annotated[Session, Depends(get_session)]


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-Id", str(uuid4()))


def idempotency_key(value: Annotated[str, Header(alias="Idempotency-Key")]) -> str:
    if not value.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Idempotency-Key 不能为空")
    return value


def current_user(
    session: SessionDep, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
    try:
        user_id: UUID = decode_access_token(credentials.credentials)
    except (ExpiredSignatureError, InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或已过期的 Token") from None
    user = session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]
