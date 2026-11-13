"""
MatsyaAI Maharashtra — Predictions API Endpoint.

Exposes Phase 4 ML predictions for next-calendar-day apparent fishing activity
over HTTP with strict independent safety decoupling.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.core.database import get_db
from backend.app.models.prediction import Prediction
from backend.app.ml.inference import get_inference_pipeline
from backend.app.ml.dataset_builder import _LANDING_CENTRES, _haversine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["Predictions"])


async def fetch_latest_persisted_predictions(db: Session, demo_mode: bool) -> List[Dict[str, Any]]:
    """
    Fetches the latest prediction batch from the database and formats it
    for the API response to maintain full contract compatibility.
    """
    try:
        # Get latest prediction timestamp
        stmt_ts = select(Prediction.prediction_timestamp).order_by(Prediction.prediction_timestamp.desc()).limit(1)
        res_ts = await db.execute(stmt_ts)
        latest_ts = res_ts.scalar_one_or_none()

        if not latest_ts:
            return []

        # Fetch the entire batch for that timestamp
        stmt_preds = select(Prediction).where(Prediction.prediction_timestamp == latest_ts)
        res_preds = await db.execute(stmt_preds)
        records = res_preds.scalars().all()
        
        pipeline = get_inference_pipeline()
        metadata = pipeline._metadata or {}
        decision_thresh = float(pipeline._threshold_info.get("decision_threshold", 0.47)) if pipeline._threshold_info else 0.47
        disclaimer = metadata.get(
            "disclaimer",
            "Predicts apparent fishing activity derived from historical GFW AIS patterns. "
            "Does not predict fish presence, biomass, species, or catch guarantee."
        )

        # Freshness checking for the batch
        now = datetime.now(timezone.utc)
        batch_age_hours = (now - latest_ts.astimezone(timezone.utc)).total_seconds() / 3600.0
        data_freshness_status = "STALE" if batch_age_hours > 24 else "LIVE"

        results = []
        for r in records:
            # Stale predictions cannot convey safe conditions
            final_safety_status = "NO_WARNING_DATA" if data_freshness_status == "STALE" else r.safety_status
            # Reconstruct dynamic properties
            dist = min(
                _haversine(r.latitude, r.longitude, lc[0], lc[1])
                for lc in _LANDING_CENTRES
            )
            is_coastal = 1.0 if dist <= 50.0 else 0.0
            
            results.append({
                "grid_cell_id": f"cell_{r.latitude:.2f}_{r.longitude:.2f}_0.25",
                "latitude": r.latitude,
                "longitude": r.longitude,
                "distance_to_coast_km": round(dist, 2),
                "is_coastal": bool(is_coastal),
                "predicted_apparent_fishing_probability": round(r.prediction_probability, 4),
                "predicted_apparent_fishing_binary": r.prediction_class,
                "prediction_label": r.prediction_label,
                "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
                "decision_threshold": decision_thresh,
                "model_version": r.model_version,
                "prediction_timestamp": r.prediction_timestamp.isoformat(),
                "data_freshness_status": data_freshness_status,
                "disclaimer": disclaimer,
                "current_wave_height_m": None, # Not persisted in DB prediction row
                "current_wind_speed_kmh": None, # Not persisted in DB prediction row
                "safety_status": final_safety_status,
                "safety_override": r.safety_override,
            })
            
        return results
    except Exception as e:
        logger.error(f"Error fetching persisted predictions: {e}")
        return []


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/latest", response_model=List[Dict[str, Any]])
async def get_current_predictions(
    demo: bool = Query(False, description="Enable DEMO mode with cached real data fallback"),
    db: Session = Depends(get_db)
):
    """
    Get latest predicted apparent fishing activity for all Maharashtra grid cells.
    Reads exclusively from the persisted scheduled batch in PostgreSQL.
    """
    try:
        predictions = await fetch_latest_persisted_predictions(db, demo)
        return predictions
    except Exception as e:
        logger.error(f"Prediction retrieval failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Prediction retrieval error: {str(e)}"
        )
