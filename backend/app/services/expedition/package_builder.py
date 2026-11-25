"""
MatsyaAI Maharashtra — Offline Expedition package builder.

Assembles everything a fisherman needs at sea without connectivity into one
JSON document. Every time-sensitive section carries its own issue/expiry
timestamps; the manifest ``valid_until`` is the EARLIEST of those expiries.

Safety principle (from backend/app/ml/safety_gate.py): missing or expired data
must never be presented as safe. The client re-evaluates safety from the
packaged warnings/forecast and falls back to NO_WARNING_DATA after expiry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from backend.app.core.landing_centres import LANDING_CENTRES, LandingCentreInfo
from backend.app.ml.config import (
    SAFETY_WAVE_HEIGHT_THRESHOLD,
    SAFETY_WIND_SPEED_THRESHOLD,
)
from backend.app.models.marine_warning import MarineWarning
from backend.app.services.expedition.forecast import fetch_route_forecast
from backend.app.services.expedition.routing import build_route, haversine_km, initial_bearing_deg, compass_point
from backend.app.services.pfz_query import get_latest_pfz_batch

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2
PACKAGE_VERSION = "2.0.0"
PREDICTION_VALIDITY = timedelta(hours=24)

SPECIES_CATALOGUE: List[Dict[str, str]] = [
    {"id": "pomfret_silver", "en": "Silver Pomfret", "mr": "पापलेट (सफेद)", "scientific": "Pampus argenteus", "category": "pelagic"},
    {"id": "pomfret_black", "en": "Black Pomfret", "mr": "हलवा", "scientific": "Parastromateus niger", "category": "pelagic"},
    {"id": "bombay_duck", "en": "Bombay Duck", "mr": "बोंबील", "scientific": "Harpadon nehereus", "category": "pelagic"},
    {"id": "mackerel", "en": "Indian Mackerel", "mr": "बांगडा", "scientific": "Rastrelliger kanagurta", "category": "pelagic"},
    {"id": "sardine", "en": "Oil Sardine", "mr": "तारली", "scientific": "Sardinella longiceps", "category": "pelagic"},
    {"id": "prawn", "en": "Prawn / Shrimp", "mr": "कोळंबी", "scientific": "Penaeus / Metapenaeus spp.", "category": "crustacean"},
    {"id": "surmai", "en": "Kingfish / Surmai", "mr": "सुरमई", "scientific": "Scomberomorus commerson", "category": "pelagic"},
    {"id": "rawas", "en": "Indian Salmon (Rawas)", "mr": "रावस", "scientific": "Eleutheronema tetradactylum", "category": "demersal"},
    {"id": "ghol", "en": "Blackspotted Croaker (Ghol)", "mr": "घोळ", "scientific": "Protonibea diacanthus", "category": "demersal"},
    {"id": "koth", "en": "Croaker (Koth / Dhoma)", "mr": "ढोमा / कोथ", "scientific": "Otolithoides biauritus", "category": "demersal"},
    {"id": "squid", "en": "Squid", "mr": "माकूळ", "scientific": "Uroteuthis duvaucelii", "category": "cephalopod"},
    {"id": "cuttlefish", "en": "Cuttlefish", "mr": "गोट्या माकूळ", "scientific": "Sepia pharaonis", "category": "cephalopod"},
    {"id": "tuna", "en": "Yellowfin / Skipjack Tuna", "mr": "कुपा", "scientific": "Thunnus / Katsuwonus spp.", "category": "pelagic"},
    {"id": "ribbonfish", "en": "Ribbonfish", "mr": "वागटी / बाला", "scientific": "Trichiurus lepturus", "category": "demersal"},
    {"id": "lobster", "en": "Spiny Lobster", "mr": "शेवंड", "scientific": "Panulirus polyphagus", "category": "crustacean"},
    {"id": "other", "en": "Other / Mixed Catch", "mr": "इतर", "scientific": "Unclassified", "category": "other"},
]


def _canonical_for_hash(val: Any) -> Any:
    if isinstance(val, list):
        return [_canonical_for_hash(x) for x in val]
    if isinstance(val, dict):
        return {k: _canonical_for_hash(v) for k, v in val.items()}
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return val


def _sha256_canonical(val: Any) -> str:
    encoded = json.dumps(
        _canonical_for_hash(val),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

OFFLINE_ASSETS_DIR = Path(__file__).resolve().parents[3] / "static" / "offline"
OFFLINE_ASSETS_URL = "/api/v1/offline-assets"
BASEMAP_FILE = "maharashtra-coast.pmtiles"
BATHYMETRY_FILE = "bathymetry-contours.geojson"
MPA_FILE = "marine-protected-areas.geojson"
OFFSHORE_FILE = "offshore-installations.geojson"
SHIPPING_FILE = "shipping-lanes.geojson"
CURRENTS_FILE = "ocean-currents-latest.geojson"

# Maharashtra coastal bounding box (matches ml/config grid, padded)
REGION_BBOX = {"min_lat": 15.0, "max_lat": 20.6, "min_lon": 71.0, "max_lon": 74.2}

DISCLAIMERS = [
    "Decision support only. Not a navigational chart. Always follow official IMD/INCOIS advisories and port signals.",
    "Predictions show apparent fishing activity from historical vessel tracking. They do NOT predict fish presence, catch, or safety.",
    "Safety cannot be confirmed once warning or forecast data has expired.",
]


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def resolve_destination(destination: Optional[Dict], pfz_index: Optional[int], pfz: Dict) -> Dict:
    if destination is not None:
        return {"latitude": float(destination["latitude"]), "longitude": float(destination["longitude"]),
                "name": destination.get("name") or "Selected point", "source": "USER_SELECTED"}
    if pfz_index is not None:
        locs = pfz.get("locations", [])
        if not 0 <= pfz_index < len(locs):
            raise ValueError(f"pfz_index {pfz_index} out of range (0..{len(locs) - 1})")
        loc = locs[pfz_index]
        return {"latitude": loc["latitude"], "longitude": loc["longitude"],
                "name": f"INCOIS PFZ ({loc['landing_centre']} {loc['direction']})", "source": "INCOIS_PFZ",
                "pfz_index": pfz_index}
    raise ValueError("Either destination or pfz_index is required")


def build_emergency_returns(destination: Dict, route: Dict) -> List[Dict]:
    mid = route["waypoints"][len(route["waypoints"]) // 2]
    out = []
    for lc in LANDING_CENTRES:
        d_dest = haversine_km(destination["latitude"], destination["longitude"], lc.latitude, lc.longitude)
        brg = initial_bearing_deg(destination["latitude"], destination["longitude"], lc.latitude, lc.longitude)
        out.append({
            "id": lc.id, "name": lc.name, "name_mr": lc.name_mr, "district": lc.district,
            "latitude": lc.latitude, "longitude": lc.longitude, "verified": lc.verified,
            "distance_from_destination_km": round(d_dest, 2),
            "bearing_from_destination_deg": round(brg, 1),
            "bearing_from_destination_compass": compass_point(brg),
            "distance_from_route_midpoint_km": round(
                haversine_km(mid["latitude"], mid["longitude"], lc.latitude, lc.longitude), 2),
        })
    out.sort(key=lambda r: r["distance_from_destination_km"])
    return out


async def get_active_warnings(db: Optional[Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    base = {"status": "UNAVAILABLE", "source": "IMD Mumbai Fishermen Warning Bulletin",
            "issued_at": None, "valid_until": None, "items": []}
    if db is None:
        return base
    try:
        stmt = select(MarineWarning).where(MarineWarning.valid_until >= now).order_by(MarineWarning.valid_from)
        rows = (await db.execute(stmt)).scalars().all()
    except Exception as e:
        logger.warning(f"Failed to query marine warnings: {e}")
        return base
    if not rows:
        return {**base, "status": "NO_ACTIVE_BULLETIN"}
    items = [{
        "warning_type": r.warning_type,
        "severity": r.severity,
        "description": r.description,
        "valid_from": _iso(r.valid_from),
        "valid_until": _iso(r.valid_until),
        "issued_at": _iso(r.source_timestamp),
        "source_name": r.source_name,
    } for r in rows]
    return {
        **base,
        "status": "LIVE",
        "issued_at": _iso(max(r.source_timestamp for r in rows)),
        "valid_until": _iso(max(r.valid_until for r in rows)),
        "items": items,
    }


async def get_compact_predictions(db: Optional[Any]) -> Dict[str, Any]:
    from backend.app.api.v1.predictions import fetch_latest_persisted_predictions

    preds = await fetch_latest_persisted_predictions(db, False) if db is not None else []
    if not preds:
        return {"status": "UNAVAILABLE", "model_version": None, "prediction_timestamp": None,
                "valid_until": None, "cells": []}
    ts = _parse(preds[0]["prediction_timestamp"])
    return {
        "status": preds[0].get("data_freshness_status", "UNKNOWN"),
        "model_version": preds[0].get("model_version"),
        "prediction_timestamp": _iso(ts),
        "valid_until": _iso(ts + PREDICTION_VALIDITY) if ts else None,
        "target_interpretation": preds[0].get("target_interpretation"),
        "decision_threshold": preds[0].get("decision_threshold"),
        "grid_resolution_deg": 0.25,
        "cells": [{
            "lat": p["latitude"], "lon": p["longitude"],
            "p": p["predicted_apparent_fishing_probability"],
            "high": p["predicted_apparent_fishing_binary"],
        } for p in preds],
        "disclaimer": DISCLAIMERS[1],
    }


def safety_rules() -> Dict[str, Any]:
    return {
        "wave_height_threshold_m": SAFETY_WAVE_HEIGHT_THRESHOLD,
        "wind_speed_threshold_kmh": SAFETY_WIND_SPEED_THRESHOLD,
        "severe_severities": ["SEVERE", "VERY_SEVERE", "EXTREMELY_SEVERE"],
        "caution_severities": ["MODERATE", "CAUTION", "WARNING", "ROUGH_SEA"],
        "normal_severities": ["NONE", "NORMAL", "NIL", "ALL_CLEAR", "SAFE"],
        "statuses": ["UNSAFE", "CAUTION", "SAFE_CONFIRMED", "NO_WARNING_DATA"],
        "rule": "Mirror of backend SafetyGate: severe warning => UNSAFE; caution warning or threshold exceeded "
                "=> CAUTION; active normal bulletin + env data within thresholds => SAFE_CONFIRMED; "
                "otherwise (incl. expired data) => NO_WARNING_DATA.",
    }


def offline_assets() -> Dict[str, Any]:
    def asset(name: str, kind: str, note: str) -> Dict[str, Any]:
        path = OFFLINE_ASSETS_DIR / name
        return {
            "kind": kind,
            "url": f"{OFFLINE_ASSETS_URL}/{name}",
            "available": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "note": note,
        }
    return {
        "basemap": asset(BASEMAP_FILE, "pmtiles-vector", "OpenStreetMap contributors (ODbL). Not a nautical chart."),
        "bathymetry": asset(BATHYMETRY_FILE, "geojson-contours", "GEBCO general-purpose bathymetry (10/20/50/100/200 m). NOT verified navigation depth."),
        "marine_protected_areas": asset(MPA_FILE, "geojson-polygons", "Verified public MPA boundaries (Malvan Marine Sanctuary)."),
        "offshore_installations": asset(OFFSHORE_FILE, "geojson-points", "Verified public offshore platform points where available."),
        "shipping_lanes": asset(SHIPPING_FILE, "geojson-lines", "OpenSeaMap seamark lanes where available (not official ENC)."),
        "ocean_currents": asset(CURRENTS_FILE, "geojson-vectors", "Coarse modeled surface currents (U/V) for drift estimation only."),
        "nautical_charts": {"kind": "enc", "available": False,
                            "note": "Official NHO charts not included (licensing)."},
        "bbox": REGION_BBOX,
    }


def earliest(*timestamps: Optional[str]) -> Optional[str]:
    parsed = [t for t in (_parse(x) for x in timestamps) if t is not None]
    return _iso(min(parsed)) if parsed else None


async def build_package(
    db: Optional[Any],
    device_id: str,
    landing_centre: LandingCentreInfo,
    origin: Optional[Dict] = None,
    destination: Optional[Dict] = None,
    pfz_index: Optional[int] = None,
    planned_departure: Optional[datetime] = None,
    planned_return: Optional[datetime] = None,
) -> Dict[str, Any]:
    created_at = datetime.now(timezone.utc)
    pfz = await get_latest_pfz_batch(db)
    dest = resolve_destination(destination, pfz_index, pfz)

    if origin is not None:
        start = {
            "latitude": float(origin["latitude"]),
            "longitude": float(origin["longitude"]),
            "name": origin.get("name") or "Current location",
        }
    else:
        start = {"latitude": landing_centre.latitude, "longitude": landing_centre.longitude, "name": landing_centre.name}
    route = build_route(start, dest)

    warnings = await get_active_warnings(db)
    forecast = await fetch_route_forecast(route["waypoints"])
    predictions = await get_compact_predictions(db)

    valid_until = earliest(
        warnings.get("valid_until"),
        forecast.get("valid_until"),
        predictions.get("valid_until"),
        pfz.get("validity_date"),
    )

    emergency_returns = build_emergency_returns(dest, route)
    rules = safety_rules()
    assets = offline_assets()
    created_iso = _iso(created_at)

    checksums = {
        "route": _sha256_canonical(route),
        "emergency_returns": _sha256_canonical(emergency_returns),
        "pfz": _sha256_canonical(pfz),
        "warnings": _sha256_canonical(warnings),
        "forecast": _sha256_canonical(forecast),
        "predictions": _sha256_canonical(predictions),
        "safety_rules": _sha256_canonical(rules),
    }

    package_id = str(uuid.uuid4())
    return {
        "manifest": {
            "schema_version": SCHEMA_VERSION,
            "version": PACKAGE_VERSION,
            "source": "MatsyaAI Maharashtra Expedition Builder",
            "package_id": package_id,
            "device_id": device_id,
            "created_at": created_iso,
            "generated_at": created_iso,
            "valid_from": created_iso,
            "valid_until": valid_until,
            "planned_departure": _iso(planned_departure),
            "planned_return": _iso(planned_return),
            "coverage": {**REGION_BBOX, "region": "Maharashtra Coast"},
            "component_versions": {
                "routing": "2",
                "safety_gate": "phase6-v2",
                "species_catalogue": "1",
                "predictions": str(predictions.get("model_version") or "unavailable"),
            },
            "checksums": checksums,
            "component_expiry": {
                "warnings": warnings.get("valid_until"),
                "forecast": forecast.get("valid_until"),
                "predictions": predictions.get("valid_until"),
                "pfz": pfz.get("validity_date"),
            },
            "disclaimers": DISCLAIMERS,
        },
        "landing_centre": landing_centre.to_dict(),
        "destination": dest,
        "route": route,
        "emergency_returns": emergency_returns,
        "pfz": pfz,
        "warnings": warnings,
        "forecast": forecast,
        "predictions": predictions,
        "safety_rules": rules,
        "species_catalogue": SPECIES_CATALOGUE,
        "offline_assets": assets,
    }
