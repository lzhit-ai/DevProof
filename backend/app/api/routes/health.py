from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import engine

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness; it never implies database readiness."""

    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response) -> dict[str, str]:
    """Readiness requires the PostgreSQL fact store to be reachable."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}
