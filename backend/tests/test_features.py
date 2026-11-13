import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.core.database import async_session
from backend.app.models.feature import SpatialGrid, ModelFeature
from backend.app.services.features.pipeline import FeatureEngineeringPipeline

pytestmark = pytest.mark.asyncio(loop_scope="session")

async def test_spatial_grid_generation(db_session=None):
    async with async_session() as session:
        # Generate 0.5 degree grid for testing speed
        pipeline = FeatureEngineeringPipeline(session=session, resolution=0.5)
        grids = await pipeline._ensure_grid_exists()
        
        # Lat: 15.5 to 20.2 (approx 10 steps)
        # Lon: 72.0 to 74.0 (approx 5 steps)
        # Expected around 50 cells
        assert len(grids) > 0
        assert grids[0].resolution == 0.5
        assert "cell_" in grids[0].id
        
        # Idempotency check: calling again shouldn't duplicate
        grids2 = await pipeline._ensure_grid_exists()
        assert len(grids) == len(grids2)

async def test_feature_pipeline_execution(db_session=None):
    async with async_session() as session:
        # Run pipeline
        pipeline = FeatureEngineeringPipeline(session=session, resolution=0.5)
        num_features = await pipeline.run()
        
        # Verify persistence
        assert num_features > 0
        
        result = await session.execute(select(ModelFeature).limit(1))
        feature = result.scalars().first()
        
        assert feature is not None
        # Verify schema
        assert feature.grid_cell_id is not None
        assert feature.hour >= 0 and feature.hour <= 23
        assert feature.day_of_year >= 1 and feature.day_of_year <= 366
        assert feature.season in ["Monsoon", "Pre-Monsoon/Summer", "Post-Monsoon/Winter"]
        
        # Verify missing data explicitly tracked
        # (Since we didn't inject wind_speed, it should be NULL)
        assert feature.wind_speed is None
        assert feature.sst is None
        
        if feature.is_valid:
            assert feature.provenance != "MISSING"
        else:
            assert feature.provenance == "MISSING"
