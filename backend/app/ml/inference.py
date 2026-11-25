"""
MatsyaAI Maharashtra — Phase 4 Production Inference Pipeline.

Supports the frozen two-stage `Phase4_SpatioOcean_v1` pipeline (Stage 1 Habitat
Suitability + Stage 2 Operational XGBoost + Post-Hoc Calibration) with clean
fallback to Phase 3 (`Phase3_XGBoost_v1`) when requested (`prefer_phase4=False`)
or when Phase 4 artifacts are absent.

All models and calibrators are strictly frozen during inference. Safety is NEVER
determined by ML scores; SafetyGate remains 100% independent.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

try:
    from global_land_mask import globe
except ImportError:
    globe = None

from backend.app.ml.config import (
    ARTIFACTS_DIR,
    GRID_MAX_LAT,
    GRID_MAX_LON,
    GRID_MIN_LAT,
    GRID_MIN_LON,
    GRID_RESOLUTION,
    HISTORICAL_CACHE_PATH,
    MULTIYEAR_HISTORICAL_CACHE_PATH,
    OCEAN_CACHE_DIR,
    PHASE4_CALIBRATOR_PATH,
    PHASE4_FEATURES_PATH,
    PHASE4_METADATA_PATH,
    PHASE4_SEASONAL_CALIBRATOR_PATH,
    PHASE4_STAGE1_IMPUTER_PATH,
    PHASE4_STAGE1_MODEL_PATH,
    PHASE4_STAGE1_SCALER_PATH,
    PHASE4_STAGE2_IMPUTER_PATH,
    PHASE4_STAGE2_MODEL_PATH,
    PHASE4_STAGE2_SCALER_PATH,
    PHASE4_THRESHOLD_PATH,
)
from backend.app.ml.dataset_builder import _LANDING_CENTRES, _haversine
from ml.features.features_spatial_ocean import (
    OCEAN_HABITAT_FEATURES,
    SPATIAL_NEIGHBOR_FEATURES,
    GriddedOceanIngestor,
    SpatialAdjacencyMapper,
    compute_ocean_habitat_features,
    compute_spatial_neighborhood_features,
)

logger = logging.getLogger(__name__)

PHASE3_MODEL_PATH = ARTIFACTS_DIR / "phase3_xgboost_model.joblib"
PHASE3_IMPUTER_PATH = ARTIFACTS_DIR / "phase3_imputer.joblib"
PHASE3_SCALER_PATH = ARTIFACTS_DIR / "phase3_scaler.joblib"
PHASE3_METADATA_PATH = ARTIFACTS_DIR / "phase3_metadata.json"
PHASE3_THRESHOLD_PATH = ARTIFACTS_DIR / "phase3_threshold.json"
PHASE3_FEATURES_PATH = ARTIFACTS_DIR / "phase3_feature_columns.json"


class Phase4InferencePipeline:
    """
    Production Inference Pipeline supporting two-stage Phase 4 (`Phase4_SpatioOcean_v1`)
    and frozen Phase 3 fallback (`Phase3_XGBoost_v1`).
    """

    def __init__(self, demo_mode: bool = False, prefer_phase4: bool = True):
        self.demo_mode = demo_mode
        self.prefer_phase4 = prefer_phase4
        self._pipeline_mode = "phase3"

        # Phase 3 fields
        self._model = None
        self._imputer = None
        self._scaler = None

        # Phase 4 fields
        self._stage1_model = None
        self._stage1_imputer = None
        self._stage1_scaler = None
        self._stage2_model = None
        self._stage2_imputer = None
        self._stage2_scaler = None
        self._calibrator = None
        self._seasonal_calibrator = None
        self._stage1_features: List[str] = []
        self._stage2_features: List[str] = []

        self._threshold_info: Dict[str, Any] = {}
        self._feature_columns: List[str] = []
        self._metadata: Dict[str, Any] = {}
        self._loaded = False

        self._historical_reference_df: Optional[pd.DataFrame] = None
        self._seasonal_anchor_date: Optional[pd.Timestamp] = None
        self._gfw_context_mode: str = "latest_active_window"
        self._cached_env_df: Optional[pd.DataFrame] = None
        self._cached_env_status: str = "UNKNOWN"
        self._cached_env_time: Optional[datetime] = None
        self._cached_ocean_status: str = "UNAVAILABLE"
        self._cached_ocean_latest_date: Optional[str] = None
        self._last_provenance: Optional[Dict[str, Any]] = None

    @staticmethod
    def _phase4_artifacts_exist() -> bool:
        required = [
            PHASE4_STAGE1_MODEL_PATH,
            PHASE4_STAGE1_IMPUTER_PATH,
            PHASE4_STAGE1_SCALER_PATH,
            PHASE4_STAGE2_MODEL_PATH,
            PHASE4_STAGE2_IMPUTER_PATH,
            PHASE4_STAGE2_SCALER_PATH,
            PHASE4_CALIBRATOR_PATH,
            PHASE4_FEATURES_PATH,
            PHASE4_THRESHOLD_PATH,
        ]
        return all(p.exists() for p in required)

    def load_artifacts(self):
        """Loads frozen Phase 4 artifacts if available and preferred; else loads Phase 3."""
        if self.prefer_phase4 and self._phase4_artifacts_exist():
            self._stage1_model = joblib.load(PHASE4_STAGE1_MODEL_PATH)
            self._stage1_imputer = joblib.load(PHASE4_STAGE1_IMPUTER_PATH)
            self._stage1_scaler = joblib.load(PHASE4_STAGE1_SCALER_PATH)
            self._stage2_model = joblib.load(PHASE4_STAGE2_MODEL_PATH)
            self._stage2_imputer = joblib.load(PHASE4_STAGE2_IMPUTER_PATH)
            self._stage2_scaler = joblib.load(PHASE4_STAGE2_SCALER_PATH)
            self._calibrator = joblib.load(PHASE4_CALIBRATOR_PATH)
            self._seasonal_calibrator = (
                joblib.load(PHASE4_SEASONAL_CALIBRATOR_PATH)
                if PHASE4_SEASONAL_CALIBRATOR_PATH.exists()
                else None
            )

            with open(PHASE4_FEATURES_PATH) as fp:
                feat_payload = json.load(fp)
            if isinstance(feat_payload, dict):
                self._stage1_features = list(feat_payload["stage1_features"])
                self._stage2_features = list(feat_payload["stage2_features"])
            else:
                self._stage2_features = list(feat_payload)
            self._feature_columns = list(self._stage2_features)

            with open(PHASE4_THRESHOLD_PATH) as fp:
                self._threshold_info = json.load(fp)

            if PHASE4_METADATA_PATH.exists():
                with open(PHASE4_METADATA_PATH) as fp:
                    self._metadata = json.load(fp)
            else:
                self._metadata = {"model_version": "Phase4_SpatioOcean_v1"}

            self._pipeline_mode = "phase4"
            self._loaded = True
            logger.info(
                f"Loaded Phase 4 two-stage model ({self._metadata.get('model_version', 'Phase4_SpatioOcean_v1')}) "
                f"with calibration={self._threshold_info.get('calibration_method')}, "
                f"threshold={self._threshold_info.get('decision_threshold')}."
            )
            return

        # Fallback to frozen Phase 3 pipeline
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
        else:
            self._metadata = {}

        self._pipeline_mode = "phase3"
        self._loaded = True
        logger.info(
            f"Loaded Phase 3 model ({self._metadata.get('model_version', 'Phase3_XGBoost_v1')}) "
            f"with decision threshold {self._threshold_info.get('decision_threshold', 0.47)}."
        )

    def _load_historical_context(self) -> pd.DataFrame:
        """Loads recent historical GFW patterns to seed causal trailing features."""
        if self._historical_reference_df is None:
            hist_path = (
                MULTIYEAR_HISTORICAL_CACHE_PATH
                if MULTIYEAR_HISTORICAL_CACHE_PATH.exists()
                else HISTORICAL_CACHE_PATH
            )
            if hist_path.exists():
                logger.info(f"Loading historical context from {hist_path}...")
                df = pd.read_parquet(hist_path)
                df["observation_date"] = pd.to_datetime(df["observation_date"])
                self._historical_reference_df = df
            else:
                logger.warning("Historical cache path not found. Initializing empty GFW history.")
                self._historical_reference_df = pd.DataFrame()
        return self._historical_reference_df

    @staticmethod
    def _resolve_seasonal_anchor_date(prediction_time: datetime, max_dt: pd.Timestamp) -> pd.Timestamp:
        """Resolve the most recent date <= max_dt sharing prediction_time's calendar month/day."""
        anchor_year = int(max_dt.year)
        month = int(prediction_time.month)
        while anchor_year >= int(max_dt.year) - 5:
            max_day = int(pd.Timestamp(year=anchor_year, month=month, day=1).days_in_month)
            cand = pd.Timestamp(year=anchor_year, month=month, day=min(int(prediction_time.day), max_day))
            if cand <= max_dt:
                return cand
            anchor_year -= 1
        return max_dt

    def _get_effective_gfw_history(self, prediction_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        Return causal GFW trailing history:
        - When historical context spans >= 2 years and lags prediction_time by > 14 days,
          builds a 5-year seasonal climatology over the matching 14-day calendar window
          (applying a < 1.0 h noise floor matching the > 1.0 h active target) so inference
          reflects typical seasonal fishing distribution rather than year-end AIS gaps.
        - Otherwise returns history up to the latest date with actual AIS coverage (`fishing_hours > 0`).
        """
        self._seasonal_anchor_date = None
        self._gfw_context_mode = "latest_active_window"
        hist = self._load_historical_context()
        if hist.empty:
            return hist

        obs_dt = pd.to_datetime(hist["observation_date"])
        max_dt = obs_dt.max()
        years = int(obs_dt.dt.year.nunique())

        if prediction_time is not None and years >= 2 and (pd.Timestamp(prediction_time.date()) - max_dt).days > 14:
            target_doy = min(365, int(prediction_time.timetuple().tm_yday))
            window_doys = [((target_doy - 13 + k - 1) % 365) + 1 for k in range(14)]
            anchor_dt = self._resolve_seasonal_anchor_date(prediction_time, max_dt)
            self._seasonal_anchor_date = anchor_dt
            self._gfw_context_mode = "multiyear_seasonal_climatology"

            doy_series = obs_dt.dt.dayofyear
            sub = hist[doy_series.isin(window_doys)].copy()
            sub["_doy"] = pd.to_datetime(sub["observation_date"]).dt.dayofyear

            agg_spec: Dict[str, str] = {"fishing_hours": "mean"}
            if "ocean_current_velocity" in sub.columns:
                agg_spec["ocean_current_velocity"] = "mean"

            clim = sub.groupby(["grid_cell_id", "_doy"], as_index=False).agg(agg_spec)
            clim.loc[clim["fishing_hours"] < 1.0, "fishing_hours"] = 0.0
            doy_to_date = {d: anchor_dt - pd.Timedelta(days=13 - i) for i, d in enumerate(window_doys)}
            clim["observation_date"] = clim["_doy"].map(doy_to_date)
            clim = clim.drop(columns=["_doy"]).sort_values(["grid_cell_id", "observation_date"]).reset_index(drop=True)
            return clim

        daily_sum = hist.groupby("observation_date")["fishing_hours"].sum()
        active_dates = daily_sum[daily_sum > 0.0].index
        if len(active_dates) > 0:
            latest_active = active_dates.max()
            return hist[hist["observation_date"] <= latest_active].copy()
        return hist

    def _generate_grid(self) -> List[Dict]:
        """
        Generate canonical 0.25-deg Maharashtra marine grid cells.
        Uses global_land_mask when installed; otherwise extracts the exact canonical
        97 ocean-masked grid cells from the validated historical dataset.
        """
        if globe is None:
            hist = self._load_historical_context()
            if not hist.empty and {"grid_cell_id", "latitude", "longitude"}.issubset(hist.columns):
                unique_cells = (
                    hist[["grid_cell_id", "latitude", "longitude"]]
                    .drop_duplicates(subset=["grid_cell_id"])
                    .sort_values("grid_cell_id")
                )
                cells: List[Dict[str, Any]] = []
                for row in unique_cells.itertuples(index=False):
                    c_lat = round(float(row.latitude), 4)
                    c_lon = round(float(row.longitude), 4)
                    dist = min(
                        _haversine(c_lat, c_lon, lc[0], lc[1])
                        for lc in _LANDING_CENTRES
                    )
                    cells.append(
                        {
                            "grid_cell_id": str(row.grid_cell_id),
                            "latitude": c_lat,
                            "longitude": c_lon,
                            "distance_to_coast_km": round(dist, 2),
                            "is_coastal": 1.0 if dist <= 50.0 else 0.0,
                        }
                    )
                return cells

        cells = []
        lat = GRID_MIN_LAT
        while lat <= GRID_MAX_LAT:
            lon = GRID_MIN_LON
            while lon <= GRID_MAX_LON:
                centroid_lat = round(lat + GRID_RESOLUTION / 2, 4)
                centroid_lon = round(lon + GRID_RESOLUTION / 2, 4)

                points = [
                    (centroid_lat, centroid_lon),
                    (lat, lon),
                    (lat + GRID_RESOLUTION, lon),
                    (lat, lon + GRID_RESOLUTION),
                    (lat + GRID_RESOLUTION, lon + GRID_RESOLUTION),
                ]

                if globe is not None:
                    is_ocean = any(globe.is_ocean(p[0], p[1]) for p in points)
                else:
                    is_ocean = centroid_lon <= 73.25 or centroid_lat <= 16.75

                if is_ocean:
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

    def _fetch_current_env(
        self, grid_cells: List[Dict], prediction_time: Optional[datetime] = None
    ) -> Tuple[pd.DataFrame, str]:
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
            fb = self._get_fallback_env(grid_cells, prediction_time=prediction_time)
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
                    f"&current=wave_height,wave_period,wave_direction,swell_wave_height,ocean_current_velocity"
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

                for idx, (_lat_val, _lon_val, cell_id) in enumerate(batch):
                    row: Dict[str, Any] = {"grid_cell_id": cell_id}
                    if idx < len(m_list) and m_list[idx]:
                        mc = m_list[idx].get("current", {})
                        row["wave_height"] = mc.get("wave_height")
                        row["wave_period"] = mc.get("wave_period")
                        row["wave_direction"] = mc.get("wave_direction")
                        row["swell_wave_height"] = mc.get("swell_wave_height")
                        row["ocean_current_velocity"] = mc.get("ocean_current_velocity")

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
            fb = self._get_fallback_env(grid_cells, prediction_time=prediction_time)
            self._cached_env_df = fb
            self._cached_env_status = "DEMO_MODE"
            self._cached_env_time = now
            return fb, "DEMO_MODE"

    def _get_fallback_env(
        self, grid_cells: List[Dict], prediction_time: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Extracts representative real environmental records from historical data (season-aligned when multi-year)."""
        hist = self._load_historical_context()
        if hist.empty:
            return pd.DataFrame()
        obs_dt = pd.to_datetime(hist["observation_date"])
        max_dt = obs_dt.max()
        target_dt = max_dt
        if self._seasonal_anchor_date is not None:
            eligible = obs_dt[obs_dt <= self._seasonal_anchor_date]
            if not eligible.empty:
                target_dt = eligible.max()
        elif prediction_time is not None and int(obs_dt.dt.year.nunique()) >= 2 and (pd.Timestamp(prediction_time.date()) - max_dt).days > 14:
            cand = self._resolve_seasonal_anchor_date(prediction_time, max_dt)
            eligible = obs_dt[obs_dt <= cand]
            if not eligible.empty:
                target_dt = eligible.max()
        subset = hist[obs_dt == target_dt][
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
        Builds the 29 base Phase 3 features cleanly for both Phase 3 and Phase 4 pipelines.
        """
        df = pd.DataFrame(grid_cells)

        if not env_df.empty:
            df = df.merge(env_df, on="grid_cell_id", how="left")
        else:
            for col in ["wave_height", "wave_period", "wave_direction", "swell_wave_height", "ocean_current_velocity", "wind_speed"]:
                df[col] = np.nan

        if "ocean_current_velocity" not in df.columns:
            df["ocean_current_velocity"] = np.nan

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

        df["wave_height_isna"] = df["wave_height"].isna().astype(float)
        df["ocean_current_isna"] = df["ocean_current_velocity"].isna().astype(float)
        df["wind_speed_isna"] = df["wind_speed"].isna().astype(float)

        doy = prediction_time.timetuple().tm_yday
        month = prediction_time.month
        dow = prediction_time.weekday()
        df["day_of_year"] = doy
        df["month"] = month
        df["day_of_week"] = dow
        df["sin_day_of_year"] = math.sin(2 * math.pi * doy / 365.25)
        df["cos_day_of_year"] = math.cos(2 * math.pi * doy / 365.25)

        hist = self._get_effective_gfw_history(prediction_time=prediction_time)
        if not hist.empty:
            hist_by_cell = hist.groupby("grid_cell_id")
            recent_map: Dict[str, float] = {}
            lag1_map: Dict[str, float] = {}
            lag2_map: Dict[str, float] = {}
            lag3_map: Dict[str, float] = {}
            m7_map: Dict[str, float] = {}
            max7_map: Dict[str, float] = {}
            std7_map: Dict[str, float] = {}
            freq7_map: Dict[str, float] = {}
            m14_map: Dict[str, float] = {}

            for cid, c_df in hist_by_cell:
                efforts = c_df.sort_values("observation_date")["fishing_hours"].fillna(0.0).values
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

        for col in self._feature_columns:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _build_phase4_features(
        self, grid_cells: List[Dict], env_df: pd.DataFrame, prediction_time: datetime
    ) -> pd.DataFrame:
        """
        Extends the base feature matrix with causal spatial neighborhood AIS context,
        current convergence proxy, GEBCO bathymetry, daily SST thermal front gradients,
        and trailing 3/7/14-day Chl-a habitat signals.
        """
        df = self._build_features(grid_cells, env_df, prediction_time)
        mapper = SpatialAdjacencyMapper(grid_cells)

        # 1. Spatial neighbor AIS context from trailing historical window
        hist = self._get_effective_gfw_history(prediction_time=prediction_time)
        if not hist.empty:
            hist_dates = sorted(pd.to_datetime(hist["observation_date"]).unique())
            tail_dates = hist_dates[-14:]
            hist_tail = hist[pd.to_datetime(hist["observation_date"]).isin(tail_dates)][
                ["grid_cell_id", "observation_date", "fishing_hours", "ocean_current_velocity"]
            ].copy()
            ais_nbr_all = compute_spatial_neighborhood_features(hist_tail, mapper, gfw_lag_days=0)
            latest_gfw_dt = ais_nbr_all["observation_date"].max()
            ais_nbr_latest = ais_nbr_all[ais_nbr_all["observation_date"] == latest_gfw_dt].drop(
                columns=["observation_date", "current_convergence_proxy", "current_convergence_isna"],
                errors="ignore",
            )
            df = df.drop(columns=[c for c in ais_nbr_latest.columns if c != "grid_cell_id" and c in df.columns])
            df = df.merge(ais_nbr_latest, on="grid_cell_id", how="left")
        else:
            for col in SPATIAL_NEIGHBOR_FEATURES:
                if not col.startswith("current_convergence"):
                    df[col] = 0.0

        # 2. Current convergence proxy strictly from active env_df snapshot
        curr_frame = df[["grid_cell_id", "ocean_current_velocity"]].copy()
        curr_frame["observation_date"] = pd.Timestamp(prediction_time.date())
        curr_frame["fishing_hours"] = 0.0
        conv_df = compute_spatial_neighborhood_features(curr_frame, mapper, gfw_lag_days=0)[
            ["grid_cell_id", "current_convergence_proxy", "current_convergence_isna"]
        ]
        df = df.drop(columns=[c for c in ("current_convergence_proxy", "current_convergence_isna") if c in df.columns])
        df = df.merge(conv_df, on="grid_cell_id", how="left")

        # 3. Ocean habitat + bathymetry features from cache (never blocks on missing network)
        ingestor = GriddedOceanIngestor(ocean_cache_dir=OCEAN_CACHE_DIR)
        bathy_df = ingestor.load_bathymetry(grid_cells, allow_fetch=False)
        sst_all = ingestor.load_daily_sst(grid_cells, "2020-01-01", "2030-12-31", allow_fetch=False)
        chl_all = ingestor.load_daily_chla(grid_cells, "2020-01-01", "2030-12-31", allow_fetch=False)

        ocean_dates = sorted(
            set(pd.to_datetime(sst_all["observation_date"]).unique() if not sst_all.empty else [])
            | set(pd.to_datetime(chl_all["observation_date"]).unique() if not chl_all.empty else [])
        )
        if self._seasonal_anchor_date is not None and ocean_dates:
            anchored_ocean = [d for d in ocean_dates if pd.Timestamp(d) <= self._seasonal_anchor_date]
            if anchored_ocean:
                ocean_dates = anchored_ocean

        if ocean_dates:
            tail_ocean_dates = ocean_dates[-14:]
            latest_ocean_dt = pd.Timestamp(tail_ocean_dates[-1])
            self._cached_ocean_status = "CACHED_OCEAN"
            self._cached_ocean_latest_date = str(latest_ocean_dt.date())

            grid_rows = []
            for dt_val in tail_ocean_dates:
                for c in grid_cells:
                    grid_rows.append({"grid_cell_id": c["grid_cell_id"], "observation_date": dt_val})
            ocean_panel = pd.DataFrame(grid_rows)
            ocean_feats_all = compute_ocean_habitat_features(
                ocean_panel, mapper, sst_df=sst_all, chla_df=chl_all, bathy_df=bathy_df
            )
            ocean_latest = ocean_feats_all[ocean_feats_all["observation_date"] == latest_ocean_dt].drop(
                columns=["observation_date"]
            )
        else:
            self._cached_ocean_status = "UNAVAILABLE"
            self._cached_ocean_latest_date = None
            ocean_panel = pd.DataFrame(
                [
                    {
                        "grid_cell_id": c["grid_cell_id"],
                        "observation_date": pd.Timestamp(prediction_time.date()),
                    }
                    for c in grid_cells
                ]
            )
            ocean_latest = compute_ocean_habitat_features(
                ocean_panel, mapper, sst_df=None, chla_df=None, bathy_df=bathy_df
            ).drop(columns=["observation_date"])

        df = df.drop(columns=[c for c in OCEAN_HABITAT_FEATURES if c in df.columns])
        df = df.merge(ocean_latest, on="grid_cell_id", how="left")

        for col in set(self._stage1_features + self._stage2_features):
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _build_provenance(
        self, env_status: str, prediction_time: datetime
    ) -> Dict[str, Any]:
        """
        Builds prediction provenance metadata describing what data sources
        contributed and their freshness.
        """
        now = prediction_time

        env_source: Dict[str, Any] = {
            "status": env_status,
            "data_timestamp": (
                self._cached_env_time.isoformat() if self._cached_env_time else None
            ),
            "age_minutes": None,
        }
        if self._cached_env_time:
            env_source["age_minutes"] = round(
                max(0.0, (now - self._cached_env_time).total_seconds() / 60.0), 1
            )

        hist = self._historical_reference_df
        gfw_has_data = hist is not None and not hist.empty
        if gfw_has_data:
            latest_obs_date = hist["observation_date"].max()
            if hasattr(latest_obs_date, "to_pydatetime"):
                latest_obs_date = latest_obs_date.to_pydatetime()
            if latest_obs_date.tzinfo is None:
                latest_obs_date = latest_obs_date.replace(tzinfo=timezone.utc)
            age_days = (now.date() - latest_obs_date.date()).days
            gfw_source = {
                "status": "CACHED_HISTORICAL",
                "observation_date": latest_obs_date.isoformat(),
                "age_days": age_days,
                "record_count": len(hist),
                "context_mode": self._gfw_context_mode,
                "seasonal_anchor_date": (
                    str(self._seasonal_anchor_date.date())
                    if self._seasonal_anchor_date is not None
                    else None
                ),
            }
        else:
            gfw_source = {
                "status": "UNAVAILABLE",
                "observation_date": None,
                "age_days": None,
                "record_count": 0,
            }

        if env_status == "LIVE" and not gfw_has_data:
            overall = "LIVE"
        elif env_status == "LIVE" and gfw_has_data:
            overall = "HISTORICAL_CONTEXT"
        elif env_status == "DEMO_MODE":
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
                "ocean_habitat": {
                    "status": self._cached_ocean_status,
                    "latest_observation_date": self._cached_ocean_latest_date,
                },
            },
        }
        return provenance

    def get_last_provenance(self) -> Optional[Dict[str, Any]]:
        """Returns the provenance metadata from the most recent predict() call."""
        return self._last_provenance

    def predict(self) -> List[Dict[str, Any]]:
        """
        Runs frozen inference and produces predictions for all canonical Maharashtra cells.
        """
        if not self._loaded:
            self.load_artifacts()

        prediction_time = datetime.now(timezone.utc)
        grid_cells = self._generate_grid()

        env_df, freshness_status = self._fetch_current_env(grid_cells, prediction_time=prediction_time)

        if self._pipeline_mode == "phase4":
            feature_df = self._build_phase4_features(grid_cells, env_df, prediction_time)

            X1_raw = feature_df[self._stage1_features]
            X1_imp = self._stage1_imputer.transform(X1_raw)
            X1_scl = self._stage1_scaler.transform(X1_imp)
            habitat_scores = np.clip(self._stage1_model.predict_proba(X1_scl)[:, 1], 0.0, 1.0)
            feature_df["habitat_suitability_score"] = habitat_scores

            X2_raw = feature_df[self._stage2_features]
            X2_imp = self._stage2_imputer.transform(X2_raw)
            X2_scl = self._stage2_scaler.transform(X2_imp)
            raw_probs = np.clip(self._stage2_model.predict_proba(X2_scl)[:, 1], 0.0, 1.0)
            if self._gfw_context_mode == "multiyear_seasonal_climatology" and self._seasonal_calibrator is not None:
                probabilities = np.clip(self._seasonal_calibrator.predict_proba(raw_probs), 0.0, 1.0)
                active_cal_method = f"{self._seasonal_calibrator.method}_seasonal"
                prediction_mode = "seasonal_climatology"
            else:
                probabilities = np.clip(self._calibrator.predict_proba(raw_probs), 0.0, 1.0)
                active_cal_method = getattr(self._calibrator, "method", "unknown")
                prediction_mode = (
                    "seasonal_climatology"
                    if self._gfw_context_mode == "multiyear_seasonal_climatology"
                    else "daily_operational"
                )
            default_version = "Phase4_SpatioOcean_v1"
        else:
            feature_df = self._build_features(grid_cells, env_df, prediction_time)
            X_raw = feature_df[self._feature_columns]
            X_imputed = self._imputer.transform(X_raw)
            X_scaled = self._scaler.transform(X_imputed)
            probabilities = np.clip(self._model.predict_proba(X_scaled)[:, 1], 0.0, 1.0)
            habitat_scores = None
            active_cal_method = None
            prediction_mode = "daily_operational"
            default_version = "Phase3_XGBoost_v1"

        base_thresh = float(self._threshold_info.get("decision_threshold", 0.47))
        decision_thresh = (
            float(self._threshold_info.get("seasonal_decision_threshold", base_thresh))
            if prediction_mode == "seasonal_climatology"
            else base_thresh
        )
        seasonal_anchor_str = (
            str(self._seasonal_anchor_date.date()) if self._seasonal_anchor_date is not None else None
        )
        binary_classes = (probabilities >= decision_thresh).astype(int)

        model_version = self._metadata.get("model_version", default_version)
        disclaimer = self._metadata.get(
            "disclaimer",
            "Predicts apparent fishing activity derived from historical GFW AIS patterns. "
            "Does not predict fish presence, biomass, species, or catch guarantee.",
        )

        provenance = self._build_provenance(freshness_status, prediction_time)
        provenance["prediction_mode"] = prediction_mode
        self._last_provenance = provenance
        overall_data_status = provenance["overall_data_status"]

        results: List[Dict[str, Any]] = []
        for idx, cell in enumerate(grid_cells):
            prob = round(float(probabilities[idx]), 4)
            b_class = 1 if prob >= decision_thresh else 0

            row_env = feature_df.iloc[idx]
            wh = float(row_env["wave_height"]) if pd.notna(row_env.get("wave_height")) else None
            ws = float(row_env["wind_speed"]) if pd.notna(row_env.get("wind_speed")) else None

            rec: Dict[str, Any] = {
                "grid_cell_id": cell["grid_cell_id"],
                "latitude": cell["latitude"],
                "longitude": cell["longitude"],
                "distance_to_coast_km": cell["distance_to_coast_km"],
                "is_coastal": bool(cell["is_coastal"]),
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
                "prediction_mode": prediction_mode,
                "seasonal_anchor_date": seasonal_anchor_str,
                "prediction_timestamp": prediction_time.isoformat(),
                "data_freshness_status": overall_data_status,
                "disclaimer": disclaimer,
                "current_wave_height_m": wh,
                "current_wind_speed_kmh": ws,
                "safety_status": "NO_WARNING_DATA",
                "safety_override": False,
            }
            if habitat_scores is not None:
                rec["habitat_suitability_score"] = round(float(habitat_scores[idx]), 4)
                rec["calibration_method"] = active_cal_method or "unknown"

            results.append(rec)

        logger.info(
            f"Inference complete ({model_version}): {sum(r['predicted_apparent_fishing_binary'] for r in results)} "
            f"active cells / {len(results)} total (data_status: {overall_data_status})"
        )
        return results


_pipeline_instance: Optional[Phase4InferencePipeline] = None


def get_inference_pipeline() -> Phase4InferencePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = Phase4InferencePipeline()
        _pipeline_instance.load_artifacts()
    return _pipeline_instance
