"""
Tests for Offline Expedition Mode: landing centres, routing, package builder, sync.
"""

import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from backend.app.core.database import async_session
from backend.app.core.landing_centres import LANDING_CENTRES, get_landing_centre
from backend.app.main import app
from backend.app.models.expedition import CatchRecord, Expedition, ExpeditionTrackPoint, FieldObservation
from backend.app.services.expedition import package_builder
from backend.app.services.expedition.forecast import select_forecast_points
from backend.app.services.expedition.routing import (
    build_route,
    haversine_km,
    initial_bearing_deg,
    intermediate_point,
    is_on_land,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _fake_forecast(valid_until: str):
    async def _f(waypoints, timeout=20.0):
        return {
            "status": "LIVE", "provider": "test", "retrieved_at": "2026-01-01T00:00:00+00:00",
            "valid_from": "2026-01-01T00:00:00Z", "valid_until": valid_until,
            "points": [{"waypoint_index": 0, "latitude": waypoints[0]["latitude"],
                        "longitude": waypoints[0]["longitude"], "hourly": {"time": []}}],
            "error": None,
        }
    return _f


# ---------------------------------------------------------------------------
# Landing centres
# ---------------------------------------------------------------------------
def test_landing_centre_ids_unique_and_lookup():
    ids = [lc.id for lc in LANDING_CENTRES]
    assert len(ids) == len(set(ids))
    assert get_landing_centre("mirkarwada").district == "Ratnagiri"
    assert get_landing_centre("nope") is None


def test_landing_centres_are_coastal():
    """Every landing centre must have open sea within 3 km (land mask ~1 km resolution)."""
    for lc in LANDING_CENTRES:
        near_sea = False
        for r_km in (0.5, 1.0, 2.0, 3.0):
            for brg in range(0, 360, 15):
                d = r_km / 111.0
                lat = lc.latitude + d * math.cos(math.radians(brg))
                lon = lc.longitude + d * math.sin(math.radians(brg)) / math.cos(math.radians(lc.latitude))
                if not is_on_land(lat, lon):
                    near_sea = True
                    break
            if near_sea:
                break
        assert near_sea, f"{lc.name} has no sea within 3 km — coordinates likely wrong"


def test_mirkarwada_coordinates_fixed():
    """Regression: old map.py list placed Mirkarwada at 18.25N (~140 km off)."""
    lc = get_landing_centre("mirkarwada")
    assert 16.8 < lc.latitude < 17.2


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
def test_haversine_and_bearing_known_values():
    # One degree of latitude ~ 111.2 km, due north
    assert abs(haversine_km(18.0, 72.0, 19.0, 72.0) - 111.2) < 0.5
    assert abs(initial_bearing_deg(18.0, 72.0, 19.0, 72.0) - 0.0) < 0.01
    assert abs(initial_bearing_deg(18.0, 72.0, 18.0, 71.0) - 270.0) < 0.5


def test_intermediate_point_endpoints():
    assert intermediate_point(18.0, 72.0, 17.0, 71.0, 0.0) == pytest.approx((18.0, 72.0))
    assert intermediate_point(18.0, 72.0, 17.0, 71.0, 1.0) == pytest.approx((17.0, 71.0))


def test_route_to_open_sea_is_navigable():
    lc = get_landing_centre("mirkarwada")
    route = build_route({"latitude": lc.latitude, "longitude": lc.longitude, "name": lc.name},
                        {"latitude": 16.9, "longitude": 72.8, "name": "Offshore"})
    assert route["warnings"] == []
    assert route["is_navigable_direct"] is True
    assert route["waypoints"][0]["name"] == "Mirkarwada"
    assert route["waypoints"][-1]["name"] == "Offshore"
    assert 225 < route["initial_bearing_deg"] < 290  # roughly west
    assert route["distance_km"] > 40


def test_route_across_land_is_flagged():
    # Satpati (Palghar) to a point inland near Nashik
    lc = get_landing_centre("satpati")
    route = build_route({"latitude": lc.latitude, "longitude": lc.longitude},
                        {"latitude": 19.9, "longitude": 73.7})
    assert "ROUTE_CROSSES_LAND" in route["warnings"]
    assert "DESTINATION_ON_LAND" in route["warnings"]
    assert route["is_navigable_direct"] is False


def test_forecast_point_selection_keeps_ends():
    wps = [{"index": i, "latitude": 0, "longitude": 0} for i in range(20)]
    pts = select_forecast_points(wps)
    assert len(pts) <= 6
    assert pts[0]["index"] == 0 and pts[-1]["index"] == 19


# ---------------------------------------------------------------------------
# Package builder (no DB)
# ---------------------------------------------------------------------------
async def test_package_builder_without_db_never_claims_live_data():
    lc = get_landing_centre("malvan")
    with patch.object(package_builder, "fetch_route_forecast", _fake_forecast("2026-01-03T23:00Z")):
        pkg = await package_builder.build_package(
            db=None, device_id="device-test-1", landing_centre=lc,
            destination={"latitude": 16.0, "longitude": 73.1},
        )
    for section in ("manifest", "landing_centre", "destination", "route", "emergency_returns",
                    "pfz", "warnings", "forecast", "predictions", "safety_rules", "offline_assets"):
        assert section in pkg
    assert pkg["warnings"]["status"] == "UNAVAILABLE"
    assert pkg["predictions"]["status"] == "UNAVAILABLE"
    assert pkg["pfz"]["status"] == "UNAVAILABLE"
    # Only the forecast had an expiry, so it bounds the package
    assert pkg["manifest"]["valid_until"].startswith("2026-01-03T23:00")
    assert pkg["emergency_returns"][0]["id"] == "malvan"
    assert pkg["offline_assets"]["nautical_charts"]["available"] is False


async def test_package_valid_until_is_earliest_expiry():
    assert package_builder.earliest(
        "2026-01-05T00:00:00+00:00", None, "2026-01-02T06:00:00Z", "2026-01-03T00:00:00+00:00"
    ).startswith("2026-01-02T06:00")


async def test_resolve_destination_pfz_index_out_of_range():
    with pytest.raises(ValueError):
        package_builder.resolve_destination(None, 5, {"locations": []})


# ---------------------------------------------------------------------------
# API (real DB)
# ---------------------------------------------------------------------------
async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_api_landing_centres():
    async with await _client() as c:
        r = await c.get("/api/v1/expedition/landing-centres")
    assert r.status_code == 200
    assert len(r.json()["landing_centres"]) == len(LANDING_CENTRES)


async def test_api_package_validation():
    async with await _client() as c:
        r = await c.post("/api/v1/expedition/packages", json={
            "device_id": "device-test-1", "landing_centre_id": "malvan"})
        assert r.status_code == 422  # no destination
        r = await c.post("/api/v1/expedition/packages", json={
            "device_id": "device-test-1", "landing_centre_id": "atlantis",
            "destination": {"latitude": 16.0, "longitude": 73.0}})
        assert r.status_code == 404


async def test_api_package_and_idempotent_sync():
    device_id = f"test-{uuid.uuid4()}"
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:00Z")
    with patch.object(package_builder, "fetch_route_forecast", _fake_forecast(future)):
        async with await _client() as c:
            r = await c.post("/api/v1/expedition/packages", json={
                "device_id": device_id, "landing_centre_id": "mirkarwada",
                "destination": {"latitude": 16.9, "longitude": 72.8}})
            assert r.status_code == 200, r.text
            pkg = r.json()
            exp_id = pkg["manifest"]["package_id"]

            now = datetime.now(timezone.utc).isoformat()
            body = {
                "device_id": device_id, "expedition_id": exp_id, "include_delta": False,
                "track_points": [{"client_uuid": str(uuid.uuid4()), "recorded_at": now,
                                  "latitude": 16.95, "longitude": 73.1, "speed_mps": 3.2}],
                "catches": [{"client_uuid": str(uuid.uuid4()), "recorded_at": now,
                             "latitude": 16.9, "longitude": 72.8, "species": "Pomfret", "weight_kg": 12.5}],
                "observations": [{"client_uuid": str(uuid.uuid4()), "recorded_at": now,
                                  "observation_type": "sea_state", "value": "moderate"}],
            }
            r1 = await c.post("/api/v1/expedition/sync", json=body)
            r2 = await c.post("/api/v1/expedition/sync", json=body)  # retry: must not duplicate
            wrong = await c.post("/api/v1/expedition/sync", json={**body, "device_id": "someone-else"})

    try:
        assert r1.status_code == 200, r1.text
        assert r1.json()["inserted"] == {"track_points": 1, "catches": 1, "observations": 1}
        assert r2.status_code == 200
        assert r2.json()["inserted"] == {"track_points": 0, "catches": 0, "observations": 0}
        assert r2.json()["duplicates"] == {"track_points": 1, "catches": 1, "observations": 1}
        assert wrong.status_code == 404

        async with async_session() as db:
            n = (await db.execute(select(func.count()).select_from(CatchRecord)
                                  .where(CatchRecord.expedition_id == exp_id))).scalar_one()
            assert n == 1
    finally:
        async with async_session() as db:
            for model in (ExpeditionTrackPoint, CatchRecord, FieldObservation):
                await db.execute(delete(model).where(model.expedition_id == exp_id))
            await db.execute(delete(Expedition).where(Expedition.id == exp_id))
            await db.commit()
