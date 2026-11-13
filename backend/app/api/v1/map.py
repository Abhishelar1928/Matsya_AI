"""
MatsyaAI Maharashtra — Consolidated Map API Endpoint.

Delivers the comprehensive map payload for the fisherman-facing interactive UI:
- Predicted apparent fishing activity grid (0.25 deg)
- Official INCOIS PFZ advisory points
- Independent marine safety status
- Coastal landing centres
- Live/Demo freshness provenance
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.api.v1.predictions import fetch_latest_persisted_predictions
from backend.app.ml.dataset_builder import _LANDING_CENTRES
from backend.app.ml.inference import get_inference_pipeline
from backend.app.ml.safety_gate import SafetyGate
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.services.freshness.source_tracker import SourceFreshnessTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/map", tags=["Map"])

LANDING_CENTRE_METADATA = [
    {"name": "Mumbai - Sassoon Dock", "district": "Mumbai", "latitude": 19.0760, "longitude": 72.8777},
    {"name": "Mumbai - Versova", "district": "Mumbai", "latitude": 18.9388, "longitude": 72.8354},
    {"name": "Palghar - Arnala", "district": "Palghar", "latitude": 19.2183, "longitude": 72.8145},
    {"name": "Ratnagiri - Mirkarwada", "district": "Ratnagiri", "latitude": 18.2513, "longitude": 73.2698},
    {"name": "Ratnagiri - Harnai", "district": "Ratnagiri", "latitude": 17.6835, "longitude": 73.3011},
    {"name": "Sindhudurg - Malvan", "district": "Sindhudurg", "latitude": 16.0600, "longitude": 73.4700},
    {"name": "Sindhudurg - Devgad", "district": "Sindhudurg", "latitude": 15.7280, "longitude": 73.5150},
    {"name": "Raigad - Alibaug", "district": "Raigad", "latitude": 18.7495, "longitude": 72.8242},
    {"name": "Palghar - Satpati", "district": "Palghar", "latitude": 19.8135, "longitude": 72.7557},
]


@router.get("/summary", response_model=Dict[str, Any])
async def get_map_summary(
    demo: bool = Query(False, description="Enable DEMO mode with cached real data fallback"),
    db: Optional[Session] = Depends(get_db),
):
    """
    Consolidated map endpoint delivering:
    1. 171 canonical grid cell predictions (apparent fishing activity)
    2. INCOIS PFZ advisory points
    3. Marine safety and weather summary
    4. Coastal landing centres
    5. Data freshness & model provenance
    """
    pipeline = get_inference_pipeline()
    if demo:
        pipeline.demo_mode = True

    # 1. Predictions from DB
    predictions = await fetch_latest_persisted_predictions(db, demo)

    # 2. Safety Status
    statuses = [p.get("safety_status") for p in predictions]
    if "UNSAFE" in statuses:
        overall_safety = "UNSAFE"
        safety_message = "Active severe marine warning. Fishermen are advised not to venture into rough sea sectors."
    elif "CAUTION" in statuses:
        overall_safety = "CAUTION"
        safety_message = "Rough sea or high wind conditions observed in certain marine sectors. Exercise caution."
    elif "SAFE_CONFIRMED" in statuses:
        overall_safety = "SAFE_CONFIRMED"
        safety_message = "Normal sea conditions confirmed. Official marine warnings report no active alerts."
    else:
        overall_safety = "NO_WARNING_DATA"
        safety_message = "Marine warning feed unavailable. Check official local port signals before sailing."

    # 3. Official INCOIS PFZ
    pfz_data = {
        "status": "UNAVAILABLE",
        "advisory_date": None,
        "validity_date": None,
        "count": 0,
        "locations": [],
        "source": "INCOIS (Official Government Advisory)",
    }

    if db is not None:
        try:
            from sqlalchemy import select
            stmt = select(INCOISPFZAdvisory).order_by(INCOISPFZAdvisory.retrieved_at.desc()).limit(1)
            result = await db.execute(stmt)
            latest_record = result.scalars().first()
            if latest_record:
                retrieval_time = latest_record.retrieved_at
                stmt_batch = select(INCOISPFZAdvisory).where(INCOISPFZAdvisory.retrieved_at == retrieval_time)
                res_batch = await db.execute(stmt_batch)
                records = res_batch.scalars().all()
                now = datetime.now(timezone.utc)
                status_str = "LIVE"
                if latest_record.validity_date and latest_record.validity_date < now:
                    status_str = "STALE"

                locations = []
                for r in records:
                    locations.append({
                        "landing_centre": r.landing_centre,
                        "direction": r.direction,
                        "bearing_degrees": r.bearing_degrees,
                        "distance_km": r.distance_km,
                        "latitude": r.latitude,
                        "longitude": r.longitude,
                    })

                pfz_data = {
                    "status": status_str,
                    "advisory_date": latest_record.advisory_date.isoformat() if latest_record.advisory_date else None,
                    "validity_date": latest_record.validity_date.isoformat() if latest_record.validity_date else None,
                    "count": len(locations),
                    "locations": locations,
                    "source": "INCOIS (Official Government Advisory)",
                }
        except Exception as e:
            logger.warning(f"Failed to query database for PFZ records: {e}")

    # If DB has no PFZ and in DEMO mode, provide documented sample coordinates from INCOIS feed
    if pfz_data["count"] == 0 and (demo or pipeline.demo_mode):
        pfz_data = {
            "status": "DEMO_HISTORICAL",
            "advisory_date": "2023-10-15T06:00:00Z",
            "validity_date": "2023-10-17T06:00:00Z",
            "count": 3,
            "locations": [
                {"landing_centre": "Ratnagiri - Mirkarwada", "direction": "SW", "bearing_degrees": 225.0, "distance_km": 32.5, "latitude": 17.85, "longitude": 73.05},
                {"landing_centre": "Sindhudurg - Malvan", "direction": "WNW", "bearing_degrees": 290.0, "distance_km": 28.0, "latitude": 16.15, "longitude": 73.20},
                {"landing_centre": "Mumbai - Sassoon Dock", "direction": "WSW", "bearing_degrees": 240.0, "distance_km": 45.0, "latitude": 18.80, "longitude": 72.45},
            ],
            "source": "INCOIS Historical Archive (Demonstration Reference)",
        }

    freshness = predictions[0].get("data_freshness_status", "LIVE") if predictions else "UNAVAILABLE"

    # Query comprehensive source-level freshness
    source_tracker = SourceFreshnessTracker()
    freshness_report = await source_tracker.get_all_freshness(db=db)
    tracked_sources = freshness_report.get("sources", {})

    # Construct Prediction Provenance from tracked sources and latest DB batch timestamp
    pred_ts = predictions[0].get("prediction_timestamp") if predictions else None
    
    prediction_provenance = {
        "overall_data_status": freshness,
        "prediction_timestamp": pred_ts,
        "sources": {
            "gfw_context": {
                "status": tracked_sources.get("global_fishing_watch", {}).get("status", "UNAVAILABLE"),
                "observation_date": tracked_sources.get("global_fishing_watch", {}).get("data_timestamp"),
                "age_days": tracked_sources.get("global_fishing_watch", {}).get("age_days"),
            },
            "environmental": {
                "status": tracked_sources.get("open_meteo_marine", {}).get("status", "UNAVAILABLE"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "data_timestamp": tracked_sources.get("open_meteo_marine", {}).get("data_timestamp"),
                "age_minutes": tracked_sources.get("open_meteo_marine", {}).get("age_minutes"),
            },
            "incois_pfz": {
                "status": tracked_sources.get("incois_pfz", {}).get("status", pfz_data.get("status", "UNAVAILABLE")),
                "advisory_date": tracked_sources.get("incois_pfz", {}).get("data_timestamp") or pfz_data.get("advisory_date"),
                "valid_until": tracked_sources.get("incois_pfz", {}).get("valid_until"),
                "age_minutes": tracked_sources.get("incois_pfz", {}).get("age_minutes"),
            },
            "marine_safety": {
                "overall_status": overall_safety,
                "imd_status": tracked_sources.get("imd_marine_warnings", {}).get("status", "UNAVAILABLE"),
                "data_timestamp": tracked_sources.get("imd_marine_warnings", {}).get("data_timestamp"),
                "valid_until": tracked_sources.get("imd_marine_warnings", {}).get("valid_until"),
                "independent_of_ml": True,
            }
        }
    }

    return {
        "metadata": {
            "application": "MatsyaAI Maharashtra",
            "model_version": "Phase3_XGBoost_v1",
            "prediction_timestamp": pred_ts or datetime.now(timezone.utc).isoformat(),
            "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
            "data_freshness_status": freshness,
            "demo_mode": pipeline.demo_mode or demo,
            "data_sources": {
                "gfw": {
                    "provider": "Global Fishing Watch (GFW 4Wings Report API)",
                    "status": "DEMO_OFFLINE" if (demo or pipeline.demo_mode) else tracked_sources.get("global_fishing_watch", {}).get("status", "CACHED_HISTORICAL"),
                    "dataset": "public-global-fishing-effort:latest",
                    "temporal_basis": "Causal historical trailing effort up to prediction time T",
                    "data_timestamp": tracked_sources.get("global_fishing_watch", {}).get("data_timestamp"),
                    "age_days": tracked_sources.get("global_fishing_watch", {}).get("age_days"),
                },
                "environmental": {
                    "provider": "Open-Meteo Current Marine & Forecast API",
                    "status": tracked_sources.get("open_meteo_marine", {}).get("status", freshness),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "data_timestamp": tracked_sources.get("open_meteo_marine", {}).get("data_timestamp"),
                    "age_minutes": tracked_sources.get("open_meteo_marine", {}).get("age_minutes"),
                    "variables": ["wave_height", "wave_period", "wave_direction", "swell_wave_height", "wind_speed_10m"],
                },
                "incois_pfz": {
                    "provider": "INCOIS (Indian National Centre for Ocean Information Services)",
                    "status": tracked_sources.get("incois_pfz", {}).get("status", pfz_data.get("status", "UNAVAILABLE")),
                    "advisory_date": tracked_sources.get("incois_pfz", {}).get("data_timestamp") or pfz_data.get("advisory_date"),
                    "valid_until": tracked_sources.get("incois_pfz", {}).get("valid_until"),
                    "age_minutes": tracked_sources.get("incois_pfz", {}).get("age_minutes"),
                },
                "marine_safety": {
                    "provider": "IMD / INCOIS Official Marine Weather Guidelines",
                    "status": overall_safety,
                    "imd_status": tracked_sources.get("imd_marine_warnings", {}).get("status", "UNAVAILABLE"),
                    "data_timestamp": tracked_sources.get("imd_marine_warnings", {}).get("data_timestamp"),
                    "valid_until": tracked_sources.get("imd_marine_warnings", {}).get("valid_until"),
                    "independent_of_ml": True,
                },
            },
            "disclaimer": (
                "Predictions indicate apparent fishing activity derived from historical vessel tracking patterns. "
                "Matsya AI does NOT predict fish presence, biomass, species abundance, or guaranteed catch. "
                "Safety status is determined independently of ML predictions."
            ),
        },
        "marine_safety": {
            "overall_status": overall_safety,
            "message": safety_message,
            "independent_of_ml": True,
            "authority": "IMD / INCOIS Official Marine Weather Guidelines",
        },

        "source_freshness": tracked_sources,
        "prediction_provenance": prediction_provenance,
        "predictions": predictions,
        "pfz_advisory": pfz_data,
        "landing_centres": LANDING_CENTRE_METADATA,
    }
