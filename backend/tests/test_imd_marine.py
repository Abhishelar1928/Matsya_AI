"""
Tests for IMD Marine / Fishermen Warning Ingestion Provider (Phase 5.2).

Verifies:
- Real PDF parsing structure and token cleanup
- Issue timestamp and validity period extraction
- North & South Maharashtra coast warning extraction
- Nil/Normal severity classification (NORMAL)
- Advisory/warning conditions classification (WARNING)
- Cyclone/gale severity classification (SEVERE)
- Idempotent deduplication (duplicate bulletin prevention)
- Malformed PDF resilience
- Unavailable source handling (never creates fake records, never inserts NORMAL on failure)
- Stale-data behavior
- Structured result format compliance
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from backend.app.services.ingestion.imd_marine_provider import (
    IMDMarineProvider,
    GEOM_NORTH_MH_COAST,
    GEOM_SOUTH_MH_GOA_COAST,
    GEOM_HIGH_SEA,
)
from backend.app.models.marine_warning import MarineWarning

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF_PATH = FIXTURES_DIR / "sample_imd_fisherman.pdf"


@pytest.fixture
def provider():
    return IMDMarineProvider()


def test_token_spacing_cleanup(provider):
    """Test collapsing kerned spaces/tabs from PDF character streams."""
    raw = "T h u r s d a y ,\t 1 0 \t S e p t e m b e r ,\t 2 0 2 6"
    cleaned = provider._clean_token_spacing(raw)
    assert cleaned == "Thursday , 10 September , 2026"

    raw2 = "N i l ."
    assert provider._clean_token_spacing(raw2) == "Nil ."

    raw3 = "S q u a l l y \t w i n d"
    assert provider._clean_token_spacing(raw3) == "Squally wind"


def test_issue_timestamp_extraction(provider):
    """Test extracting issue timestamp with IST to UTC conversion."""
    text = "Thursday , 10 September , 2026 Time Of Issue : 2030 HRS IST"
    ts = provider.extract_issue_timestamp(text)
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 9
    assert ts.day == 10
    # 20:30 IST is 15:00 UTC
    assert ts.hour == 15
    assert ts.minute == 0
    assert ts.tzinfo == timezone.utc


def test_validity_period_extraction(provider):
    """Test extracting start and end validity timestamps from 5-day bulletin."""
    text = "Valid For Next Five Days From 10 - Sep - 2026 to 14 - Sep - 2026"
    v_from, v_until = provider.extract_validity_period(text)
    assert v_from is not None
    assert v_until is not None
    assert v_from.year == 2026
    assert v_from.month == 9
    assert v_from.day == 10
    assert v_until.year == 2026
    assert v_until.month == 9
    assert v_until.day == 14
    assert v_until.hour == 23


def test_severity_classification(provider):
    """
    Test strict severity mapping:
    - NORMAL: only when explicitly Nil / Normal
    - WARNING: advisory conditions like squally wind
    - SEVERE: cyclone, gale, extreme weather
    """
    # 1. NORMAL
    assert provider.classify_severity("Nil.") == "NORMAL"
    assert provider.classify_severity("Nil .") == "NORMAL"
    assert provider.classify_severity("Normal") == "NORMAL"
    assert provider.classify_severity("No warning") == "NORMAL"
    assert provider.classify_severity("") == "NORMAL"

    # 2. WARNING
    warning_text = "Squally wind with speed 45 - 55 kmph gusting to 65 kmph is likely to prevail"
    assert provider.classify_severity(warning_text) == "WARNING"

    caution_text = "Fishermen are advised not to venture into southwest Arabian Sea due to rough sea conditions"
    assert provider.classify_severity(caution_text) == "WARNING"

    # 3. SEVERE
    cyclone_text = "Cyclonic storm likely to intensify into Very Severe Cyclonic Storm with gale wind 80-90 kmph"
    assert provider.classify_severity(cyclone_text) == "SEVERE"

    gale_text = "Gale force winds speed 70-80 kmph gusting to 90 kmph over eastcentral Arabian Sea"
    assert provider.classify_severity(gale_text) == "SEVERE"


def test_parse_bulletin_lines_mock(provider):
    """Test section extraction from parsed line array."""
    lines = [
        "Thursday , 10 September , 2026 Time Of Issue : 2030 HRS IST",
        "FISHERMEN WARNING FOR MAHARASHTRA - GOA COAST FOR NEXT FIVE DAYS",
        "Valid For Next Five Days From 10 - Sep - 2026 to 14 - Sep - 2026",
        "Warning for coastal areas for North Maharashtra coast ( upto 75km from the coast ) : -",
        "Nil .",
        "Warning for coastal areas for South Maharashtra - Goa coast ( upto 75km from the coast ) : -",
        "Nil .",
        "Warning for High Sea and other coasts ( Beyond 75km from the coast ) : -",
        "Wind warning : -",
        "Squally wind with speed 45 - 55 kmph gusting to 65 kmph over southwest Arabian Sea .",
        "Fishermen are advised not to venture into these areas .",
        "High Wave / Swell Surge Warning from INCOIS : -",
        "North Maharashtra : Nil .",
        "South Maharashtra : Nil .",
        "Port Warning for North Maharashtra coast : -",
        "Nil .",
        "Port Warning for South Maharashtra - Goa coast : -",
        "Nil .",
    ]

    parsed = provider.parse_bulletin_lines(lines)
    assert parsed["issue_timestamp"] is not None
    assert parsed["valid_from"] is not None
    assert len(parsed["warnings"]) >= 3

    # Check North Maharashtra Coast warning
    north = next(w for w in parsed["warnings"] if "North Maharashtra Coast" in w["region"])
    assert north["severity"] == "NORMAL"
    assert north["warning_type"] == "COASTAL_FISHERMEN_WARNING"
    assert north["geom"] == GEOM_NORTH_MH_COAST

    # Check South Maharashtra Coast warning
    south = next(w for w in parsed["warnings"] if "South Maharashtra-Goa Coast" in w["region"])
    assert south["severity"] == "NORMAL"
    assert south["warning_type"] == "COASTAL_FISHERMEN_WARNING"
    assert south["geom"] == GEOM_SOUTH_MH_GOA_COAST

    # Check High Sea warning
    high_sea = next(w for w in parsed["warnings"] if "High Sea" in w["region"])
    assert high_sea["severity"] == "WARNING"
    assert high_sea["warning_type"] == "HIGH_SEA_WIND_WARNING"
    assert high_sea["geom"] == GEOM_HIGH_SEA


def test_real_pdf_fixture_parsing(provider):
    """Test full parsing pipeline against the real saved IMD PDF fixture."""
    if not SAMPLE_PDF_PATH.exists():
        pytest.skip("Sample IMD PDF fixture not found.")

    with open(SAMPLE_PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    lines = provider.extract_structured_lines(pdf_bytes)
    assert len(lines) >= 20

    parsed = provider.parse_bulletin_lines(lines)
    assert parsed["issue_timestamp"] is not None
    assert parsed["issue_timestamp"].year == 2026
    assert parsed["valid_from"] is not None
    assert parsed["valid_until"] is not None

    warnings = parsed["warnings"]
    assert len(warnings) >= 3

    north_warn = next(w for w in warnings if "North Maharashtra Coast" in w["region"])
    assert north_warn["severity"] == "NORMAL"
    assert "Nil" in north_warn["text"]

    south_warn = next(w for w in warnings if "South Maharashtra-Goa Coast" in w["region"])
    assert south_warn["severity"] == "NORMAL"

    high_sea_warn = next(w for w in warnings if "High Sea" in w["region"])
    assert high_sea_warn["severity"] == "WARNING"
    assert "Squally" in high_sea_warn["text"]


@pytest.mark.asyncio
async def test_fetch_latest_bulletin_structured_result(provider):
    """Test structured return keys and format from fetch_latest_bulletin."""
    if not SAMPLE_PDF_PATH.exists():
        pytest.skip("Sample IMD PDF fixture not found.")

    with open(SAMPLE_PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    with patch.object(provider, "_fetch_pdf_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = pdf_bytes

        res = await provider.fetch_latest_bulletin()

        # Check required schema keys
        required_keys = {
            "status", "count", "issue_timestamp", "valid_from",
            "valid_until", "warnings", "retrieved_at", "errors"
        }
        assert required_keys.issubset(res.keys())
        assert res["status"] == "SUCCESS"
        assert res["count"] >= 3
        assert res["issue_timestamp"] is not None
        assert res["valid_from"] is not None
        assert res["valid_until"] is not None
        assert res["errors"] == []


@pytest.mark.asyncio
async def test_malformed_pdf_handling(provider):
    """Test that invalid non-PDF bytes return UNAVAILABLE and explicit error."""
    with patch.object(provider, "_fetch_pdf_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = ValueError("Downloaded content is not a valid PDF document.")

        res = await provider.fetch_latest_bulletin()
        assert res["status"] == "UNAVAILABLE"
        assert res["count"] == 0
        assert len(res["errors"]) > 0
        assert "not a valid PDF" in res["errors"][0]


@pytest.mark.asyncio
async def test_unavailable_source_does_not_insert_normal(provider):
    """
    CRITICAL SAFETY REQUIREMENT:
    If source cannot be fetched or times out:
    - Do NOT insert fake records
    - Do NOT insert NORMAL
    - Do NOT alter previous records to NORMAL
    - Return explicit UNAVAILABLE status
    """
    with patch.object(provider, "fetch_latest_bulletin", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "status": "UNAVAILABLE",
            "count": 0,
            "issue_timestamp": None,
            "valid_from": None,
            "valid_until": None,
            "warnings": [],
            "retrieved_at": datetime.now(timezone.utc),
            "errors": ["Connection timed out to IMD Mumbai portal"]
        }

        mock_db = AsyncMock()
        res = await provider.ingest_latest_bulletin(mock_db)

        # 1. Status is UNAVAILABLE
        assert res["status"] == "UNAVAILABLE"
        assert res["count"] == 0

        # 2. No database records inserted
        mock_db.add_all.assert_not_called()
        mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_bulletin_deduplication(provider):
    """
    Test deterministic deduplication:
    Ingesting the same bulletin multiple times must NOT insert duplicate records.
    """
    mock_bulletin = {
        "status": "SUCCESS",
        "count": 3,
        "issue_timestamp": datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
        "valid_from": datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
        "valid_until": datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
        "retrieved_at": datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
        "warnings": [
            {
                "region": "North Maharashtra Coast",
                "warning_type": "COASTAL_FISHERMEN_WARNING",
                "severity": "NORMAL",
                "text": "Nil.",
                "geom": GEOM_NORTH_MH_COAST,
                "valid_from": datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
            }
        ],
        "errors": []
    }

    with patch.object(provider, "fetch_latest_bulletin", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_bulletin

        mock_db = AsyncMock()
        mock_exec_res = MagicMock()
        mock_db.execute.return_value = mock_exec_res

        # Run 1: Bulletin is new (not in DB)
        mock_exec_res.scalars.return_value.first.return_value = None
        res1 = await provider.ingest_latest_bulletin(mock_db)
        assert res1["status"] == "SUCCESS"
        assert mock_db.add_all.call_count == 1

        # Run 2: Bulletin already exists in DB with same issue_timestamp
        existing_warning = MagicMock(id=101)
        mock_exec_res.scalars.return_value.first.return_value = existing_warning

        res2 = await provider.ingest_latest_bulletin(mock_db)
        assert res2["status"] == "SUCCESS"
        # Crucial: add_all must NOT have been called again
        assert mock_db.add_all.call_count == 1


@pytest.mark.asyncio
async def test_database_record_attributes(provider):
    """Test that generated MarineWarning records contain all expected attributes."""
    mock_bulletin = {
        "status": "SUCCESS",
        "count": 1,
        "issue_timestamp": datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc),
        "valid_from": datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
        "valid_until": datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
        "retrieved_at": datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
        "warnings": [
            {
                "region": "North Maharashtra Coast (upto 75km from coast)",
                "warning_type": "COASTAL_FISHERMEN_WARNING",
                "severity": "NORMAL",
                "text": "Nil.",
                "geom": GEOM_NORTH_MH_COAST,
                "valid_from": datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc),
                "valid_until": datetime(2026, 9, 14, 23, 59, tzinfo=timezone.utc),
            }
        ],
        "errors": []
    }

    with patch.object(provider, "fetch_latest_bulletin", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_bulletin

        mock_db = AsyncMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_exec_res

        await provider.ingest_latest_bulletin(mock_db)
        mock_db.add_all.assert_called_once()
        records = mock_db.add_all.call_args[0][0]
        assert len(records) == 1

        rec = records[0]
        assert isinstance(rec, MarineWarning)
        assert rec.source_name == "IMD_MUMBAI"
        assert rec.dataset_name == "OFFICIAL_FISHERMAN_BULLETIN"
        assert rec.warning_type == "COASTAL_FISHERMEN_WARNING"
        assert rec.severity == "NORMAL"
        assert "North Maharashtra Coast" in rec.description
        assert "mcdata/fisherman.pdf" in rec.description
        assert rec.geom == GEOM_NORTH_MH_COAST
        assert rec.is_stale is False
        assert rec.data_quality_status == "VALID"
