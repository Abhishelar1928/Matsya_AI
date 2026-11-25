"""
MatsyaAI Maharashtra — Phase 4 Spatial Neighborhood & Oceanographic Habitat Features.

Implements:
1. SpatialAdjacencyMapper:
   3x3 Moore (1-ring) and 2-ring (~54 km) grid-cell topology + Haversine distances
   and cardinal finite-difference neighbors over the canonical 0.25-deg Maharashtra grid.
2. GriddedOceanIngestor:
   Modular ingestion + local Parquet caching for GEBCO bathymetry (depth_m, seabed_slope),
   daily Sea Surface Temperature (sst), and Chlorophyll-a (chl_a) using local cache,
   optional Copernicus Marine (CMEMS), and pure-Python NOAA CoastWatch ERDDAP endpoints.
3. Zero-leakage vectorized feature engineering:
   - Strictly causal spatial neighborhood AIS effort aggregations (<= T)
   - Current convergence / spatial shear proxy at T
   - SST thermal front spatial gradient (|grad SST|) at T
   - Strictly causal trailing Chl-a rolling windows (3d, 7d, 14d) & bloom anomaly (<= T)
   - Missingness flags so satellite cloud cover never breaks training or inference
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import argparse
import io
import json
import logging
import math
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from backend.app.ml.config import (
    CMEMS_PASSWORD,
    CMEMS_PRODUCT_BGC,
    CMEMS_PRODUCT_PHYSICS,
    CMEMS_USERNAME,
    DATA_DIR,
    GRID_MAX_LAT,
    GRID_MAX_LON,
    GRID_MIN_LAT,
    GRID_MIN_LON,
    GRID_RESOLUTION,
    HISTORICAL_CACHE_PATH,
)
from ml.features.causal_dataset import FEATURE_COLUMNS as PHASE3_FEATURE_COLUMNS
from ml.features.causal_dataset import build_causal_dataset

logger = logging.getLogger(__name__)

OCEAN_CACHE_DIR = DATA_DIR / "ocean_cache"

# Canonical Phase 4 feature groups
SPATIAL_NEIGHBOR_FEATURES: List[str] = [
    "nbr_1ring_fishing_mean",
    "nbr_1ring_fishing_max",
    "nbr_1ring_active_count",
    "nbr_1ring_fishing_7d_mean",
    "nbr_1ring_fishing_7d_max",
    "nbr_1ring_active_7d_count",
    "nbr_2ring_fishing_mean",
    "current_convergence_proxy",
    "current_convergence_isna",
]

OCEAN_HABITAT_FEATURES: List[str] = [
    "sst",
    "sst_spatial_gradient",
    "chl_a",
    "chl_a_lag3_mean",
    "chl_a_lag7_mean",
    "chl_a_lag14_mean",
    "chl_a_anomaly",
    "depth_m",
    "seabed_slope",
    "sst_isna",
    "sst_spatial_gradient_isna",
    "chl_a_isna",
    "chl_a_lag14_isna",
    "depth_m_isna",
]

# Open-Meteo marine hindcast starts Oct 2021 -> these missingness flags act as 2020-2021 vs 2022-2024 year proxies.
YEAR_CONFOUNDED_MISSINGNESS_FLAGS: set = {
    "wave_height_isna",
    "ocean_current_isna",
    "current_convergence_isna",
}

# Stage 1 Habitat Suitability Model features: strictly ZERO AIS/fishing features & ZERO year-confounded flags!
STAGE1_HABITAT_FEATURES: List[str] = [
    # Ocean & biological habitat
    "sst",
    "sst_spatial_gradient",
    "chl_a",
    "chl_a_lag3_mean",
    "chl_a_lag7_mean",
    "chl_a_lag14_mean",
    "chl_a_anomaly",
    "depth_m",
    "seabed_slope",
    "sst_isna",
    "sst_spatial_gradient_isna",
    "chl_a_isna",
    "chl_a_lag14_isna",
    "depth_m_isna",
    # Marine & atmospheric physics (Open-Meteo / Copernicus)
    "wave_height",
    "wave_period",
    "wave_direction_sin",
    "wave_direction_cos",
    "swell_wave_height",
    "ocean_current_velocity",
    "wind_speed",
    "wind_speed_isna",
    "current_convergence_proxy",
    # Spatial geography
    "latitude",
    "longitude",
    "distance_to_coast_km",
    "is_coastal",
    # Cyclical seasonality & calendar
    "day_of_year",
    "month",
    "day_of_week",
    "sin_day_of_year",
    "cos_day_of_year",
]

SPATIAL_ONLY_FEATURES: List[str] = list(
    dict.fromkeys(
        c
        for c in (PHASE3_FEATURE_COLUMNS + SPATIAL_NEIGHBOR_FEATURES)
        if c not in YEAR_CONFOUNDED_MISSINGNESS_FLAGS
    )
)

STAGE2_OPERATIONAL_FEATURES: List[str] = list(
    dict.fromkeys(
        c
        for c in (
            ["habitat_suitability_score"]
            + PHASE3_FEATURE_COLUMNS
            + SPATIAL_NEIGHBOR_FEATURES
            + OCEAN_HABITAT_FEATURES
        )
        if c not in YEAR_CONFOUNDED_MISSINGNESS_FLAGS
    )
)

_CELL_ID_PATTERN = re.compile(
    r"^cell_(?P<lat>-?\d+(?:\.\d+)?)_(?P<lon>-?\d+(?:\.\d+)?)_(?P<res>\d+(?:\.\d+)?)$"
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    r_earth_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    return r_earth_km * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def parse_cell_coordinates(
    cell_id: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    default_res: float = GRID_RESOLUTION,
) -> Tuple[float, float, float, float, float]:
    """
    Parse (grid_lat, grid_lon, resolution, centroid_lat, centroid_lon) from a canonical cell ID.
    Falls back cleanly to explicit centroid latitude/longitude when non-standard IDs are used.
    """
    match = _CELL_ID_PATTERN.match(str(cell_id))
    if match:
        grid_lat = float(match.group("lat"))
        grid_lon = float(match.group("lon"))
        res = float(match.group("res"))
        cent_lat = float(latitude) if latitude is not None and pd.notna(latitude) else round(grid_lat + res / 2.0, 4)
        cent_lon = float(longitude) if longitude is not None and pd.notna(longitude) else round(grid_lon + res / 2.0, 4)
        return grid_lat, grid_lon, res, cent_lat, cent_lon

    if latitude is None or longitude is None or pd.isna(latitude) or pd.isna(longitude):
        raise ValueError(f"Cannot infer coordinates for non-canonical grid_cell_id={cell_id}")

    cent_lat = float(latitude)
    cent_lon = float(longitude)
    res = float(default_res)
    grid_lat = round(math.floor(cent_lat / res) * res, 4)
    grid_lon = round(math.floor(cent_lon / res) * res, 4)
    return grid_lat, grid_lon, res, cent_lat, cent_lon


class SpatialAdjacencyMapper:
    """
    Precomputes spatial grid topology across canonical Maharashtra 0.25-deg cells:
    - 1-ring Moore neighborhood (max(|dr|, |dc|) == 1, up to 8 neighbors)
    - 2-ring neighborhood (max(|dr|, |dc|) == 2, ~54 km radius)
    - Cardinal directional neighbors (N, S, E, W) with exact Haversine spacing in km
    """

    def __init__(
        self,
        cells: Union[pd.DataFrame, Sequence[Dict[str, Any]]],
        resolution: float = GRID_RESOLUTION,
    ):
        if isinstance(cells, pd.DataFrame):
            unique_df = (
                cells[["grid_cell_id", "latitude", "longitude"]]
                if {"latitude", "longitude"}.issubset(cells.columns)
                else cells[["grid_cell_id"]]
            ).drop_duplicates(subset=["grid_cell_id"])
            raw_cells = unique_df.to_dict(orient="records")
        else:
            seen: Dict[str, Dict[str, Any]] = {}
            for item in cells:
                cid = item["grid_cell_id"]
                if cid not in seen:
                    seen[cid] = dict(item)
            raw_cells = list(seen.values())

        if not raw_cells:
            raise ValueError("SpatialAdjacencyMapper requires at least one grid cell.")

        self.resolution = float(resolution)
        parsed: List[Dict[str, Any]] = []
        for row in raw_cells:
            cid = str(row["grid_cell_id"])
            g_lat, g_lon, res, c_lat, c_lon = parse_cell_coordinates(
                cid,
                latitude=row.get("latitude"),
                longitude=row.get("longitude"),
                default_res=self.resolution,
            )
            parsed.append(
                {
                    "grid_cell_id": cid,
                    "grid_lat": g_lat,
                    "grid_lon": g_lon,
                    "res": res,
                    "latitude": c_lat,
                    "longitude": c_lon,
                }
            )

        parsed.sort(key=lambda r: (r["grid_lat"], r["grid_lon"], r["grid_cell_id"]))
        self.cells_df = pd.DataFrame(parsed)
        self.cell_ids: List[str] = self.cells_df["grid_cell_id"].tolist()
        self.cell_to_idx: Dict[str, int] = {cid: idx for idx, cid in enumerate(self.cell_ids)}

        min_grid_lat = float(self.cells_df["grid_lat"].min())
        min_grid_lon = float(self.cells_df["grid_lon"].min())

        self.coords: Dict[str, Tuple[float, float]] = {}
        self.grid_indices: Dict[str, Tuple[int, int]] = {}
        self.idx_to_cell: Dict[Tuple[int, int], str] = {}
        for r in parsed:
            cid = r["grid_cell_id"]
            row_i = int(round((r["grid_lat"] - min_grid_lat) / self.resolution))
            col_j = int(round((r["grid_lon"] - min_grid_lon) / self.resolution))
            self.coords[cid] = (r["latitude"], r["longitude"])
            self.grid_indices[cid] = (row_i, col_j)
            self.idx_to_cell[(row_i, col_j)] = cid

        n = len(self.cell_ids)
        self.ring1: Dict[str, List[str]] = {}
        self.ring2: Dict[str, List[str]] = {}
        self.ring1_2_distances_km: Dict[Tuple[str, str], float] = {}
        self.cardinal_neighbors: Dict[str, Dict[str, Optional[Tuple[str, float]]]] = {}

        # Precompute binary adjacency matrices for fast O(T * N^2) vectorized operations
        self.ring1_adj = np.zeros((n, n), dtype=float)
        self.ring2_adj = np.zeros((n, n), dtype=float)

        for i, cid in enumerate(self.cell_ids):
            ri, ci = self.grid_indices[cid]
            lat_i, lon_i = self.coords[cid]
            r1_list: List[str] = []
            r2_list: List[str] = []

            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    if dr == 0 and dc == 0:
                        continue
                    nbr_cid = self.idx_to_cell.get((ri + dr, ci + dc))
                    if nbr_cid is None:
                        continue
                    j = self.cell_to_idx[nbr_cid]
                    lat_j, lon_j = self.coords[nbr_cid]
                    dist_km = _haversine_km(lat_i, lon_i, lat_j, lon_j)
                    self.ring1_2_distances_km[(cid, nbr_cid)] = dist_km
                    cheb = max(abs(dr), abs(dc))
                    if cheb == 1:
                        r1_list.append(nbr_cid)
                        self.ring1_adj[i, j] = 1.0
                    elif cheb == 2:
                        r2_list.append(nbr_cid)
                        self.ring2_adj[i, j] = 1.0

            self.ring1[cid] = r1_list
            self.ring2[cid] = r2_list

            card: Dict[str, Optional[Tuple[str, float]]] = {}
            for label, (dr, dc) in (("N", (1, 0)), ("S", (-1, 0)), ("E", (0, 1)), ("W", (0, -1))):
                ncid = self.idx_to_cell.get((ri + dr, ci + dc))
                if ncid is not None:
                    card[label] = (ncid, self.ring1_2_distances_km[(cid, ncid)])
                else:
                    card[label] = None
            self.cardinal_neighbors[cid] = card

    def get_ring1(self, cell_id: str) -> List[str]:
        """Return 1-ring Moore neighbor cell IDs."""
        return list(self.ring1.get(cell_id, []))

    def get_ring2(self, cell_id: str) -> List[str]:
        """Return 2-ring (~54 km) neighbor cell IDs."""
        return list(self.ring2.get(cell_id, []))

    def distance_km(self, cell_a: str, cell_b: str) -> float:
        """Return great-circle distance in km between two mapped cells."""
        if (cell_a, cell_b) in self.ring1_2_distances_km:
            return self.ring1_2_distances_km[(cell_a, cell_b)]
        lat1, lon1 = self.coords[cell_a]
        lat2, lon2 = self.coords[cell_b]
        return _haversine_km(lat1, lon1, lat2, lon2)

    def to_summary(self) -> Dict[str, Any]:
        """Summarize neighbor cardinality and spacing."""
        r1_counts = [len(v) for v in self.ring1.values()]
        r2_counts = [len(v) for v in self.ring2.values()]
        return {
            "total_cells": len(self.cell_ids),
            "resolution_deg": self.resolution,
            "ring1_neighbors_min": int(min(r1_counts)),
            "ring1_neighbors_mean": round(float(np.mean(r1_counts)), 2),
            "ring1_neighbors_max": int(max(r1_counts)),
            "ring2_neighbors_min": int(min(r2_counts)),
            "ring2_neighbors_mean": round(float(np.mean(r2_counts)), 2),
            "ring2_neighbors_max": int(max(r2_counts)),
        }


class GriddedOceanIngestor:
    """
    Modular acquisition & Parquet cache manager for Maharashtra gridded oceanography:
    1. GEBCO bathymetry -> static per-cell depth_m and seabed_slope (m/km)
    2. Daily SST (NOAA jplMURSST41 / optional CMEMS thetao) -> daily per-cell sst (deg C)
    3. Daily/Composite Chlorophyll-a (NOAA VIIRS/MODIS / optional CMEMS chl) -> per-cell chl_a (mg m^-3)

    Preserves NaN for satellite cloud cover or land masking; never fabricates observations.
    """

    USER_AGENT = "MatsyaAI-Phase4-OceanPipeline/1.0"

    # Verified NOAA CoastWatch ERDDAP chlorophyll datasets (daily prioritized over 8-day composites)
    DAILY_CHLA_DATASETS: List[Tuple[str, str, int]] = [
        # (dataset_id, variable_name, causal_forward_shift_days)
        ("nesdisVHNSQchlaDaily", "chlor_a", 0),
        ("noaacwNPPVIIRSchlaDaily", "chlor_a", 0),
        ("erdMH1chla1day", "chlorophyll", 0),
        ("nesdisVHNchlaDaily", "chlor_a", 0),
        # 8-day composite fallbacks MUST shift observation_date forward by +4 days for strict causality
        ("nesdisVHNSQchlaWeekly", "chlor_a", 4),
        ("erdMH1chla8day", "chlorophyll", 4),
    ]

    def __init__(
        self,
        ocean_cache_dir: Optional[Path] = None,
        min_lat: float = GRID_MIN_LAT,
        max_lat: float = GRID_MAX_LAT + GRID_RESOLUTION,
        min_lon: float = GRID_MIN_LON,
        max_lon: float = GRID_MAX_LON + GRID_RESOLUTION,
        resolution: float = GRID_RESOLUTION,
    ):
        self.cache_dir = Path(ocean_cache_dir) if ocean_cache_dir else OCEAN_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_lat = float(min_lat)
        self.max_lat = float(max_lat)
        self.min_lon = float(min_lon)
        self.max_lon = float(max_lon)
        self.resolution = float(resolution)

    @staticmethod
    def _http_get_text(url: str, timeout: int = 90) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": GriddedOceanIngestor.USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @staticmethod
    def _erddap_dataset_meta(dataset_id: str) -> Dict[str, Any]:
        """Inspect ERDDAP DAS/info JSON to determine axis names and coordinate directions."""
        url = f"https://coastwatch.pfeg.noaa.gov/erddap/info/{dataset_id}/index.json"
        raw = json.loads(GriddedOceanIngestor._http_get_text(url, timeout=45))
        rows = raw.get("table", {}).get("rows", [])
        dims: List[str] = []
        attrs: Dict[str, Any] = {}
        variables: set = set()
        for row in rows:
            row_type, var_name, attr_name, _dtype, val = row[0], row[1], row[2], row[3], row[4]
            if row_type == "dimension":
                dims.append(var_name)
            elif row_type == "variable":
                variables.add(var_name)
            elif row_type == "attribute":
                attrs[f"{var_name}.{attr_name}"] = val
        return {"dims": dims, "variables": variables, "attrs": attrs}

    @staticmethod
    def _snap_points_to_cells(
        lats: np.ndarray,
        lons: np.ndarray,
        valid_cell_ids: set,
        res: float = GRID_RESOLUTION,
    ) -> np.ndarray:
        """Vectorized snap of coordinates onto SW-corner canonical cell_<lat>_<lon>_<res> IDs."""
        g_lats = np.floor(lats / res + 1e-9) * res
        g_lons = np.floor(lons / res + 1e-9) * res
        return np.array(
            [
                f"cell_{la:.2f}_{lo:.2f}_{res}" if f"cell_{la:.2f}_{lo:.2f}_{res}" in valid_cell_ids else ""
                for la, lo in zip(g_lats, g_lons)
            ],
            dtype=object,
        )

    def _find_covering_parquet(
        self, prefix: str, start_date: str, end_date: str
    ) -> Optional[pd.DataFrame]:
        """Search exact or covering Parquet caches in self.cache_dir."""
        exact = self.cache_dir / f"{prefix}_{start_date}_{end_date}.parquet"
        if exact.exists():
            df = pd.read_parquet(exact)
            df["observation_date"] = pd.to_datetime(df["observation_date"])
            return df

        req_start = pd.Timestamp(start_date)
        req_end = pd.Timestamp(end_date)
        frames: List[pd.DataFrame] = []
        for path in sorted(self.cache_dir.glob(f"{prefix}_*.parquet")):
            part = pd.read_parquet(path)
            if part.empty or "observation_date" not in part.columns:
                continue
            part["observation_date"] = pd.to_datetime(part["observation_date"])
            sliced = part[(part["observation_date"] >= req_start) & (part["observation_date"] <= req_end)]
            if not sliced.empty:
                frames.append(sliced)
        if not frames:
            return None
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        return combined.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)

    @staticmethod
    def _cmems_available() -> bool:
        if not (CMEMS_USERNAME and CMEMS_PASSWORD):
            return False
        try:
            import copernicusmarine  # noqa: F401
            import xarray  # noqa: F401
            return True
        except ImportError:
            return False

    def _fetch_cmems_sst_or_chla(
        self,
        variable: str,
        grid_cells: Sequence[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> Optional[pd.DataFrame]:
        """Optional Copernicus Marine hook when copernicusmarine + credentials are configured."""
        if not self._cmems_available():
            return None
        try:
            import copernicusmarine  # type: ignore

            dataset_id = CMEMS_PRODUCT_PHYSICS if variable == "sst" else CMEMS_PRODUCT_BGC
            cm_var = "thetao" if variable == "sst" else "chl"
            ds = copernicusmarine.open_dataset(
                dataset_id=dataset_id,
                variables=[cm_var],
                minimum_longitude=self.min_lon,
                maximum_longitude=self.max_lon,
                minimum_latitude=self.min_lat,
                maximum_latitude=self.max_lat,
                start_datetime=start_date,
                end_datetime=end_date,
                username=CMEMS_USERNAME,
                password=CMEMS_PASSWORD,
            )
            if "depth" in ds.dims:
                ds = ds.isel(depth=0)
            out_col = "sst" if variable == "sst" else "chl_a"
            rows: List[Dict[str, Any]] = []
            for cell in grid_cells:
                sub = ds[cm_var].sel(latitude=cell["latitude"], longitude=cell["longitude"], method="nearest")
                times = pd.to_datetime(sub["time"].values).strftime("%Y-%m-%d")
                vals = np.asarray(sub.values, dtype=float)
                for d_str, v in zip(times, vals):
                    rows.append(
                        {
                            "grid_cell_id": cell["grid_cell_id"],
                            "observation_date": d_str,
                            out_col: float(v) if np.isfinite(v) else np.nan,
                            f"{out_col}_source": f"CMEMS:{dataset_id}",
                        }
                    )
            df = pd.DataFrame(rows)
            if not df.empty:
                df["observation_date"] = pd.to_datetime(df["observation_date"])
            return df
        except Exception as exc:
            logger.warning(f"CMEMS {variable} fetch fell back to ERDDAP: {exc}")
            return None

    # ------------------------------------------------------------------
    # 1. Bathymetry (GEBCO_2020)
    # ------------------------------------------------------------------
    def load_bathymetry(
        self,
        grid_cells: Sequence[Dict[str, Any]],
        allow_fetch: bool = False,
    ) -> pd.DataFrame:
        """
        Load per-cell static GEBCO bathymetry: depth_m (positive ocean depth) and seabed_slope (m/km).
        Reads cached `gebco_bathymetry_grid.parquet` if present; otherwise returns NaNs unless allow_fetch=True.
        """
        cache_path = self.cache_dir / "gebco_bathymetry_grid.parquet"
        valid_ids = {c["grid_cell_id"] for c in grid_cells}
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
            return df[df["grid_cell_id"].isin(valid_ids)].reset_index(drop=True)

        if not allow_fetch:
            return pd.DataFrame(
                [
                    {
                        "grid_cell_id": c["grid_cell_id"],
                        "depth_m": np.nan,
                        "seabed_slope": np.nan,
                        "bathy_source": "UNAVAILABLE",
                    }
                    for c in grid_cells
                ]
            )

        logger.info("Fetching GEBCO_2020 elevation grid from NOAA CoastWatch ERDDAP...")
        stride = 12  # ~0.05 deg (~5.5 km) across Maharashtra coastal box
        b_min_lat = max(14.5, self.min_lat - 0.25)
        b_max_lat = min(21.0, self.max_lat + 0.25)
        b_min_lon = max(71.0, self.min_lon - 0.25)
        b_max_lon = min(74.5, self.max_lon + 0.25)
        url = (
            "https://coastwatch.pfeg.noaa.gov/erddap/griddap/GEBCO_2020.csv"
            f"?elevation[({b_min_lat}):{stride}:({b_max_lat})][({b_min_lon}):{stride}:({b_max_lon})]"
        )
        csv_text = self._http_get_text(url, timeout=90)
        raw = pd.read_csv(io.StringIO(csv_text), skiprows=[1])
        raw.columns = [c.strip() for c in raw.columns]
        raw["latitude"] = pd.to_numeric(raw["latitude"], errors="coerce")
        raw["longitude"] = pd.to_numeric(raw["longitude"], errors="coerce")
        raw["elevation"] = pd.to_numeric(raw["elevation"], errors="coerce")
        raw = raw.dropna(subset=["latitude", "longitude", "elevation"])

        # Reconstruct 2D matrix to compute finite-difference seabed slope (m/km)
        lats = np.sort(raw["latitude"].unique())
        lons = np.sort(raw["longitude"].unique())
        piv = raw.pivot_table(index="latitude", columns="longitude", values="elevation", aggfunc="mean")
        piv = piv.reindex(index=lats, columns=lons)
        elev = piv.values.astype(float)

        mean_lat_rad = math.radians(float(np.mean(lats)))
        dlat_deg = float(np.median(np.diff(lats))) if len(lats) > 1 else 0.05
        dlon_deg = float(np.median(np.diff(lons))) if len(lons) > 1 else 0.05
        dy_km = max(1e-6, dlat_deg * 111.32)
        dx_km = max(1e-6, dlon_deg * 111.32 * math.cos(mean_lat_rad))

        dz_dy, dz_dx = np.gradient(elev, dy_km, dx_km)
        slope_grid = np.hypot(dz_dx, dz_dy)  # metres of elevation change per km

        lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
        pts = pd.DataFrame(
            {
                "latitude": lat_grid.ravel(),
                "longitude": lon_grid.ravel(),
                "elevation": elev.ravel(),
                "slope": slope_grid.ravel(),
            }
        )
        pts["grid_cell_id"] = self._snap_points_to_cells(
            pts["latitude"].values, pts["longitude"].values, valid_ids, res=self.resolution
        )
        pts = pts[pts["grid_cell_id"] != ""]

        rows: List[Dict[str, Any]] = []
        for cid in sorted(valid_ids):
            sub = pts[pts["grid_cell_id"] == cid]
            ocean_sub = sub[sub["elevation"] < 0]
            if ocean_sub.empty:
                rows.append(
                    {
                        "grid_cell_id": cid,
                        "depth_m": np.nan,
                        "seabed_slope": np.nan,
                        "bathy_source": "GEBCO_2020_ERDDAP",
                    }
                )
            else:
                valid_slopes = ocean_sub["slope"].dropna()
                rows.append(
                    {
                        "grid_cell_id": cid,
                        "depth_m": round(float(-ocean_sub["elevation"].mean()), 3),
                        "seabed_slope": round(float(valid_slopes.mean()), 4) if not valid_slopes.empty else np.nan,
                        "bathy_source": "GEBCO_2020_ERDDAP",
                    }
                )

        bathy_df = pd.DataFrame(rows)
        bathy_df.to_parquet(cache_path, index=False)
        logger.info(
            f"Saved bathymetry cache to {cache_path}: "
            f"{int(bathy_df['depth_m'].notna().sum())}/{len(bathy_df)} cells with valid depth_m."
        )
        return bathy_df

    # ------------------------------------------------------------------
    # 2. Daily Sea Surface Temperature (jplMURSST41)
    # ------------------------------------------------------------------
    def _quarterly_ranges(self, start_date: str, end_date: str, max_days: int = 44) -> List[Tuple[str, str]]:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        windows: List[Tuple[str, str]] = []
        cur = start
        while cur <= end:
            nxt = min(end, cur + pd.Timedelta(days=max_days))
            windows.append((cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")))
            cur = nxt + pd.Timedelta(days=1)
        return windows

    def load_daily_sst(
        self,
        grid_cells: Sequence[Dict[str, Any]],
        start_date: str,
        end_date: str,
        allow_fetch: bool = False,
    ) -> pd.DataFrame:
        """
        Load daily gridded SST (deg C) per cell for [start_date, end_date].
        Reads cache first; if missing and allow_fetch=True, fetches CMEMS or NOAA jplMURSST41.
        """
        valid_ids = {c["grid_cell_id"] for c in grid_cells}
        cached = self._find_covering_parquet("sst", start_date, end_date)
        if cached is not None:
            return cached[cached["grid_cell_id"].isin(valid_ids)].reset_index(drop=True)

        if not allow_fetch:
            return pd.DataFrame(columns=["grid_cell_id", "observation_date", "sst", "sst_source"])

        cmems_df = self._fetch_cmems_sst_or_chla("sst", grid_cells, start_date, end_date)
        if cmems_df is not None and not cmems_df.empty:
            out_path = self.cache_dir / f"sst_{start_date}_{end_date}.parquet"
            cmems_df.to_parquet(out_path, index=False)
            return cmems_df

        dataset_id = "jplMURSST41"
        logger.info(f"Fetching daily SST ({dataset_id}) from NOAA CoastWatch ERDDAP for {start_date}..{end_date}...")
        meta = self._erddap_dataset_meta(dataset_id)
        lat_spacing_raw = str(meta["attrs"].get("latitude.actual_range", ""))
        lat_asc = True
        if "jplMURSST41" in dataset_id or lat_spacing_raw:
            lat_asc = True  # jplMURSST41 stores ascending lat (-89.99..89.99)

        stride = 12  # ~0.12 deg (~13 km), gives >= 4 samples per 0.25 deg cell
        chunk_frames: List[pd.DataFrame] = []
        for q_start, q_end in self._quarterly_ranges(start_date, end_date):
            lat_slice = (
                f"({self.min_lat}):{stride}:({self.max_lat})"
                if lat_asc
                else f"({self.max_lat}):{stride}:({self.min_lat})"
            )
            urls = [
                (
                    f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{dataset_id}.csv"
                    f"?analysed_sst[({q_start}T09:00:00Z):1:({q_end}T09:00:00Z)][{lat_slice}][({self.min_lon}):{stride}:({self.max_lon})]"
                ),
                (
                    f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{dataset_id}.csv"
                    f"?analysed_sst[({q_start}T09:00:00Z):1:({q_end}T09:00:00Z)][({self.max_lat}):{stride}:({self.min_lat})][({self.min_lon}):{stride}:({self.max_lon})]"
                ),
            ]
            csv_text = None
            for url in urls:
                try:
                    csv_text = self._http_get_text(url, timeout=120)
                    break
                except Exception as exc:
                    logger.debug(f"SST chunk query attempt failed ({url}): {exc}")
            if csv_text is None:
                logger.warning(f"Failed to fetch SST chunk {q_start}..{q_end}; preserving missing dates as NaN.")
                continue

            sub = pd.read_csv(io.StringIO(csv_text), skiprows=[1])
            sub.columns = [c.strip() for c in sub.columns]
            sub["observation_date"] = pd.to_datetime(sub["time"].astype(str).str[:10])
            sub["latitude"] = pd.to_numeric(sub["latitude"], errors="coerce")
            sub["longitude"] = pd.to_numeric(sub["longitude"], errors="coerce")
            sub["sst"] = pd.to_numeric(sub["analysed_sst"], errors="coerce")
            sub = sub.dropna(subset=["observation_date", "latitude", "longitude"])
            sub["grid_cell_id"] = self._snap_points_to_cells(
                sub["latitude"].values, sub["longitude"].values, valid_ids, res=self.resolution
            )
            sub = sub[sub["grid_cell_id"] != ""]
            agg = (
                sub.groupby(["grid_cell_id", "observation_date"], as_index=False)["sst"]
                .mean()
            )
            chunk_frames.append(agg)
            logger.info(f"  SST chunk {q_start}..{q_end}: {len(agg)} cell-day records")

        if not chunk_frames:
            return pd.DataFrame(columns=["grid_cell_id", "observation_date", "sst", "sst_source"])

        sst_df = pd.concat(chunk_frames, ignore_index=True)
        sst_df = sst_df.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        sst_df["sst"] = sst_df["sst"].round(4)
        sst_df["sst_source"] = "NOAA_ERDDAP:jplMURSST41"
        sst_df = sst_df.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)

        out_path = self.cache_dir / f"sst_{start_date}_{end_date}.parquet"
        sst_df.to_parquet(out_path, index=False)
        logger.info(f"Saved SST cache to {out_path} ({len(sst_df)} cell-days, non-null={int(sst_df['sst'].notna().sum())})")
        return sst_df

    # ------------------------------------------------------------------
    # 3. Daily / Composite Chlorophyll-a
    # ------------------------------------------------------------------
    def _build_erddap_chla_url(
        self,
        dataset_id: str,
        var_name: str,
        dims: List[str],
        lat_desc: bool,
        q_start: str,
        q_end: str,
        stride: int,
    ) -> str:
        t_axis = f"[({q_start}T12:00:00Z):1:({q_end}T12:00:00Z)]"
        lat_axis = (
            f"[({self.max_lat}):{stride}:({self.min_lat})]"
            if lat_desc
            else f"[({self.min_lat}):{stride}:({self.max_lat})]"
        )
        lon_axis = f"[({self.min_lon}):{stride}:({self.max_lon})]"
        axes: List[str] = []
        for dim in dims:
            d_low = dim.lower()
            if "time" in d_low:
                axes.append(t_axis)
            elif "alt" in d_low or "lev" in d_low or "depth" in d_low:
                axes.append("[(0.0)]")
            elif "lat" in d_low:
                axes.append(lat_axis)
            elif "lon" in d_low:
                axes.append(lon_axis)
        return f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{dataset_id}.csv?{var_name}{''.join(axes)}"

    def load_daily_chla(
        self,
        grid_cells: Sequence[Dict[str, Any]],
        start_date: str,
        end_date: str,
        allow_fetch: bool = False,
    ) -> pd.DataFrame:
        """
        Load gridded Chlorophyll-a (mg m^-3) for [start_date, end_date].
        Prioritizes daily ocean-color datasets; if only 8-day composite datasets exist,
        shifts effective observation_date forward by +4 days to enforce strict causality.
        """
        valid_ids = {c["grid_cell_id"] for c in grid_cells}
        cached = self._find_covering_parquet("chla", start_date, end_date)
        if cached is not None:
            return cached[cached["grid_cell_id"].isin(valid_ids)].reset_index(drop=True)

        if not allow_fetch:
            return pd.DataFrame(columns=["grid_cell_id", "observation_date", "chl_a", "chl_a_source"])

        cmems_df = self._fetch_cmems_sst_or_chla("chl_a", grid_cells, start_date, end_date)
        if cmems_df is not None and not cmems_df.empty:
            out_path = self.cache_dir / f"chla_{start_date}_{end_date}.parquet"
            cmems_df.to_parquet(out_path, index=False)
            return cmems_df

        req_start_ts = pd.Timestamp(start_date)
        req_end_ts = pd.Timestamp(end_date)

        expected_pairs = max(1, len(valid_ids) * max(1, (req_end_ts - req_start_ts).days + 1))
        collected_frames: List[pd.DataFrame] = []

        for dataset_id, var_name, causal_shift_days in self.DAILY_CHLA_DATASETS:
            try:
                meta = self._erddap_dataset_meta(dataset_id)
                if var_name not in meta["variables"]:
                    logger.debug(f"Chl-a dataset {dataset_id} missing expected variable {var_name}")
                    continue
                dims = meta["dims"]
                raw_spacing = meta["attrs"].get("latitude.averageSpacing")
                lat_spacing = float(raw_spacing) if raw_spacing is not None else -0.0375
                lat_desc = True if "nesdis" in dataset_id.lower() else (lat_spacing < 0)
                stride = max(4, int(round(0.15 / max(1e-4, abs(lat_spacing)))))

                # If shifted forward (+4d) for weekly composites, start slightly earlier to cover start_date
                fetch_start = (req_start_ts - pd.Timedelta(days=causal_shift_days)).strftime("%Y-%m-%d")
                chunk_frames: List[pd.DataFrame] = []
                logger.info(
                    f"Trying ERDDAP Chl-a dataset {dataset_id} ({var_name}, "
                    f"causal_shift=+{causal_shift_days}d, stride={stride})..."
                )
                for q_start, q_end in self._quarterly_ranges(fetch_start, end_date, max_days=30):
                    fetched_text = None
                    for try_desc in (lat_desc, not lat_desc):
                        url = self._build_erddap_chla_url(
                            dataset_id, var_name, dims, try_desc, q_start, q_end, stride
                        )
                        try:
                            fetched_text = self._http_get_text(url, timeout=60)
                            break
                        except Exception as exc:
                            logger.debug(f"Chl-a attempt failed ({url}): {exc}")
                    if fetched_text is None:
                        continue

                    sub = pd.read_csv(io.StringIO(fetched_text), skiprows=[1])
                    sub.columns = [c.strip() for c in sub.columns]
                    obs_dt = pd.to_datetime(sub["time"].astype(str).str[:10])
                    if causal_shift_days > 0:
                        # Weekly composite timestamp is centered on the 8-day window;
                        # shifting by +4d guarantees all composite satellite passes <= observation_date.
                        obs_dt = obs_dt + pd.Timedelta(days=causal_shift_days)
                    sub["observation_date"] = obs_dt
                    sub["latitude"] = pd.to_numeric(sub["latitude"], errors="coerce")
                    sub["longitude"] = pd.to_numeric(sub["longitude"], errors="coerce")
                    sub["chl_a"] = pd.to_numeric(sub[var_name], errors="coerce")
                    sub.loc[sub["chl_a"] <= 0, "chl_a"] = np.nan
                    sub = sub.dropna(subset=["observation_date", "latitude", "longitude"])
                    sub["grid_cell_id"] = self._snap_points_to_cells(
                        sub["latitude"].values, sub["longitude"].values, valid_ids, res=self.resolution
                    )
                    sub = sub[sub["grid_cell_id"] != ""]
                    if sub.empty:
                        continue
                    agg = (
                        sub.groupby(["grid_cell_id", "observation_date"], as_index=False)["chl_a"]
                        .mean()
                    )
                    chunk_frames.append(agg)
                    logger.info(f"  Chl-a chunk {q_start}..{q_end}: {len(agg)} cell-day records")

                if not chunk_frames:
                    continue

                part_df = pd.concat(chunk_frames, ignore_index=True)
                part_df = part_df[
                    (part_df["observation_date"] >= req_start_ts)
                    & (part_df["observation_date"] <= req_end_ts)
                ]
                part_df = part_df.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
                valid_part = int(part_df["chl_a"].notna().sum())
                if valid_part == 0:
                    continue

                part_df["chl_a_source"] = f"NOAA_ERDDAP:{dataset_id}_shift{causal_shift_days}d"
                part_df["_priority"] = 0 if causal_shift_days == 0 else 1
                collected_frames.append(part_df)

                # Check cumulative non-null coverage; only stop early once we have >= 15% coverage
                merged_so_far = pd.concat(collected_frames, ignore_index=True)
                valid_cov = (
                    merged_so_far.dropna(subset=["chl_a"])
                    .drop_duplicates(subset=["grid_cell_id", "observation_date"])
                    .shape[0]
                ) / expected_pairs
                logger.info(f"  Cumulative Chl-a non-null coverage={valid_cov:.3f} after {dataset_id}")
                if valid_cov >= 0.15 and causal_shift_days > 0:
                    break
                if valid_cov >= 0.25:
                    break
            except Exception as exc:
                logger.warning(f"Chl-a dataset {dataset_id} skipped: {exc}")

        if not collected_frames:
            return pd.DataFrame(columns=["grid_cell_id", "observation_date", "chl_a", "chl_a_source"])

        all_chl = pd.concat(collected_frames, ignore_index=True)
        all_chl["_is_valid"] = all_chl["chl_a"].notna().astype(int)
        # Prefer valid daily (priority=0, _is_valid=1) over valid causal weekly (priority=1, _is_valid=1)
        all_chl = all_chl.sort_values(
            ["grid_cell_id", "observation_date", "_is_valid", "_priority"],
            ascending=[True, True, False, True],
        )
        chl_df = (
            all_chl.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="first")
            .drop(columns=["_priority", "_is_valid"])
            .sort_values(["observation_date", "grid_cell_id"])
            .reset_index(drop=True)
        )
        chl_df["chl_a"] = chl_df["chl_a"].round(4)

        out_path = self.cache_dir / f"chla_{start_date}_{end_date}.parquet"
        chl_df.to_parquet(out_path, index=False)
        logger.info(
            f"Saved Chl-a cache to {out_path} ({len(chl_df)} rows, "
            f"valid={int(chl_df['chl_a'].notna().sum())}, sources={chl_df['chl_a_source'].unique().tolist()})"
        )
        return chl_df


def _ensure_daily_matrix(
    df: pd.DataFrame,
    value_col: str,
    cell_ids: List[str],
    fill_missing_dates_with: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.DatetimeIndex]:
    """
    Pivot `value_col` into a strictly sorted dense daily matrix (all calendar days x canonical cell_ids).
    Reindexing to continuous daily frequency enforces strict calendar-day windows even with date gaps.
    """
    orig_dates = pd.DatetimeIndex(sorted(pd.to_datetime(df["observation_date"]).unique()))
    if len(orig_dates) == 0:
        return pd.DataFrame(index=orig_dates, columns=cell_ids, dtype=float), orig_dates

    piv = df.pivot_table(
        index="observation_date",
        columns="grid_cell_id",
        values=value_col,
        aggfunc="mean",
    )
    piv.index = pd.to_datetime(piv.index)
    full_daily_index = pd.date_range(orig_dates.min(), orig_dates.max(), freq="D")
    piv = piv.reindex(index=full_daily_index, columns=cell_ids)
    if fill_missing_dates_with is not None:
        piv = piv.fillna(fill_missing_dates_with)
    return piv.astype(float), orig_dates


def compute_spatial_neighborhood_features(
    raw_df: pd.DataFrame,
    mapper: SpatialAdjacencyMapper,
    gfw_lag_days: int = 0,
) -> pd.DataFrame:
    """
    Compute strictly causal (<= T) spatial neighborhood features over (grid_cell_id, observation_date).
    Zero future observations (> T) can enter any neighborhood statistic or rolling window.
    """
    work = raw_df.copy()
    work["observation_date"] = pd.to_datetime(work["observation_date"])
    work = work.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)
    cell_ids = mapper.cell_ids
    n_cells = len(cell_ids)

    fh_work = work.copy()
    fh_work["fishing_hours"] = pd.to_numeric(fh_work["fishing_hours"], errors="coerce").fillna(0.0)
    fh_mat, orig_dates = _ensure_daily_matrix(
        fh_work, "fishing_hours", cell_ids, fill_missing_dates_with=0.0
    )

    # Shift fishing observations by gfw_lag_days so day T sees only <= T - gfw_lag_days
    fh_eligible = fh_mat.shift(gfw_lag_days).fillna(0.0) if gfw_lag_days > 0 else fh_mat

    adj1 = mapper.ring1_adj  # (n, n), row i = neighbors of i
    adj2 = mapper.ring2_adj
    deg1 = np.maximum(1.0, adj1.sum(axis=1))  # prevent divide by zero on isolated cells
    deg2 = np.maximum(1.0, adj2.sum(axis=1))
    has_r1 = (adj1.sum(axis=1) > 0).astype(float)
    has_r2 = (adj2.sum(axis=1) > 0).astype(float)

    fh_vals = fh_eligible.values  # (D, N)
    r1_mean = ((fh_vals @ adj1.T) / deg1) * has_r1
    r2_mean = ((fh_vals @ adj2.T) / deg2) * has_r2
    r1_active = (fh_vals > 0.0).astype(float) @ adj1.T

    # Neighbor 1-ring max per day T
    r1_max = np.zeros_like(fh_vals)
    for i in range(n_cells):
        nbr_idx = np.where(adj1[i] > 0)[0]
        if len(nbr_idx) > 0:
            r1_max[:, i] = np.max(fh_vals[:, nbr_idx], axis=1)

    # Trailing 7-day rolling windows strictly on eligible values (window=7 on daily index => [T-lag-6 .. T-lag])
    fh_7d_mean_mat = fh_eligible.rolling(window=7, min_periods=1).mean().fillna(0.0).values
    fh_7d_max_mat = fh_eligible.rolling(window=7, min_periods=1).max().fillna(0.0).values

    r1_7d_mean = ((fh_7d_mean_mat @ adj1.T) / deg1) * has_r1
    r1_7d_max = np.zeros_like(fh_vals)
    for i in range(n_cells):
        nbr_idx = np.where(adj1[i] > 0)[0]
        if len(nbr_idx) > 0:
            r1_7d_max[:, i] = np.max(fh_7d_max_mat[:, nbr_idx], axis=1)

    r1_active_df = pd.DataFrame(r1_active, index=fh_eligible.index, columns=cell_ids)
    r1_active_7d = r1_active_df.rolling(window=7, min_periods=1).mean().fillna(0.0).values

    # Current convergence proxy strictly at date T (no target/lag needed; weather/ocean at T)
    has_uv = {"current_u", "current_v"}.issubset(work.columns)
    conv_mat = np.full((len(fh_eligible.index), n_cells), np.nan, dtype=float)

    if has_uv:
        u_mat, _ = _ensure_daily_matrix(work, "current_u", cell_ids)
        v_mat, _ = _ensure_daily_matrix(work, "current_v", cell_ids)
        u_vals = u_mat.values
        v_vals = v_mat.values
        for i, cid in enumerate(cell_ids):
            card = mapper.cardinal_neighbors[cid]
            du_dx = np.full(len(fh_eligible.index), np.nan, dtype=float)
            dv_dy = np.full(len(fh_eligible.index), np.nan, dtype=float)
            if card["E"] and card["W"]:
                je = mapper.cell_to_idx[card["E"][0]]
                jw = mapper.cell_to_idx[card["W"][0]]
                dist_m = (card["E"][1] + card["W"][1]) * 1000.0
                du_dx = (u_vals[:, je] - u_vals[:, jw]) / dist_m
            elif card["E"]:
                je = mapper.cell_to_idx[card["E"][0]]
                du_dx = (u_vals[:, je] - u_vals[:, i]) / (card["E"][1] * 1000.0)
            elif card["W"]:
                jw = mapper.cell_to_idx[card["W"][0]]
                du_dx = (u_vals[:, i] - u_vals[:, jw]) / (card["W"][1] * 1000.0)

            if card["N"] and card["S"]:
                jn = mapper.cell_to_idx[card["N"][0]]
                js = mapper.cell_to_idx[card["S"][0]]
                dist_m = (card["N"][1] + card["S"][1]) * 1000.0
                dv_dy = (v_vals[:, jn] - v_vals[:, js]) / dist_m
            elif card["N"]:
                jn = mapper.cell_to_idx[card["N"][0]]
                dv_dy = (v_vals[:, jn] - v_vals[:, i]) / (card["N"][1] * 1000.0)
            elif card["S"]:
                js = mapper.cell_to_idx[card["S"][0]]
                dv_dy = (v_vals[:, i] - v_vals[:, js]) / (card["S"][1] * 1000.0)

            both_valid = np.isfinite(du_dx) & np.isfinite(dv_dy)
            partial_valid = np.isfinite(du_dx) ^ np.isfinite(dv_dy)
            conv_mat[both_valid, i] = -(du_dx[both_valid] + dv_dy[both_valid]) * 1e5
            conv_mat[partial_valid, i] = -np.where(np.isfinite(du_dx[partial_valid]), du_dx[partial_valid], dv_dy[partial_valid]) * 1e5
    elif "ocean_current_velocity" in work.columns:
        cv_mat, _ = _ensure_daily_matrix(work, "ocean_current_velocity", cell_ids)
        cv_vals = cv_mat.values
        for i, cid in enumerate(cell_ids):
            card = mapper.cardinal_neighbors[cid]
            d_dx = np.full(len(fh_eligible.index), np.nan, dtype=float)
            d_dy = np.full(len(fh_eligible.index), np.nan, dtype=float)
            if card["E"] and card["W"]:
                je = mapper.cell_to_idx[card["E"][0]]
                jw = mapper.cell_to_idx[card["W"][0]]
                d_dx = (cv_vals[:, je] - cv_vals[:, jw]) / ((card["E"][1] + card["W"][1]) / 100.0)
            elif card["E"]:
                je = mapper.cell_to_idx[card["E"][0]]
                d_dx = (cv_vals[:, je] - cv_vals[:, i]) / (card["E"][1] / 100.0)
            elif card["W"]:
                jw = mapper.cell_to_idx[card["W"][0]]
                d_dx = (cv_vals[:, i] - cv_vals[:, jw]) / (card["W"][1] / 100.0)

            if card["N"] and card["S"]:
                jn = mapper.cell_to_idx[card["N"][0]]
                js = mapper.cell_to_idx[card["S"][0]]
                d_dy = (cv_vals[:, jn] - cv_vals[:, js]) / ((card["N"][1] + card["S"][1]) / 100.0)
            elif card["N"]:
                jn = mapper.cell_to_idx[card["N"][0]]
                d_dy = (cv_vals[:, jn] - cv_vals[:, i]) / (card["N"][1] / 100.0)
            elif card["S"]:
                js = mapper.cell_to_idx[card["S"][0]]
                d_dy = (cv_vals[:, i] - cv_vals[:, js]) / (card["S"][1] / 100.0)

            nbr_idx = np.where(adj1[i] > 0)[0]
            if len(nbr_idx) > 0:
                nbr_vals = cv_vals[:, nbr_idx]
                with np.errstate(all="ignore"):
                    nbr_mean = np.nanmean(nbr_vals, axis=1)
                inflow = nbr_mean - cv_vals[:, i]
            else:
                inflow = np.full(len(fh_eligible.index), np.nan)

            grad_mag = np.where(
                np.isfinite(d_dx) & np.isfinite(d_dy),
                np.hypot(np.nan_to_num(d_dx), np.nan_to_num(d_dy)),
                np.where(np.isfinite(d_dx), np.abs(d_dx), np.where(np.isfinite(d_dy), np.abs(d_dy), np.nan)),
            )
            # Signed shear/convergence proxy combining directional shear magnitude and surrounding inflow
            sign_term = np.where(np.isfinite(inflow) & (inflow < 0), -1.0, 1.0)
            valid = np.isfinite(grad_mag) & np.isfinite(inflow)
            conv_mat[valid, i] = 0.5 * (sign_term[valid] * grad_mag[valid]) + 0.5 * inflow[valid]
            only_inflow = (~np.isfinite(grad_mag)) & np.isfinite(inflow)
            conv_mat[only_inflow, i] = inflow[only_inflow]

    # Stack back only on orig_dates
    full_idx = fh_eligible.index
    def _to_long(arr: np.ndarray, col_name: str) -> pd.Series:
        df_tmp = pd.DataFrame(arr, index=full_idx, columns=cell_ids).loc[orig_dates]
        return df_tmp.stack(future_stack=True).rename(col_name)

    stacked = pd.concat(
        [
            _to_long(r1_mean, "nbr_1ring_fishing_mean"),
            _to_long(r1_max, "nbr_1ring_fishing_max"),
            _to_long(r1_active, "nbr_1ring_active_count"),
            _to_long(r1_7d_mean, "nbr_1ring_fishing_7d_mean"),
            _to_long(r1_7d_max, "nbr_1ring_fishing_7d_max"),
            _to_long(r1_active_7d, "nbr_1ring_active_7d_count"),
            _to_long(r2_mean, "nbr_2ring_fishing_mean"),
            _to_long(conv_mat, "current_convergence_proxy"),
        ],
        axis=1,
    ).reset_index()
    stacked = stacked.rename(columns={"level_0": "observation_date", "level_1": "grid_cell_id"})
    stacked["observation_date"] = pd.to_datetime(stacked["observation_date"])
    stacked["current_convergence_isna"] = stacked["current_convergence_proxy"].isna().astype(float)

    out = work[["grid_cell_id", "observation_date"]].merge(
        stacked, on=["grid_cell_id", "observation_date"], how="left"
    )
    return out


def compute_ocean_habitat_features(
    raw_df: pd.DataFrame,
    mapper: SpatialAdjacencyMapper,
    sst_df: Optional[pd.DataFrame] = None,
    chla_df: Optional[pd.DataFrame] = None,
    bathy_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Merge & compute strictly causal (<= T) oceanographic & biological habitat features:
    - sst, sst_spatial_gradient (|grad SST| in degC per 100 km)
    - chl_a, chl_a_lag3_mean, chl_a_lag7_mean, chl_a_lag14_mean, chl_a_anomaly
    - depth_m, seabed_slope
    - Clean missingness flags (sst_isna, sst_spatial_gradient_isna, chl_a_isna, chl_a_lag14_isna, depth_m_isna)
    """
    work = raw_df[["grid_cell_id", "observation_date"]].copy()
    for col in ("sst", "chl_a", "depth_m", "seabed_slope"):
        if col in raw_df.columns:
            work[col] = pd.to_numeric(raw_df[col], errors="coerce")
        else:
            work[col] = np.nan
    work["observation_date"] = pd.to_datetime(work["observation_date"])

    if sst_df is not None and not sst_df.empty:
        s_in = sst_df[["grid_cell_id", "observation_date", "sst"]].copy()
        s_in["observation_date"] = pd.to_datetime(s_in["observation_date"])
        s_in = s_in.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        work = work.merge(s_in, on=["grid_cell_id", "observation_date"], how="left", suffixes=("", "_ext"))
        work["sst"] = work["sst"].combine_first(work.pop("sst_ext"))

    if chla_df is not None and not chla_df.empty:
        c_in = chla_df[["grid_cell_id", "observation_date", "chl_a"]].copy()
        c_in["observation_date"] = pd.to_datetime(c_in["observation_date"])
        c_in = c_in.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        work = work.merge(c_in, on=["grid_cell_id", "observation_date"], how="left", suffixes=("", "_ext"))
        work["chl_a"] = work["chl_a"].combine_first(work.pop("chl_a_ext"))

    if bathy_df is not None and not bathy_df.empty:
        b_in = bathy_df[["grid_cell_id", "depth_m", "seabed_slope"]].drop_duplicates(subset=["grid_cell_id"], keep="last")
        work = work.merge(b_in, on="grid_cell_id", how="left", suffixes=("", "_ext"))
        work["depth_m"] = work["depth_m"].combine_first(work.pop("depth_m_ext"))
        work["seabed_slope"] = work["seabed_slope"].combine_first(work.pop("seabed_slope_ext"))

    work = work.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)
    cell_ids = mapper.cell_ids
    n_cells = len(cell_ids)

    # 1. SST spatial thermal front gradient |grad SST| at date T (degC / 100 km)
    sst_mat, orig_dates = _ensure_daily_matrix(work, "sst", cell_ids)
    sst_vals = sst_mat.values
    sst_grad_mat = np.full_like(sst_vals, np.nan)

    for i, cid in enumerate(cell_ids):
        card = mapper.cardinal_neighbors[cid]
        dx = np.full(len(sst_mat.index), np.nan, dtype=float)
        dy = np.full(len(sst_mat.index), np.nan, dtype=float)

        if card["E"] and card["W"]:
            je = mapper.cell_to_idx[card["E"][0]]
            jw = mapper.cell_to_idx[card["W"][0]]
            center = (sst_vals[:, je] - sst_vals[:, jw]) / ((card["E"][1] + card["W"][1]) / 100.0)
            one_e = (sst_vals[:, je] - sst_vals[:, i]) / (card["E"][1] / 100.0)
            one_w = (sst_vals[:, i] - sst_vals[:, jw]) / (card["W"][1] / 100.0)
            dx = np.where(np.isfinite(center), center, np.where(np.isfinite(one_e), one_e, one_w))
        elif card["E"]:
            je = mapper.cell_to_idx[card["E"][0]]
            dx = (sst_vals[:, je] - sst_vals[:, i]) / (card["E"][1] / 100.0)
        elif card["W"]:
            jw = mapper.cell_to_idx[card["W"][0]]
            dx = (sst_vals[:, i] - sst_vals[:, jw]) / (card["W"][1] / 100.0)

        if card["N"] and card["S"]:
            jn = mapper.cell_to_idx[card["N"][0]]
            js = mapper.cell_to_idx[card["S"][0]]
            center = (sst_vals[:, jn] - sst_vals[:, js]) / ((card["N"][1] + card["S"][1]) / 100.0)
            one_n = (sst_vals[:, jn] - sst_vals[:, i]) / (card["N"][1] / 100.0)
            one_s = (sst_vals[:, i] - sst_vals[:, js]) / (card["S"][1] / 100.0)
            dy = np.where(np.isfinite(center), center, np.where(np.isfinite(one_n), one_n, one_s))
        elif card["N"]:
            jn = mapper.cell_to_idx[card["N"][0]]
            dy = (sst_vals[:, jn] - sst_vals[:, i]) / (card["N"][1] / 100.0)
        elif card["S"]:
            js = mapper.cell_to_idx[card["S"][0]]
            dy = (sst_vals[:, i] - sst_vals[:, js]) / (card["S"][1] / 100.0)

        grad = np.where(
            np.isfinite(dx) & np.isfinite(dy),
            np.hypot(np.nan_to_num(dx), np.nan_to_num(dy)),
            np.where(np.isfinite(dx), np.abs(dx), np.where(np.isfinite(dy), np.abs(dy), np.nan)),
        )

        # Fallback to diagonal 1-ring differences when neither N/S nor E/W axis has valid pair
        nbr_idx = np.where(mapper.ring1_adj[i] > 0)[0]
        if len(nbr_idx) > 0:
            dists_100km = np.array([mapper.distance_km(cid, cell_ids[j]) / 100.0 for j in nbr_idx])
            diffs = np.abs(sst_vals[:, nbr_idx] - sst_vals[:, [i]]) / np.maximum(1e-6, dists_100km)
            valid_cnt = np.sum(np.isfinite(diffs), axis=1)
            diag_fallback = np.where(
                valid_cnt > 0,
                np.nansum(diffs, axis=1) / np.maximum(1, valid_cnt),
                np.nan,
            )
            grad = np.where(np.isfinite(grad), grad, diag_fallback)

        sst_grad_mat[:, i] = grad

    # 2. Strictly causal Chl-a trailing windows (min_periods=1 on dense daily index => [T-k+1 .. T])
    chl_mat, _ = _ensure_daily_matrix(work, "chl_a", cell_ids)
    chl_lag3 = chl_mat.rolling(window=3, min_periods=1).mean()
    chl_lag7 = chl_mat.rolling(window=7, min_periods=1).mean()
    chl_lag14 = chl_mat.rolling(window=14, min_periods=1).mean()
    chl_anom = chl_lag3 - chl_lag14

    full_idx = sst_mat.index

    def _df_to_long(mat_df: pd.DataFrame, col_name: str) -> pd.Series:
        return mat_df.loc[orig_dates].stack(future_stack=True).rename(col_name)

    grad_df = pd.DataFrame(sst_grad_mat, index=full_idx, columns=cell_ids)
    derived = pd.concat(
        [
            _df_to_long(grad_df, "sst_spatial_gradient"),
            _df_to_long(chl_lag3, "chl_a_lag3_mean"),
            _df_to_long(chl_lag7, "chl_a_lag7_mean"),
            _df_to_long(chl_lag14, "chl_a_lag14_mean"),
            _df_to_long(chl_anom, "chl_a_anomaly"),
        ],
        axis=1,
    ).reset_index()
    derived = derived.rename(columns={"level_0": "observation_date", "level_1": "grid_cell_id"})
    derived["observation_date"] = pd.to_datetime(derived["observation_date"])

    out = work.merge(derived, on=["grid_cell_id", "observation_date"], how="left")
    out["sst_isna"] = out["sst"].isna().astype(float)
    out["sst_spatial_gradient_isna"] = out["sst_spatial_gradient"].isna().astype(float)
    out["chl_a_isna"] = out["chl_a"].isna().astype(float)
    out["chl_a_lag14_isna"] = out["chl_a_lag14_mean"].isna().astype(float)
    out["depth_m_isna"] = out["depth_m"].isna().astype(float)
    return out


