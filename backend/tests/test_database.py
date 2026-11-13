import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.landing_centre import LandingCentre, DistrictEnum

from backend.app.core.database import async_session

pytestmark = pytest.mark.asyncio(loop_scope="session")

async def test_postgis_spatial_query():
    """
    Test that PostGIS functions like ST_Distance work correctly via GeoAlchemy2.
    """
    async with async_session() as db_session:
        # Insert a temporary test point
        test_centre = LandingCentre(
            name="Test Point",
            district=DistrictEnum.MUMBAI,
            latitude=19.0,
            longitude=72.8,
            geom="POINT(72.8 19.0)",
            source="TEST_DATA"
        )
        db_session.add(test_centre)
        await db_session.commit()

        # Query using ST_Distance from a point nearby (72.8, 18.9)
        # The distance should be roughly 0.1 degrees
        query = select(
            LandingCentre,
            func.ST_Distance(LandingCentre.geom, func.ST_GeomFromText('POINT(72.8 18.9)', 4326)).label('distance')
        ).where(
            LandingCentre.name == "Test Point"
        )
        
        result = await db_session.execute(query)
        row = result.first()
        
        assert row is not None
        centre, distance = row
        
        assert centre.name == "Test Point"
        assert centre.district == DistrictEnum.MUMBAI
        
        # Check that distance was calculated and is approx 0.1 degrees
        assert abs(distance - 0.1) < 0.01

        # Cleanup
        await db_session.delete(test_centre)
        await db_session.commit()
