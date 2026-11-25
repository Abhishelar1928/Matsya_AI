"""
MatsyaAI Maharashtra — Expedition routing.

v1 builds a direct great-circle route from a landing centre to the chosen
destination and flags any leg that crosses land (using ``global_land_mask``,
~1 km resolution). It does NOT auto-route around land; a flagged route tells
the fisherman to plan the passage themselves.

This is decision support, not a navigational chart.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from global_land_mask import globe

EARTH_RADIUS_KM = 6371.0088

# Landing centres sit on the coastline, and the land mask is ~1 km resolution,
# so samples within this distance of the start/end are not treated as land crossings.
HARBOUR_EXCLUSION_KM = 3.0
LAND_SAMPLE_STEP_KM = 0.5
WAYPOINT_SPACING_KM = 10.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def intermediate_point(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> Tuple[float, float]:
    """Point at ``fraction`` (0..1) along the great circle between two points."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = haversine_km(lat1, lon1, lat2, lon2) / EARTH_RADIUS_KM
    if d == 0:
        return lat1, lon1
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def compass_point(bearing: float) -> str:
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return points[int((bearing % 360) / 22.5 + 0.5) % 16]


def is_on_land(lat: float, lon: float) -> bool:
    return bool(globe.is_land(lat, lon))


def find_land_crossings(lat1: float, lon1: float, lat2: float, lon2: float) -> List[Dict[str, float]]:
    """Sample the great circle and return land points outside the harbour exclusion zones."""
    total = haversine_km(lat1, lon1, lat2, lon2)
    if total == 0:
        return []
    steps = max(1, int(total / LAND_SAMPLE_STEP_KM))
    crossings = []
    for i in range(steps + 1):
        f = i / steps
        along = f * total
        if along < HARBOUR_EXCLUSION_KM or (total - along) < HARBOUR_EXCLUSION_KM:
            continue
        lat, lon = intermediate_point(lat1, lon1, lat2, lon2, f)
        if is_on_land(lat, lon):
            crossings.append({"latitude": round(lat, 5), "longitude": round(lon, 5), "km_from_start": round(along, 2)})
    return crossings


def build_route(start: Dict, destination: Dict) -> Dict:
    """
    Build a direct route.

    ``start``/``destination`` are dicts with ``latitude``/``longitude`` (and optional ``name``).
    """
    lat1, lon1 = start["latitude"], start["longitude"]
    lat2, lon2 = destination["latitude"], destination["longitude"]
    total = haversine_km(lat1, lon1, lat2, lon2)
    bearing = initial_bearing_deg(lat1, lon1, lat2, lon2)

    n_legs = max(1, math.ceil(total / WAYPOINT_SPACING_KM))
    waypoints = []
    for i in range(n_legs + 1):
        lat, lon = intermediate_point(lat1, lon1, lat2, lon2, i / n_legs)
        waypoints.append({
            "index": i,
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "km_from_start": round(total * i / n_legs, 2),
            "name": start.get("name") if i == 0 else (destination.get("name") if i == n_legs else None),
        })

    crossings = find_land_crossings(lat1, lon1, lat2, lon2)
    destination_on_land = is_on_land(lat2, lon2)

    warnings = []
    if destination_on_land:
        warnings.append("DESTINATION_ON_LAND")
    if crossings:
        warnings.append("ROUTE_CROSSES_LAND")

    return {
        "type": "DIRECT_GREAT_CIRCLE",
        "distance_km": round(total, 2),
        "distance_nm": round(total / 1.852, 2),
        "initial_bearing_deg": round(bearing, 1),
        "initial_bearing_compass": compass_point(bearing),
        "waypoints": waypoints,
        "land_crossings": crossings[:20],
        "warnings": warnings,
        "is_navigable_direct": not warnings,
        "is_direct_reference_only": True,
        "coverage_disclosures": [
            "Great-circle path is a direct-distance reference only, NOT a safe navigable route.",
            "Land check uses ~1 km global_land_mask with a 3 km harbour exclusion; narrow reefs, shoals, wrecks, and shallow water are not checked.",
        ],
        "disclaimer": "Direct great-circle reference only. NOT a safe navigable route or nautical chart; verify passage against official charts and local knowledge.",
    }