def _load_multi_source_raw(
    source_parquet_paths: Optional[Union[Path, str, Sequence[Union[Path, str]]]],
) -> Tuple[pd.DataFrame, Path, Optional[tempfile.TemporaryDirectory]]:
    """
    Load one or many raw historical parquets, merging chronologically with deduplication.
    For multi-year lists, stages a combined temporary parquet so build_causal_dataset()
    executes across continuous boundaries without breaking Phase 3 parity.
    """
    if source_parquet_paths is None:
        path = Path(HISTORICAL_CACHE_PATH)
        return pd.read_parquet(path), path, None

    if isinstance(source_parquet_paths, (str, Path)):
        path = Path(source_parquet_paths)
        return pd.read_parquet(path), path, None

    paths = [Path(p) for p in source_parquet_paths]
    if len(paths) == 1:
        return pd.read_parquet(paths[0]), paths[0], None

    frames = [pd.read_parquet(p) for p in paths]
    raw_df = pd.concat(frames, ignore_index=True)
    raw_df["observation_date"] = pd.to_datetime(raw_df["observation_date"])
    raw_df = (
        raw_df.sort_values(["observation_date", "grid_cell_id"])
        .drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        .reset_index(drop=True)
    )
    tmp_dir = tempfile.TemporaryDirectory()
    combined_path = Path(tmp_dir.name) / "combined_multiyear.parquet"
    raw_df.to_parquet(combined_path, index=False)
    return raw_df, combined_path, tmp_dir


