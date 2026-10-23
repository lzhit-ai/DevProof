"""Runtime-only resolution for credential references persisted by the domain model."""

import os
import re

from app.domain.errors import DomainError


_SECRET_REF = re.compile(r"^[A-Z][A-Z0-9_]{2,159}$")


def normalize_secret_ref(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    secret_ref = value.strip()
    if not _SECRET_REF.fullmatch(secret_ref):
        raise DomainError("INPUT_INVALID", "密钥引用必须是服务端环境变量名称")
    return secret_ref


def resolve_environment_secret(*, secret_ref: str | None, unavailable_code: str, unavailable_message: str) -> str | None:
    if secret_ref is None:
        return None
    secret = os.environ.get(secret_ref)
    if not secret:
        raise DomainError(unavailable_code, unavailable_message)
    return secret
