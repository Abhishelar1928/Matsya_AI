"""
MatsyaAI Maharashtra — Predictions Batch CLI.

Usage:
  python backend/scripts/run_predictions.py
  python backend/scripts/run_predictions.py --help
"""

import sys
import json
import logging
import asyncio
import argparse
from pathlib import Path

# Add project root to python path
root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root))

from backend.app.core.database import async_session
from backend.app.services.ingestion.ingestion_runner import IngestionRunner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_predictions_batch() -> int:
    """Runs a single prediction execution and returns exit code."""
    runner = IngestionRunner()
    
    async with async_session() as db:
        res = await runner.run_predictions(db)
            
        print(json.dumps(res, indent=2))
        
        if res.get("status") == "ERROR":
            return 1
                
        return 0

def main():
    parser = argparse.ArgumentParser(description="MatsyaAI Predictions Batch CLI")
    args = parser.parse_args()
    
    exit_code = asyncio.run(run_predictions_batch())
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
