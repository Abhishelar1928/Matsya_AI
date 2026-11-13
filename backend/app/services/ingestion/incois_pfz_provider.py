"""
INCOIS PFZ (Potential Fishing Zone) Provider

Consumes the official INCOIS TextData web endpoints to retrieve
Potential Fishing Zone advisory data for Maharashtra.

Endpoints:
- Session Init: https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en
- Maharashtra Data: https://incois.gov.in/MarineFisheries/TextData?secid=SEC002

Data source:
  - Official TextData HTML tables.

Access: Public, requires JSESSIONID cookie acquired via TextDataHome.

IMPORTANT: 
- Strict freshness validation is applied.
- Rejects missing tables or redirected generic pages.
- Coordinates are validated to ensure geographic plausibility for Maharashtra.
- Normalizes into incois_pfz_advisories and pfz_zones tables.
- Batch deduplication prevents duplicate records on repeated ingestion runs.
- Handles unavailable official source by retaining last valid data and marking it stale.
"""

import logging
import asyncio
import re
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, update

from backend.app.services.ingestion.base import BaseProvider, ProviderStatus
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.models.pfz_zone import PFZZone


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INCOIS_BASE_URL = "https://incois.gov.in"
TEXT_DATA_HOME_URL = f"{INCOIS_BASE_URL}/MarineFisheries/TextDataHome?mfid=1&request_locale=en"
TEXT_DATA_MAHARASHTRA_URL = f"{INCOIS_BASE_URL}/MarineFisheries/TextData?secid=SEC002"

