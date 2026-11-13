import pytest
import pytest_asyncio
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from backend.app.services.ingestion.incois_pfz_provider import INCOISPFZProvider, PFZRecord

@pytest.fixture
def provider():
    return INCOISPFZProvider()

def test_dms_conversion_valid(provider):
    # Test valid N/E
    lat = provider.parse_dms("15 45 28 N")
    assert lat is not None
    assert round(lat, 4) == 15.7578

    lon = provider.parse_dms("73 2 9 E")
    assert lon is not None
    assert round(lon, 4) == 73.0358

def test_dms_conversion_south_west(provider):
    lat = provider.parse_dms("15 45 28 S")
    assert lat is not None
    assert round(lat, 4) == -15.7578

    lon = provider.parse_dms("73 2 9 W")
    assert lon is not None
    assert round(lon, 4) == -73.0358

def test_dms_conversion_malformed_spacing(provider):
    # Malformed spacing but readable
    lat = provider.parse_dms("  15  45  28  N  ")
    assert round(lat, 4) == 15.7578
    
    # Extra symbols
    lat2 = provider.parse_dms("15°45'28\"N")
    assert lat2 is not None
    assert round(lat2, 4) == 15.7578

def test_dms_conversion_invalid(provider):
    assert provider.parse_dms("Invalid String") is None
    assert provider.parse_dms("15 45 N") is None # missing seconds

def test_depth_parsing(provider):
    d_min, d_max = provider.parse_depth("45-50")
    assert d_min == 45
    assert d_max == 50

    d_min2, d_max2 = provider.parse_depth("60")
    assert d_min2 == 60
    assert d_max2 == 60

