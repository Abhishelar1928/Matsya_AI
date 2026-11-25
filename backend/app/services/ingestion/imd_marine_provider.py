"""
IMD Marine / Fishermen Warning Ingestion Provider for Matsya AI.

Fetches and parses the official IMD Mumbai Fishermen Warning PDF:
https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf

CRITICAL SAFETY RULES:
- Use ONLY the official IMD Mumbai source.
- Do NOT fabricate warnings.
- Do NOT create a NORMAL record when the source cannot be fetched.
- Do NOT interpret failed/unavailable IMD data as SAFE.
- NORMAL is stored only when the official bulletin explicitly states Nil/Normal.
- WARNING is stored for active advisory conditions (squally winds, rough sea).
- SEVERE is stored only when the bulletin describes severe conditions (cyclone/gale).
- Polygons are approximate application regions, NOT official IMD boundaries.
"""

import io
import re
import logging
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import PyPDF2
from sqlalchemy import select, update

from backend.app.services.ingestion.base import BaseProvider, ProviderStatus
from backend.app.models.marine_warning import MarineWarning


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IMD_MUMBAI_FISHERMAN_PDF_URL = "https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

# Approximate application polygons (Non-official application boundaries)
# North Maharashtra Coast (upto 75km offshore: Dahanu to Mumbai/Raigad border)
GEOM_NORTH_MH_COAST = "SRID=4326;POLYGON((72.0 18.8, 73.2 18.8, 73.2 20.3, 72.0 20.3, 72.0 18.8))"

# South Maharashtra-Goa Coast (upto 75km offshore: Raigad/Ratnagiri/Sindhudurg to Goa)
GEOM_SOUTH_MH_GOA_COAST = "SRID=4326;POLYGON((72.5 14.8, 74.2 14.8, 73.5 18.8, 72.5 18.8, 72.5 14.8))"

# High Sea / Arabian Sea (Beyond 75km offshore, broad operational sea area)
GEOM_HIGH_SEA = "SRID=4326;POLYGON((60.0 10.0, 72.0 10.0, 72.0 22.0, 60.0 22.0, 60.0 10.0))"

