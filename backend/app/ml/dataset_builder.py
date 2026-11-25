"""
MatsyaAI Maharashtra — Historical Dataset Builder.

Builds a temporally-aligned training dataset by:
1. Fetching GFW fishing effort with per-day observation dates
2. Fetching historical environmental data from Open-Meteo for those SAME dates
3. Joining on (grid_cell_id, observation_date) — never on grid_cell_id alone
4. Caching the result as Parquet for reproducibility

CRITICAL RULES:
- Environmental data MUST correspond to the GFW observation date
- NaN is preserved when data is genuinely missing — never filled with 0
- The dataset is self-contained: no database dependency for training
"""
import logging
import json
import math
try:
    from global_land_mask import globe
except ImportError:
    globe = None
import time
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import numpy as np

from backend.app.ml.config import (
    GRID_RESOLUTION, GRID_MIN_LAT, GRID_MAX_LAT, GRID_MIN_LON, GRID_MAX_LON,
    GFW_START_DATE, GFW_END_DATE,
    OPEN_METEO_MARINE_URL, OPEN_METEO_WEATHER_URL,
    HISTORICAL_MARINE_VARIABLES, HISTORICAL_WEATHER_VARIABLES,
    OPEN_METEO_MAX_LOCATIONS, ENV_DAILY_AGGREGATION,
    HISTORICAL_CACHE_PATH, ENV_RAW_CACHE_DIR, DATA_DIR,
    ALL_FEATURE_COLUMNS, FISHING_HOURS_COLUMN,
)

logger = logging.getLogger(__name__)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great circle distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Maharashtra landing centres (from seed data)
_LANDING_CENTRES = [
    (19.0760, 72.8777),  # Mumbai - Sassoon Dock
    (18.9388, 72.8354),  # Mumbai - Versova
    (19.2183, 72.8145),  # Mumbai - Arnala
    (18.2513, 73.2698),  # Ratnagiri - Mirkarwada
    (17.6835, 73.3011),  # Ratnagiri - Harnai
    (16.0600, 73.4700),  # Sindhudurg - Malvan
    (15.7280, 73.5150),  # Sindhudurg - Devgad
    (18.7495, 72.8242),  # Raigad - Alibaug
    (19.8135, 72.7557),  # Palghar - Satpati
    (19.6350, 72.7174),  # Palghar - Arnala
]


