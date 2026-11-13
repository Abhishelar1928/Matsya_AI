"""
MatsyaAI Maharashtra — Phase 5.3 Source Freshness & Health Tracking Test Suite.

Covers all 15 required verification scenarios:
1. Fresh INCOIS advisory (future valid_until -> LIVE)
2. Expired INCOIS advisory (past valid_until -> STALE)
3. Fresh IMD bulletin (future valid_until -> LIVE)
4. Expired IMD bulletin (past valid_until -> STALE)
5. IMD unavailable (empty DB -> UNAVAILABLE)
6. Open-Meteo fresh observation (<180 min -> LIVE)
7. Open-Meteo stale observation (>180 min -> STALE)
8. Historical GFW data (AIS latency -> CACHED_HISTORICAL, never LIVE)
9. GFW age calculation (age_days from observation_date)
10. Unavailable source behavior (db=None or empty -> UNAVAILABLE)
11. Error source resilience (DB exception -> ERROR status, non-crashing)
12. age_minutes calculation (measured against data_timestamp, NOT retrieved_at)
13. valid_until handling (expired validity strictly yields STALE)
14. API response structure (GET /api/v1/sources/freshness contract)
15. Map summary compatibility (GET /api/v1/map/summary contract preserved)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.freshness.source_tracker import (
    SourceFreshnessTracker,
    STATUS_LIVE,
    STATUS_STALE,
    STATUS_UNAVAILABLE,
    STATUS_CACHED_HISTORICAL,
    STATUS_ERROR,
    STATUS_AUTHENTICATED,
    STATUS_PUBLIC,
)
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.models.marine_warning import MarineWarning
from backend.app.models.ocean_observation import OceanObservation
from backend.app.models.gfw import GFWFishingEffort


@pytest.fixture
def tracker():
    return SourceFreshnessTracker()


def _mock_db_result(single_record=None, count=1):
    """Helper to build a mock DB session returning a given record and count."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    
    # scalars().first()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = single_record
    mock_result.scalars.return_value = mock_scalars
    
    # count scalar()
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = count
    
    mock_db.execute.side_effect = [mock_result, mock_count_result]
    return mock_db


# -----------------------------------------------------------------------------
# 1. Fresh INCOIS Advisory
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_fresh_incois_advisory(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    advisory_date = now - timedelta(hours=2)
    validity_date = now + timedelta(hours=22)
    retrieved_at = now - timedelta(minutes=15)

    rec = MagicMock(spec=INCOISPFZAdvisory)
    rec.id = 1
    rec.advisory_date = advisory_date
    rec.validity_date = validity_date
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=8)
    res = await tracker.check_incois_pfz(db=db, now=now)

    assert res["status"] == STATUS_LIVE
    assert res["data_timestamp"] == advisory_date.isoformat()
    assert res["valid_until"] == validity_date.isoformat()
    assert res["age_minutes"] == 120.0
    assert res["record_count"] == 8
    assert res["error"] is None


# -----------------------------------------------------------------------------
# 2. Expired INCOIS Advisory
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_2_expired_incois_advisory(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    # Advisory downloaded 5 minutes ago, but validity expired 1 hour ago
    advisory_date = now - timedelta(hours=25)
    validity_date = now - timedelta(hours=1)
    retrieved_at = now - timedelta(minutes=5)

    rec = MagicMock(spec=INCOISPFZAdvisory)
    rec.id = 1
    rec.advisory_date = advisory_date
    rec.validity_date = validity_date
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=5)
    res = await tracker.check_incois_pfz(db=db, now=now)

    # Must be STALE, not LIVE!
    assert res["status"] == STATUS_STALE
    assert res["valid_until"] == validity_date.isoformat()
    assert res["age_minutes"] == 25.0 * 60.0


# -----------------------------------------------------------------------------
# 3. Fresh IMD Bulletin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_3_fresh_imd_bulletin(tracker):
    now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    source_ts = now - timedelta(hours=3)
    valid_until = now + timedelta(hours=9)
    retrieved_at = now - timedelta(minutes=10)

    rec = MagicMock(spec=MarineWarning)
    rec.id = 1
    rec.source_name = "IMD_MUMBAI"
    rec.source_timestamp = source_ts
    rec.valid_until = valid_until
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=2)
    res = await tracker.check_imd_marine(db=db, now=now)

    assert res["status"] == STATUS_LIVE
    assert res["data_timestamp"] == source_ts.isoformat()
    assert res["valid_until"] == valid_until.isoformat()
    assert res["age_minutes"] == 180.0
    assert res["record_count"] == 2