def build_phase4_causal_dataset(
    source_parquet_paths: Optional[Union[Path, str, Sequence[Union[Path, str]]]] = None,
    lookback_days: int = 14,
    gfw_lag_days: int = 0,
    ocean_cache_dir: Optional[Path] = None,
    allow_ocean_fetch: bool = False,
    sst_df: Optional[pd.DataFrame] = None,
    chla_df: Optional[pd.DataFrame] = None,
    bathy_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Build the complete Phase 4 causal training/evaluation dataset (T -> T+1):
    - Preserves exact Phase 3 base causal dataset columns (29 features + metadata + target)
    - Adds strictly causal spatial neighborhood features (1-ring, 2-ring, current convergence)
    - Adds strictly causal oceanographic & biological habitat features (SST front, Chl-a blooms, depth/slope)
    """
    raw_df, resolved_path, tmp_dir = _load_multi_source_raw(source_parquet_paths)
    try:
        base_df = build_causal_dataset(
            source_parquet_path=resolved_path,
            lookback_days=lookback_days,
            gfw_lag_days=gfw_lag_days,
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    if base_df.empty:
        return base_df

    raw_df["observation_date"] = pd.to_datetime(raw_df["observation_date"])
    mapper = SpatialAdjacencyMapper(raw_df)
    grid_cells = mapper.cells_df.to_dict(orient="records")

    min_date_str = str(raw_df["observation_date"].min().date())
    max_date_str = str(raw_df["observation_date"].max().date())

    ingestor = GriddedOceanIngestor(ocean_cache_dir=ocean_cache_dir)
    if bathy_df is None and "depth_m" not in raw_df.columns:
        bathy_df = ingestor.load_bathymetry(grid_cells, allow_fetch=allow_ocean_fetch)
    if sst_df is None and "sst" not in raw_df.columns:
        sst_df = ingestor.load_daily_sst(grid_cells, min_date_str, max_date_str, allow_fetch=allow_ocean_fetch)
    if chla_df is None and "chl_a" not in raw_df.columns:
        chla_df = ingestor.load_daily_chla(grid_cells, min_date_str, max_date_str, allow_fetch=allow_ocean_fetch)

    nbr_df = compute_spatial_neighborhood_features(raw_df, mapper, gfw_lag_days=gfw_lag_days)
    ocean_df = compute_ocean_habitat_features(
        raw_df, mapper, sst_df=sst_df, chla_df=chla_df, bathy_df=bathy_df
    )

    nbr_df = nbr_df.rename(columns={"observation_date": "prediction_date_T"})
    ocean_df = ocean_df.rename(columns={"observation_date": "prediction_date_T"})

    merged = base_df.merge(nbr_df, on=["grid_cell_id", "prediction_date_T"], how="left")
    merged = merged.merge(ocean_df, on=["grid_cell_id", "prediction_date_T"], how="left")
    merged = merged.sort_values(["prediction_date_T", "grid_cell_id"]).reset_index(drop=True)
    return merged


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="MatsyaAI Phase 4 Spatial & Ocean Data Pipeline")
    parser.add_argument("--fetch-ocean", action="store_true", help="Acquire & cache GEBCO bathymetry, daily SST, and Chl-a")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, default="2023-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--parquet", type=Path, default=HISTORICAL_CACHE_PATH, help="Canonical grid parquet source")
    args = parser.parse_args()

    raw_df = pd.read_parquet(args.parquet)
    mapper = SpatialAdjacencyMapper(raw_df)
    logger.info(f"Spatial mapper summary: {mapper.to_summary()}")

    if args.fetch_ocean:
        ingestor = GriddedOceanIngestor()
        cells = mapper.cells_df.to_dict(orient="records")
        bathy = ingestor.load_bathymetry(cells, allow_fetch=True)
        sst = ingestor.load_daily_sst(cells, args.start, args.end, allow_fetch=True)
        chl = ingestor.load_daily_chla(cells, args.start, args.end, allow_fetch=True)
        print(
            json.dumps(
                {
                    "status": "OK",
                    "bathy_rows": len(bathy),
                    "bathy_valid": int(bathy["depth_m"].notna().sum()) if "depth_m" in bathy else 0,
                    "sst_rows": len(sst),
                    "sst_valid": int(sst["sst"].notna().sum()) if "sst" in sst else 0,
                    "chla_rows": len(chl),
                    "chla_valid": int(chl["chl_a"].notna().sum()) if "chl_a" in chl else 0,
                    "chla_source": str(chl["chl_a_source"].iloc[0]) if not chl.empty and "chl_a_source" in chl else "UNAVAILABLE",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    _cli()