class HistoricalDatasetBuilder:
    """
    Builds a properly time-aligned historical training dataset.

    For every GFW observation (grid_cell, date):
      - Fetches environmental conditions for that SAME date from Open-Meteo
      - Joins on (grid_cell_id, observation_date)
      - Never uses current/2026 data for 2023 labels
    """

    def __init__(self, start_date: str = None, end_date: str = None,
                 force_refresh: bool = False):
        from backend.app.services.ingestion.gfw_provider import GfwFishingEffortProvider
        self.start_date = start_date or GFW_START_DATE
        self.end_date = end_date or GFW_END_DATE
        self.force_refresh = force_refresh
        self.gfw_provider = GfwFishingEffortProvider()

    def build(self) -> pd.DataFrame:
        """
        Build the historical dataset. Uses cache if available.

        Returns a DataFrame with columns:
            grid_cell_id, latitude, longitude, observation_date,
            fishing_hours, wave_height, wave_period, wave_direction,
            swell_wave_height, wind_speed, ocean_current_velocity,
            distance_to_coast_km, day_of_year,
            env_source, env_matched_date, env_temporal_offset_hours
        """
        # Check cache
        if not self.force_refresh and HISTORICAL_CACHE_PATH.exists():
            logger.info(f"Loading cached dataset from {HISTORICAL_CACHE_PATH}")
            df = pd.read_parquet(HISTORICAL_CACHE_PATH)
            if self._validate_cache(df):
                return df
            logger.warning("Cached dataset failed validation. Rebuilding.")

        # Step 1: Generate spatial grid
        grid_cells = self._generate_grid()
        logger.info(f"Generated {len(grid_cells)} grid cells")

        # Step 2: Fetch GFW data (with dates preserved)
        gfw_df = self._fetch_gfw_data()
        if gfw_df.empty:
            logger.error("No GFW data retrieved. Cannot build dataset.")
            return pd.DataFrame()

        # Step 3: Aggregate GFW per-vessel records to grid cells by date
        gfw_grid_df = self._aggregate_gfw_to_grid(gfw_df, grid_cells)
        logger.info(f"GFW grid aggregation: {len(gfw_grid_df)} (cell, date) rows")

        # Step 4: Expand to full grid × date matrix
        full_df = self._expand_full_grid_dates(grid_cells, gfw_grid_df)
        logger.info(f"Full grid-date matrix: {len(full_df)} rows")

        # Step 5: Fetch historical environmental data
        env_df = self._fetch_historical_env(grid_cells)
        logger.info(f"Environmental data: {len(env_df)} rows")

        # Step 6: Join on (grid_cell_id, observation_date)
        dataset = self._join_dataset(full_df, env_df)

        # Step 7: Add static features
        dataset = self._add_static_features(dataset, grid_cells)

        # Step 8: Add temporal features
        dataset = self._add_temporal_features(dataset)
        
        # Step 8b: Add env feature processing (isna flags, cyclical wind)
        dataset = self._add_env_features(dataset)
        
        # Step 8c: Add lag features
        dataset = self._add_lag_features(dataset)

        # Step 9: Save cache
        HISTORICAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_parquet(HISTORICAL_CACHE_PATH, index=False)
        logger.info(f"Dataset cached to {HISTORICAL_CACHE_PATH}")

        return dataset

    def _validate_cache(self, df: pd.DataFrame) -> bool:
        """Validate that a cached dataset is structurally correct."""
        required = ['grid_cell_id', 'observation_date', FISHING_HOURS_COLUMN]
        if not all(c in df.columns for c in required):
            return False
        # Check date range
        dates = pd.to_datetime(df['observation_date'])
        if str(dates.min().date()) != self.start_date:
            return False
        if str(dates.max().date()) != self.end_date:
            return False
        return True

    def _generate_grid(self) -> List[Dict]:
        """Generate 0.25° grid cells for Maharashtra marine area, excluding land."""
        cells = []
        lat = GRID_MIN_LAT
        while lat <= GRID_MAX_LAT:
            lon = GRID_MIN_LON
            while lon <= GRID_MAX_LON:
                centroid_lat = lat + GRID_RESOLUTION / 2
                centroid_lon = lon + GRID_RESOLUTION / 2
                
                # Check corners and centroid
                points = [
                    (centroid_lat, centroid_lon),
                    (lat, lon),
                    (lat + GRID_RESOLUTION, lon),
                    (lat, lon + GRID_RESOLUTION),
                    (lat + GRID_RESOLUTION, lon + GRID_RESOLUTION)
                ]
                # is_marine if any point is ocean (fallback longitude shelf filter when global_land_mask missing)
                if globe is not None:
                    is_marine = any(globe.is_ocean(p[0], p[1]) for p in points)
                else:
                    is_marine = centroid_lon <= 73.25 or centroid_lat <= 16.75
                
                if is_marine:
                    cell_id = f"cell_{lat:.2f}_{lon:.2f}_{GRID_RESOLUTION}"

                    # Distance to nearest landing centre
                    dist = min(
                        _haversine(centroid_lat, centroid_lon, lc[0], lc[1])
                        for lc in _LANDING_CENTRES
                    )

                    cells.append({
                        'grid_cell_id': cell_id,
                        'latitude': round(centroid_lat, 4),
                        'longitude': round(centroid_lon, 4),
                        'grid_lat': lat,
                        'grid_lon': lon,
                        'distance_to_coast_km': round(dist, 2),
                        'is_coastal': 1.0 if dist <= 50.0 else 0.0,
                    })
                lon = round(lon + GRID_RESOLUTION, 4)
            lat = round(lat + GRID_RESOLUTION, 4)
        return cells

    def _fetch_gfw_data(self) -> pd.DataFrame:
        """Fetch GFW fishing effort, preserving observation dates."""
        # Try cache first
        cached = self.gfw_provider.load_cached(self.start_date, self.end_date)
        if cached and not self.force_refresh:
            logger.info(f"Using cached GFW data: {len(cached)} records")
            return pd.DataFrame(cached)

        records = self.gfw_provider.fetch_fishing_events(
            self.start_date, self.end_date
        )
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)

    def _aggregate_gfw_to_grid(
        self, gfw_df: pd.DataFrame, grid_cells: List[Dict]
    ) -> pd.DataFrame:
        """
        Snap GFW per-vessel coordinates to 0.25° grid and aggregate
        fishing_hours by (grid_cell_id, observation_date).
        """
        # Snap to grid
        gfw_df = gfw_df.copy()
        gfw_df['grid_lat'] = (gfw_df['lat'] // GRID_RESOLUTION) * GRID_RESOLUTION
        gfw_df['grid_lon'] = (gfw_df['lon'] // GRID_RESOLUTION) * GRID_RESOLUTION
        gfw_df['grid_cell_id'] = gfw_df.apply(
            lambda r: f"cell_{r['grid_lat']:.2f}_{r['grid_lon']:.2f}_{GRID_RESOLUTION}",
            axis=1
        )

        # Only keep cells that are in our grid
        valid_ids = {c['grid_cell_id'] for c in grid_cells}
        gfw_df = gfw_df[gfw_df['grid_cell_id'].isin(valid_ids)]

        if gfw_df.empty:
            logger.warning("No GFW records fall within the Maharashtra grid.")
            return pd.DataFrame(columns=['grid_cell_id', 'observation_date', 'fishing_hours'])

        # Aggregate: sum fishing hours per (cell, date)
        agg = (
            gfw_df.groupby(['grid_cell_id', 'observation_date'])['fishing_hours']
            .sum()
            .reset_index()
        )
        logger.info(
            f"GFW aggregated to {len(agg)} (cell, date) pairs "
            f"from {len(gfw_df)} vessel records"
        )
        return agg

    def _expand_full_grid_dates(
        self, grid_cells: List[Dict], gfw_grid_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Create a full (grid_cell × date) matrix.

        For cells with GFW records: use the aggregated fishing_hours.
        For cells WITHOUT GFW records on a given date:
          - If the date is present ANYWHERE in gfw_grid_df (meaning the source was active),
            fishing_hours = 0.0 (True Zero - no detected apparent fishing activity).
          - If the date is completely absent from gfw_grid_df,
            fishing_hours = NaN (Missing - source data unavailable/query failed).
        """
        # Generate all dates in the range
        all_dates = pd.date_range(self.start_date, self.end_date, freq='D')
        date_strs = [d.strftime('%Y-%m-%d') for d in all_dates]

        # Create full cross product
        rows = []
        for cell in grid_cells:
            for ds in date_strs:
                rows.append({
                    'grid_cell_id': cell['grid_cell_id'],
                    'latitude': cell['latitude'],
                    'longitude': cell['longitude'],
                    'observation_date': ds,
                })

        full_df = pd.DataFrame(rows)

        # Merge GFW fishing hours
        full_df = full_df.merge(
            gfw_grid_df[['grid_cell_id', 'observation_date', 'fishing_hours']],
            on=['grid_cell_id', 'observation_date'],
            how='left'
        )

        # Distinguish True Zero vs Missing
        covered_dates = set(gfw_grid_df['observation_date'].unique()) if not gfw_grid_df.empty else set()
        is_covered = full_df['observation_date'].isin(covered_dates)
        
        # Fill with 0.0 ONLY for covered dates where records are absent
        full_df.loc[is_covered & full_df['fishing_hours'].isna(), 'fishing_hours'] = 0.0

        return full_df

    def _fetch_historical_env(self, grid_cells: List[Dict]) -> pd.DataFrame:
        """
        Fetch historical environmental data from Open-Meteo for all grid cells
        and all dates in the GFW range.

        Uses the SAME dates as the GFW data — never current/forecast data.
        """
        cache_path = ENV_RAW_CACHE_DIR / f"env_{self.start_date}_{self.end_date}.parquet"
        if cache_path.exists() and not self.force_refresh:
            logger.info(f"Loading cached environmental data from {cache_path}")
            return pd.read_parquet(cache_path)

        ENV_RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Batch grid cells into groups for Open-Meteo API
        centroids = [(c['latitude'], c['longitude'], c['grid_cell_id'])
                     for c in grid_cells]

        all_env_records = []
        batch_size = OPEN_METEO_MAX_LOCATIONS

        for i in range(0, len(centroids), batch_size):
            batch = centroids[i:i + batch_size]
            logger.info(f"Fetching env batch {i // batch_size + 1}/{(len(centroids) + batch_size - 1) // batch_size}")

            # Fetch marine variables
            marine_records = self._fetch_marine_batch(batch)
            # Fetch weather variables (wind)
            weather_records = self._fetch_weather_batch(batch)

            # Merge marine and weather by (cell, date)
            for cell_id in set(r['grid_cell_id'] for r in marine_records):
                marine_by_date = {
                    r['observation_date']: r
                    for r in marine_records if r['grid_cell_id'] == cell_id
                }
                weather_by_date = {
                    r['observation_date']: r
                    for r in weather_records if r['grid_cell_id'] == cell_id
                }
                for date_str, marine_row in marine_by_date.items():
                    combined = {**marine_row}
                    weather_row = weather_by_date.get(date_str, {})
                    combined['wind_speed'] = weather_row.get('wind_speed')
                    all_env_records.append(combined)

            # Rate limiting: be polite to the free API
            time.sleep(0.5)

        if not all_env_records:
            logger.warning("No environmental data retrieved.")
            return pd.DataFrame()

        env_df = pd.DataFrame(all_env_records)

        # Cache
        env_df.to_parquet(cache_path, index=False)
        logger.info(f"Environmental data cached to {cache_path} ({len(env_df)} rows)")

        return env_df

    def _fetch_marine_batch(
        self, batch: List[Tuple[float, float, str]]
    ) -> List[Dict]:
        """Fetch historical marine data for a batch of grid cell centroids."""
        lats = ",".join(str(b[0]) for b in batch)
        lons = ",".join(str(b[1]) for b in batch)
        variables = ",".join(HISTORICAL_MARINE_VARIABLES)

        url = (
            f"{OPEN_METEO_MARINE_URL}"
            f"?latitude={lats}&longitude={lons}"
            f"&hourly={variables}"
            f"&start_date={self.start_date}&end_date={self.end_date}"
            f"&timezone=UTC"
        )

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'MatsyaAI/1.0'})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode())
        except Exception as e:
            logger.error(f"Open-Meteo marine API error: {e}")
            return []

        return self._parse_hourly_to_daily(data, batch, HISTORICAL_MARINE_VARIABLES)

    def _fetch_weather_batch(
        self, batch: List[Tuple[float, float, str]]
    ) -> List[Dict]:
        """Fetch historical weather data (wind) for a batch of grid cell centroids."""
        lats = ",".join(str(b[0]) for b in batch)
        lons = ",".join(str(b[1]) for b in batch)

        url = (
            f"{OPEN_METEO_WEATHER_URL}"
            f"?latitude={lats}&longitude={lons}"
            f"&hourly=wind_speed_10m"
            f"&start_date={self.start_date}&end_date={self.end_date}"
            f"&timezone=UTC"
        )

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'MatsyaAI/1.0'})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode())
        except Exception as e:
            logger.error(f"Open-Meteo weather API error: {e}")
            return []

        # Rename wind_speed_10m -> wind_speed for consistency
        records = self._parse_hourly_to_daily(data, batch, ['wind_speed_10m'])
        for r in records:
            if 'wind_speed_10m' in r:
                r['wind_speed'] = r.pop('wind_speed_10m')
        return records

    def _parse_hourly_to_daily(
        self, data: dict, batch: List[Tuple[float, float, str]],
        variables: List[str]
    ) -> List[Dict]:
        """
        Parse Open-Meteo hourly response and aggregate to daily means.

        Open-Meteo returns a list for multi-coordinate requests,
        or a single dict for single-coordinate requests.
        """
        # Normalize to list
        if isinstance(data, dict) and 'hourly' in data:
            data_list = [data]
        elif isinstance(data, list):
            data_list = data
        else:
            logger.warning(f"Unexpected Open-Meteo response format: {type(data)}")
            return []

        records = []
        for idx, point_data in enumerate(data_list):
            if idx >= len(batch):
                break

            cell_id = batch[idx][2]
            hourly = point_data.get('hourly', {})
            times = hourly.get('time', [])

            if not times:
                continue

            # Group hourly values by date
            daily_values: Dict[str, Dict[str, list]] = {}
            for t_idx, time_str in enumerate(times):
                date_str = time_str[:10]  # "2023-10-01T05:00" -> "2023-10-01"
                if date_str not in daily_values:
                    daily_values[date_str] = {v: [] for v in variables}

                for var in variables:
                    var_data = hourly.get(var, [])
                    if t_idx < len(var_data) and var_data[t_idx] is not None:
                        daily_values[date_str][var].append(var_data[t_idx])

            # Compute daily aggregation (mean)
            for date_str, var_lists in daily_values.items():
                row = {
                    'grid_cell_id': cell_id,
                    'observation_date': date_str,
                    'env_source': 'open-meteo-historical',
                    'env_matched_date': date_str,
                    'env_temporal_offset_hours': 0,
                }
                for var in variables:
                    values = var_lists[var]
                    if values:
                        row[var] = round(float(np.mean(values)), 4)
                    else:
                        row[var] = None  # Preserve NaN — do NOT fill with 0

                records.append(row)

        return records

    def _join_dataset(
        self, full_df: pd.DataFrame, env_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Join GFW grid data with environmental data on
        (grid_cell_id, observation_date).

        This is the critical temporal alignment step.
        """
        if env_df.empty:
            logger.warning("No environmental data to join. Environmental features will be NaN.")
            for col in ['wave_height', 'wave_period', 'wave_direction',
                        'swell_wave_height', 'wind_speed', 'ocean_current_velocity',
                        'env_source', 'env_matched_date', 'env_temporal_offset_hours']:
                full_df[col] = None
            return full_df

        merged = full_df.merge(
            env_df,
            on=['grid_cell_id', 'observation_date'],
            how='left'
        )

        env_cols = ['wave_height', 'wave_period', 'wave_direction',
                    'swell_wave_height', 'wind_speed', 'ocean_current_velocity']
        for col in env_cols:
            if col not in merged.columns:
                merged[col] = None

        matched = merged[merged['wave_height'].notna()].shape[0]
        total = len(merged)
        logger.info(
            f"Temporal join complete: {matched}/{total} rows have environmental data "
            f"({matched/total*100:.1f}% coverage)"
        )

        return merged

    def _add_static_features(
        self, df: pd.DataFrame, grid_cells: List[Dict]
    ) -> pd.DataFrame:
        """Add static spatial features."""
        dist_map = {c['grid_cell_id']: c['distance_to_coast_km'] for c in grid_cells}
        is_coastal_map = {c['grid_cell_id']: c.get('is_coastal', 0.0) for c in grid_cells}
        df['distance_to_coast_km'] = df['grid_cell_id'].map(dist_map)
        df['is_coastal'] = df['grid_cell_id'].map(is_coastal_map)
        # latitude and longitude are already in the dataframe from _expand_full_grid_dates
        return df

    def _add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add temporal features derived from observation_date."""
        dates = pd.to_datetime(df['observation_date'])
        df['day_of_year'] = dates.dt.dayofyear
        df['month'] = dates.dt.month
        df['day_of_week'] = dates.dt.dayofweek
        
        days_in_year = 365.25
        df['sin_day_of_year'] = np.sin(2 * np.pi * df['day_of_year'] / days_in_year)
        df['cos_day_of_year'] = np.cos(2 * np.pi * df['day_of_year'] / days_in_year)
        return df
        
    def _add_env_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add environmental derived features (_isna, trig)."""
        df['wave_height_isna'] = df['wave_height'].isna().astype(float)
        df['ocean_current_isna'] = df['ocean_current_velocity'].isna().astype(float)
        df['wind_speed_isna'] = df['wind_speed'].isna().astype(float)
        
        if 'wave_direction' in df.columns:
            df['wave_direction_sin'] = np.sin(np.radians(df['wave_direction']))
            df['wave_direction_cos'] = np.cos(np.radians(df['wave_direction']))
        else:
            df['wave_direction_sin'] = np.nan
            df['wave_direction_cos'] = np.nan
            
        return df
        
    def _add_lag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add historical GFW lag features."""
        df = df.sort_values(['grid_cell_id', 'observation_date'])
        
        # We group by cell and compute rolling windows on fishing_hours.
        # But missing values (NaN) should be handled. We already distinguished true zero vs missing.
        # For lags, we only want to look at available historical values.
        # However, typical lag features just shift the target.
        # We fillna(0) just for lag computation because we are counting apparent effort.
        fh = df.groupby('grid_cell_id')['fishing_hours'].fillna(0.0)
        
        # Shifted values
        df['fishing_hours_lag_1'] = df.groupby('grid_cell_id')['fishing_hours'].shift(1).fillna(0.0)
        df['fishing_hours_lag_2'] = df.groupby('grid_cell_id')['fishing_hours'].shift(2).fillna(0.0)
        df['fishing_hours_lag_3'] = df.groupby('grid_cell_id')['fishing_hours'].shift(3).fillna(0.0)
        df['fishing_hours_recent'] = df['fishing_hours_lag_1'] # Simple alias used in inference
        
        # 7d stats
        rolling_7 = df.groupby('grid_cell_id')['fishing_hours'].rolling(window=7, min_periods=1, closed='left')
        df['fishing_hours_7d_mean'] = rolling_7.mean().reset_index(level=0, drop=True).fillna(0.0)
        df['fishing_hours_7d_max'] = rolling_7.max().reset_index(level=0, drop=True).fillna(0.0)
        df['fishing_hours_7d_std'] = rolling_7.std().reset_index(level=0, drop=True).fillna(0.0)
        
        # 7d positive frequency (how many days > 0)
        df['fishing_hours_7d_pos_freq'] = df.groupby('grid_cell_id')['fishing_hours'].transform(
            lambda x: (x > 0).rolling(window=7, min_periods=1, closed='left').mean()
        ).fillna(0.0)
        
        # 14d mean
        df['fishing_hours_14d_mean'] = df.groupby('grid_cell_id')['fishing_hours'].transform(
            lambda x: x.rolling(window=14, min_periods=1, closed='left').mean()
        ).fillna(0.0)
        
        # Regional mean (mean over all cells on date T-1)
        # Shift dates by 1 for regional
        regional_mean = df.groupby('observation_date')['fishing_hours'].mean().shift(1).fillna(0.0)
        df['regional_fishing_hours_T'] = df['observation_date'].map(regional_mean)
        
        return df