# -----------------------------------------------------------------------------
# 4. Expired IMD Bulletin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_expired_imd_bulletin(tracker):
    now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    source_ts = now - timedelta(hours=30)
    valid_until = now - timedelta(hours=6)
    retrieved_at = now - timedelta(minutes=2)  # Downloaded recently

    rec = MagicMock(spec=MarineWarning)
    rec.id = 1
    rec.source_name = "IMD_MUMBAI"
    rec.source_timestamp = source_ts
    rec.valid_until = valid_until
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=1)
    res = await tracker.check_imd_marine(db=db, now=now)

    # Must be STALE, not LIVE!
    assert res["status"] == STATUS_STALE
    assert res["valid_until"] == valid_until.isoformat()


# -----------------------------------------------------------------------------
# 5. IMD Unavailable
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_imd_unavailable(tracker):
    now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    db = _mock_db_result(single_record=None, count=0)
    res = await tracker.check_imd_marine(db=db, now=now)

    assert res["status"] == STATUS_UNAVAILABLE
    assert res["record_count"] == 0
    assert "No IMD marine warnings" in res["error"]


# -----------------------------------------------------------------------------
# 6. Open-Meteo Fresh Observation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_open_meteo_fresh_observation(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    obs_ts = now - timedelta(minutes=45)
    retrieved_at = now - timedelta(minutes=5)

    rec = MagicMock(spec=OceanObservation)
    rec.id = 1
    rec.timestamp = obs_ts
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=171)
    res = await tracker.check_open_meteo_marine(db=db, now=now)

    assert res["status"] == STATUS_LIVE
    assert res["data_timestamp"] == obs_ts.isoformat()
    assert res["age_minutes"] == 45.0
    assert res["record_count"] == 171


# -----------------------------------------------------------------------------
# 7. Open-Meteo Stale Observation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_7_open_meteo_stale_observation(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    obs_ts = now - timedelta(hours=4)  # 240 mins ago (> 180 mins)
    retrieved_at = now - timedelta(minutes=5)

    rec = MagicMock(spec=OceanObservation)
    rec.id = 1
    rec.timestamp = obs_ts
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=171)
    res = await tracker.check_open_meteo_marine(db=db, now=now)

    assert res["status"] == STATUS_STALE
    assert res["age_minutes"] == 240.0


# -----------------------------------------------------------------------------
# 8. Historical GFW Data (Never LIVE)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_historical_gfw_data(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    obs_date = now - timedelta(days=5)

    rec = MagicMock(spec=GFWFishingEffort)
    rec.id = 1
    rec.observation_date = obs_date
    rec.retrieved_at = now - timedelta(hours=1)

    db = _mock_db_result(single_record=rec, count=171)
    res = await tracker.check_global_fishing_watch(db=db, now=now)

    # Must NEVER be LIVE
    assert res["status"] == STATUS_CACHED_HISTORICAL
    assert res["status"] != STATUS_LIVE
    assert res["data_timestamp"] == obs_date.isoformat()


# -----------------------------------------------------------------------------
# 9. GFW Age Calculation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_9_gfw_age_calculation(tracker):
    now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    obs_date = now - timedelta(days=12)

    rec = MagicMock(spec=GFWFishingEffort)
    rec.id = 1
    rec.observation_date = obs_date
    rec.retrieved_at = now - timedelta(days=1)

    db = _mock_db_result(single_record=rec, count=50)
    res = await tracker.check_global_fishing_watch(db=db, now=now)

    assert res["age_days"] == 12
    assert res["age_minutes"] == 12 * 24 * 60.0


# -----------------------------------------------------------------------------
# 10. Unavailable Source Behavior
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_unavailable_source(tracker):
    # db is None
    res_incois = await tracker.check_incois_pfz(db=None)
    assert res_incois["status"] == STATUS_UNAVAILABLE
    assert res_incois["record_count"] == 0
    assert "Database session not available" in res_incois["error"]

    res_imd = await tracker.check_imd_marine(db=None)
    assert res_imd["status"] == STATUS_UNAVAILABLE
    assert res_imd["record_count"] == 0

    res_meteo = await tracker.check_open_meteo_marine(db=None)
    assert res_meteo["status"] == STATUS_UNAVAILABLE
    assert res_meteo["record_count"] == 0


# -----------------------------------------------------------------------------
# 11. Error Source Resilience
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_error_source_handling(tracker):
    broken_db = AsyncMock()
    broken_db.execute.side_effect = RuntimeError("Database connection reset by peer")

    res_incois = await tracker.check_incois_pfz(db=broken_db)
    assert res_incois["status"] == STATUS_ERROR
    assert "Database connection reset by peer" in res_incois["error"]

    res_imd = await tracker.check_imd_marine(db=broken_db)
    assert res_imd["status"] == STATUS_ERROR
    assert "Database connection reset by peer" in res_imd["error"]


