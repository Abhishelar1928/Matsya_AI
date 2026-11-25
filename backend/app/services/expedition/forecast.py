"""
MatsyaAI Maharashtra — Route forecast for Offline Expedition packages.

Fetches 72 h of hourly marine (waves/swell) and weather (wind) forecasts from
Open-Meteo for a small set of points along the route. If the fetch fails the
section is returned as UNAVAILABLE — values are never fabricated.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_VARS = (
    "wave_height,wave_period,wave_direction,swell_wave_height,"
    "swell_wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature"
)
WEATHER_VARS = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
FORECAST_DAYS = 3
MAX_POINTS = 6


def select_forecast_points(waypoints: List[Dict]) -> List[Dict]:
    """Evenly pick up to MAX_POINTS waypoints, always including start and destination."""
    if len(waypoints) <= MAX_POINTS:
        return waypoints
    step = (len(waypoints) - 1) / (MAX_POINTS - 1)
    idx = sorted({round(i * step) for i in range(MAX_POINTS)})
    return [waypoints[i] for i in idx]


def _as_list(payload: Any) -> List[Dict]:
    return payload if isinstance(payload, list) else [payload]


def _normalize_current_mps(speeds: List[Any], unit: str) -> List[Any]:
    factor = (1.0 / 3.6) if unit.lower() in ("km/h", "kmh") else 1.0
    return [None if s is None else round(float(s) * factor, 4) for s in speeds]


def _uv_components(speeds_mps: List[Any], dirs: List[Any]) -> tuple[List[Any], List[Any]]:
    u_list: List[Any] = []
    v_list: List[Any] = []
    for spd, deg in zip(speeds_mps, dirs):
        if spd is None or deg is None:
            u_list.append(None)
            v_list.append(None)
        else:
            rad = math.radians(float(deg))
            u_list.append(round(float(spd) * math.sin(rad), 4))
            v_list.append(round(float(spd) * math.cos(rad), 4))
    return u_list, v_list


def _merge(points: List[Dict], marine: List[Dict], weather: List[Dict]) -> List[Dict]:
    out = []
    for i, pt in enumerate(points):
        m_item = marine[i] if i < len(marine) else {}
        m = m_item.get("hourly", {}) or {}
        m_units = m_item.get("hourly_units", {}) or {}
        w = (weather[i] if i < len(weather) else {}).get("hourly", {}) or {}
        times = m.get("time") or w.get("time") or []
        curr_unit = str(m_units.get("ocean_current_velocity") or "km/h")
        curr_spd = _normalize_current_mps(m.get("ocean_current_velocity", []), curr_unit)
        curr_dir = m.get("ocean_current_direction", [])
        u_mps, v_mps = _uv_components(curr_spd, curr_dir)
        out.append({
            "waypoint_index": pt.get("index"),
            "latitude": pt["latitude"],
            "longitude": pt["longitude"],
            "hourly": {
                "time": [f"{t}Z" if not t.endswith("Z") else t for t in times],
                "wave_height_m": m.get("wave_height", []),
                "wave_period_s": m.get("wave_period", []),
                "wave_direction_deg": m.get("wave_direction", []),
                "swell_wave_height_m": m.get("swell_wave_height", []),
                "swell_wave_period_s": m.get("swell_wave_period", []),
                "ocean_current_velocity_mps": curr_spd,
                "ocean_current_direction_deg": curr_dir,
                "ocean_current_u_mps": u_mps,
                "ocean_current_v_mps": v_mps,
                "sea_surface_temperature_c": m.get("sea_surface_temperature", []),
                "wind_speed_kmh": w.get("wind_speed_10m", []),
                "wind_direction_deg": w.get("wind_direction_10m", []),
                "wind_gusts_kmh": w.get("wind_gusts_10m", []),
            },
        })
    return out


async def fetch_route_forecast(waypoints: List[Dict], timeout: float = 20.0) -> Dict[str, Any]:
    points = select_forecast_points(waypoints)
    retrieved_at = datetime.now(timezone.utc)
    common = {
        "latitude": ",".join(str(p["latitude"]) for p in points),
        "longitude": ",".join(str(p["longitude"]) for p in points),
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "MatsyaAI/1.0"}) as client:
            marine_res = await client.get(MARINE_URL, params={**common, "hourly": MARINE_VARS})
            weather_res = await client.get(WEATHER_URL, params={**common, "hourly": WEATHER_VARS, "wind_speed_unit": "kmh"})
        marine_res.raise_for_status()
        weather_res.raise_for_status()
        series = _merge(points, _as_list(marine_res.json()), _as_list(weather_res.json()))
    except Exception as e:
        logger.warning(f"Route forecast fetch failed: {e}")
        return {
            "status": "UNAVAILABLE",
            "provider": "Open-Meteo Marine & Forecast API",
            "retrieved_at": retrieved_at.isoformat(),
            "valid_from": None,
            "valid_until": None,
            "points": [],
            "error": str(e),
        }

    times = series[0]["hourly"]["time"] if series and series[0]["hourly"]["time"] else []
    return {
        "status": "LIVE" if times else "UNAVAILABLE",
        "provider": "Open-Meteo Marine & Forecast API",
        "retrieved_at": retrieved_at.isoformat(),
        "valid_from": times[0] if times else None,
        "valid_until": times[-1] if times else None,
        "points": series,
        "error": None if times else "Empty forecast response",
    }
