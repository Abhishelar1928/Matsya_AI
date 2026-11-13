import os
import urllib.request
import json
from datetime import datetime, timezone
from typing import Any, List, Dict
import logging

from backend.app.services.ingestion.base import BaseProvider, ProviderStatus

logger = logging.getLogger(__name__)

class IncoisOsfProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "INCOIS_OSF_PROVIDER"

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.STUB

    async def fetch_data(self) -> Any:
        return None

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return []

class IncoisPfzProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "INCOIS_PFZ_PROVIDER"

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.STUB

    async def fetch_data(self) -> Any:
        return None

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return []

class ImdMarineProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "IMD_MARINE_PROVIDER"

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.AUTHENTICATED

    def has_credentials(self) -> bool:
        return bool(os.getenv("IMD_API_KEY"))

    async def fetch_data(self) -> Any:
        return None

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return []

class OpenMeteoMarineProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "OPEN_METEO_MARINE"

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.LIVE

    def __init__(self, coordinates: List[tuple[float, float]] = None):
        # Default to Maharashtra coast representative points if not provided
        # (Mumbai, Ratnagiri, Malvan)
        self.coordinates = coordinates or [(19.0, 72.8), (17.0, 73.2), (16.0, 73.4)]

    async def fetch_data(self) -> Any:
        lats = ",".join(str(lat) for lat, lon in self.coordinates)
        lons = ",".join(str(lon) for lat, lon in self.coordinates)
        
        url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}&current=wave_height,wave_period&timezone=UTC"
        logger.info(f"Fetching Open-Meteo data for {len(self.coordinates)} locations...")
        
        req = urllib.request.Request(url, headers={'User-Agent': 'MatsyaAI/1.0'})
        res = urllib.request.urlopen(req, timeout=15)
        return json.loads(res.read().decode())

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        if not raw_data:
            return []
            
        # Open-Meteo returns a list if multiple coordinates, or a dict for a single coordinate
        if isinstance(raw_data, dict):
            raw_data = [raw_data]
            
        records = []
        retrieved_at = datetime.now(timezone.utc)
        
        for data in raw_data:
            if 'current' not in data:
                continue
                
            current = data['current']
            # Time is iso8601 string, e.g., '2026-09-03T03:00'
            try:
                # Open-Meteo returns time in UTC since we requested timezone=UTC
                source_timestamp = datetime.fromisoformat(current['time']).replace(tzinfo=timezone.utc)
            except ValueError:
                source_timestamp = retrieved_at
                
            # Create WKT point format
            lat, lon = data['latitude'], data['longitude']
            geom_wkt = f"POINT({lon} {lat})"
            
            record = {
                "source_name": "Open-Meteo",
                "dataset_name": "Marine_Global_Models",
                "latitude": lat,
                "longitude": lon,
                "geom": geom_wkt,
                "wave_height": current.get('wave_height'),
                "wave_period": current.get('wave_period'),
                "source_publication_time": source_timestamp,
                "retrieved_at": retrieved_at,
                "spatial_resolution": "0.08 degree",
                "temporal_resolution": "hourly",
                "data_quality_status": "VALID",
                "timestamp": source_timestamp 
            }
            records.append(record)
            
        return records

    def validate_data(self, parsed_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        valid = []
        for r in parsed_data:
            # Basic geographic filtering for Maharashtra Coast bounds
            # Roughly Lat 15.5 to 20.2, Lon 72.0 to 74.0
            if 15.5 <= r['latitude'] <= 20.2 and 72.0 <= r['longitude'] <= 74.0:
                valid.append(r)
            else:
                logger.warning(f"Record filtered out: outside Maharashtra bounds (Lat {r['latitude']}, Lon {r['longitude']})")
        return valid
