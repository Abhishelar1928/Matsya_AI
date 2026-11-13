import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.ocean_observation import OceanObservation
from backend.app.services.ingestion.base import BaseProvider
from backend.app.services.ingestion.providers import (
    IncoisOsfProvider,
    IncoisPfzProvider,
    ImdMarineProvider,
    OpenMeteoMarineProvider
)

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.providers: List[BaseProvider] = [
            IncoisOsfProvider(),
            IncoisPfzProvider(),
            ImdMarineProvider(),
            OpenMeteoMarineProvider() # LIVE provider
        ]

    def _calculate_freshness(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Adds is_stale flag based on observation timestamp."""
        now = datetime.now(timezone.utc)
        for record in records:
            obs_time = record.get('source_publication_time')
            if obs_time:
                # If older than 48 hours, mark as stale
                delta = now - obs_time
                record['is_stale'] = delta.total_seconds() > (48 * 3600)
            else:
                record['is_stale'] = True
        return records

    async def run(self):
        """Runs the entire ingestion pipeline across all providers."""
        logger.info("Starting ingestion pipeline execution...")
        total_ingested = 0
        
        for provider in self.providers:
            logger.info(f"Executing {provider.name}...")
            records = await provider.execute()
            
            if not records:
                logger.info(f"No records retrieved from {provider.name}")
                continue
                
            records = self._calculate_freshness(records)
            
            # Route to OceanObservation model
            if provider.name == "OPEN_METEO_MARINE":
                await self.session.execute(insert(OceanObservation).values(records))
                total_ingested += len(records)
            
        await self.session.commit()
        logger.info(f"Ingestion pipeline completed. Total records: {total_ingested}")
        return total_ingested
