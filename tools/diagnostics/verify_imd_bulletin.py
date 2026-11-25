import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock
from backend.app.services.ingestion.imd_marine_provider import IMDMarineProvider

async def verify_live():
    provider = IMDMarineProvider()
    print("Fetching live IMD Fisherman bulletin from: https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf")
    
    # 1. Download verification
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        r = await client.get("https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf")
        http_status = r.status_code
        pdf_downloaded = "YES" if http_status == 200 and r.content.startswith(b"%PDF") else "NO"
        pdf_size = len(r.content)
    
    print(f"HTTP status: {http_status}")
    print(f"PDF successfully downloaded: {pdf_downloaded}")
    print(f"PDF size: {pdf_size} bytes")
    
    # 2. Parsing verification
    res = await provider.fetch_latest_bulletin()
    print(f"STATUS: {res['status']}")
    print(f"Extracted issue timestamp: {res['issue_timestamp']}")
    print(f"Extracted validity period: {res['valid_from']} to {res['valid_until']}")
    
    north_w = next((w for w in res["warnings"] if "North Maharashtra Coast" in w["region"]), None)
    south_w = next((w for w in res["warnings"] if "South Maharashtra-Goa Coast" in w["region"]), None)
    high_sea_w = next((w for w in res["warnings"] if "High Sea" in w["region"]), None)
    
    print(f"North Coast warning: [{north_w['severity']}] {north_w['text']}" if north_w else "None")
    print(f"South Coast warning: [{south_w['severity']}] {south_w['text']}" if south_w else "None")
    print(f"High Sea warning: [{high_sea_w['severity']}] {high_sea_w['text'][:140]}..." if high_sea_w else "None")
    print(f"Number of records generated: {res['count']}")
    
    # 3. Database insertion test
    mock_db = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_exec_res
    
    ingest_res = await provider.ingest_latest_bulletin(mock_db)
    print(f"Database insertion result: Status = {ingest_res['status']}, Added = {mock_db.add_all.call_count} batch(es) ({len(mock_db.add_all.call_args[0][0])} records)")

if __name__ == "__main__":
    asyncio.run(verify_live())
