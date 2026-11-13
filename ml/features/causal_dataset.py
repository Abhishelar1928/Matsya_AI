"""
Matsya AI — Causal Dataset Builder for Phase 3.

Strictly enforces causal feature engineering for Next-Calendar-Day prediction:
- Prediction date = T
- Features = Information available at or before T
- Target = GFW apparent fishing activity/effort on T+1 calendar day
- No future information is permitted to enter any feature.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.app.ml.config import HISTORICAL_CACHE_PATH

logger = logging.getLogger(__name__)


def build_causal_dataset(
    source_parquet_path: Optional[Path] = None,
    lookback_days: int = 14,
    gfw_lag_days: int = 0,
) -> pd.DataFrame:
    """
    Constructs a tabular dataset where each row corresponds to:
    - (grid_cell_id, prediction_date_T)
    - All features computed strictly using data available on or before date T.
    - Target: fishing_hours on calendar day T+1.
    
    :param source_parquet_path: Path to raw historical daily records.
    :param lookback_days: Days reserved at the start to seed rolling windows.
    :param gfw_lag_days: Availability lag for GFW (0 for prospective/same-day, 4 for conservative backtest).
    """
    path = source_parquet_path or HISTORICAL_CACHE_PATH
    df = pd.read_parquet(path)
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    df = df.sort_values(["grid_cell_id", "observation_date"]).reset_index(drop=True)
    
    # Fill apparent fishing effort: non-reported in GFW 4Wings implies no detected AIS fishing
    # but we record missingness of environmental data explicitly.
    df["fishing_hours"] = df["fishing_hours"].fillna(0.0)

    # 1. Precompute fleet-wide total daily effort (regional activity at T)
    daily_regional_effort = (
        df.groupby("observation_date")["fishing_hours"]
        .sum()
        .rename("regional_fishing_hours_T")
        .to_dict()
    )

    records = []
    
    # Process cell by cell to ensure causal window computations
    grouped = df.groupby("grid_cell_id")
    
    for cell_id, cell_df in grouped:
        cell_df = cell_df.sort_values("observation_date").reset_index(drop=True)
        dates = cell_df["observation_date"].values
        efforts = cell_df["fishing_hours"].values
        lats = cell_df["latitude"].values
        lons = cell_df["longitude"].values
        dist_coasts = cell_df["distance_to_coast_km"].values
        
        # Environmental variables
        wave_heights = cell_df["wave_height"].values if "wave_height" in cell_df else [np.nan]*len(dates)
        wave_periods = cell_df["wave_period"].values if "wave_period" in cell_df else [np.nan]*len(dates)
        wave_dirs = cell_df["wave_direction"].values if "wave_direction" in cell_df else [np.nan]*len(dates)
        swell_heights = cell_df["swell_wave_height"].values if "swell_wave_height" in cell_df else [np.nan]*len(dates)
        current_vels = cell_df["ocean_current_velocity"].values if "ocean_current_velocity" in cell_df else [np.nan]*len(dates)
        wind_speeds = cell_df["wind_speed"].values if "wind_speed" in cell_df else [np.nan]*len(dates)

        n_days = len(dates)
        
        # We need at least lookback_days of history, and at least 1 future day for target T+1
        # Loop over i where i is prediction day index T
        for i in range(lookback_days, n_days - 1):
            date_T = pd.Timestamp(dates[i])
            date_T_plus_1 = pd.Timestamp(dates[i + 1])
            
            # Verify exact 1-day spacing
            if (date_T_plus_1 - date_T).days != 1:
                continue
                
            # TARGET: Next-calendar-day fishing effort (T+1)
            target_effort = float(efforts[i + 1])
            
            # Eligible GFW index according to lag policy
            # If gfw_lag_days = 0, most recent is day T (index i)
            # If gfw_lag_days = 4, most recent is day T-4 (index i - 4)
            idx_recent = i - gfw_lag_days
            if idx_recent < 0:
                continue
                
            recent_effort = float(efforts[idx_recent])
            
            # Lagged effort values
            lag_1 = float(efforts[idx_recent - 1]) if idx_recent >= 1 else 0.0
            lag_2 = float(efforts[idx_recent - 2]) if idx_recent >= 2 else 0.0
            lag_3 = float(efforts[idx_recent - 3]) if idx_recent >= 3 else 0.0
            
            # Trailing 7-day window: [idx_recent - 6 ... idx_recent] (strictly causal)
            w7_start = max(0, idx_recent - 6)
            w7 = efforts[w7_start : idx_recent + 1]
            rolling_7d_mean = float(np.mean(w7)) if len(w7) > 0 else 0.0
            rolling_7d_max = float(np.max(w7)) if len(w7) > 0 else 0.0
            rolling_7d_std = float(np.std(w7)) if len(w7) > 0 else 0.0
            rolling_7d_pos_freq = float(np.mean(w7 > 0)) if len(w7) > 0 else 0.0
            
            # Trailing 14-day window: [idx_recent - 13 ... idx_recent]
            w14_start = max(0, idx_recent - 13)
            w14 = efforts[w14_start : idx_recent + 1]
            rolling_14d_mean = float(np.mean(w14)) if len(w14) > 0 else 0.0
            
            # Environmental features at prediction date T
            wh = wave_heights[i]
            wp = wave_periods[i]
            wdir = wave_dirs[i]
            swh = swell_heights[i]
            cv = current_vels[i]
            ws = wind_speeds[i]
            
            # Circular encoding of wave direction (degrees to sin and cos)
            if pd.notna(wdir):
                rad = math.radians(float(wdir))
                wave_dir_sin = math.sin(rad)
                wave_dir_cos = math.cos(rad)
            else:
                wave_dir_sin = np.nan
                wave_dir_cos = np.nan
                
            # Missingness indicator flags
            wh_isna = 1.0 if pd.isna(wh) else 0.0
            cv_isna = 1.0 if pd.isna(cv) else 0.0
            ws_isna = 1.0 if pd.isna(ws) else 0.0
            
            # Temporal features
            doy = date_T.dayofyear
            month = date_T.month
            dow = date_T.dayofweek
            sin_doy = math.sin(2 * math.pi * doy / 365.25)
            cos_doy = math.cos(2 * math.pi * doy / 365.25)
            
            # Spatial features
            lat = float(lats[i])
            lon = float(lons[i])
            dist_c = float(dist_coasts[i])
            is_coastal = 1.0 if dist_c <= 50.0 else 0.0
            
            # Regional fleet activity at T
            reg_effort_T = float(daily_regional_effort.get(date_T, 0.0))
            
            rec = {
                "grid_cell_id": cell_id,
                "prediction_date_T": date_T.strftime("%Y-%m-%d"),
                "target_date_T_plus_1": date_T_plus_1.strftime("%Y-%m-%d"),
                # Target
                "target_fishing_hours": target_effort,
                # Baselines & Causal Historical Features
                "fishing_hours_recent": recent_effort,
                "fishing_hours_lag_1": lag_1,
                "fishing_hours_lag_2": lag_2,
                "fishing_hours_lag_3": lag_3,
                "fishing_hours_7d_mean": rolling_7d_mean,
                "fishing_hours_7d_max": rolling_7d_max,
                "fishing_hours_7d_std": rolling_7d_std,
                "fishing_hours_7d_pos_freq": rolling_7d_pos_freq,
                "fishing_hours_14d_mean": rolling_14d_mean,
                "regional_fishing_hours_T": reg_effort_T,
                # Environmental Features at T
                "wave_height": float(wh) if pd.notna(wh) else np.nan,
                "wave_period": float(wp) if pd.notna(wp) else np.nan,
                "wave_direction_sin": float(wave_dir_sin) if pd.notna(wave_dir_sin) else np.nan,
                "wave_direction_cos": float(wave_dir_cos) if pd.notna(wave_dir_cos) else np.nan,
                "swell_wave_height": float(swh) if pd.notna(swh) else np.nan,
                "ocean_current_velocity": float(cv) if pd.notna(cv) else np.nan,
                "wind_speed": float(ws) if pd.notna(ws) else np.nan,
                # Missingness indicators
                "wave_height_isna": wh_isna,
                "ocean_current_isna": cv_isna,
                "wind_speed_isna": ws_isna,
                # Spatial & Coordinates
                "latitude": lat,
                "longitude": lon,
                "distance_to_coast_km": dist_c,
                "is_coastal": is_coastal,
                # Temporal
                "day_of_year": doy,
                "month": month,
                "day_of_week": dow,
                "sin_day_of_year": sin_doy,
                "cos_day_of_year": cos_doy,
            }
            records.append(rec)

    dataset_df = pd.DataFrame(records)
    dataset_df["prediction_date_T"] = pd.to_datetime(dataset_df["prediction_date_T"])
    dataset_df["target_date_T_plus_1"] = pd.to_datetime(dataset_df["target_date_T_plus_1"])
    dataset_df = dataset_df.sort_values(["prediction_date_T", "grid_cell_id"]).reset_index(drop=True)
    
    logger.info(
        f"Constructed causal dataset: {len(dataset_df)} rows, "
        f"{dataset_df['grid_cell_id'].nunique()} cells, "
        f"dates from {dataset_df['prediction_date_T'].min().date()} to {dataset_df['prediction_date_T'].max().date()}"
    )
    return dataset_df


FEATURE_COLUMNS = [
    # Historical GFW (causal)
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
    # Environmental
    "wave_height",
    "wave_period",
    "wave_direction_sin",
    "wave_direction_cos",
    "swell_wave_height",
    "ocean_current_velocity",
    "wind_speed",
    # Missingness indicators
    "wave_height_isna",
    "ocean_current_isna",
    "wind_speed_isna",
    # Spatial
    "latitude",
    "longitude",
    "distance_to_coast_km",
    "is_coastal",
    # Temporal
    "day_of_year",
    "month",
    "day_of_week",
    "sin_day_of_year",
    "cos_day_of_year",
]
