"""
MatsyaAI Maharashtra — Phase 4 Inference Pipeline.

Applies the validated Phase 3 XGBoost model to produce next-calendar-day (T+1)
apparent fishing activity predictions for all canonical Maharashtra marine grid cells.
The model is strictly frozen and never retrained during inference.
"""

import json
import logging
import math
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from global_land_mask import globe
from backend.app.ml.config import (
    ARTIFACTS_DIR,
    GRID_MAX_LAT,
    GRID_MAX_LON,
    GRID_MIN_LAT,
    GRID_MIN_LON,
    GRID_RESOLUTION,
    HISTORICAL_CACHE_PATH,
    OPEN_METEO_MAX_LOCATIONS,
)
from backend.app.ml.dataset_builder import _LANDING_CENTRES, _haversine
from ml.features.causal_dataset import FEATURE_COLUMNS, build_causal_dataset

logger = logging.getLogger(__name__)

PHASE3_MODEL_PATH = ARTIFACTS_DIR / "phase3_xgboost_model.joblib"
PHASE3_IMPUTER_PATH = ARTIFACTS_DIR / "phase3_imputer.joblib"
PHASE3_SCALER_PATH = ARTIFACTS_DIR / "phase3_scaler.joblib"
PHASE3_METADATA_PATH = ARTIFACTS_DIR / "phase3_metadata.json"
PHASE3_THRESHOLD_PATH = ARTIFACTS_DIR / "phase3_threshold.json"
PHASE3_FEATURES_PATH = ARTIFACTS_DIR / "phase3_feature_columns.json"


