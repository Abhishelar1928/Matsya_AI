"""
MatsyaAI Maharashtra — FastAPI Application Entry Point.

Creates and configures the FastAPI application with:
- CORS middleware
- Structured logging
- API v1 router
- Root health endpoint
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.logging import setup_logging
from backend.app.api.v1 import health as health_v1
from backend.app.api.v1 import predictions as predictions_v1
from backend.app.api.v1 import pfz as pfz_v1
from backend.app.api.v1 import map as map_v1
from backend.app.api.v1 import sources as sources_v1
from backend.app.api.v1 import expedition as expedition_v1
from backend.app.api.v1 import marine as marine_v1
from backend.app.services.expedition.package_builder import OFFLINE_ASSETS_DIR, OFFLINE_ASSETS_URL
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler — runs on startup and shutdown."""
    setup_logging()

    import structlog
    log = structlog.get_logger()
    await log.ainfo(
        "application_startup",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    yield
    await log.ainfo("application_shutdown")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Marine decision-support platform for Maharashtra fishermen. "
        "Combines INCOIS oceanographic data, IMD weather warnings, and "
        "geospatial intelligence to recommend safe, productive fishing zones."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_v1.router, prefix="/api/v1")
app.include_router(predictions_v1.router, prefix="/api/v1")
app.include_router(pfz_v1.router, prefix="/api/v1")
app.include_router(map_v1.router, prefix="/api/v1")
app.include_router(sources_v1.router, prefix="/api/v1")
app.include_router(expedition_v1.router, prefix="/api/v1")
app.include_router(marine_v1.router, prefix="/api/v1")

# Offline basemap (PMTiles) and bathymetry contours for Expedition Mode.
# Served under /api so the Vite dev proxy forwards it. StaticFiles supports
# HTTP Range requests, which PMTiles relies on.
OFFLINE_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(OFFLINE_ASSETS_URL, StaticFiles(directory=OFFLINE_ASSETS_DIR), name="offline-assets")


# ---------------------------------------------------------------------------
# Root endpoint (convenience redirect / quick check)
# ---------------------------------------------------------------------------
@app.get("/", tags=["root"])
async def root() -> dict:
    """Root endpoint — confirms the API is running."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
