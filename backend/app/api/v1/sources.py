"""
MatsyaAI Maharashtra — Source Freshness & Health API Router.

Exposes source-level operational health and data freshness for:
- INCOIS Potential Fishing Zone (PFZ)
- IMD Mumbai Marine / Fishermen Warnings
- Open-Meteo Current Marine Weather
- Global Fishing Watch (GFW AIS)
"""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.services.freshness.source_tracker import SourceFreshnessTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get(
    "/freshness",
    response_model=Dict[str, Any],
    summary="Get Source Freshness & Health Status",
    description=(
        "Returns the operational health, actual data timestamp, expiration validity, "
        "age in minutes, and freshness status across all authoritative data sources."
    ),
)
async def get_source_freshness(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns source-level freshness tracking information.
    Freshness is calculated from actual data timestamps, never retrieved_at alone.
    """
    tracker = SourceFreshnessTracker()
    return await tracker.get_all_freshness(db=db)