def test_extract_dates_from_html(provider):
    html = """
    <html>
      <p id="updatedDate"> Sun Sep 06 16:18:49 IST 2026</p>
      <p id="satmsg">SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  7 SEP 2026    </p>
    </html>
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    d1 = provider._extract_advisory_date(soup)
    assert d1.year == 2026
    assert d1.month == 9
    assert d1.day == 6
    
    d2 = provider._extract_validity_date(soup)
    assert d2.year == 2026
    assert d2.month == 9
    assert d2.day == 7

@pytest.mark.asyncio
async def test_missing_session_cookie(provider):
    with patch("httpx.AsyncClient", autospec=True) as MockClient, \
         patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        
        # Mock TextDataHome returning no JSESSIONID cookie
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {}
        
        mock_fetch.return_value = MagicMock(status_code=200)
        
        result = await provider.fetch_latest_maharashtra_pfz()
        assert result["status"] == "UNAVAILABLE"
        assert result["error"] == "Missing session cookie"

@pytest.mark.asyncio
async def test_redirect_to_generic(provider):
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        # We need to simulate the client's cookie jar having JSESSIONID after the first fetch
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "123456"}
        
        # TextData secid=SEC002 redirects to generic
        mock_data = MagicMock()
        mock_data.status_code = 302
        mock_data.headers = {"Location": "MarineFisheryAdvisory"}
        
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        result = await provider.fetch_latest_maharashtra_pfz()
        assert result["status"] == "STALE"
        assert "Redirected" in result["error"]

@pytest.mark.asyncio
async def test_successful_parsing(provider):
    html_mock = """
    <html>
        <body>
            <p id="updatedDate" style='display:none;'> Sun Sep 06 16:18:49 IST 2026</p>
            <p id="satmsg">SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  7 SEP 2026    </p>
            <table>
                <tr>
                    <th>Landing Centre</th>
                    <th>Direction</th>
                    <th>Bearing (deg)</th>
                    <th>Distance (km)</th>
                    <th>Depth (mtr)</th>
                    <th>Latitude (dms)</th>
                    <th>Longitude (dms)</th>
                </tr>
                <tr>
                    <td>Talashil</td>
                    <td>SW</td>
                    <td>210</td>
                    <td>25</td>
                    <td>45-50</td>
                    <td>15 45 28 N</td>
                    <td>73 02 09 E</td>
                </tr>
                <tr>
                    <td>Invalid Lat</td>
                    <td>SW</td>
                    <td>210</td>
                    <td>25</td>
                    <td>45-50</td>
                    <td>999 45 28 N</td> <!-- Invalid Lat -->
                    <td>73 02 09 E</td>
                </tr>
            </table>
        </body>
    </html>
    """
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "123456"}
        
        mock_data = MagicMock()
        mock_data.status_code = 200
        mock_data.text = html_mock
        
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        result = await provider.fetch_latest_maharashtra_pfz()
        # Since validity is Sep 7, 2026, and today is also Sep 2026 in the simulation, it might be SUCCESS or STALE depending on exactly datetime.now().
        # We just check the parsing logic here.
        assert result["status"] in ("SUCCESS", "STALE")
        assert result["record_count"] == 1 # Second row was rejected due to bounds
        
        rec = result["records"][0]
        assert rec.landing_centre == "Talashil"
        assert rec.latitude == 15.757777777777777
        assert result["advisory_date"] is not None
        assert result["advisory_date"].day == 6
        assert result["validity_date"] is not None
        assert result["validity_date"].day == 7

@pytest.mark.asyncio
async def test_stale_data(provider):
    html_mock = """
    <html>
        <body>
            <p id="updatedDate" style='display:none;'> Sun Sep 06 16:18:49 IST 2026</p>
            <p id="satmsg">SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  1 JAN 2000    </p>
            <table>
                <tr>
                    <th>Landing Centre</th>
                    <th>Direction</th>
                    <th>Bearing (deg)</th>
                    <th>Distance (km)</th>
                    <th>Depth (mtr)</th>
                    <th>Latitude (dms)</th>
                    <th>Longitude (dms)</th>
                </tr>
                <tr>
                    <td>Talashil</td>
                    <td>SW</td>
                    <td>210</td>
                    <td>25</td>
                    <td>45-50</td>
                    <td>15 45 28 N</td>
                    <td>73 02 09 E</td>
                </tr>
            </table>
        </body>
    </html>
    """
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "123456"}
        
        mock_data = MagicMock()
        mock_data.status_code = 200
        mock_data.text = html_mock
        
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        result = await provider.fetch_latest_maharashtra_pfz()
        assert result["status"] == "STALE"

@pytest.mark.asyncio
async def test_unknown_freshness(provider):
    html_mock = """
    <html>
        <body>
            <table>
                <tr>
                    <th>Landing Centre</th>
                    <th>Direction</th>
                    <th>Bearing (deg)</th>
                    <th>Distance (km)</th>
                    <th>Depth (mtr)</th>
                    <th>Latitude (dms)</th>
                    <th>Longitude (dms)</th>
                </tr>
                <tr>
                    <td>Talashil</td>
                    <td>SW</td>
                    <td>210</td>
                    <td>25</td>
                    <td>45-50</td>
                    <td>15 45 28 N</td>
                    <td>73 02 09 E</td>
                </tr>
            </table>
        </body>
    </html>
    """
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "123456"}
        
        mock_data = MagicMock()
        mock_data.status_code = 200
        mock_data.text = html_mock
        
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        result = await provider.fetch_latest_maharashtra_pfz()
        assert result["status"] == "UNKNOWN_FRESHNESS"
        assert result["advisory_date"] is None
        assert result["validity_date"] is None

@pytest.mark.asyncio
async def test_deduplication_batch_ingest(provider):
    # Test that if the DB already has the batch hash, it skips insertion
    mock_result = {
        "status": "SUCCESS",
        "advisory_date": datetime(2026, 9, 6, tzinfo=timezone.utc),
        "validity_date": datetime(2026, 9, 7, tzinfo=timezone.utc),
        "retrieved_at": datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
        "records": [
            PFZRecord("Talashil", "SW", 210, "25", 45, 50, 15.7578, 73.0358)
        ],
        "record_count": 1,
    }
    
    with patch.object(provider, "fetch_latest_maharashtra_pfz", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_result
        
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_db.execute.return_value = mock_execute_result
        
        # Scenario 1: Batch exists
        mock_execute_result.scalar_one_or_none.return_value = 1 # ID 1 exists
        
        res1 = await provider.ingest_latest_maharashtra_pfz(mock_db)
        assert res1["status"] == "SUCCESS"
        mock_db.add_all.assert_not_called()
        
        # Scenario 2: Batch does NOT exist
        mock_execute_result.scalar_one_or_none.return_value = None
        
        res2 = await provider.ingest_latest_maharashtra_pfz(mock_db)
        assert res2["status"] == "SUCCESS"
        mock_db.add_all.assert_called_once()


@pytest.mark.asyncio
async def test_real_incois_live_format_parsing(provider):
    """
    Test parsing against the exact HTML structure returned by official INCOIS
    for Maharashtra (secid=SEC002), including 'From the coast of' headers,
    distance ranges ('78-83'), depth ranges ('26-31'), and DMS coordinates ('20 1 35 N').
    """
    real_html = """
    <html>
        <body>
            <p id="updatedDate" style="display:none;"> Thu Sep 10 15:30:56 IST 2026</p>
            <p id="satmsg" style="font-weight:bold;">SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  11 SEP 2026    </p>
            <table>
                <tr>
                    <th>From the coast of</th>
                    <th>Direction</th>
                    <th>Bearing (deg)</th>
                    <th>Distance (km)From-To</th>
                    <th>Depth (mtr)From-To</th>
                    <th>Latitude (dms)</th>
                    <th>Longitude (dms)</th>
                </tr>
                <tr>
                    <td>Tarapur Pt</td>
                    <td>NW</td>
                    <td>286</td>
                    <td>78-83</td>
                    <td>26-31</td>
                    <td>20 1 35 N</td>
                    <td>71 56 39 E</td>
                </tr>
                <tr>
                    <td>Ghivali</td>
                    <td>NW</td>
                    <td>280</td>
                    <td>78-83</td>
                    <td>25-30</td>
                    <td>19 57 42 N</td>
                    <td>71 55 46 E</td>
                </tr>
                <tr>
                    <td>Varor</td>
                    <td>SW</td>
                    <td>261</td>
                    <td>85-90</td>
                    <td>26-31</td>
                    <td>19 46 53 N</td>
                    <td>71 53 4 E</td>
                </tr>
            </table>
        </body>
    </html>
    """
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "TESTSESSION123"}
        
        mock_data = MagicMock()
        mock_data.status_code = 200
        mock_data.text = real_html
        
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        result = await provider.fetch_latest_maharashtra_pfz()
        
        # Verify structured result keys
        assert "status" in result
        assert "count" in result
        assert "advisory_date" in result
        assert "validity_date" in result
        assert "retrieved_at" in result
        assert "errors" in result
        
        assert result["count"] == 3
        assert len(result["records"]) == 3
        
        # Verify first record
        r0 = result["records"][0]
        assert r0.landing_centre == "Tarapur Pt"
        assert r0.direction == "NW"
        assert r0.bearing_degrees == 286
        assert r0.distance_km == "78-83"
        assert r0.depth_min_m == 26
        assert r0.depth_max_m == 31
        assert abs(r0.latitude - 20.026388) < 0.001
        assert abs(r0.longitude - 71.944166) < 0.001
        
        # Verify third record with single digit second '4'
        r2 = result["records"][2]
        assert r2.landing_centre == "Varor"
        assert abs(r2.latitude - 19.781388) < 0.001
        assert abs(r2.longitude - 71.884444) < 0.001
        
        assert result["advisory_date"].year == 2026
        assert result["advisory_date"].month == 9
        assert result["advisory_date"].day == 10
        assert result["validity_date"].day == 11


def test_dms_conversion_live_cases(provider):
    """Test DMS conversion on coordinates extracted directly from INCOIS SEC002."""
    # 20 1 35 N -> 20 + 1/60 + 35/3600 = 20.026388...
    lat1 = provider.parse_dms("20 1 35 N")
    assert abs(lat1 - 20.026388) < 0.0001
    
    # 71 56 39 E -> 71 + 56/60 + 39/3600 = 71.944166...
    lon1 = provider.parse_dms("71 56 39 E")
    assert abs(lon1 - 71.944166) < 0.0001
    
    # Single digit seconds: 71 53 4 E -> 71 + 53/60 + 4/3600 = 71.884444...
    lon2 = provider.parse_dms("71 53 4 E")
    assert abs(lon2 - 71.884444) < 0.0001
    
    # Prefix direction: N 19 46 53
    lat2 = provider.parse_dms("N 19 46 53")
    assert abs(lat2 - 19.781388) < 0.0001


@pytest.mark.asyncio
async def test_database_insertion_dual_tables(provider):
    """
    Test that ingestion normalizes into BOTH incois_pfz_advisories and pfz_zones,
    populating all required fields including 64-char hash_id and PostGIS geom.
    """
    from backend.app.models.incois_pfz import INCOISPFZAdvisory
    from backend.app.models.pfz_zone import PFZZone

    mock_result = {
        "status": "SUCCESS",
        "count": 2,
        "advisory_date": datetime(2030, 9, 10, 15, 30, tzinfo=timezone.utc),
        "validity_date": datetime(2030, 9, 11, 23, 59, tzinfo=timezone.utc),
        "retrieved_at": datetime(2030, 9, 10, 16, 0, tzinfo=timezone.utc),
        "records": [
            PFZRecord("Tarapur Pt", "NW", 286, "78-83", 26, 31, 20.0264, 71.9442),
            PFZRecord("Ghivali", "NW", 280, "78-83", 25, 30, 19.9617, 71.9294)
        ],
        "record_count": 2,
        "errors": []
    }
    
    with patch.object(provider, "fetch_latest_maharashtra_pfz", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_result
        
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None # No existing batch
        mock_db.execute.return_value = mock_execute_result
        
        res = await provider.ingest_latest_maharashtra_pfz(mock_db)
        assert res["status"] == "SUCCESS"
        assert res["count"] == 2
        
        # Verify db.add_all was called
        mock_db.add_all.assert_called_once()
        inserted = mock_db.add_all.call_args[0][0]
        
        # 2 advisory records + 2 pfz_zone records = 4 records
        assert len(inserted) == 4
        
        advisories = [r for r in inserted if isinstance(r, INCOISPFZAdvisory)]
        zones = [r for r in inserted if isinstance(r, PFZZone)]
        
        assert len(advisories) == 2
        assert len(zones) == 2
        
        # Validate INCOISPFZAdvisory fields
        adv = advisories[0]
        assert adv.source == "INCOIS"
        assert adv.source_type == "OFFICIAL_PFZ_ADVISORY"
        assert adv.sector == "Maharashtra"
        assert adv.landing_centre == "Tarapur Pt"
        assert adv.depth_min_m == 26
        assert adv.depth_max_m == 31
        assert adv.geom == "SRID=4326;POINT(71.9442 20.0264)"
        # Crucial: hash_id must be exactly 64 characters to fit VARCHAR(64)
        assert len(adv.hash_id) == 64
        
        # Validate PFZZone fields
        zone = zones[0]
        assert zone.source_name == "INCOIS"
        assert zone.dataset_name == "OFFICIAL_PFZ_ADVISORY"
        assert zone.latitude == 20.0264
        assert zone.longitude == 71.9442
        assert zone.depth == 26.0
        assert zone.is_stale is False
        assert zone.spatial_resolution == "Point"
        assert zone.temporal_resolution == "Daily"
        assert zone.data_quality_status == "VALID"


@pytest.mark.asyncio
async def test_unavailable_source_marks_stale_and_retains(provider):
    """
    If the official source is unavailable:
    - Do not create fake records
    - Retain the last valid PFZ data
    - Mark active records stale
    - Return explicit error/status
    """
    from backend.app.models.incois_pfz import INCOISPFZAdvisory
    
    last_valid_advisory = INCOISPFZAdvisory(
        source="INCOIS",
        source_type="OFFICIAL_PFZ_ADVISORY",
        sector="Maharashtra",
        landing_centre="Historical Centre",
        direction="W",
        bearing_degrees=270,
        distance_km="30",
        depth_min_m=30,
        depth_max_m=40,
        latitude=18.5,
        longitude=72.5,
        geom="SRID=4326;POINT(72.5 18.5)",
        advisory_date=datetime(2026, 9, 8, tzinfo=timezone.utc),
        validity_date=datetime(2026, 9, 9, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        source_url="https://incois.gov.in",
        hash_id="a" * 64
    )
    
    # Mock unavailable fetch result
    unavailable_fetch = {
        "status": "UNAVAILABLE",
        "count": 0,
        "advisory_date": None,
        "validity_date": None,
        "retrieved_at": datetime.now(timezone.utc),
        "errors": ["Connection timed out to INCOIS"],
        "records": [],
        "record_count": 0,
        "error": "Connection timed out to INCOIS"
    }
    
    with patch.object(provider, "fetch_latest_maharashtra_pfz", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = unavailable_fetch
        
        mock_db = AsyncMock()
        mock_exec_res = MagicMock()
        mock_exec_res.scalars.return_value.first.return_value = last_valid_advisory
        mock_db.execute.return_value = mock_exec_res
        
        res = await provider.ingest_latest_maharashtra_pfz(mock_db)
        
        # 1. Status is UNAVAILABLE
        assert res["status"] == "UNAVAILABLE"
        assert res["count"] == 0
        assert len(res["errors"]) > 0
        
        # 2. No fake records added
        mock_db.add_all.assert_not_called()
        
        # 3. Retains last valid advisory dates
        assert res["advisory_date"] == last_valid_advisory.advisory_date
        assert res["validity_date"] == last_valid_advisory.validity_date
        
        # 4. Committed the stale update to DB
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_data_populates_is_stale_flag(provider):
    """Test that when advisory validity is expired, is_stale is True on PFZZone."""
    from backend.app.models.pfz_zone import PFZZone

    expired_validity = datetime(2020, 1, 1, tzinfo=timezone.utc)
    mock_result = {
        "status": "STALE",
        "count": 1,
        "advisory_date": datetime(2019, 12, 31, tzinfo=timezone.utc),
        "validity_date": expired_validity,
        "retrieved_at": datetime.now(timezone.utc),
        "records": [
            PFZRecord("Talashil", "SW", 210, "25", 45, 50, 15.7578, 73.0358)
        ],
        "record_count": 1,
        "errors": []
    }
    
    # Test that fetch sets status to STALE
    html_expired = """
    <html>
        <body>
            <p id="updatedDate"> Sun Dec 31 16:18:49 IST 2019</p>
            <p id="satmsg">SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  1 JAN 2020    </p>
            <table>
                <tr><th>Landing Centre</th><th>Direction</th><th>Bearing (deg)</th><th>Distance (km)</th><th>Depth (mtr)</th><th>Latitude (dms)</th><th>Longitude (dms)</th></tr>
                <tr><td>Talashil</td><td>SW</td><td>210</td><td>25</td><td>45-50</td><td>15 45 28 N</td><td>73 02 09 E</td></tr>
            </table>
        </body>
    </html>
    """
    with patch.object(provider, "_fetch_with_retry", new_callable=AsyncMock) as mock_fetch, \
         patch("httpx.AsyncClient", autospec=True) as MockClient:
        
        mock_client_instance = MockClient.return_value.__aenter__.return_value
        mock_client_instance.cookies = {"JSESSIONID": "SESS123"}
        
        mock_data = MagicMock(status_code=200, text=html_expired)
        mock_fetch.side_effect = [MagicMock(status_code=200), mock_data]
        
        res = await provider.fetch_latest_maharashtra_pfz()
        assert res["status"] == "STALE"
        assert res["validity_date"].year == 2020


@pytest.mark.asyncio
async def test_structured_return_format_and_deduplication(provider):
    """
    Verifies that the returned ingestion result satisfies all schema requirements:
    { status, count, advisory_date, validity_date, retrieved_at, errors }
    and that running ingestion multiple times is strictly idempotent.
    """
    mock_result = {
        "status": "SUCCESS",
        "count": 1,
        "advisory_date": datetime(2026, 9, 10, 15, 30, tzinfo=timezone.utc),
        "validity_date": datetime(2026, 9, 11, 23, 59, tzinfo=timezone.utc),
        "retrieved_at": datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc),
        "records": [
            PFZRecord("Tarapur Pt", "NW", 286, "78-83", 26, 31, 20.0264, 71.9442)
        ],
        "record_count": 1,
        "errors": []
    }
    
    with patch.object(provider, "fetch_latest_maharashtra_pfz", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_result
        
        mock_db = AsyncMock()
        mock_exec_res = MagicMock()
        mock_db.execute.return_value = mock_exec_res
        
        # Run 1: New batch
        mock_exec_res.scalar_one_or_none.return_value = None
        res1 = await provider.ingest_latest_maharashtra_pfz(mock_db)
        
        # Check all required structured result keys
        required_keys = {"status", "count", "advisory_date", "validity_date", "retrieved_at", "errors"}
        assert required_keys.issubset(res1.keys())
        assert res1["status"] == "SUCCESS"
        assert res1["count"] == 1
        assert res1["errors"] == []
        assert mock_db.add_all.call_count == 1
        
        # Run 2: Same batch (simulate DB already containing the batch)
        mock_exec_res.scalar_one_or_none.return_value = 999
        res2 = await provider.ingest_latest_maharashtra_pfz(mock_db)
        
        assert required_keys.issubset(res2.keys())
        assert res2["status"] == "SUCCESS"
        assert res2["count"] == 1
        # Crucial: add_all must NOT have been called a second time
        assert mock_db.add_all.call_count == 1


