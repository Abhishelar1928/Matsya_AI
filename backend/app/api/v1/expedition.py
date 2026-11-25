"""
MatsyaAI Maharashtra — Offline Expedition Mode API.

- GET  /expedition/landing-centres   canonical departure/return points
- POST /expedition/packages          build a downloadable offline package
- POST /expedition/sync              idempotent upload of track/catch/observation
                                     records + fresh warnings/forecast delta
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.landing_centres import get_landing_centre, landing_centres_as_dicts
from backend.app.models.expedition import Expedition
from backend.app.services.expedition.forecast import fetch_route_forecast
from backend.app.services.expedition.package_builder import (
    _parse,
    build_package,
    get_active_warnings,
    get_compact_predictions,
)
from backend.app.services.expedition.routing import build_route
from backend.app.services.expedition.sync import apply_sync
from backend.app.services.pfz_query import get_latest_pfz_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/expedition", tags=["Offline Expedition"])

# Maharashtra EEZ-ish sanity bounds for destinations
LAT_RANGE = (14.5, 21.5)
LON_RANGE = (68.0, 74.5)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Point(BaseModel):
    latitude: float = Field(..., ge=LAT_RANGE[0], le=LAT_RANGE[1])
    longitude: float = Field(..., ge=LON_RANGE[0], le=LON_RANGE[1])
    name: Optional[str] = Field(None, max_length=100)


class OriginPoint(BaseModel):
    latitude: float = Field(..., ge=14.0, le=22.5)
    longitude: float = Field(..., ge=68.0, le=78.0)
    name: Optional[str] = Field(None, max_length=100)


class PackageRequest(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64)
    landing_centre_id: str
    origin: Optional[OriginPoint] = None
    destination: Optional[Point] = None
    pfz_index: Optional[int] = Field(None, ge=0)
    planned_departure: Optional[datetime] = None
    planned_return: Optional[datetime] = None

    @model_validator(mode="after")
    def one_destination(self):
        if (self.destination is None) == (self.pfz_index is None):
            raise ValueError("Provide exactly one of 'destination' or 'pfz_index'")
        return self


class TrackPointIn(BaseModel):
    client_uuid: str = Field(..., min_length=8, max_length=36)
    recorded_at: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None
    cog_deg: Optional[float] = None
    compass_heading_deg: Optional[float] = None
    xte_km: Optional[float] = None
    accuracy_m: Optional[float] = None


class CatchIn(BaseModel):
    client_uuid: str = Field(..., min_length=8, max_length=36)
    recorded_at: datetime
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    species: str = Field(..., min_length=1, max_length=100)
    species_id: Optional[str] = Field(None, max_length=64)
    weight_kg: Optional[float] = Field(None, ge=0, le=100000)
    quantity: Optional[int] = Field(None, ge=0, le=1000000)
    fishing_duration_min: Optional[int] = Field(None, ge=0, le=10000)
    estimated_value_inr: Optional[float] = Field(None, ge=0, le=100000000)
    notes: Optional[str] = Field(None, max_length=2000)


class ObservationIn(BaseModel):
    client_uuid: str = Field(..., min_length=8, max_length=36)
    recorded_at: datetime
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    observation_type: str = Field(..., min_length=1, max_length=50)
    value: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)


class SyncRequest(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=64)
    expedition_id: str = Field(..., min_length=8, max_length=36)
    batch_id: Optional[str] = Field(None, max_length=64)
    track_points: List[TrackPointIn] = Field(default_factory=list, max_length=20000)
    catches: List[CatchIn] = Field(default_factory=list, max_length=2000)
    observations: List[ObservationIn] = Field(default_factory=list, max_length=2000)
    include_delta: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/landing-centres")
async def list_landing_centres() -> Dict[str, Any]:
    return {"landing_centres": landing_centres_as_dicts()}


@router.post("/packages")
async def create_package(req: PackageRequest, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    centre = get_landing_centre(req.landing_centre_id)
    if centre is None:
        raise HTTPException(status_code=404, detail=f"Unknown landing_centre_id '{req.landing_centre_id}'")

    try:
        package = await build_package(
            db=db,
            device_id=req.device_id,
            landing_centre=centre,
            origin=req.origin.model_dump() if req.origin else None,
            destination=req.destination.model_dump() if req.destination else None,
            pfz_index=req.pfz_index,
            planned_departure=req.planned_departure,
            planned_return=req.planned_return,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    manifest, dest = package["manifest"], package["destination"]
    try:
        db.add(Expedition(
            id=manifest["package_id"],
            device_id=req.device_id,
            landing_centre_id=centre.id,
            destination_latitude=dest["latitude"],
            destination_longitude=dest["longitude"],
            destination_geom=f"SRID=4326;POINT({dest['longitude']} {dest['latitude']})",
            package_created_at=_parse(manifest["created_at"]),
            package_valid_until=_parse(manifest["valid_until"]),
            planned_departure=req.planned_departure,
            planned_return=req.planned_return,
        ))
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to persist expedition {manifest['package_id']}: {e}")
        raise HTTPException(status_code=503, detail="Could not register expedition; try again when connected")

    return package


@router.post("/sync")
async def sync_expedition(
    req: SyncRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    expedition = await db.get(Expedition, req.expedition_id)
    if expedition is None or expedition.device_id != req.device_id:
        raise HTTPException(status_code=404, detail="Expedition not found for this device")

    result = await apply_sync(
        db,
        expedition,
        [t.model_dump() for t in req.track_points],
        [c.model_dump() for c in req.catches],
        [o.model_dump() for o in req.observations],
    )
    if req.batch_id or x_idempotency_key:
        result["batch_id"] = req.batch_id or x_idempotency_key

    if req.include_delta:
        centre = get_landing_centre(expedition.landing_centre_id)
        delta: Dict[str, Any] = {
            "warnings": await get_active_warnings(db),
            "predictions": await get_compact_predictions(db),
            "pfz": await get_latest_pfz_batch(db),
        }
        if centre is not None:
            route = build_route(
                {"latitude": centre.latitude, "longitude": centre.longitude},
                {"latitude": expedition.destination_latitude, "longitude": expedition.destination_longitude},
            )
            delta["forecast"] = await fetch_route_forecast(route["waypoints"])
        result["delta"] = delta

    return result
