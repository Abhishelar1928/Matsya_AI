"""
MatsyaAI Maharashtra — Source Freshness & Health Tracker.

Tracks the operational status, data timestamp, expiration, and freshness age
of all authoritative data sources feeding the system:
1. INCOIS Potential Fishing Zone (PFZ)
2. IMD Mumbai Marine / Fishermen Warnings
3. Open-Meteo Current Marine Weather
4. Global Fishing Watch (GFW AIS)

CRITICAL RULES:
- Freshness is calculated from actual DATA/ADVISORY timestamps, NEVER retrieved_at alone.
- Expired advisories are labeled STALE, never LIVE.
- GFW AIS effort data has publication latency and is labeled CACHED_HISTORICAL, never LIVE.
- Tracking source health does NOT declare fishing SAFE.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from sqlalchemy import select, func

from backend.app.core.config import settings
from backend.app.models.incois_pfz import INCOISPFZAdvisory
from backend.app.models.marine_warning import MarineWarning
from backend.app.models.ocean_observation import OceanObservation
from backend.app.models.gfw import GFWFishingEffort

logger = logging.getLogger(__name__)

# Allowed statuses
STATUS_LIVE = "LIVE"
STATUS_STALE = "STALE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_AUTHENTICATED = "AUTHENTICATED"
STATUS_PUBLIC = "PUBLIC"
STATUS_CACHED_HISTORICAL = "CACHED_HISTORICAL"
STATUS_ERROR = "ERROR"


class SourceFreshnessTracker:
    """
    Centralized tracker for source health and data freshness across all ingestors.
    """

    @staticmethod
    def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure a datetime object is timezone-aware UTC."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    async def _safe_exec(cls, db: Any, stmt: Any) -> Any:
        """Executes a SQLAlchemy statement against async/sync or mock sessions."""
        res = db.execute(stmt)
        if asyncio.iscoroutine(res):
            return await res
        return res

    async def check_incois_pfz(
        self, db: Optional[Any] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate freshness of INCOIS PFZ advisory data.
        Freshness is determined by advisory_date and validity_date.
        """
        now = self._ensure_utc(now or datetime.now(timezone.utc))
        source_name = "INCOIS Potential Fishing Zone (PFZ)"

        if db is None:
            return {
                "source_name": source_name,
                "status": STATUS_UNAVAILABLE,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": "Database session not available",
            }

        try:
            stmt = (
                select(INCOISPFZAdvisory)
                .order_by(INCOISPFZAdvisory.retrieved_at.desc())
                .limit(1)
            )
            res = await self._safe_exec(db, stmt)
            record = (
                res.scalars().first()
                if hasattr(res, "scalars")
                else (res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None)
            )

            if not record:
                return {
                    "source_name": source_name,
                    "status": STATUS_UNAVAILABLE,
                    "last_successful_fetch": None,
                    "data_timestamp": None,
                    "valid_until": None,
                    "age_minutes": None,
                    "record_count": 0,
                    "error": "No INCOIS PFZ advisory records in database",
                }

            advisory_date = self._ensure_utc(record.advisory_date)
            validity_date = self._ensure_utc(record.validity_date)
            retrieved_at = self._ensure_utc(record.retrieved_at)

            # Query count of records in this batch
            count_stmt = select(func.count(INCOISPFZAdvisory.id)).where(
                INCOISPFZAdvisory.retrieved_at == record.retrieved_at
            )
            count_res = await self._safe_exec(db, count_stmt)
            record_count = (
                count_res.scalar()
                if hasattr(count_res, "scalar")
                else (count_res if isinstance(count_res, int) else 1)
            )

            # Age is measured against the actual advisory date
            age_minutes = None
            if advisory_date:
                age_minutes = max(0.0, round((now - advisory_date).total_seconds() / 60.0, 1))

            # Status rule:
            # If validity date has passed, it is STALE regardless of when retrieved!
            if validity_date and validity_date < now:
                status = STATUS_STALE
            elif advisory_date and (now - advisory_date).total_seconds() > 36 * 3600:
                # If older than 36 hours without an explicit future validity date
                status = STATUS_STALE
            else:
                status = STATUS_LIVE

            return {
                "source_name": source_name,
                "status": status,
                "last_successful_fetch": retrieved_at.isoformat() if retrieved_at else None,
                "data_timestamp": advisory_date.isoformat() if advisory_date else None,
                "valid_until": validity_date.isoformat() if validity_date else None,
                "age_minutes": age_minutes,
                "record_count": record_count,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Error checking INCOIS PFZ freshness: {e}")
            return {
                "source_name": source_name,
                "status": STATUS_ERROR,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": str(e),
            }

    async def check_imd_marine(
        self, db: Optional[Any] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate freshness of IMD Mumbai Marine / Fishermen Warnings.
        Freshness is determined by bulletin issue_timestamp and valid_until.
        """
        now = self._ensure_utc(now or datetime.now(timezone.utc))
        source_name = "IMD Mumbai Fishermen Warning Bulletin"

        if db is None:
            return {
                "source_name": source_name,
                "status": STATUS_UNAVAILABLE,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": "Database session not available",
            }

        try:
            stmt = (
                select(MarineWarning)
                .where(MarineWarning.source_name == "IMD_MUMBAI")
                .order_by(MarineWarning.source_timestamp.desc(), MarineWarning.retrieved_at.desc())
                .limit(1)
            )
            res = await self._safe_exec(db, stmt)
            record = (
                res.scalars().first()
                if hasattr(res, "scalars")
                else (res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None)
            )

            if not record:
                return {
                    "source_name": source_name,
                    "status": STATUS_UNAVAILABLE,
                    "last_successful_fetch": None,
                    "data_timestamp": None,
                    "valid_until": None,
                    "age_minutes": None,
                    "record_count": 0,
                    "error": "No IMD marine warnings in database",
                }

            source_timestamp = self._ensure_utc(record.source_timestamp)
            valid_until = self._ensure_utc(record.valid_until)
            retrieved_at = self._ensure_utc(record.retrieved_at)

            # Count of active warnings from this bulletin
            count_stmt = select(func.count(MarineWarning.id)).where(
                MarineWarning.source_name == "IMD_MUMBAI",
                MarineWarning.source_timestamp == record.source_timestamp,
            )
            count_res = await self._safe_exec(db, count_stmt)
            record_count = (
                count_res.scalar()
                if hasattr(count_res, "scalar")
                else (count_res if isinstance(count_res, int) else 1)
            )

            age_minutes = None
            if source_timestamp:
                age_minutes = max(0.0, round((now - source_timestamp).total_seconds() / 60.0, 1))

            # Status rule:
            # If validity date has expired, bulletin is STALE!
            if valid_until and valid_until < now:
                status = STATUS_STALE
            elif source_timestamp and (now - source_timestamp).total_seconds() > 24 * 3600:
                # IMD Mumbai bulletins are issued every 12 to 24 hours
                status = STATUS_STALE
            else:
                status = STATUS_LIVE

            return {
                "source_name": source_name,
                "status": status,
                "last_successful_fetch": retrieved_at.isoformat() if retrieved_at else None,
                "data_timestamp": source_timestamp.isoformat() if source_timestamp else None,
                "valid_until": valid_until.isoformat() if valid_until else None,
                "age_minutes": age_minutes,
                "record_count": record_count,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Error checking IMD Marine freshness: {e}")
            return {
                "source_name": source_name,
                "status": STATUS_ERROR,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": str(e),
            }

    async def check_open_meteo_marine(
        self, db: Optional[Any] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate freshness of Open-Meteo current marine weather observations.
        Freshness is determined by observation timestamp.
        """
        now = self._ensure_utc(now or datetime.now(timezone.utc))
        source_name = "Open-Meteo Marine Forecast"

        if db is None:
            return {
                "source_name": source_name,
                "status": STATUS_UNAVAILABLE,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": "Database session not available",
            }

        try:
            stmt = (
                select(OceanObservation)
                .order_by(OceanObservation.timestamp.desc(), OceanObservation.retrieved_at.desc())
                .limit(1)
            )
            res = await self._safe_exec(db, stmt)
            record = (
                res.scalars().first()
                if hasattr(res, "scalars")
                else (res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None)
            )

            if not record:
                return {
                    "source_name": source_name,
                    "status": STATUS_UNAVAILABLE,
                    "last_successful_fetch": None,
                    "data_timestamp": None,
                    "valid_until": None,
                    "age_minutes": None,
                    "record_count": 0,
                    "error": "No ocean observations in database",
                }

            obs_timestamp = self._ensure_utc(record.timestamp)
            retrieved_at = self._ensure_utc(record.retrieved_at)

            count_stmt = select(func.count(OceanObservation.id)).where(
                OceanObservation.timestamp == record.timestamp
            )
            count_res = await self._safe_exec(db, count_stmt)
            record_count = (
                count_res.scalar()
                if hasattr(count_res, "scalar")
                else (count_res if isinstance(count_res, int) else 1)
            )

            age_minutes = None
            if obs_timestamp:
                age_minutes = max(0.0, round((now - obs_timestamp).total_seconds() / 60.0, 1))

            # Open-Meteo observations are valid for ~3 hours (180 mins)
            valid_until = obs_timestamp + timedelta(hours=3) if obs_timestamp else None

            # Status rule:
            if age_minutes is not None and age_minutes > 180:
                status = STATUS_STALE
            else:
                status = STATUS_LIVE

            return {
                "source_name": source_name,
                "status": status,
                "last_successful_fetch": retrieved_at.isoformat() if retrieved_at else None,
                "data_timestamp": obs_timestamp.isoformat() if obs_timestamp else None,
                "valid_until": valid_until.isoformat() if valid_until else None,
                "age_minutes": age_minutes,
                "record_count": record_count,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Error checking Open-Meteo freshness: {e}")
            return {
                "source_name": source_name,
                "status": STATUS_ERROR,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "record_count": 0,
                "error": str(e),
            }

    async def check_global_fishing_watch(
        self, db: Optional[Any] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate Global Fishing Watch (GFW AIS) effort context.
        CRITICAL: GFW AIS data has publication latency and is NEVER labeled LIVE.
        Exposes context observation date and age_days.
        """
        now = self._ensure_utc(now or datetime.now(timezone.utc))
        source_name = "Global Fishing Watch (GFW AIS)"

        try:
            record = None
            record_count = 0
            if db is not None:
                stmt = (
                    select(GFWFishingEffort)
                    .order_by(GFWFishingEffort.observation_date.desc())
                    .limit(1)
                )
                res = await self._safe_exec(db, stmt)
                record = (
                    res.scalars().first()
                    if hasattr(res, "scalars")
                    else (res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None)
                )

                if record:
                    count_stmt = select(func.count(GFWFishingEffort.id))
                    count_res = await self._safe_exec(db, count_stmt)
                    record_count = (
                        count_res.scalar()
                        if hasattr(count_res, "scalar")
                        else (count_res if isinstance(count_res, int) else 1)
                    )

            if record and record.observation_date:
                obs_date = self._ensure_utc(record.observation_date)
                retrieved_at = self._ensure_utc(record.retrieved_at)
                age_minutes = max(0.0, round((now - obs_date).total_seconds() / 60.0, 1))
                age_days = (now.date() - obs_date.date()).days

                return {
                    "source_name": source_name,
                    "status": STATUS_CACHED_HISTORICAL,
                    "last_successful_fetch": retrieved_at.isoformat() if retrieved_at else None,
                    "data_timestamp": obs_date.isoformat(),
                    "valid_until": None,
                    "age_minutes": age_minutes,
                    "age_days": age_days,
                    "record_count": record_count,
                    "error": None,
                }

            # If no DB records, it is UNAVAILABLE
            has_token = bool(settings.GFW_API_TOKEN)
            status = STATUS_UNAVAILABLE

            return {
                "source_name": source_name,
                "status": status,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "age_days": None,
                "record_count": 0,
                "error": None if has_token else "GFW API token not configured; operating in public mode",
            }

        except Exception as e:
            logger.exception(f"Error checking GFW freshness: {e}")
            return {
                "source_name": source_name,
                "status": STATUS_ERROR,
                "last_successful_fetch": None,
                "data_timestamp": None,
                "valid_until": None,
                "age_minutes": None,
                "age_days": None,
                "record_count": 0,
                "error": str(e),
            }

    async def get_all_freshness(
        self, db: Optional[Any] = None, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Gathers freshness information for all four monitored sources.
        Runs sequentially to respect SQLAlchemy session concurrency constraints.
        """
        now = self._ensure_utc(now or datetime.now(timezone.utc))

        incois_res = await self.check_incois_pfz(db, now)
        imd_res = await self.check_imd_marine(db, now)
        open_meteo_res = await self.check_open_meteo_marine(db, now)
        gfw_res = await self.check_global_fishing_watch(db, now)

        return {
            "sources": {
                "incois_pfz": incois_res,
                "imd_marine_warnings": imd_res,
                "open_meteo_marine": open_meteo_res,
                "global_fishing_watch": gfw_res,
            },
            "generated_at": now.isoformat(),
        }
