"""
Standalone ingestion script for official IMD Mumbai Fishermen Warning bulletin.
"""

import sys
import logging
import asyncio
from pathlib import Path

# Add project root to path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from backend.app.core.database import async_session
from backend.app.services.ingestion.imd_marine_provider import IMDMarineProvider

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting IMD Marine Fishermen Warning ingestion...")
    provider = IMDMarineProvider()
    
    # 1. Test live fetch
    logger.info("Fetching official bulletin from IMD Mumbai...")
    res = await provider.fetch_latest_bulletin()
    
    logger.info(f"Fetch Status: {res.get('status')}")
    logger.info(f"Bulletin Issue Timestamp: {res.get('issue_timestamp')}")
    logger.info(f"Validity Period: {res.get('valid_from')} to {res.get('valid_until')}")
    logger.info(f"Total Warnings Parsed: {res.get('count')}")
    if res.get("errors"):
        logger.error(f"Errors: {res.get('errors')}")

    for idx, w in enumerate(res.get("warnings", [])):
        logger.info(f"  Warning {idx+1}: [{w['region']}] Type={w['warning_type']}, Severity={w['severity']}")
        logger.info(f"    Text: {w['text'][:120]}...")

    # 2. Ingestion with database session
    try:
        async with async_session() as db:
            logger.info("Ingesting into database...")
            ingest_res = await provider.ingest_latest_bulletin(db)
            logger.info(f"Ingestion outcome: status={ingest_res.get('status')}, count={ingest_res.get('count')}")
    except Exception as e:
        logger.warning(f"Database session not available or error during DB write: {e}")

if __name__ == "__main__":
    asyncio.run(main())
