import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.schemas.pfz import PFZLatestResponse, PFZLocation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pfz", tags=["pfz"])

DEMO_HISTORICAL_PFZ = [
    PFZLocation(
        landing_centre="Ratnagiri - Mirkarwada",
        direction="SW",
        bearing_degrees=225,
        distance_km="32.5",
        depth_min_m=40,
        depth_max_m=55,
        latitude=17.85,
        longitude=73.05,
    ),
    PFZLocation(
        landing_centre="Sindhudurg - Malvan",
        direction="WNW",
        bearing_degrees=290,
        distance_km="28.0",
        depth_min_m=35,
        depth_max_m=50,
        latitude=16.15,
        longitude=73.20,
    ),
    PFZLocation(
        landing_centre="Mumbai - Sassoon Dock",
        direction="WSW",
        bearing_degrees=240,
        distance_km="45.0",
        depth_min_m=50,
        depth_max_m=65,
        latitude=18.80,
        longitude=72.45,
    ),
]


@router.get(
    "/latest",
    response_model=PFZLatestResponse,
    summary="Get Latest Official INCOIS PFZ Advisory",
    description="Returns the most recently successfully ingested INCOIS PFZ records for Maharashtra.",
)
async def get_latest_pfz(
    demo: bool = Query(False, description="Enable DEMO mode with cached real data fallback"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    now = datetime.now(timezone.utc)
    try:
        stmt = select(INCOISPFZAdvisory).order_by(INCOISPFZAdvisory.retrieved_at.desc()).limit(1)
        result = await db.execute(stmt)
        latest_record = result.scalars().first()

        if not latest_record:
            if demo:
                return PFZLatestResponse(
                    source="INCOIS",
                    source_type="OFFICIAL_PFZ_ADVISORY",
                    sector="Maharashtra",
                    status="DEMO_HISTORICAL",
                    advisory_date=datetime(2023, 10, 15, 6, 0, tzinfo=timezone.utc),
                    validity_date=datetime(2023, 10, 17, 6, 0, tzinfo=timezone.utc),
                    retrieved_at=now,
                    count=len(DEMO_HISTORICAL_PFZ),
                    locations=DEMO_HISTORICAL_PFZ,
                )
            return PFZLatestResponse(
                status="UNAVAILABLE",
                retrieved_at=now,
                error="No PFZ data available in the database. Awaiting next scheduled ingestion.",
            )

        latest_retrieval_time = latest_record.retrieved_at
        advisory_date = latest_record.advisory_date
        validity_date = latest_record.validity_date

        api_status = "LIVE"
        if validity_date and validity_date < now:
            api_status = "STALE"
        elif advisory_date is None and validity_date is None:
            api_status = "UNKNOWN_FRESHNESS"

        stmt_batch = select(INCOISPFZAdvisory).where(
            INCOISPFZAdvisory.retrieved_at == latest_retrieval_time
        )
        res_batch = await db.execute(stmt_batch)
        records = res_batch.scalars().all()

        locations = []
        for r in records:
            locations.append(
                PFZLocation(
                    landing_centre=r.landing_centre,
                    direction=r.direction,
                    bearing_degrees=r.bearing_degrees,
                    distance_km=str(r.distance_km),
                    depth_min_m=r.depth_min_m,
                    depth_max_m=r.depth_max_m,
                    latitude=r.latitude,
                    longitude=r.longitude,
                )
            )

        return PFZLatestResponse(
            status=api_status,
            advisory_date=advisory_date,
            validity_date=validity_date,
            retrieved_at=latest_retrieval_time,
            count=len(locations),
            locations=locations,
        )

    except Exception as e:
        logger.warning(f"Failed to query database for PFZ records: {e}")
        if demo:
            return PFZLatestResponse(
                source="INCOIS",
                source_type="OFFICIAL_PFZ_ADVISORY",
                sector="Maharashtra",
                status="DEMO_HISTORICAL",
                advisory_date=datetime(2023, 10, 15, 6, 0, tzinfo=timezone.utc),
                validity_date=datetime(2023, 10, 17, 6, 0, tzinfo=timezone.utc),
                retrieved_at=now,
                count=len(DEMO_HISTORICAL_PFZ),
                locations=DEMO_HISTORICAL_PFZ,
            )
        return PFZLatestResponse(
            status="UNAVAILABLE",
            retrieved_at=now,
            error=f"Database query failed: {str(e)}",
        )

