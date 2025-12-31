"""Health check endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from mise.db.unit_of_work import UnitOfWork
from mise.api.dependencies import get_uow

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str


@router.get("/api/health", response_model=HealthResponse)
def health_check(uow: UnitOfWork = Depends(get_uow)) -> HealthResponse:
    """
    Health check endpoint.

    Returns system health status including database connectivity.
    """
    try:
        # Simple database connectivity check
        uow.session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(status="ok", database=db_status)
