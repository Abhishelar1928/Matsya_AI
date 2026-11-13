import sys
import logging
import asyncio
from pathlib import Path

# Add the project root to the python path so imports work when running as script
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from backend.app.core.database import async_session
from backend.app.services.ingestion.incois_pfz_provider import INCOISPFZProvider

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting INCOIS PFZ ingestion process...")
    
    async with async_session() as db:
        try:
            provider = INCOISPFZProvider()
            result = await provider.ingest_latest_maharashtra_pfz(db)
            
            logger.info(f"Ingestion result status: {result.get('status')}")
            if result.get("error"):
                logger.error(f"Ingestion error: {result['error']}")
                
            logger.info(f"Extracted {result.get('record_count', 0)} PFZ records.")
            logger.info(f"Advisory Date: {result.get('advisory_date')}")
            logger.info(f"Validity Date: {result.get('validity_date')}")
            
            # Display first 3 locations as per integration test requirements
            records = result.get("records", [])
            if records:
                logger.info("First 3 extracted coordinates:")
                for i, rec in enumerate(records[:3]):
                    logger.info(f"  {i+1}: Lat={rec.latitude}, Lon={rec.longitude}, LC={rec.landing_centre}")
                    
        except Exception as e:
            logger.exception("Fatal error during PFZ ingestion")
        finally:
            logger.info("PFZ ingestion process finished.")

if __name__ == "__main__":
    asyncio.run(main())
