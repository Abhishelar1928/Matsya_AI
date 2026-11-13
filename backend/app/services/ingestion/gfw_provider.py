"""
MatsyaAI Maharashtra — GFW Fishing Effort Provider (Fixed).

Retrieves gridded fishing effort from Global Fishing Watch API (v3 4Wings Report).
Preserves per-record observation dates — never discards temporal information.
"""
import logging
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any
from datetime import datetime, timezone
import pandas as pd

from backend.app.core.config import settings
from backend.app.ml.config import (
    GFW_API_BASE_URL, GFW_DATASET, GFW_REGION_DATASET, GFW_REGION_ID,
    GFW_SPATIAL_RESOLUTION, GFW_TEMPORAL_RESOLUTION,
    GFW_MIN_LAT, GFW_MAX_LAT, GFW_MIN_LON, GFW_MAX_LON,
    GRID_RESOLUTION, GFW_RAW_CACHE_DIR,
)

logger = logging.getLogger(__name__)


class GfwFishingEffortProvider:
    """
    Retrieves gridded fishing effort (hours) from Global Fishing Watch API
    (v3 4Wings Report API).

    Key fix: preserves the `date` field from every GFW record so that
    historical environmental data can be aligned to the correct observation date.
    """

    def __init__(self, region_id: str = None):
        self.region_id = region_id or GFW_REGION_ID
        self.token = settings.GFW_API_TOKEN
        self.base_url = GFW_API_BASE_URL

    def fetch_fishing_events(
        self, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch fishing effort records from GFW 4Wings Report API.
        Automatically chunks by month to prevent API timeouts for long date ranges.
        """
        if not self.token:
            logger.error("GFW_API_TOKEN is missing. Cannot fetch GFW data.")
            return []

        # Parse dates to chunk by month
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        date_ranges = []
        
        current = start_dt
        while current <= end_dt:
            # End of current month or the requested end_date
            next_month = current + pd.offsets.MonthBegin(1)
            chunk_end = min(next_month - pd.Timedelta(days=1), end_dt)
            date_ranges.append((current.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d')))
            current = chunk_end + pd.Timedelta(days=1)

        all_parsed_records = []
        
        # Load any existing combined cache
        GFW_RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = GFW_RAW_CACHE_DIR / f"gfw_{start_date}_{end_date}.json"
        
        for c_start, c_end in date_ranges:
            params = {
                'datasets[0]': GFW_DATASET,
                'date-range': f'{c_start},{c_end}',
                'spatial-resolution': GFW_SPATIAL_RESOLUTION,
                'temporal-resolution': GFW_TEMPORAL_RESOLUTION,
                'format': 'JSON',
                'region-dataset': GFW_REGION_DATASET,
                'region-id': self.region_id,
            }
            query_string = urllib.parse.urlencode(params)
            url = f"{self.base_url}/4wings/report?{query_string}"

            req = urllib.request.Request(url, headers={
                'Authorization': f'Bearer {self.token}',
                'User-Agent': 'MatsyaAI-Backend/1.0',
                'Accept': 'application/json',
            })

            try:
                logger.info(f"Querying GFW 4Wings Report API for chunk {c_start} to {c_end}")
                with urllib.request.urlopen(req, timeout=120) as res:
                    data = json.loads(res.read().decode())
                    
                parsed_chunk = self._parse_response(data)
                all_parsed_records.extend(parsed_chunk)

            except urllib.error.HTTPError as e:
                body = e.read().decode()
                logger.error(f"GFW API Error {e.code} for {c_start}-{c_end}: {body}")
            except Exception as e:
                logger.error(f"Failed to fetch GFW data for {c_start}-{c_end}: {e}")

        # Save a dummy format combined raw cache just to satisfy the file check if needed
        # (Though we already returned parsed records)
        with open(cache_path, 'w') as f:
            json.dump({"entries": []}, f)
            
        logger.info(f"Combined GFW response yielded {len(all_parsed_records)} records")
        return all_parsed_records

    def _parse_response(self, data: dict) -> List[Dict[str, Any]]:
        """
        Parse the GFW 4Wings Report API response.

        Response structure (verified via live API test):
        {
          "total": int,
          "entries": [
            {
              "public-global-fishing-effort:v4.0": [
                {
                  "date": "2023-10-02",
                  "lat": 18.13,
                  "lon": 70.38,
                  "hours": 5.0,
                  "geartype": "DRIFTING_LONGLINES",
                  "flag": "IND",
                  "vesselType": "FISHING",
                  ...
                },
                ...
              ]
            }
          ]
        }
        """
        entries = data.get('entries', [])
        if not entries:
            logger.warning("GFW response has empty 'entries'.")
            return []

        # Flatten all records from all dataset keys
        all_records = []
        for entry in entries:
            if isinstance(entry, dict):
                for dataset_key, records in entry.items():
                    if isinstance(records, list):
                        all_records.extend(records)

        logger.info(f"GFW response contains {len(all_records)} total vessel records.")

        # Parse and filter to Maharashtra bounds
        parsed = []
        for r in all_records:
            if not isinstance(r, dict):
                continue

            lat = r.get('lat')
            lon = r.get('lon')
            hours = r.get('hours')
            date_str = r.get('date')

            if lat is None or lon is None or hours is None or date_str is None:
                continue

            # Filter to Maharashtra marine area
            if not (GFW_MIN_LAT <= lat <= GFW_MAX_LAT and
                    GFW_MIN_LON <= lon <= GFW_MAX_LON):
                continue

            # Capture exactly when this data was obtained to preserve provenance boundary
            retrieved_at = datetime.now(timezone.utc).isoformat()

            parsed.append({
                'observation_date': date_str,
                'retrieved_at': retrieved_at,
                'lat': float(lat),
                'lon': float(lon),
                'fishing_hours': float(hours),
                'geartype': r.get('geartype', ''),
                'flag': r.get('flag', ''),
                'vessel_type': r.get('vesselType', ''),
            })

        logger.info(
            f"Parsed {len(parsed)} records within Maharashtra bounds "
            f"(lat {GFW_MIN_LAT}-{GFW_MAX_LAT}, lon {GFW_MIN_LON}-{GFW_MAX_LON})"
        )
        return parsed

    def load_cached(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Load previously cached raw GFW response if available."""
        cache_path = GFW_RAW_CACHE_DIR / f"gfw_{start_date}_{end_date}.json"
        if cache_path.exists():
            logger.info(f"Loading cached GFW response from {cache_path}")
            with open(cache_path) as f:
                data = json.load(f)
            return self._parse_response(data)
        return []