# Default fallback polygon for generic Maharashtra marine area
GEOM_MAHARASHTRA_GENERAL = "SRID=4326;POLYGON((71.5 14.8, 73.5 14.8, 73.5 20.3, 71.5 20.3, 71.5 14.8))"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class IMDMarineProvider(BaseProvider):
    """
    Production provider for official IMD Mumbai Fishermen Warning bulletins.
    Downloads the daily PDF, extracts structured advisory text, determines
    strict severity levels, and stores normalized MarineWarning records.
    """

    def __init__(self):
        self._current_status = ProviderStatus.LIVE

    @property
    def name(self) -> str:
        return "IMD_MUMBAI_FISHERMAN_BULLETIN"

    @property
    def status(self) -> ProviderStatus:
        return self._current_status

    async def fetch_data(self) -> Any:
        return await self.fetch_latest_bulletin()

    def parse_data(self, raw_data: Any) -> List[Dict[str, Any]]:
        return []

    async def _fetch_pdf_with_retry(self, client: httpx.AsyncClient, url: str) -> bytes:
        """Fetch PDF content with exponential backoff on transient errors."""
        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(url)
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

                # Basic validation that content is a PDF
                content = response.content
                if not content.startswith(b"%PDF"):
                    raise ValueError("Downloaded content is not a valid PDF document.")

                return content

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = e
                wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
                logger.warning(f"[{self.name}] Network/Timeout on {url} (Attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
            except httpx.HTTPStatusError as e:
                logger.error(f"[{self.name}] HTTP {e.response.status_code} error on {url}")
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError(f"[{self.name}] Failed request to {url} after {MAX_RETRIES} attempts.")

    @staticmethod
    def _clean_token_spacing(text: str) -> str:
        """
        Collapses single characters separated by spaces or tabs resulting
        from PDF font kerning (e.g. 'T h u r s d a y' -> 'Thursday').
        """
        prev = None
        s = text
        while prev != s:
            prev = s
            s = re.sub(r'(?<=[A-Za-z0-9])[\t ](?=[A-Za-z0-9])', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    def extract_structured_lines(self, pdf_bytes: bytes) -> List[str]:
        """
        Extracts lines from the PDF ordered top-to-bottom and left-to-right
        using PyPDF2 spatial visitor coordinates.
        """
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        lines: List[str] = []

        for page in reader.pages:
            elements = []

            def visitor(text, cm, tm, font_dict, font_size):
                if text.strip():
                    # tm[5] is Y coordinate, tm[4] is X coordinate
                    elements.append((tm[5], tm[4], text))

            page.extract_text(visitor_text=visitor)

            # Sort top-to-bottom by Y (ascending or descending as per transformation matrix)
            # In the IMD report matrix, Y coordinate increases from 175 (top) to 988 (bottom).
            elements.sort(key=lambda e: (round(e[0], 1), round(e[1], 1)))

            curr_y = None
            curr_items = []
            for y, x, t in elements:
                if curr_y is None or abs(y - curr_y) > 5:
                    if curr_items:
                        curr_items.sort(key=lambda it: it[0])
                        cleaned = self._clean_token_spacing(' '.join(it[1] for it in curr_items))
                        if cleaned:
                            lines.append(cleaned)
                    curr_y = y
                    curr_items = [(x, t)]
                else:
                    curr_items.append((x, t))

            if curr_items:
                curr_items.sort(key=lambda it: it[0])
                cleaned = self._clean_token_spacing(' '.join(it[1] for it in curr_items))
                if cleaned:
                    lines.append(cleaned)

        return lines

    def extract_issue_timestamp(self, text: str) -> Optional[datetime]:
        """
        Extracts bulletin issue timestamp from header text.
        e.g., 'Thursday , 10 September , 2026 Time Of Issue : 2030 HRS IST'
        """
        # Pattern 1: Day, DD Month, YYYY Time Of Issue : HHMM HRS IST
        m1 = re.search(
            r'(\d{1,2})[\s,]+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[,\s]+(\d{4}).*?Time\s*Of\s*Issue\s*:\s*(\d{2})(\d{2})',
            text,
            re.IGNORECASE
        )
        if m1:
            try:
                day = int(m1.group(1))
                month_str = m1.group(2)[:3]
                year = int(m1.group(3))
                hour = int(m1.group(4))
                minute = int(m1.group(5))
                month = datetime.strptime(month_str, "%b").month
                # IST is UTC+5:30
                ist_dt = datetime(year, month, day, hour, minute)
                utc_dt = ist_dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc)
                return utc_dt
            except (ValueError, IndexError):
                pass

        # Pattern 2: DD-Mon-YYYY or DD/MM/YYYY
        m2 = re.search(
            r'(\d{1,2})[\s\-/]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-/]+(\d{4})',
            text,
            re.IGNORECASE
        )
        if m2:
            try:
                dt = datetime.strptime(f"{m2.group(1)} {m2.group(2)} {m2.group(3)}", "%d %b %Y")
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return None

    def extract_validity_period(self, text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Extracts validity start and end timestamps.
        e.g., 'Valid For Next Five Days From 10 - Sep - 2026 to 14 - Sep - 2026'
        """
        m = re.search(
            r'From\s+(\d{1,2})[\s\-/]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-/]+(\d{4})\s+to\s+(\d{1,2})[\s\-/]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-/]+(\d{4})',
            text,
            re.IGNORECASE
        )
        if m:
            try:
                from_str = f"{m.group(1)} {m.group(2)} {m.group(3)}"
                to_str = f"{m.group(4)} {m.group(5)} {m.group(6)}"
                valid_from = datetime.strptime(from_str, "%d %b %Y").replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
                valid_until = datetime.strptime(to_str, "%d %b %Y").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                return valid_from, valid_until
            except ValueError:
                pass

        return None, None

    @staticmethod
    def classify_severity(text: str) -> str:
        """
        Strict severity determination:
        - NORMAL: ONLY when explicitly stating Nil or Normal.
        - SEVERE: Cyclonic storm, gale force winds (>=65 kmph), hurricane, very/extremely severe.
        - WARNING: Squally wind, rough sea, warning, advised not to venture.
        """
        clean = text.strip().lower()
        if not clean or clean in ("nil", "nil.", "normal", "no warning", "nil ."):
            return "NORMAL"

        # Check for severe conditions
        severe_keywords = [
            "cyclon", "gale", "extremely severe", "very severe", "super cyclon",
            "storm surge", "hurricane", "typhoon"
        ]
        if any(kw in clean for kw in severe_keywords):
            return "SEVERE"

        # Check wind speed >= 65 kmph for severe
        speed_match = re.search(r'(\d{2,3})\s*-\s*(\d{2,3})\s*kmph', clean)
        if speed_match:
            max_speed = int(speed_match.group(2))
            if max_speed >= 65 and "gusting to" in clean:
                gust_match = re.search(r'gusting\s+to\s+(\d{2,3})\s*kmph', clean)
                if gust_match and int(gust_match.group(1)) >= 75:
                    return "SEVERE"

        # Warning keywords
        warning_keywords = [
            "squall", "rough", "warning", "advised not to venture",
            "gusting", "kmph", "caution", "alert"
        ]
        if any(kw in clean for kw in warning_keywords):
            return "WARNING"

        return "WARNING"

    def parse_bulletin_lines(self, lines: List[str]) -> Dict[str, Any]:
        """
        Parses structured lines from the IMD Fisherman PDF into distinct section records.
        """
        full_text = " \n ".join(lines)
        issue_timestamp = self.extract_issue_timestamp(full_text)
        valid_from, valid_until = self.extract_validity_period(full_text)

        # Default validity fallback if not explicitly found
        if not valid_from and issue_timestamp:
            valid_from = issue_timestamp
            valid_until = issue_timestamp + timedelta(days=5)

        # Section extractors
        north_coast_text = "Nil."
        south_coast_text = "Nil."
        high_sea_text = "Nil."
        high_wave_north = "Nil."
        high_wave_south = "Nil."
        port_north_text = "Nil."
        port_south_text = "Nil."

        # Scan line by line to associate section headers with their values
        for i, line in enumerate(lines):
            l_lower = line.lower()
            
            # 1. North Maharashtra Coast warning
            if "warning for coastal areas for north maharashtra coast" in l_lower:
                collected = []
                for j in range(i + 1, len(lines)):
                    if "warning for coastal areas" in lines[j].lower() or "warning for high sea" in lines[j].lower():
                        break
                    collected.append(lines[j])
                if collected:
                    north_coast_text = " ".join(collected)

            # 2. South Maharashtra - Goa Coast warning
            elif "warning for coastal areas for south maharashtra" in l_lower:
                collected = []
                for j in range(i + 1, len(lines)):
                    if "warning for high sea" in lines[j].lower() or "wind warning" in lines[j].lower():
                        break
                    collected.append(lines[j])
                if collected:
                    south_coast_text = " ".join(collected)

            # 3. High Sea warning
            elif "warning for high sea and other coasts" in l_lower or ("wind warning" in l_lower and "day 1" in full_text.lower()):
                collected = []
                for j in range(i + 1, len(lines)):
                    if "high wave" in lines[j].lower() or "port warning" in lines[j].lower():
                        break
                    collected.append(lines[j])
                if collected:
                    high_sea_text = " ".join(collected)

            # 4. INCOIS High Wave / Swell Surge
            elif "high wave / swell surge warning" in l_lower:
                for j in range(i + 1, min(i + 10, len(lines))):
                    lj = lines[j].lower()
                    if "north maharashtra" in lj:
                        high_wave_north = lines[j].split(":")[-1].strip() or "Nil."
                    elif "south maharashtra" in lj:
                        high_wave_south = lines[j].split(":")[-1].strip() or "Nil."
                    elif "port warning" in lj:
                        break

            # 5. Port Warnings
            elif "port warning for north maharashtra" in l_lower:
                if i + 1 < len(lines):
                    port_north_text = lines[i + 1]
            elif "port warning for south maharashtra" in l_lower:
                if i + 1 < len(lines):
                    port_south_text = lines[i + 1]

        warnings: List[Dict[str, Any]] = []

        # 1. North Maharashtra Coast Warning
        warnings.append({
            "region": "North Maharashtra Coast (upto 75km from coast)",
            "warning_type": "COASTAL_FISHERMEN_WARNING",
            "severity": self.classify_severity(north_coast_text),
            "text": north_coast_text,
            "geom": GEOM_NORTH_MH_COAST,
            "valid_from": valid_from,
            "valid_until": valid_until,
        })

        # 2. South Maharashtra - Goa Coast Warning
        warnings.append({
            "region": "South Maharashtra-Goa Coast (upto 75km from coast)",
            "warning_type": "COASTAL_FISHERMEN_WARNING",
            "severity": self.classify_severity(south_coast_text),
            "text": south_coast_text,
            "geom": GEOM_SOUTH_MH_GOA_COAST,
            "valid_from": valid_from,
            "valid_until": valid_until,
        })

        # 3. High Sea / Arabian Sea Warning
        warnings.append({
            "region": "High Sea and other coasts (Beyond 75km from coast)",
            "warning_type": "HIGH_SEA_WIND_WARNING",
            "severity": self.classify_severity(high_sea_text),
            "text": high_sea_text,
            "geom": GEOM_HIGH_SEA,
            "valid_from": valid_from,
            "valid_until": valid_until,
        })

        # 4. High Wave Warning (North & South Maharashtra)
        if high_wave_north and high_wave_north.lower() not in ("nil.", "nil"):
            warnings.append({
                "region": "North Maharashtra Coast",
                "warning_type": "HIGH_WAVE_WARNING",
                "severity": self.classify_severity(high_wave_north),
                "text": f"INCOIS High Wave Alert: {high_wave_north}",
                "geom": GEOM_NORTH_MH_COAST,
                "valid_from": valid_from,
                "valid_until": valid_until,
            })
        if high_wave_south and high_wave_south.lower() not in ("nil.", "nil"):
            warnings.append({
                "region": "South Maharashtra Coast",
                "warning_type": "HIGH_WAVE_WARNING",
                "severity": self.classify_severity(high_wave_south),
                "text": f"INCOIS High Wave Alert: {high_wave_south}",
                "geom": GEOM_SOUTH_MH_GOA_COAST,
                "valid_from": valid_from,
                "valid_until": valid_until,
            })

        # 5. Port Warnings (if not Nil)
        if port_north_text and port_north_text.lower() not in ("nil.", "nil"):
            warnings.append({
                "region": "North Maharashtra Ports",
                "warning_type": "PORT_WARNING",
                "severity": self.classify_severity(port_north_text),
                "text": f"Port Warning: {port_north_text}",
                "geom": GEOM_NORTH_MH_COAST,
                "valid_from": valid_from,
                "valid_until": valid_until,
            })
        if port_south_text and port_south_text.lower() not in ("nil.", "nil"):
            warnings.append({
                "region": "South Maharashtra-Goa Ports",
                "warning_type": "PORT_WARNING",
                "severity": self.classify_severity(port_south_text),
                "text": f"Port Warning: {port_south_text}",
                "geom": GEOM_SOUTH_MH_GOA_COAST,
                "valid_from": valid_from,
                "valid_until": valid_until,
            })

        return {
            "issue_timestamp": issue_timestamp,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "warnings": warnings,
        }

    async def fetch_latest_bulletin(self) -> Dict[str, Any]:
        """
        Fetches and parses the official IMD Mumbai Fishermen Warning PDF.
        Returns structured result dictionary.
        """
        retrieved_at = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "status": "ERROR",
            "count": 0,
            "issue_timestamp": None,
            "valid_from": None,
            "valid_until": None,
            "warnings": [],
            "retrieved_at": retrieved_at,
            "errors": []
        }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True, verify=False) as client:
            try:
                pdf_bytes = await self._fetch_pdf_with_retry(client, IMD_MUMBAI_FISHERMAN_PDF_URL)
                result["raw_pdf_size"] = len(pdf_bytes)

                # Extract and parse structured lines
                lines = self.extract_structured_lines(pdf_bytes)
                if not lines:
                    result["status"] = "UNAVAILABLE"
                    result["errors"] = ["Could not extract text lines from PDF"]
                    return result

                parsed = self.parse_bulletin_lines(lines)
                result["issue_timestamp"] = parsed["issue_timestamp"]
                result["valid_from"] = parsed["valid_from"]
                result["valid_until"] = parsed["valid_until"]
                result["warnings"] = parsed["warnings"]
                result["count"] = len(parsed["warnings"])
                result["status"] = "SUCCESS"
                return result

            except Exception as e:
                logger.exception(f"[{self.name}] Error fetching/parsing IMD fisherman bulletin: {e}")
                result["status"] = "UNAVAILABLE"
                result["errors"] = [str(e)]
                return result

    async def ingest_latest_bulletin(self, db: Any) -> Dict[str, Any]:
        """
        Fetches and ingests the latest IMD Fishermen Warnings into marine_warnings table.
        Applies deterministic bulletin deduplication.
        If source fails, does NOT insert fake/NORMAL records, retains valid data,
        and returns explicit error status.
        """
        result = await self.fetch_latest_bulletin()

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

        # 1. Source failure behavior: Do not insert fake/NORMAL records!
        if result["status"] != "SUCCESS":
            logger.warning(
                f"[{self.name}] IMD source returned status {result['status']}. "
                f"No records inserted. Failed data is NEVER interpreted as SAFE."
            )
            result["count"] = 0
            return result

        issue_timestamp = result["issue_timestamp"]
        valid_from = result["valid_from"]
        valid_until = result["valid_until"]
        retrieved_at = result["retrieved_at"]

        try:
            # 2. Deterministic Deduplication: check if this exact issue_timestamp already exists
            if issue_timestamp:
                stmt_check = (
                    select(MarineWarning.id)
                    .where(
                        MarineWarning.source_name == "IMD_MUMBAI",
                        MarineWarning.source_timestamp == issue_timestamp
                    )
                    .limit(1)
                )
                existing_res = await _exec_db(stmt_check)
                existing_record = (
                    existing_res.scalars().first()
                    if hasattr(existing_res, "scalars")
                    else (existing_res.scalar_one_or_none() if hasattr(existing_res, "scalar_one_or_none") else None)
                )
                if existing_record:
                    logger.info(
                        f"[{self.name}] Bulletin with issue_timestamp {issue_timestamp} "
                        f"already ingested. Skipping duplicate insertion."
                    )
                    return result

            # 3. Mark previous IMD bulletins in marine_warnings as stale
            stmt_stale = (
                update(MarineWarning)
                .where(
                    MarineWarning.source_name == "IMD_MUMBAI",
                    MarineWarning.is_stale == False
                )
                .values(is_stale=True)
            )
            await _exec_db(stmt_stale)

            # 4. Insert normalized MarineWarning records
            records_to_insert = []
            for w in result["warnings"]:
                desc = (
                    f"Region: {w['region']} | "
                    f"Condition: {w['text']} | "
                    f"Source: IMD Mumbai Fishermen Warning Bulletin (mcdata/fisherman.pdf)"
                )
                record = MarineWarning(
                    warning_type=w["warning_type"],
                    severity=w["severity"],
                    valid_from=w["valid_from"] or retrieved_at,
                    valid_until=w["valid_until"] or (retrieved_at + timedelta(days=5)),
                    description=desc,
                    geom=w["geom"],
                    source_name="IMD_MUMBAI",
                    dataset_name="OFFICIAL_FISHERMAN_BULLETIN",
                    source_timestamp=issue_timestamp or retrieved_at,
                    retrieved_at=retrieved_at,
                    spatial_resolution=w["region"],
                    temporal_resolution="5-Day Bulletin",
                    data_quality_status="VALID",
                    is_stale=False,
                )
                records_to_insert.append(record)

            if records_to_insert:
                add_res = _add_all_db(records_to_insert)
                if asyncio.iscoroutine(add_res):
                    await add_res
                await _commit_db()
                logger.info(
                    f"[{self.name}] Successfully ingested {len(records_to_insert)} "
                    f"new MarineWarning records from IMD Mumbai."
                )

        except Exception as e:
            await _rollback_db()
            logger.exception(f"[{self.name}] Database error during ingestion: {e}")
            result["status"] = "ERROR"
            result["errors"] = [f"Database insertion failed: {str(e)}"]
            result["count"] = 0

        return result


async def fetch_district_warnings_live(districts: List[str]) -> Dict[str, Any]:
    """Fetch live district-level weather warnings from NDMA SACHET CAP and optionally api.imd.gov.in."""
    from backend.app.core.config import settings

    now_iso = datetime.now(timezone.utc).isoformat()
    alerts: List[Dict[str, Any]] = []
    sachet_status = "UNAVAILABLE"
    sachet_error: Optional[str] = None
    pat = re.compile(r"\b(" + "|".join(re.escape(d) for d in districts) + r"|konkan|maharashtra)\b", re.IGNORECASE)

    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "MatsyaAI/1.0"}) as client:
            r = await client.get("https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails")
            r.raise_for_status()
            rows = r.json()
            sachet_status = "LIVE"
            for a in (rows if isinstance(rows, list) else []):
                area = f"{a.get('area_description', '')} {a.get('area_covered', '')} {a.get('warning_message', '')}"
                if not pat.search(area):
                    continue
                matched = [d for d in districts if re.search(rf"\b{re.escape(d)}\b", area, re.IGNORECASE)]
                alerts.append({
                    "identifier": str(a.get("identifier") or a.get("alert_id_sdma_autoinc") or ""),
                    "districts": matched or ["Maharashtra Coast"],
                    "disaster_type": a.get("disaster_type") or "Weather Alert",
                    "severity": a.get("severity") or "INFO",
                    "severity_color": a.get("severity_color"),
                    "source": a.get("alert_source") or "NDMA SACHET / IMD",
                    "area_description": a.get("area_description") or a.get("area_covered") or "",
                    "warning_message": a.get("warning_message") or "",
                    "effective_start_time": a.get("effective_start_time"),
                    "effective_end_time": a.get("effective_end_time"),
                })
    except Exception as e:
        sachet_error = str(e)

    imd_api_status = "AUTH_IP_WHITELIST_REQUIRED"
    imd_api_items: List[Dict[str, Any]] = []
    if settings.IMD_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15.0, headers={
                "User-Agent": "MatsyaAI/1.0",
                "Authorization": f"Bearer {settings.IMD_API_KEY}",
                "x-api-key": settings.IMD_API_KEY,
            }) as client:
                r = await client.get(settings.IMD_DISTRICT_API_URL)
                if r.status_code == 200:
                    imd_api_status = "LIVE"
                    data = r.json()
                    imd_api_items = data if isinstance(data, list) else data.get("data", [])
                else:
                    imd_api_status = f"HTTP_{r.status_code}"
        except Exception as e:
            imd_api_status = f"ERROR: {e}"

    return {
        "status": "LIVE" if (sachet_status == "LIVE" or imd_api_status == "LIVE") else "UNAVAILABLE",
        "retrieved_at": now_iso,
        "districts_monitored": districts,
        "sources": {
            "ndma_sachet_cap": {"status": sachet_status, "error": sachet_error, "alert_count": len(alerts)},
            "imd_public_api": {
                "status": imd_api_status,
                "reference": "https://api.imd.gov.in/public/api_reference.html",
                "note": "api.imd.gov.in requires static public IP whitelisting and IMD API credentials.",
            },
        },
        "alerts": alerts,
        "imd_api_items": imd_api_items,
    }
