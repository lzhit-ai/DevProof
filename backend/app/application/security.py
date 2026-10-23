import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import get_settings


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    algorithm, rounds, encoded_salt, encoded_digest = encoded.split("$", maxsplit=3)
    if algorithm != "pbkdf2_sha256" or rounds != "310000":
        return False
    candidate = hash_password(password, base64.urlsafe_b64decode(encoded_salt.encode("ascii")))
    return hmac.compare_digest(candidate, encoded)


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_access_ttl_seconds)
    return jwt.encode({"sub": str(user_id), "exp": expires_at}, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> UUID:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return UUID(payload["sub"])