# -----------------------------------------------------------------------------
# 12. age_minutes Calculated Against Data Timestamp (NOT retrieved_at)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_age_minutes_calculation_not_retrieved_at(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    # Advisory from 10 hours ago (600 mins)
    advisory_date = now - timedelta(hours=10)
    # Retrieved 2 minutes ago
    retrieved_at = now - timedelta(minutes=2)

    rec = MagicMock(spec=INCOISPFZAdvisory)
    rec.id = 1
    rec.advisory_date = advisory_date
    rec.validity_date = now + timedelta(hours=14)
    rec.retrieved_at = retrieved_at

    db = _mock_db_result(single_record=rec, count=1)
    res = await tracker.check_incois_pfz(db=db, now=now)

    # age_minutes must be ~600, NOT 2.0!
    assert res["age_minutes"] == 600.0
    assert res["last_successful_fetch"] == retrieved_at.isoformat()


# -----------------------------------------------------------------------------
# 13. valid_until Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_valid_until_handling(tracker):
    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    
    # 1. Past valid_until
    past_validity = now - timedelta(minutes=1)
    rec_past = MagicMock(spec=MarineWarning)
    rec_past.source_name = "IMD_MUMBAI"
    rec_past.source_timestamp = now - timedelta(hours=6)
    rec_past.valid_until = past_validity
    rec_past.retrieved_at = now - timedelta(minutes=1)

    db_past = _mock_db_result(single_record=rec_past, count=1)
    res_past = await tracker.check_imd_marine(db=db_past, now=now)
    assert res_past["status"] == STATUS_STALE

    # 2. Future valid_until
    future_validity = now + timedelta(hours=12)
    rec_future = MagicMock(spec=MarineWarning)
    rec_future.source_name = "IMD_MUMBAI"
    rec_future.source_timestamp = now - timedelta(hours=1)
    rec_future.valid_until = future_validity
    rec_future.retrieved_at = now - timedelta(minutes=5)

    db_future = _mock_db_result(single_record=rec_future, count=1)
    res_future = await tracker.check_imd_marine(db=db_future, now=now)
    assert res_future["status"] == STATUS_LIVE


# -----------------------------------------------------------------------------
# 14. API Response Structure (GET /api/v1/sources/freshness)
# -----------------------------------------------------------------------------
def test_14_sources_freshness_endpoint_structure():
    client = TestClient(app)
    response = client.get("/api/v1/sources/freshness")
    assert response.status_code == 200

    data = response.json()
    assert "sources" in data
    assert "generated_at" in data

    sources = data["sources"]
    for src_key in ["incois_pfz", "imd_marine_warnings", "open_meteo_marine", "global_fishing_watch"]:
        assert src_key in sources, f"Missing source key {src_key}"
        src_data = sources[src_key]
        assert "source_name" in src_data
        assert "status" in src_data
        assert "last_successful_fetch" in src_data
        assert "data_timestamp" in src_data
        assert "valid_until" in src_data
        assert "age_minutes" in src_data
        assert "record_count" in src_data
        assert "error" in src_data
        assert src_data["status"] in [
            STATUS_LIVE,
            STATUS_STALE,
            STATUS_UNAVAILABLE,
            STATUS_AUTHENTICATED,
            STATUS_PUBLIC,
            STATUS_CACHED_HISTORICAL,
            STATUS_ERROR,
        ]


# -----------------------------------------------------------------------------
# 15. Map Summary Compatibility (GET /api/v1/map/summary)
# -----------------------------------------------------------------------------
def test_15_map_summary_compatibility():
    client = TestClient(app)
    response = client.get("/api/v1/map/summary?demo=true")
    assert response.status_code == 200

    data = response.json()
    # Ensure legacy keys are present
    assert "metadata" in data
    assert "marine_safety" in data
    assert "predictions" in data
    assert "pfz_advisory" in data
    assert "landing_centres" in data

    # Verify new source freshness field in root
    assert "source_freshness" in data
    assert "incois_pfz" in data["source_freshness"]
    assert "imd_marine_warnings" in data["source_freshness"]
    assert "open_meteo_marine" in data["source_freshness"]
    assert "global_fishing_watch" in data["source_freshness"]

    # Verify metadata.data_sources backwards compatibility
    meta_sources = data["metadata"]["data_sources"]
    assert "gfw" in meta_sources
    assert "environmental" in meta_sources
    assert "incois_pfz" in meta_sources
    assert "marine_safety" in meta_sources

    # Check that safety gate remains independent
    assert data["marine_safety"]["independent_of_ml"] is True
