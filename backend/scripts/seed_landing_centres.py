import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import async_session
from backend.app.models.landing_centre import LandingCentre, DistrictEnum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_SOURCE = "MOCK_DEVELOPMENT_DATA"

mock_landing_centres = [
    {"name": "Satpati", "district": DistrictEnum.PALGHAR, "latitude": 19.7258, "longitude": 72.7058},
    {"name": "Arnala", "district": DistrictEnum.PALGHAR, "latitude": 19.4589, "longitude": 72.7483},
    {"name": "Sassoon Dock", "district": DistrictEnum.MUMBAI, "latitude": 18.9172, "longitude": 72.8258},
    {"name": "Versova", "district": DistrictEnum.MUMBAI, "latitude": 19.1334, "longitude": 72.8146},
    {"name": "Alibag", "district": DistrictEnum.RAIGAD, "latitude": 18.6416, "longitude": 72.8722},
    {"name": "Murud", "district": DistrictEnum.RAIGAD, "latitude": 18.3269, "longitude": 72.9645},
    {"name": "Mirkarwada", "district": DistrictEnum.RATNAGIRI, "latitude": 16.9958, "longitude": 73.2758},
    {"name": "Harnai", "district": DistrictEnum.RATNAGIRI, "latitude": 17.8131, "longitude": 73.0908},
    {"name": "Malvan", "district": DistrictEnum.SINDHUDURG, "latitude": 16.0632, "longitude": 73.4682},
    {"name": "Vengurla", "district": DistrictEnum.SINDHUDURG, "latitude": 15.8617, "longitude": 73.6267},
]

async def seed_landing_centres():
    async with async_session() as session:
        # Check if already seeded
        result = await session.execute(select(LandingCentre).limit(1))
        existing = result.scalars().first()
        
        if existing:
            logger.info("Landing centres already seeded. Skipping.")
            return

        logger.info("Seeding mock landing centres...")
        for data in mock_landing_centres:
            # Create WKT point format 'POINT(lon lat)'
            geom_wkt = f"POINT({data['longitude']} {data['latitude']})"
            
            centre = LandingCentre(
                name=data["name"],
                district=data["district"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                geom=geom_wkt,
                source=MOCK_SOURCE
            )
            session.add(centre)
            
        await session.commit()
        logger.info(f"Successfully seeded {len(mock_landing_centres)} mock landing centres.")

if __name__ == "__main__":
    asyncio.run(seed_landing_centres())
