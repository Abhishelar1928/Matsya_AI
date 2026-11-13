"""
MatsyaAI Maharashtra — Source Ingestion CLI & Daemon.

Usage:
  python backend/scripts/run_ingestion.py --source incois_pfz
  python backend/scripts/run_ingestion.py --source all
  python backend/scripts/run_ingestion.py --daemon
"""

import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add project root to python path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from backend.app.core.config import settings
from backend.app.core.database import async_session
from backend.app.services.ingestion.ingestion_runner import IngestionRunner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_single_source(source_name: str) -> int:
    """Runs a single execution and returns exit code."""
    runner = IngestionRunner()
    
    async with async_session() as db:
        if source_name == "incois_pfz":
            res = await runner.run_incois(db)
        elif source_name == "imd_marine_warnings":
            res = await runner.run_imd(db)
        elif source_name == "open_meteo_marine":
            res = await runner.run_open_meteo(db)
        elif source_name == "gfw":
            res = await runner.run_gfw(db)
        elif source_name == "predictions":
            res = await runner.run_predictions(db)
        elif source_name == "all":
            res = await runner.run_all(db)
        else:
            logger.error(f"Unknown source: {source_name}")
            return 1
            
        print(json.dumps(res, indent=2))
        
        # Determine exit code based on structured result
        if source_name == "all":
            for s_name, s_res in res.get("sources", {}).items():
                if s_res.get("status") == "ERROR":
                    return 1
        else:
            if res.get("status") == "ERROR":
                return 1
                
        return 0

async def daemon_loop():
    """Runs a lightweight asyncio scheduling loop for continuous ingestion."""
    logger.info("Starting Ingestion Scheduler Daemon...")
    runner = IngestionRunner()
    
    # State tracking
    last_run = {
        "incois_pfz": datetime.min.replace(tzinfo=timezone.utc),
        "imd_marine_warnings": datetime.min.replace(tzinfo=timezone.utc),
        "open_meteo_marine": datetime.min.replace(tzinfo=timezone.utc),
        "gfw": datetime.min.replace(tzinfo=timezone.utc),
        "predictions": datetime.min.replace(tzinfo=timezone.utc),
    }
    
    intervals = {
        "incois_pfz": settings.INCOIS_PFZ_INTERVAL_MINUTES,
        "imd_marine_warnings": settings.IMD_MARINE_INTERVAL_MINUTES,
        "open_meteo_marine": settings.OPEN_METEO_INTERVAL_MINUTES,
        "gfw": settings.GFW_CONTEXT_INTERVAL_MINUTES,
        "predictions": int(getattr(settings, "PREDICTIONS_INTERVAL_MINUTES", 360)),
    }
    
    logger.info(f"Scheduler intervals configured: {intervals}")
    
    while True:
        now = datetime.now(timezone.utc)
        
        async with async_session() as db:
            # 1. Check INCOIS
            if (now - last_run["incois_pfz"]).total_seconds() >= intervals["incois_pfz"] * 60:
                logger.info("Executing scheduled job: INCOIS PFZ")
                res = await runner.run_incois(db)
                if res.get("status") != "ERROR":
                    last_run["incois_pfz"] = datetime.now(timezone.utc)
                else:
                    logger.error(f"INCOIS job failed: {res.get('error')}")

            # 2. Check IMD
            if (now - last_run["imd_marine_warnings"]).total_seconds() >= intervals["imd_marine_warnings"] * 60:
                logger.info("Executing scheduled job: IMD Marine Warnings")
                res = await runner.run_imd(db)
                if res.get("status") != "ERROR":
                    last_run["imd_marine_warnings"] = datetime.now(timezone.utc)
                else:
                    logger.error(f"IMD job failed: {res.get('error')}")
                    
            # 3. Check Open-Meteo
            if (now - last_run["open_meteo_marine"]).total_seconds() >= intervals["open_meteo_marine"] * 60:
                logger.info("Executing scheduled job: Open-Meteo")
                res = await runner.run_open_meteo(db)
                if res.get("status") != "ERROR":
                    last_run["open_meteo_marine"] = datetime.now(timezone.utc)
                    
            # 4. Check GFW
            if (now - last_run["gfw"]).total_seconds() >= intervals["gfw"] * 60:
                logger.info("Executing scheduled job: GFW Historical Cache")
                res = await runner.run_gfw(db)
                if res.get("status") != "ERROR":
                    last_run["gfw"] = datetime.now(timezone.utc)
                    
            # 5. Check Predictions
            if (now - last_run["predictions"]).total_seconds() >= intervals["predictions"] * 60:
                logger.info("Executing scheduled job: Prediction Batch")
                res = await runner.run_predictions(db)
                if res.get("status") != "ERROR":
                    last_run["predictions"] = datetime.now(timezone.utc)
                else:
                    logger.error(f"Prediction Batch failed: {res.get('error')}")
        
        # Sleep for a short interval before checking again
        await asyncio.sleep(60)

def main():
    parser = argparse.ArgumentParser(description="MatsyaAI Source Ingestion CLI")
    parser.add_argument(
        "--source", 
        type=str, 
        choices=["incois_pfz", "imd_marine_warnings", "open_meteo_marine", "gfw", "predictions", "all"],
        default="all",
        help="Source to ingest"
    )
    parser.add_argument(
        "--daemon", 
        action="store_true", 
        help="Run continuously as a background scheduling daemon"
    )
    
    args = parser.parse_args()
    
    if args.daemon:
        try:
            asyncio.run(daemon_loop())
        except KeyboardInterrupt:
            logger.info("Daemon gracefully shut down by user.")
    else:
        exit_code = asyncio.run(run_single_source(args.source))
        sys.exit(exit_code)

if __name__ == "__main__":
    main()