# Request configuration
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# Maharashtra bounds (very broad sanity check to not reject offshore)
MH_LAT_MIN, MH_LAT_MAX = 10.0, 25.0
MH_LON_MIN, MH_LON_MAX = 65.0, 80.0

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PFZRecord:
    landing_centre: str
    direction: str
    bearing_degrees: int
    distance_km: str
    depth_min_m: Optional[int]
    depth_max_m: Optional[int]
    latitude: float
    longitude: float


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class INCOISPFZProvider(BaseProvider):
    """
    Fetches Potential Fishing Zone advisory data from INCOIS TextData endpoints.
    Includes strict freshness validation, robust DMS coordinate parsing,
    dual-table normalization, deterministic deduplication, and stale fallback.
    """

    def __init__(self):
        self._current_status = ProviderStatus.LIVE

    @property
    def name(self) -> str:
        return "INCOIS-PFZ-TEXTDATA"

    @property
    def status(self) -> ProviderStatus:
        return self._current_status
        
    async def fetch_data(self) -> Any:
        return await self.fetch_latest_maharashtra_pfz()
        
    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return []

    async def _fetch_with_retry(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """Fetch an endpoint with exponential backoff for errors and retries."""
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(url)
                
                # Server busy or rate-limited
                if response.status_code in (500, 502, 503, 504, 429):
                    wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        f"[{self.name}] HTTP {response.status_code} on {url} (Attempt {attempt}/{MAX_RETRIES}). "
                        f"Retrying in {wait}s..."
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(wait)
                        continue

                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = e
                wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(f"[{self.name}] Network/Timeout exception on {url} (Attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
            except httpx.HTTPStatusError as e:
                logger.error(f"[{self.name}] HTTP {e.response.status_code} error on {url}")
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError(f"[{self.name}] Failed request to {url} after {MAX_RETRIES} attempts.")

    def parse_dms(self, dms_str: str) -> Optional[float]:
        """
        Robustly parses a DMS string into decimal degrees.
        Handles variations like:
          - '15 45 28 N'
          - '20 1 35 N'
          - '15°45\'28"N'
          - '71 56 39 E'
          - '  15  45  28  N  '
        """
        if not dms_str or not isinstance(dms_str, str):
            return None
            
        # Ensure space around cardinal letters
        clean_str = re.sub(r'([NSEWnsew])', r' \1 ', dms_str)
        # Replace punctuation/symbols with spaces, leaving digits, dots, and cardinal chars
        clean_str = re.sub(r'[^0-9NSEWnsew\. ]', ' ', clean_str).strip()
        parts = [p for p in clean_str.split() if p]
        
        if len(parts) < 4:
            return None
            
        try:
            # Check if direction is first or last part
            if parts[-1].upper() in ('N', 'S', 'E', 'W'):
                degrees = float(parts[0])
                minutes = float(parts[1])
                seconds = float(parts[2])
                direction = parts[3].upper()
            elif parts[0].upper() in ('N', 'S', 'E', 'W'):
                direction = parts[0].upper()
                degrees = float(parts[1])
                minutes = float(parts[2])
                seconds = float(parts[3])
            else:
                return None
            
            decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
            if direction in ('S', 'W'):
                decimal = -decimal
                
            return decimal
        except (ValueError, IndexError):
            return None

    def parse_depth(self, depth_str: str) -> Tuple[Optional[int], Optional[int]]:
        """Parses depth range or single integer depth in metres."""
        if not depth_str:
            return None, None
        clean = depth_str.replace(' ', '').strip()
        if '-' in clean:
            parts = clean.split('-')
            try:
                return int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                pass
        else:
            try:
                val = int(clean)
                return val, val
            except ValueError:
                pass
        return None, None
        
    def _extract_advisory_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extracts the advisory date from #updatedDate or anywhere in the HTML."""
        date_elem = soup.find(id="updatedDate")
        candidate_texts = []
        if date_elem:
            candidate_texts.append(date_elem.get_text(strip=True))
        
        # Fallback to general soup text if not found
        candidate_texts.append(soup.get_text())

        for text in candidate_texts:
            # Pattern 1: "Sun Sep 06 16:18:49 IST 2026" or "Thu Sep 10 15:30:56 IST 2026"
            match = re.search(
                r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+\d{2}:\d{2}:\d{2}.*?(\d{4})\b',
                text,
                re.IGNORECASE
            )
            if match:
                try:
                    date_str = f"{match.group(2)} {match.group(1)} {match.group(3)}"
                    return datetime.strptime(date_str, "%d %b %Y").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            
            # Pattern 2: "10 Sep 2026" or "06-Sep-2026"
            match2 = re.search(
                r'\b(\d{1,2})[\s\-\/]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-\/]+(\d{4})\b',
                text,
                re.IGNORECASE
            )
            if match2:
                try:
                    date_str = f"{match2.group(1)} {match2.group(2)} {match2.group(3)}"
                    return datetime.strptime(date_str, "%d %b %Y").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
                
        return None

    def _extract_validity_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extracts validity date from #satmsg element or page text."""
        msg_elem = soup.find(id="satmsg")
        candidate_texts = []
        if msg_elem:
            candidate_texts.append(msg_elem.get_text(strip=True))
        candidate_texts.append(soup.get_text())

        for text in candidate_texts:
            # e.g. "SATELLITE DATA SHOWS LIKELY AVAILABILITY OF FISH STOCK TILL  11 SEP 2026"
            match = re.search(
                r'TILL\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})',
                text,
                re.IGNORECASE
            )
            if match:
                try:
                    date_str = f"{match.group(1)} {match.group(2)} {match.group(3)}"
                    dt = datetime.strptime(date_str, "%d %b %Y")
                    # Set validity to end of day in UTC (23:59:59) so validity extends across that full day
                    return dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                except ValueError:
                    pass
                
        return None

    async def fetch_latest_maharashtra_pfz(self) -> Dict[str, Any]:
        """
        Fetches the official Maharashtra PFZ advisory (secid=SEC002) from INCOIS.
        Parses genuine table content and returns a structured dictionary.
        """
        retrieved_at = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "status": "ERROR",
            "count": 0,
            "advisory_date": None,
            "validity_date": None,
            "retrieved_at": retrieved_at,
            "errors": [],
            # Backward compatibility aliases
            "source": "INCOIS",
            "sector": "Maharashtra",
            "record_count": 0,
            "records": [],
            "error": None
        }
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, verify=False) as client:
            try:
                # Step 1: Initialize session on TextDataHome
                try:
                    home_resp = await self._fetch_with_retry(client, TEXT_DATA_HOME_URL)
                except Exception as e:
                    logger.error(f"[{self.name}] Failed to reach INCOIS session init: {e}")
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = [f"Failed to reach INCOIS session init: {str(e)}"]
                    result["error"] = result["errors"][0]
                    return result
                
                if not client.cookies.get('JSESSIONID'):
                    logger.error(f"[{self.name}] No JSESSIONID cookie received from TextDataHome.")
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = ["Missing session cookie"]
                    result["error"] = "Missing session cookie"
                    return result
                    
                # Step 2: Fetch Maharashtra PFZ TextData (secid=SEC002)
                try:
                    data_resp = await self._fetch_with_retry(client, TEXT_DATA_MAHARASHTRA_URL)
                except Exception as e:
                    logger.error(f"[{self.name}] Failed to fetch Maharashtra PFZ data: {e}")
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = [f"Failed to fetch Maharashtra PFZ data: {str(e)}"]
                    result["error"] = result["errors"][0]
                    return result
                
                if data_resp.status_code in (301, 302, 303, 307, 308) or 'MarineFisheryAdvisory' in data_resp.headers.get('Location', ''):
                    logger.warning(f"[{self.name}] Redirected to generic page. Data might be unavailable or session invalid.")
                    result["status"] = "STALE"
                    result["errors"] = ["Redirected to generic advisory page"]
                    result["error"] = "Redirected to generic advisory page"
                    return result
                    
                if data_resp.status_code != 200:
                    result["status"] = "ERROR"
                    result["errors"] = [f"HTTP {data_resp.status_code}"]
                    result["error"] = f"HTTP {data_resp.status_code}"
                    return result

                html_content = data_resp.text
                soup = BeautifulSoup(html_content, 'html.parser')
                
                advisory_date = self._extract_advisory_date(soup)
                validity_date = self._extract_validity_date(soup)
                
                result["advisory_date"] = advisory_date
                result["validity_date"] = validity_date
                
                # Locate advisory table
                pfz_table = None
                tables = soup.find_all('table')
                for table in tables:
                    headers = [th.get_text(strip=True).lower() for th in table.find_all(['th', 'td'])]
                    header_str = " ".join(headers)
                    # Check for signature PFZ table headers
                    if ("direction" in header_str and "bearing" in header_str and "distance" in header_str and "latitude" in header_str) or \
                       ("from the coast" in header_str and "latitude" in header_str):
                        pfz_table = table
                        break
                        
                if not pfz_table:
                    logger.warning(f"[{self.name}] No valid PFZ data table found on page.")
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = ["Table not found"]
                    result["error"] = "Table not found"
                    return result
                    
                records = []
                rows = pfz_table.find_all('tr')
                for row in rows:
                    cols = [c.get_text(strip=True) for c in row.find_all(['th', 'td'])]
                    if len(cols) < 7:
                        continue
                        
                    landing_centre = cols[0]
                    direction = cols[1]
                    bearing_str = cols[2]
                    distance = cols[3]
                    depth_str = cols[4]
                    lat_str = cols[5]
                    lon_str = cols[6]
                    
                    # Filter out header or summary rows
                    if "direction" in direction.lower() or "latitude" in lat_str.lower() or "from the coast" in landing_centre.lower():
                        continue
                        
                    lat_dec = self.parse_dms(lat_str)
                    lon_dec = self.parse_dms(lon_str)
                    
                    if lat_dec is None or lon_dec is None:
                        continue
                        
                    if not (-90 <= lat_dec <= 90 and -180 <= lon_dec <= 180):
                        continue
                        
                    # Broad Maharashtra coastal bounds check
                    if not (MH_LAT_MIN <= lat_dec <= MH_LAT_MAX and MH_LON_MIN <= lon_dec <= MH_LON_MAX):
                        continue
                        
                    depth_min, depth_max = self.parse_depth(depth_str)
                    # Parse bearing safely (handles digits or range)
                    bearing_clean = re.sub(r'[^0-9]', '', bearing_str)
                    bearing = int(bearing_clean) if bearing_clean else 0
                    
                    records.append(PFZRecord(
                        landing_centre=landing_centre,
                        direction=direction,
                        bearing_degrees=bearing,
                        distance_km=distance,
                        depth_min_m=depth_min,
                        depth_max_m=depth_max,
                        latitude=lat_dec,
                        longitude=lon_dec
                    ))

                if not records:
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = ["No valid records extracted"]
                    result["error"] = "No valid records extracted"
                    return result

                # Freshness semantics
                if validity_date and validity_date < result["retrieved_at"]:
                    result["status"] = "STALE"
                elif advisory_date is None and validity_date is None:
                    result["status"] = "UNKNOWN_FRESHNESS"
                else:
                    result["status"] = "SUCCESS"

                result["records"] = records
                result["count"] = len(records)
                result["record_count"] = len(records)
                return result

            except Exception as e:
                logger.exception(f"[{self.name}] Error fetching INCOIS PFZ")
                result["status"] = "ERROR"
                result["errors"] = [str(e)]
                result["error"] = str(e)
                return result

    async def ingest_latest_maharashtra_pfz(self, db: Any) -> Dict[str, Any]:
        """
        Asynchronously fetches and ingests the latest PFZ data into the database.
        Populates incois_pfz_advisories and pfz_zones tables.
        Applies deterministic batch deduplication.
        If official source is unavailable, retains last valid data, marks active records stale,
        and returns explicit error/status.
        """
        result = await self.fetch_latest_maharashtra_pfz()
        
        # Helper for DB async execution (handles AsyncSession and mocks)
        async def _exec_db(stmt):
            res = db.execute(stmt)
            if asyncio.iscoroutine(res):
                return await res
            return res

        async def _commit_db():
            res = db.commit()
            if asyncio.iscoroutine(res):
                await res

        async def _rollback_db():
            res = db.rollback()
            if asyncio.iscoroutine(res):
                await res

        def _add_all_db(items):
            res = db.add_all(items)
            return res

        # Handle unavailable, error, or stale official source
        if result["status"] not in ("SUCCESS", "UNKNOWN_FRESHNESS"):
            logger.warning(
                f"[{self.name}] Official PFZ source returned status {result['status']}. "
                f"Retaining last valid data, marking active records stale."
            )
            if db:
                try:
                    # Retain last valid advisory dates for auditability
                    last_rec_stmt = (
                        select(INCOISPFZAdvisory)
                        .order_by(INCOISPFZAdvisory.retrieved_at.desc())
                        .limit(1)
                    )
                    last_res = await _exec_db(last_rec_stmt)
                    last_rec = last_res.scalars().first() if hasattr(last_res, "scalars") else None
                    if not last_rec and hasattr(last_res, "scalar_one_or_none"):
                        last_rec = last_res.scalar_one_or_none()
                        
                    if last_rec and hasattr(last_rec, "advisory_date"):
                        result["advisory_date"] = result["advisory_date"] or last_rec.advisory_date
                        result["validity_date"] = result["validity_date"] or last_rec.validity_date

                    # Mark existing active INCOIS records in pfz_zones as stale
                    stmt_stale = (
                        update(PFZZone)
                        .where(
                            PFZZone.source_name == "INCOIS",
                            PFZZone.dataset_name == "OFFICIAL_PFZ_ADVISORY",
                            PFZZone.is_stale == False
                        )
                        .values(is_stale=True)
                    )
                    await _exec_db(stmt_stale)
                    await _commit_db()
                except Exception as e:
                    logger.warning(f"[{self.name}] Could not update stale status in DB: {e}")
                    await _rollback_db()

            result["count"] = 0
            result["record_count"] = 0
            return result
            
        logger.info(f"[{self.name}] Extracted {result.get('count', 0)} PFZ records. Status: {result['status']}")
        if result.get("records"):
            logger.info(f"[{self.name}] First 3 extracted coordinates:")
            for i, rec in enumerate(result["records"][:3]):
                logger.info(f"  {i+1}: Lat={rec.latitude}, Lon={rec.longitude}, LC={rec.landing_centre}")
            
        records_to_insert = []
        advisory_date = result["advisory_date"]
        validity_date = result["validity_date"]
        retrieved_at = result["retrieved_at"]
        
        try:
            # Deterministic batch deduplication
            coord_strings = [f"{r.latitude:.6f},{r.longitude:.6f}" for r in result["records"]]
            batch_input = f"SEC002_{advisory_date}_{validity_date}_{'|'.join(coord_strings)}"
            batch_hash = hashlib.sha256(batch_input.encode()).hexdigest()
            
            # Check if this batch has already been ingested using first record's 64-char hash
            first_hash_id = hashlib.sha256(f"{batch_hash}_0".encode()).hexdigest()
            stmt = select(INCOISPFZAdvisory.id).where(INCOISPFZAdvisory.hash_id == first_hash_id)
            existing_batch = await _exec_db(stmt)
            batch_exists = existing_batch.scalar_one_or_none() if hasattr(existing_batch, "scalar_one_or_none") else None
            
            if batch_exists:
                logger.info(f"[{self.name}] Batch already ingested (Batch Hash: {batch_hash}). Skipping duplicate insertion.")
                return result

            # Mark prior INCOIS advisories in pfz_zones as stale before adding fresh batch
            try:
                stmt_retire_old = (
                    update(PFZZone)
                    .where(
                        PFZZone.source_name == "INCOIS",
                        PFZZone.dataset_name == "OFFICIAL_PFZ_ADVISORY",
                        PFZZone.is_stale == False
                    )
                    .values(is_stale=True)
                )
                await _exec_db(stmt_retire_old)
            except Exception as e:
                logger.debug(f"[{self.name}] Note on updating previous zones: {e}")

            is_stale_now = bool(validity_date and validity_date < datetime.now(timezone.utc))
            obs_date = advisory_date.date() if advisory_date else retrieved_at.date()
            
            for idx, rec in enumerate(result["records"]):
                # Fixed 64-character SHA-256 hash for PostgreSQL VARCHAR(64) compatibility
                hash_id = hashlib.sha256(f"{batch_hash}_{idx}".encode()).hexdigest()
                geom = f"SRID=4326;POINT({rec.longitude} {rec.latitude})"
                
                advisory = INCOISPFZAdvisory(
                    source="INCOIS",
                    source_type="OFFICIAL_PFZ_ADVISORY",
                    sector="Maharashtra",
                    landing_centre=rec.landing_centre,
                    direction=rec.direction,
                    bearing_degrees=rec.bearing_degrees,
                    distance_km=str(rec.distance_km),
                    depth_min_m=rec.depth_min_m,
                    depth_max_m=rec.depth_max_m,
                    latitude=rec.latitude,
                    longitude=rec.longitude,
                    geom=geom,
                    advisory_date=advisory_date,
                    validity_date=validity_date,
                    retrieved_at=retrieved_at,
                    source_url=TEXT_DATA_MAHARASHTRA_URL,
                    hash_id=hash_id
                )
                records_to_insert.append(advisory)

                # Populate normalized PFZZone table
                zone = PFZZone(
                    date=obs_date,
                    latitude=rec.latitude,
                    longitude=rec.longitude,
                    geom=geom,
                    depth=float(rec.depth_min_m) if rec.depth_min_m is not None else None,
                    source_name="INCOIS",
                    dataset_name="OFFICIAL_PFZ_ADVISORY",
                    source_timestamp=advisory_date or retrieved_at,
                    retrieved_at=retrieved_at,
                    spatial_resolution="Point",
                    temporal_resolution="Daily",
                    data_quality_status="VALID",
                    is_stale=is_stale_now,
                )
                records_to_insert.append(zone)
                    
            if records_to_insert:
                add_res = _add_all_db(records_to_insert)
                if asyncio.iscoroutine(add_res):
                    await add_res
                await _commit_db()
                logger.info(
                    f"[{self.name}] Successfully ingested {len(result['records'])} new PFZ records "
                    f"into incois_pfz_advisories and pfz_zones."
                )
        except Exception as e:
            await _rollback_db()
            logger.exception(f"[{self.name}] Database error during ingestion: {e}")
            result["status"] = "ERROR"
            result["errors"] = [f"Database error: {str(e)}"]
            result["error"] = "Database insertion failed"
            result["count"] = 0
            result["record_count"] = 0
            
        return result



class INCOISHistoricalWFSProvider(BaseProvider):
    """
    Deprecated/Historical WFS provider for INCOIS PFZ.
    This provider is strictly maintained to ensure the old code does not silently
    act as a fallback for the current, production TextData PFZ fetcher.
    Do NOT use for live fetching.
    """
    
    @property
    def name(self) -> str:
        return "INCOIS-WFS-HISTORICAL"
        
    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.DEPRECATED
        
    async def fetch_data(self) -> Any:
        raise NotImplementedError("Historical WFS provider should not be called.")
        
    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        raise NotImplementedError("Historical WFS provider should not be called.")
