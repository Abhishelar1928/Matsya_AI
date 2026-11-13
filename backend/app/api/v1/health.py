"""
MatsyaAI Maharashtra — Health Check Endpoint.

Provides a quick liveness and database-connectivity check
for monitoring, Docker health-checks, and the frontend status display.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.database import check_db_connection

router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Health-check response model."""

    status: str
    version: str
    environment: str
    database: str
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description="Returns application status including database connectivity.",
)
async def health_check() -> HealthResponse:
    """Return current application health status."""

    db_connected = await check_db_connection()

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database="connected" if db_connected else "disconnected",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
