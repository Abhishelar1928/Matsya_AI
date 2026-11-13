import pytest
from datetime import datetime, timezone
import os
from sqlalchemy import select

from backend.app.core.database import async_session
from backend.app.models.ocean_observation import OceanObservation
from backend.app.services.ingestion.base import ProviderStatus
from backend.app.services.ingestion.providers import (
    IncoisOsfProvider,
    IncoisPfzProvider,
    ImdMarineProvider,
    OpenMeteoMarineProvider
)
from backend.app.services.ingestion.pipeline import IngestionPipeline

pytestmark = pytest.mark.asyncio(loop_scope="session")

async def test_stub_providers():
    osf = IncoisOsfProvider()
    pfz = IncoisPfzProvider()
    
    assert osf.status == ProviderStatus.STUB
    assert pfz.status == ProviderStatus.STUB
    
    osf_records = await osf.execute()
    assert osf_records == []
    
    pfz_records = await pfz.execute()
    assert pfz_records == []

async def test_authenticated_provider_disabled_without_keys():
    if "IMD_API_KEY" in os.environ:
        del os.environ["IMD_API_KEY"]
        
    imd = ImdMarineProvider()
    assert imd.status == ProviderStatus.AUTHENTICATED
    assert imd.has_credentials() is False
    
    records = await imd.execute()
    assert records == []

async def test_open_meteo_live_provider_integration(db_session=None):
    # Test the LIVE provider directly
    # Using specific coords for Maharashtra
    provider = OpenMeteoMarineProvider(coordinates=[(19.0, 72.8), (17.0, 73.2)])
    assert provider.status == ProviderStatus.LIVE
    
    records = await provider.execute()
    
    # Check that we got results
    assert len(records) == 2
    
    # Check provenance
    r1 = records[0]
    assert r1['source_name'] == 'Open-Meteo'
    assert r1['dataset_name'] == 'Marine_Global_Models'
    assert abs(r1['latitude'] - 19.0) < 0.1
    assert abs(r1['longitude'] - 72.8) < 0.1
    assert r1['data_quality_status'] == 'VALID'
    assert 'wave_height' in r1
    
    # Check filtering (outside Maharashtra)
    bad_provider = OpenMeteoMarineProvider(coordinates=[(50.0, 50.0)])
    bad_records = await bad_provider.execute()
    assert len(bad_records) == 0

async def test_pipeline_execution():
    async with async_session() as db_session:
        pipeline = IngestionPipeline(session=db_session)
        
        # OpenMeteo provider is live, others are stubs/disabled
        total_ingested = await pipeline.run()
        
        # It fetches 3 coordinates by default
        assert total_ingested == 3
        
        # Verify persistence
        result = await db_session.execute(select(OceanObservation))
        observations = result.scalars().all()
        assert len(observations) >= 3
        
        # Verify properties on a stored record
        obs = observations[-1]
        assert obs.source_name == 'Open-Meteo'
        assert obs.is_stale is False  # Because it's live data
        assert obs.wave_height is not None
        assert obs.spatial_resolution == '0.08 degree'

async def test_freshness_check():
    pipeline = IngestionPipeline(session=None)
    now = datetime.now(timezone.utc)
    
    records = [
        {'source_publication_time': now},
        {'source_publication_time': datetime(2020, 1, 1, tzinfo=timezone.utc)},
        {}
    ]
    
    processed = pipeline._calculate_freshness(records)
    
    assert processed[0]['is_stale'] is False
    assert processed[1]['is_stale'] is True
    assert processed[2]['is_stale'] is True
