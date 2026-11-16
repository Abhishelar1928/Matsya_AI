"""
MatsyaAI Maharashtra — Marine conditions API (read-only).

- GET /marine/warnings   active IMD marine warnings with issue/validity times
- GET /marine/forecast   72 h hourly wave/wind forecast for one offshore point per district

Both reuse the Offline Expedition services; nothing is fabricated — failures are
reported as UNAVAILABLE.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.landing_centres import LANDING_CENTRES
from backend.app.ml.config import SAFETY_WAVE_HEIGHT_THRESHOLD, SAFETY_WIND_SPEED_THRESHOLD
from backend.app.services.expedition.forecast import fetch_route_forecast
from backend.app.services.expedition.package_builder import get_active_warnings
from backend.app.services.expedition.routing import is_on_land

router = APIRouter(prefix="/marine", tags=["Marine conditions"])

DISTRICTS = ["Palghar", "Mumbai", "Raigad", "Ratnagiri", "Sindhudurg"]
FORECAST_TTL_SECONDS = 30 * 60
_forecast_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def _offshore_point(lat: float, lon: float, extra_deg: float = 0.12) -> Dict[str, float]:
    """Step west from a harbour until open sea, then a little further offshore."""
    step = 0.02
    for _ in range(40):
        if not is_on_land(lat, lon):
            break
        lon -= step
    return {"latitude": round(lat, 4), "longitude": round(lon - extra_deg, 4)}


def district_points() -> List[Dict[str, Any]]:
    pts = []
    for district in DISTRICTS:
        centres = [lc for lc in LANDING_CENTRES if lc.district == district]
        if not centres:
            continue
        lat = sum(c.latitude for c in centres) / len(centres)
        lon = min(c.longitude for c in centres)
        p = _offshore_point(lat, lon)
        pts.append({"district": district, "index": len(pts), **p})
    return pts


@router.get("/warnings")
async def marine_warnings(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await get_active_warnings(db)


@router.get("/forecast")
async def marine_forecast(refresh: Optional[bool] = False) -> Dict[str, Any]:
    now = time.time()
    cached = _forecast_cache["data"]
    if cached and not refresh and now - _forecast_cache["at"] < FORECAST_TTL_SECONDS:
        return cached

    points = district_points()
    forecast = await fetch_route_forecast(points)
    districts = []
    for i, p in enumerate(points):
        series = forecast["points"][i] if i < len(forecast.get("points", [])) else None
        districts.append({"district": p["district"], "latitude": p["latitude"], "longitude": p["longitude"],
                          "hourly": series["hourly"] if series else None})
    data = {
        "status": forecast["status"],
        "provider": forecast["provider"],
        "retrieved_at": forecast["retrieved_at"],
        "valid_from": forecast["valid_from"],
        "valid_until": forecast["valid_until"],
        "error": forecast.get("error"),
        "thresholds": {"wave_height_m": SAFETY_WAVE_HEIGHT_THRESHOLD, "wind_speed_kmh": SAFETY_WIND_SPEED_THRESHOLD},
        "districts": districts,
    }
    if forecast["status"] != "UNAVAILABLE":
        _forecast_cache.update(at=now, data=data)
    return data