class Phase4InferencePipeline:
    """
    Phase 4 Inference Pipeline for next-calendar-day apparent fishing activity.
    """

    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self._model = None
        self._imputer = None
        self._scaler = None
        self._threshold_info = None
        self._feature_columns = None
        self._metadata = None
        self._loaded = False
        self._historical_reference_df: Optional[pd.DataFrame] = None
        self._cached_env_df: Optional[pd.DataFrame] = None
        self._cached_env_status: str = "UNKNOWN"
        self._cached_env_time: Optional[datetime] = None
        self._last_provenance: Optional[Dict[str, Any]] = None

    def load_artifacts(self):
        """Loads frozen Phase 3 model artifacts."""
        required = [
            PHASE3_MODEL_PATH,
            PHASE3_IMPUTER_PATH,
            PHASE3_SCALER_PATH,
            PHASE3_THRESHOLD_PATH,
            PHASE3_FEATURES_PATH,
        ]
        for f in required:
            if not f.exists():
                raise FileNotFoundError(
                    f"Phase 3 artifact missing: {f}. Run serialize_phase3_artifacts.py first."
                )

        self._model = joblib.load(PHASE3_MODEL_PATH)
        self._imputer = joblib.load(PHASE3_IMPUTER_PATH)
        self._scaler = joblib.load(PHASE3_SCALER_PATH)

        with open(PHASE3_THRESHOLD_PATH) as fp:
            self._threshold_info = json.load(fp)

        with open(PHASE3_FEATURES_PATH) as fp:
            self._feature_columns = json.load(fp)

        if PHASE3_METADATA_PATH.exists():
            with open(PHASE3_METADATA_PATH) as fp:
                self._metadata = json.load(fp)

        self._loaded = True
        logger.info(
            f"Loaded Phase 3 model ({self._metadata.get('model_version', 'Phase3_XGBoost_v1')}) "
            f"with decision threshold {self._threshold_info.get('decision_threshold', 0.47)}."
        )

    def _load_historical_context(self) -> pd.DataFrame:
        """
        Loads recent historical GFW patterns to seed causal trailing features.
        """
        if self._historical_reference_df is None:
            if HISTORICAL_CACHE_PATH.exists():
                logger.info(f"Loading historical context from {HISTORICAL_CACHE_PATH}...")
                df = pd.read_parquet(HISTORICAL_CACHE_PATH)
                df["observation_date"] = pd.to_datetime(df["observation_date"])
                self._historical_reference_df = df
            else:
                logger.warning("Historical cache path not found. Initializing empty GFW history.")
                self._historical_reference_df = pd.DataFrame()
        return self._historical_reference_df

    def _generate_grid(self) -> List[Dict]:
        """Generate canonical 0.25° Maharashtra marine grid cells."""
        cells = []
        lat = GRID_MIN_LAT
        while lat <= GRID_MAX_LAT:
            lon = GRID_MIN_LON
            while lon <= GRID_MAX_LON:
                centroid_lat = round(lat + GRID_RESOLUTION / 2, 4)
                centroid_lon = round(lon + GRID_RESOLUTION / 2, 4)
                
                # Check corners and centroid
                points = [
                    (centroid_lat, centroid_lon),
                    (lat, lon),
                    (lat + GRID_RESOLUTION, lon),
                    (lat, lon + GRID_RESOLUTION),
                    (lat + GRID_RESOLUTION, lon + GRID_RESOLUTION)
                ]
                
                # is_marine if any point is ocean
                if any(globe.is_ocean(p[0], p[1]) for p in points):
                    dist = min(
                        _haversine(centroid_lat, centroid_lon, lc[0], lc[1])
                        for lc in _LANDING_CENTRES
                    )
                    cell_id = f"cell_{lat:.2f}_{lon:.2f}_{GRID_RESOLUTION}"
                    cells.append({
                        "grid_cell_id": cell_id,
                        "latitude": centroid_lat,
                        "longitude": centroid_lon,
                        "distance_to_coast_km": round(dist, 2),
                        "is_coastal": 1.0 if dist <= 50.0 else 0.0,
                    })
                lon = round(lon + GRID_RESOLUTION, 4)
            lat = round(lat + GRID_RESOLUTION, 4)
        return cells

    def _fetch_current_env(self, grid_cells: List[Dict]) -> Tuple[pd.DataFrame, str]:
        """
        Fetches current environmental observations from Open-Meteo Current API.
        Falls back gracefully to cached real observations under DEMO_MODE if network is unavailable.
        """
        now = datetime.now(timezone.utc)
        if self._cached_env_df is not None and self._cached_env_time is not None:
            age_secs = (now - self._cached_env_time).total_seconds()
            if age_secs < 900:  # 15 minutes cache
                return self._cached_env_df, self._cached_env_status

        if self.demo_mode:
            logger.info("Operating in DEMO_MODE: Sourcing environmental data from real historical cache.")
            fb = self._get_fallback_env(grid_cells)
            self._cached_env_df = fb
            self._cached_env_status = "DEMO_MODE"
            self._cached_env_time = now
            return fb, "DEMO_MODE"

        centroids = [(c["latitude"], c["longitude"], c["grid_cell_id"]) for c in grid_cells]
        all_records = []
        batch_size = 40

        try:
            for i in range(0, len(centroids), batch_size):
                batch = centroids[i : i + batch_size]
                lats = ",".join(str(b[0]) for b in batch)
                lons = ",".join(str(b[1]) for b in batch)

                marine_url = (
                    f"https://marine-api.open-meteo.com/v1/marine"
                    f"?latitude={lats}&longitude={lons}"
                    f"&current=wave_height,wave_period,wave_direction,swell_wave_height"
                    f"&timezone=UTC"
                )
                weather_url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={lats}&longitude={lons}"
                    f"&current=wind_speed_10m"
                    f"&timezone=UTC"
                )

                marine_data = self._api_get(marine_url)
                weather_data = self._api_get(weather_url)

                if not marine_data and not weather_data:
                    raise ConnectionError("Live Open-Meteo API unreachable.")

                m_list = marine_data if isinstance(marine_data, list) else [marine_data]
                w_list = weather_data if isinstance(weather_data, list) else [weather_data]

                for idx, (lat_val, lon_val, cell_id) in enumerate(batch):
                    row = {"grid_cell_id": cell_id}
                    if idx < len(m_list) and m_list[idx]:
                        mc = m_list[idx].get("current", {})
                        row["wave_height"] = mc.get("wave_height")
                        row["wave_period"] = mc.get("wave_period")
                        row["wave_direction"] = mc.get("wave_direction")
                        row["swell_wave_height"] = mc.get("swell_wave_height")

                    if idx < len(w_list) and w_list[idx]:
                        wc = w_list[idx].get("current", {})
                        row["wind_speed"] = wc.get("wind_speed_10m")

                    all_records.append(row)

            res_df = pd.DataFrame(all_records)
            self._cached_env_df = res_df
            self._cached_env_status = "LIVE"
            self._cached_env_time = now
            return res_df, "LIVE"

        except Exception as e:
            logger.warning(f"Live environmental fetch failed ({e}). Switching to DEMO_MODE fallback.")
            fb = self._get_fallback_env(grid_cells)
            self._cached_env_df = fb
            self._cached_env_status = "DEMO_MODE"
            self._cached_env_time = now
            return fb, "DEMO_MODE"

    def _get_fallback_env(self, grid_cells: List[Dict]) -> pd.DataFrame:
        """Extracts representative real environmental records from historical data."""
        hist = self._load_historical_context()
        if hist.empty:
            return pd.DataFrame()
        latest_date = hist["observation_date"].max()
        subset = hist[hist["observation_date"] == latest_date][
            [
                "grid_cell_id",
                "wave_height",
                "wave_period",
                "wave_direction",
                "swell_wave_height",
                "ocean_current_velocity",
                "wind_speed",
            ]
        ].copy()
        return subset

    def _api_get(self, url: str) -> Any:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MatsyaAI-Phase4/1.0"})
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read().decode())
        except Exception as e:
            logger.debug(f"API request failed: {e}")
            return {}

    def _build_features(
        self, grid_cells: List[Dict], env_df: pd.DataFrame, prediction_time: datetime
    ) -> pd.DataFrame:
        """
        Builds the exact 29-feature matrix expected by the Phase 3 model.
        """
        df = pd.DataFrame(grid_cells)

        # Merge environmental variables
        if not env_df.empty:
            df = df.merge(env_df, on="grid_cell_id", how="left")
        else:
            for col in ["wave_height", "wave_period", "wave_direction", "swell_wave_height", "ocean_current_velocity", "wind_speed"]:
                df[col] = np.nan

        # Circular wave direction encoding
        if "wave_direction" in df.columns:
            df["wave_direction_sin"] = df["wave_direction"].apply(
                lambda v: math.sin(math.radians(float(v))) if pd.notna(v) else np.nan
            )
            df["wave_direction_cos"] = df["wave_direction"].apply(
                lambda v: math.cos(math.radians(float(v))) if pd.notna(v) else np.nan
            )
        else:
            df["wave_direction_sin"] = np.nan
            df["wave_direction_cos"] = np.nan

        # Missingness indicator flags
        df["wave_height_isna"] = df["wave_height"].isna().astype(float)
        df["ocean_current_isna"] = df["ocean_current_velocity"].isna().astype(float) if "ocean_current_velocity" in df.columns else 1.0
        df["wind_speed_isna"] = df["wind_speed"].isna().astype(float)

        # Temporal features
        doy = prediction_time.timetuple().tm_yday
        month = prediction_time.month
        dow = prediction_time.weekday()
        df["day_of_year"] = doy
        df["month"] = month
        df["day_of_week"] = dow
        df["sin_day_of_year"] = math.sin(2 * math.pi * doy / 365.25)
        df["cos_day_of_year"] = math.cos(2 * math.pi * doy / 365.25)

        # Historical GFW Features (causally computed from latest reference observations)
        hist = self._load_historical_context()
        if not hist.empty:
            # Group historical records by cell
            hist_by_cell = hist.groupby("grid_cell_id")
            recent_map = {}
            lag1_map = {}
            lag2_map = {}
            lag3_map = {}
            m7_map = {}
            max7_map = {}
            std7_map = {}
            freq7_map = {}
            m14_map = {}

            for cid, c_df in hist_by_cell:
                efforts = c_df.sort_values("observation_date")["fishing_hours"].values
                if len(efforts) > 0:
                    recent_map[cid] = float(efforts[-1])
                    lag1_map[cid] = float(efforts[-2]) if len(efforts) >= 2 else 0.0
                    lag2_map[cid] = float(efforts[-3]) if len(efforts) >= 3 else 0.0
                    lag3_map[cid] = float(efforts[-4]) if len(efforts) >= 4 else 0.0
                    w7 = efforts[-7:]
                    m7_map[cid] = float(np.mean(w7))
                    max7_map[cid] = float(np.max(w7))
                    std7_map[cid] = float(np.std(w7))
                    freq7_map[cid] = float(np.mean(w7 > 0))
                    w14 = efforts[-14:]
                    m14_map[cid] = float(np.mean(w14))

            df["fishing_hours_recent"] = df["grid_cell_id"].map(recent_map).fillna(0.0)
            df["fishing_hours_lag_1"] = df["grid_cell_id"].map(lag1_map).fillna(0.0)
            df["fishing_hours_lag_2"] = df["grid_cell_id"].map(lag2_map).fillna(0.0)
            df["fishing_hours_lag_3"] = df["grid_cell_id"].map(lag3_map).fillna(0.0)
            df["fishing_hours_7d_mean"] = df["grid_cell_id"].map(m7_map).fillna(0.0)
            df["fishing_hours_7d_max"] = df["grid_cell_id"].map(max7_map).fillna(0.0)
            df["fishing_hours_7d_std"] = df["grid_cell_id"].map(std7_map).fillna(0.0)
            df["fishing_hours_7d_pos_freq"] = df["grid_cell_id"].map(freq7_map).fillna(0.0)
            df["fishing_hours_14d_mean"] = df["grid_cell_id"].map(m14_map).fillna(0.0)
            df["regional_fishing_hours_T"] = float(df["fishing_hours_recent"].sum())
        else:
            for c in [
                "fishing_hours_recent",
                "fishing_hours_lag_1",
                "fishing_hours_lag_2",
                "fishing_hours_lag_3",
                "fishing_hours_7d_mean",
                "fishing_hours_7d_max",
                "fishing_hours_7d_std",
                "fishing_hours_7d_pos_freq",
                "fishing_hours_14d_mean",
                "regional_fishing_hours_T",
            ]:
                df[c] = 0.0

        # Guarantee all feature columns exist in exact training order
        for col in self._feature_columns:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _build_provenance(
        self, env_status: str, prediction_time: datetime
    ) -> Dict[str, Any]:
        """
        Builds prediction provenance metadata describing what data sources
        contributed and their freshness.

        This is METADATA ONLY — the frozen Phase 3 model logic is untouched.
        """
        now = prediction_time

        # --- Open-Meteo Marine source ---
        env_source: Dict[str, Any] = {
            "status": env_status,
            "data_timestamp": (self._cached_env_time.isoformat()
                               if self._cached_env_time else None),
            "age_minutes": None,
        }
        if self._cached_env_time:
            env_source["age_minutes"] = round(
                max(0.0, (now - self._cached_env_time).total_seconds() / 60.0), 1
            )

        # --- Global Fishing Watch historical context ---
        hist = self._historical_reference_df
        gfw_has_data = hist is not None and not hist.empty
        gfw_source: Dict[str, Any]
        if gfw_has_data:
            latest_obs_date = hist["observation_date"].max()
            if hasattr(latest_obs_date, 'to_pydatetime'):
                latest_obs_date = latest_obs_date.to_pydatetime()
            if latest_obs_date.tzinfo is None:
                from datetime import timezone as _tz
                latest_obs_date = latest_obs_date.replace(tzinfo=_tz.utc)
            age_days = (now.date() - latest_obs_date.date()).days
            gfw_source = {
                "status": "CACHED_HISTORICAL",
                "observation_date": latest_obs_date.isoformat(),
                "age_days": age_days,
                "record_count": len(hist),
            }
        else:
            gfw_source = {
                "status": "UNAVAILABLE",
                "observation_date": None,
                "age_days": None,
                "record_count": 0,
            }

        # --- Overall data status ---
        #  LIVE: all real-time inputs live, no historical source contributes
        #  HISTORICAL_CONTEXT: real-time env live but GFW historical cache contributes
        #  MIXED: some inputs live, some stale
        #  STALE: required real-time inputs are stale or in demo mode
        #  UNAVAILABLE: critical inputs missing
        if env_status == "LIVE" and not gfw_has_data:
            overall = "LIVE"
        elif env_status == "LIVE" and gfw_has_data:
            overall = "HISTORICAL_CONTEXT"
        elif env_status == "DEMO_MODE":
            if gfw_has_data:
                overall = "STALE"
            else:
                overall = "STALE"
        elif env_status in ("STALE",):
            overall = "MIXED" if gfw_has_data else "STALE"
        else:
            overall = "UNAVAILABLE"

        provenance = {
            "overall_data_status": overall,
            "historical_context_present": gfw_has_data,
            "prediction_timestamp": now.isoformat(),
            "sources": {
                "open_meteo_marine": env_source,
                "global_fishing_watch": gfw_source,
            },
        }
        return provenance

    def get_last_provenance(self) -> Optional[Dict[str, Any]]:
        """Returns the provenance metadata from the most recent predict() call."""
        return self._last_provenance

    def predict(self) -> List[Dict[str, Any]]:
        """
        Runs inference and produces predictions for all 171 canonical cells.
        """
        if not self._loaded:
            self.load_artifacts()

        prediction_time = datetime.now(timezone.utc)
        grid_cells = self._generate_grid()

        # Fetch environmental conditions
        env_df, freshness_status = self._fetch_current_env(grid_cells)

        # Build feature matrix
        feature_df = self._build_features(grid_cells, env_df, prediction_time)

        # Preprocessing strictly using frozen Phase 3 transformers
        X_raw = feature_df[self._feature_columns]
        X_imputed = self._imputer.transform(X_raw)
        X_scaled = self._scaler.transform(X_imputed)

        # Predict probabilities
        probabilities = self._model.predict_proba(X_scaled)[:, 1]
        decision_thresh = float(self._threshold_info.get("decision_threshold", 0.47))
        binary_classes = (probabilities >= decision_thresh).astype(int)

        model_version = self._metadata.get("model_version", "Phase3_XGBoost_v1")
        disclaimer = self._metadata.get(
            "disclaimer",
            "Predicts apparent fishing activity derived from historical GFW AIS patterns. "
            "Does not predict fish presence, biomass, species, or catch guarantee.",
        )

        # Build provenance metadata (does NOT alter model logic)
        provenance = self._build_provenance(freshness_status, prediction_time)
        self._last_provenance = provenance
        overall_data_status = provenance["overall_data_status"]

        results = []
        for idx, cell in enumerate(grid_cells):
            prob = round(float(probabilities[idx]), 4)
            b_class = int(binary_classes[idx])

            # Extract raw environmental observations for HUD/Safety check
            row_env = feature_df.iloc[idx]
            wh = float(row_env["wave_height"]) if pd.notna(row_env.get("wave_height")) else None
            ws = float(row_env["wind_speed"]) if pd.notna(row_env.get("wind_speed")) else None

            results.append({
                "grid_cell_id": cell["grid_cell_id"],
                "latitude": cell["latitude"],
                "longitude": cell["longitude"],
                "distance_to_coast_km": cell["distance_to_coast_km"],
                "is_coastal": bool(cell["is_coastal"]),
                # Strict target semantics
                "predicted_apparent_fishing_probability": prob,
                "predicted_apparent_fishing_binary": b_class,
                "prediction_label": (
                    "High predicted apparent fishing activity"
                    if b_class == 1
                    else "Low predicted apparent fishing activity"
                ),
                "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
                "decision_threshold": decision_thresh,
                "model_version": model_version,
                "prediction_timestamp": prediction_time.isoformat(),
                "data_freshness_status": overall_data_status,
                "disclaimer": disclaimer,
                # Environmental snapshot
                "current_wave_height_m": wh,
                "current_wind_speed_kmh": ws,
                # Safety fields (populated by independent safety gate)
                "safety_status": "NO_WARNING_DATA",
                "safety_override": False,
            })

        logger.info(
            f"Phase 4 inference complete: {sum(binary_classes)} active cells / "
            f"{len(binary_classes)} total (data_status: {overall_data_status})"
        )
        return results


# Global singleton pipeline instance
_pipeline_instance: Optional[Phase4InferencePipeline] = None


def get_inference_pipeline() -> Phase4InferencePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = Phase4InferencePipeline()
        _pipeline_instance.load_artifacts()
    return _pipeline_instance
