import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.models.marine_warning import MarineWarning
from backend.app.models.ocean_observation import OceanObservation
from backend.app.models.gfw import GFWFishingEffort


def main():
    client = TestClient(app)

    print("\n" + "="*80)
    print("1. VERIFICATION: Populated Operational State (Simulated In-Memory Session)")
    print("="*80)

    now = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    
    # Mock records for each source
    # INCOIS PFZ: Live advisory
    incois_rec = MagicMock(spec=INCOISPFZAdvisory)
    incois_rec.id = 1
    incois_rec.advisory_date = now - timedelta(hours=3)
    incois_rec.validity_date = now + timedelta(hours=21)
    incois_rec.retrieved_at = now - timedelta(minutes=15)
    incois_rec.landing_centre = "Ratnagiri - Mirkarwada"
    incois_rec.direction = "SW"
    incois_rec.bearing_degrees = 225.0
    incois_rec.distance_km = 32.5
    incois_rec.latitude = 17.85
    incois_rec.longitude = 73.05

    # IMD Marine: Live bulletin
    imd_rec = MagicMock(spec=MarineWarning)
    imd_rec.id = 1
    imd_rec.source_name = "IMD_MUMBAI"
    imd_rec.source_timestamp = now - timedelta(hours=2)
    imd_rec.valid_until = now + timedelta(hours=22)
    imd_rec.retrieved_at = now - timedelta(minutes=20)
    imd_rec.severity = "NORMAL"

    # Open-Meteo: Live observation
    meteo_rec = MagicMock(spec=OceanObservation)
    meteo_rec.id = 1
    meteo_rec.timestamp = now - timedelta(minutes=40)
    meteo_rec.retrieved_at = now - timedelta(minutes=5)

    # GFW: Cached Historical effort
    gfw_rec = MagicMock(spec=GFWFishingEffort)
    gfw_rec.id = 1
    gfw_rec.observation_date = now - timedelta(days=7)
    gfw_rec.retrieved_at = now - timedelta(days=1)

    # Setup mock session executing these in sequence
    mock_db = AsyncMock()

    def mock_execute(stmt):
        stmt_str = str(stmt).lower()
        mock_res = MagicMock()
        mock_scalars = MagicMock()
        
        if "incois_pfz_advisories" in stmt_str or "incoispfz" in stmt_str:
            if "count" in stmt_str:
                mock_res.scalar.return_value = 8
            else:
                mock_scalars.first.return_value = incois_rec
                mock_scalars.all.return_value = [incois_rec]
        elif "marine_warning" in stmt_str or "marinewarning" in stmt_str:
            if "count" in stmt_str:
                mock_res.scalar.return_value = 2
            else:
                mock_scalars.first.return_value = imd_rec
                mock_scalars.all.return_value = [imd_rec]
        elif "ocean_observation" in stmt_str or "oceanobservation" in stmt_str:
            if "count" in stmt_str:
                mock_res.scalar.return_value = 171
            else:
                mock_scalars.first.return_value = meteo_rec
                mock_scalars.all.return_value = [meteo_rec]
        elif "gfw_fishing_effort" in stmt_str or "gfwfishingeffort" in stmt_str:
            if "count" in stmt_str:
                mock_res.scalar.return_value = 171
            else:
                mock_scalars.first.return_value = gfw_rec
                mock_scalars.all.return_value = [gfw_rec]
        else:
            mock_res.scalar.return_value = 1
            mock_scalars.first.return_value = None
            mock_scalars.all.return_value = []

        mock_res.scalars.return_value = mock_scalars
        return mock_res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        resp_populated = client.get("/api/v1/sources/freshness")
        print(f"Populated Freshness Status Code: {resp_populated.status_code}")
        print(json.dumps(resp_populated.json(), indent=2))

        resp_map_pop = client.get("/api/v1/map/summary?demo=true")
        print(f"\nPopulated Map Summary Status Code: {resp_map_pop.status_code}")
        print("Map Summary Source Freshness Metadata:")
        print(json.dumps(resp_map_pop.json().get("source_freshness", {}), indent=2))
    finally:
        app.dependency_overrides.clear()

if __name__ == "__main__":
    main()
