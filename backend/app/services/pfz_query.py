"""
MatsyaAI Maharashtra — Shared INCOIS PFZ query.

Returns the most recent INCOIS PFZ advisory batch (all rows sharing the latest
``retrieved_at``). Used by the map endpoint and the Offline Expedition package.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from backend.app.models.incois_pfz import INCOISPFZAdvisory

logger = logging.getLogger(__name__)

PFZ_SOURCE = "INCOIS (Official Government Advisory)"


def empty_pfz() -> Dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "advisory_date": None,
        "validity_date": None,
        "count": 0,
        "locations": [],
        "source": PFZ_SOURCE,
    }


async def get_latest_pfz_batch(db: Optional[Any]) -> Dict[str, Any]:
    """Latest PFZ batch, or an UNAVAILABLE payload. Never raises."""
    if db is None:
        return empty_pfz()
    try:
        stmt = select(INCOISPFZAdvisory).order_by(INCOISPFZAdvisory.retrieved_at.desc()).limit(1)
        latest = (await db.execute(stmt)).scalars().first()
        if not latest:
            return empty_pfz()

        stmt_batch = select(INCOISPFZAdvisory).where(
            INCOISPFZAdvisory.retrieved_at == latest.retrieved_at
        )
        records = (await db.execute(stmt_batch)).scalars().all()

        now = datetime.now(timezone.utc)
        status = "STALE" if latest.validity_date and latest.validity_date < now else "LIVE"
        locations = [
            {
                "landing_centre": r.landing_centre,
                "direction": r.direction,
                "bearing_degrees": r.bearing_degrees,
                "distance_km": r.distance_km,
                "depth_min_m": r.depth_min_m,
                "depth_max_m": r.depth_max_m,
                "latitude": r.latitude,
                "longitude": r.longitude,
            }
            for r in records
        ]
        return {
            "status": status,
            "advisory_date": latest.advisory_date.isoformat() if latest.advisory_date else None,
            "validity_date": latest.validity_date.isoformat() if latest.validity_date else None,
            "count": len(locations),
            "locations": locations,
            "source": PFZ_SOURCE,
        }
    except Exception as e:
        logger.warning(f"Failed to query database for PFZ records: {e}")
        return empty_pfz()
