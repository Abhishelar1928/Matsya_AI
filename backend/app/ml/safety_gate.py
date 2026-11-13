"""
MatsyaAI Maharashtra — Safety Gate.

The ML model must NEVER independently determine that a location is safe.
Safety status is determined by:
1. Active marine warnings (IMD/INCOIS)
2. Environmental condition thresholds
3. Restricted zone checks
4. PFZ advisory data

An empty MarineWarning table means NO_WARNING_DATA, NOT SAFE.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from backend.app.ml.config import (
    SAFETY_WAVE_HEIGHT_THRESHOLD,
    SAFETY_WIND_SPEED_THRESHOLD,
    SAFETY_STATUSES,
)

logger = logging.getLogger(__name__)


class SafetyGate:
    """
    Safety layer that overlays ML predictions with safety information.

    The ML prediction probability NEVER itself determines safety.
    Safety is determined independently by official warnings and
    environmental thresholds.
    """

    def __init__(self, marine_warnings: Optional[List[Dict]] = None):
        """
        Args:
            marine_warnings: List of active marine warning dicts from the DB.
                Each should have: severity, valid_from, valid_until,
                geom/lat/lon, description.
                If None or empty: safety status = NO_WARNING_DATA.
        """
        self.marine_warnings = marine_warnings or []
        self._has_warning_data = len(self.marine_warnings) > 0

    def apply(self, predictions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply safety gate to a list of predictions.

        Modifies each prediction dict in-place to set:
        - safety_status
        - safety_reason
        - safety_override
        - active_warnings (if any)
        """
        now = datetime.now(timezone.utc)

        # Filter to active warnings
        active_warnings = [
            w for w in self.marine_warnings
            if (w.get('valid_from', now) <= now <= w.get('valid_until', now))
        ]

        severe_warnings = [
            w for w in active_warnings
            if w.get('severity', '').upper() in (
                'SEVERE', 'VERY_SEVERE', 'EXTREMELY_SEVERE'
            )
        ]

        caution_warnings = [
            w for w in active_warnings
            if w.get('severity', '').upper() in (
                'MODERATE', 'CAUTION', 'WARNING', 'ROUGH_SEA'
            )
        ]

        # Authoritative active bulletin explicitly confirming calm/normal conditions
        has_active_normal_bulletin = any(
            w.get('severity', '').upper() in ('NONE', 'NORMAL', 'NIL', 'ALL_CLEAR', 'SAFE')
            for w in active_warnings
        )

        # Has valid, non-stale active warning context
        has_active_warning_feed = len(active_warnings) > 0

        for pred in predictions:
            safety_status, safety_reason = self._determine_safety(
                pred=pred,
                active_warnings=active_warnings,
                severe_warnings=severe_warnings,
                caution_warnings=caution_warnings,
                has_active_normal_bulletin=has_active_normal_bulletin,
                has_active_warning_feed=has_active_warning_feed,
            )
            pred['safety_status'] = safety_status
            pred['safety_reason'] = safety_reason
            pred['safety_override'] = safety_status in ('UNSAFE', 'BLOCKED')

        return predictions

    def _determine_safety(
        self,
        pred: Dict,
        active_warnings: List[Dict],
        severe_warnings: List[Dict],
        caution_warnings: List[Dict],
        has_active_normal_bulletin: bool,
        has_active_warning_feed: bool,
    ) -> Tuple[str, str]:
        """
        Determine the safety status for a single grid cell prediction.

        Returns (status, reason) tuple.

        Priority order:
        1. BLOCKED — restricted zone (not implemented yet)
        2. UNSAFE — active severe marine warning
        3. CAUTION — environmental thresholds exceeded or active caution warning
        4. SAFE_CONFIRMED — authoritative active bulletin explicitly confirms normal conditions
                            and no thresholds exceeded
        5. NO_WARNING_DATA — no active warning data or stale warning data
        """
        # Check environmental thresholds from the prediction's env data
        wave_height = pred.get("current_wave_height_m") if "current_wave_height_m" in pred else pred.get("_wave_height")
        wind_speed = pred.get("current_wind_speed_kmh") if "current_wind_speed_kmh" in pred else pred.get("_wind_speed")

        # 1. Check for severe warnings
        if severe_warnings:
            return ('UNSAFE', 'Active severe marine warning from authoritative source')

        # 2. Check for active caution warnings
        if caution_warnings:
            return ('CAUTION', 'Active caution-level marine warning from authoritative source')

        # 3. Check environmental thresholds
        if wave_height is not None and wave_height > SAFETY_WAVE_HEIGHT_THRESHOLD:
            return ('CAUTION', f'Wave height {wave_height:.1f}m exceeds {SAFETY_WAVE_HEIGHT_THRESHOLD}m threshold')
        if wind_speed is not None and wind_speed > SAFETY_WIND_SPEED_THRESHOLD:
            return ('CAUTION', f'Wind speed {wind_speed:.1f}km/h exceeds {SAFETY_WIND_SPEED_THRESHOLD}km/h threshold')

        # 4. Only confirm SAFE if there is an active authoritative confirmation bulletin
        # Absence of warnings in an unconfirmed or stale feed must NEVER yield SAFE.
        if has_active_normal_bulletin:
            if wave_height is None or wind_speed is None:
                return ('NO_WARNING_DATA', 'Environmental data is missing, cannot confirm safety')
            return ('SAFE_CONFIRMED', 'Active authoritative bulletin confirms normal conditions')

        # 5. Otherwise, safety cannot be confirmed
        return ('NO_WARNING_DATA', 'No current authoritative marine warning data available to confirm safety')

