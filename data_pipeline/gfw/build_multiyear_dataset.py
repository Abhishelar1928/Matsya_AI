"""
MatsyaAI Maharashtra — 5-Year (2020-2024) Multi-Year Dataset Pipeline.

Stages:
  1. `--extract-gfw`: Stream-reads `mmsi-daily-csvs-10-v3-2020..2024.zip` in parallel,
     filters strictly to the Maharashtra 0.25-deg grid (97 cells), expands the full
     daily panel (2020-01-01..2024-12-31, 177,219 rows), and caches
     `backend/app/ml/data/gfw_maharashtra_2020_2024.parquet`.
  2. `--fetch-env-ocean`: Reuses cached 2023 files and fetches missing 2020, 2021, 2022,
     and 2024 Open-Meteo marine/weather + NOAA CoastWatch ERDDAP SST (`jplMURSST41`) &
     causal +4d-shifted VIIRS Chl-a (`nesdisVHNSQchlaWeekly`).
  3. `--build-parquet`: Joins GFW + Open-Meteo across all 5 years, adds exact static,
     temporal, and environmental derived features, and writes
     `backend/app/ml/data/historical_multiyear_2020_2024.parquet`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import argparse
import concurrent.futures
import io
import json
import logging
import math
import time
import urllib.error
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from backend.app.ml.config import (
    DATA_DIR,
    ENV_RAW_CACHE_DIR,
    GRID_RESOLUTION,
    HISTORICAL_CACHE_PATH,
    HISTORICAL_MARINE_VARIABLES,
    OPEN_METEO_MARINE_URL,
    OPEN_METEO_WEATHER_URL,
)
from ml.features.features_spatial_ocean import OCEAN_CACHE_DIR, GriddedOceanIngestor, SpatialAdjacencyMapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BULK_DIR = REPO_ROOT / "data" / "gfw_bulk"
GFW_MULTIYEAR_PATH = DATA_DIR / "gfw_maharashtra_2020_2024.parquet"
MULTIYEAR_PARQUET_PATH = DATA_DIR / "historical_multiyear_2020_2024.parquet"
YEARS = [2020, 2021, 2022, 2023, 2024]


def _load_canonical_cells() -> Tuple[pd.DataFrame, List[Dict[str, Any]], Set[str]]:
    df = pd.read_parquet(HISTORICAL_CACHE_PATH)
    cells_df = (
        df[["grid_cell_id", "latitude", "longitude", "distance_to_coast_km", "is_coastal"]]
        .drop_duplicates(subset=["grid_cell_id"])
        .sort_values("grid_cell_id")
        .reset_index(drop=True)
    )
    cells = cells_df.to_dict(orient="records")
    return cells_df, cells, set(cells_df["grid_cell_id"])


def _process_year_zip(zip_path_str: str, valid_ids: Set[str]) -> Tuple[int, pd.DataFrame, List[str]]:
    """Worker: stream-read every daily CSV inside a yearly GFW v3 MMSI ZIP and filter to Maharashtra."""
    zp = Path(zip_path_str)
    year = int(zp.stem.split("-")[-1])
    daily_frames: List[pd.DataFrame] = []
    covered_dates: List[str] = []

    with zipfile.ZipFile(zp) as zf:
        csv_names = sorted(n for n in zf.namelist() if n.endswith(".csv"))
        for name in csv_names:
            # Date encoded at tail of filename: mmsi-daily-csvs-10-v3-YYYY-MM-DD.csv
            date_from_name = name[-14:-4]
            covered_dates.append(date_from_name)
            with zf.open(name) as f:
                chunk = pd.read_csv(
                    f,
                    usecols=["date", "cell_ll_lat", "cell_ll_lon", "fishing_hours"],
                    dtype={
                        "date": str,
                        "cell_ll_lat": np.float32,
                        "cell_ll_lon": np.float32,
                        "fishing_hours": np.float32,
                    },
                )
            sub = chunk[
                (chunk["cell_ll_lat"] >= 15.4)
                & (chunk["cell_ll_lat"] <= 20.3)
                & (chunk["cell_ll_lon"] >= 71.9)
                & (chunk["cell_ll_lon"] <= 74.1)
            ]
            if sub.empty:
                continue
            # Snap 0.1-deg cell centroid to 0.25-deg canonical grid
            c_lat = sub["cell_ll_lat"].to_numpy(dtype=np.float64) + 0.05
            c_lon = sub["cell_ll_lon"].to_numpy(dtype=np.float64) + 0.05
            g_lat = np.floor(c_lat / GRID_RESOLUTION + 1e-9) * GRID_RESOLUTION
            g_lon = np.floor(c_lon / GRID_RESOLUTION + 1e-9) * GRID_RESOLUTION
            cids = np.array([f"cell_{la:.2f}_{lo:.2f}_{GRID_RESOLUTION}" for la, lo in zip(g_lat, g_lon)], dtype=object)

            mask = np.isin(cids, list(valid_ids))
            if not mask.any():
                continue

            sub_mh = pd.DataFrame(
                {
                    "grid_cell_id": cids[mask],
                    "observation_date": sub["date"].to_numpy()[mask],
                    "fishing_hours": sub["fishing_hours"].to_numpy(dtype=np.float64)[mask],
                }
            )
            agg = sub_mh.groupby(["grid_cell_id", "observation_date"], as_index=False)["fishing_hours"].sum()
            daily_frames.append(agg)

    out_df = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame(columns=["grid_cell_id", "observation_date", "fishing_hours"])
    if not out_df.empty:
        out_df = out_df.groupby(["grid_cell_id", "observation_date"], as_index=False)["fishing_hours"].sum()
    return year, out_df, covered_dates


def extract_gfw_multiyear() -> pd.DataFrame:
    """Extract 2020-2024 Maharashtra GFW effort from bulk ZIPs in parallel."""
    cells_df, _, valid_ids = _load_canonical_cells()
    zip_paths = [str(BULK_DIR / f"mmsi-daily-csvs-10-v3-{y}.zip") for y in YEARS]
    for zp in zip_paths:
        if not Path(zp).exists():
            raise FileNotFoundError(f"Missing GFW bulk ZIP: {zp}")

    logger.info("Extracting Maharashtra GFW 2020-2024 from 5 global ZIPs in parallel...")
    all_agg: List[pd.DataFrame] = []
    all_covered_dates: Set[str] = set()

    with concurrent.futures.ProcessPoolExecutor(max_workers=len(zip_paths)) as ex:
        futures = [ex.submit(_process_year_zip, zp, valid_ids) for zp in zip_paths]
        for fut in concurrent.futures.as_completed(futures):
            yr, df_yr, cov = fut.result()
            all_covered_dates.update(cov)
            pos_yr = int((df_yr["fishing_hours"] > 1.0).sum()) if not df_yr.empty else 0
            logger.info(f"  Year {yr}: {len(cov)} CSV days covered, {len(df_yr)} active cell-days, {pos_yr} (>1h) cell-days")
            all_agg.append(df_yr)

    agg_df = pd.concat(all_agg, ignore_index=True)
    agg_df = agg_df.groupby(["grid_cell_id", "observation_date"], as_index=False)["fishing_hours"].sum()

    all_dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2020-01-01", "2024-12-31", freq="D")]
    grid_idx = pd.MultiIndex.from_product([sorted(valid_ids), all_dates], names=["grid_cell_id", "observation_date"])
    full_df = pd.DataFrame(index=grid_idx).reset_index()
    full_df = full_df.merge(agg_df, on=["grid_cell_id", "observation_date"], how="left")

    is_cov = full_df["observation_date"].isin(all_covered_dates)
    full_df.loc[is_cov & full_df["fishing_hours"].isna(), "fishing_hours"] = 0.0
    full_df["fishing_hours"] = full_df["fishing_hours"].round(4)
    full_df = full_df.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)

    full_df.to_parquet(GFW_MULTIYEAR_PATH, index=False)
    logger.info(f"Saved {GFW_MULTIYEAR_PATH}: {len(full_df)} rows ({len(all_dates)} days x {len(valid_ids)} cells)")

    # Print annual summary + 2023 comparison against old API parquet
    full_df["year"] = full_df["observation_date"].str[:4]
    for y, g in full_df.groupby("year"):
        pos = int((g["fishing_hours"].fillna(0) > 1.0).sum())
        tot = len(g)
        logger.info(f"  Summary {y}: rows={tot}, pos(>1h)={pos} ({pos/tot*100:.2f}%), sum_fh={g['fishing_hours'].fillna(0).sum():.1f}")

    old23 = pd.read_parquet(HISTORICAL_CACHE_PATH)
    old_pos = int((old23["fishing_hours"].fillna(0) > 1.0).sum())
    logger.info(f"  Existing 2023 API parquet: rows={len(old23)}, pos(>1h)={old_pos} ({old_pos/len(old23)*100:.2f}%), sum_fh={old23['fishing_hours'].fillna(0).sum():.1f}")
    return full_df


# ---------------------------------------------------------------------------
# Open-Meteo & NOAA ERDDAP Resumable Year-by-Year Fetcher
# ---------------------------------------------------------------------------
def _http_json_retry(url: str, timeout: int = 90, retries: int = 4) -> Any:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MatsyaAI-MultiYear/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait = 2.0 * (2 ** attempt)
            logger.warning(f"HTTP {e.code} on attempt {attempt+1}/{retries}, waiting {wait:.1f}s...")
            if attempt == retries - 1:
                raise
            time.sleep(wait)
        except Exception as e:
            wait = 2.0 * (2 ** attempt)
            logger.warning(f"Error ({e}) on attempt {attempt+1}/{retries}, waiting {wait:.1f}s...")
            if attempt == retries - 1:
                raise
            time.sleep(wait)


def _parse_openmeteo_daily(data: Any, batch: List[Tuple[float, float, str]], variables: List[str]) -> pd.DataFrame:
    if isinstance(data, dict) and "hourly" in data:
        data_list = [data]
    elif isinstance(data, list):
        data_list = data
    else:
        return pd.DataFrame()

    records: List[Dict[str, Any]] = []
    for idx, pt in enumerate(data_list):
        if idx >= len(batch):
            break
        cid = batch[idx][2]
        hourly = pt.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            continue
        frame = pd.DataFrame({"observation_date": [t[:10] for t in times]})
        for v in variables:
            arr = hourly.get(v)
            frame[v] = pd.to_numeric(arr, errors="coerce") if arr is not None else np.nan
        daily = frame.groupby("observation_date", as_index=False)[variables].mean()
        daily["grid_cell_id"] = cid
        records.append(daily)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def _fetch_openmeteo_year(year: int, cells: List[Dict[str, Any]]) -> Path:
    ENV_RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ENV_RAW_CACHE_DIR / f"env_{year}-01-01_{year}-12-31.parquet"
    if out_path.exists():
        logger.info(f"Using cached Open-Meteo env for {year}: {out_path}")
        return out_path

    start_d, end_d = f"{year}-01-01", f"{year}-12-31"
    centroids = [(c["latitude"], c["longitude"], c["grid_cell_id"]) for c in cells]
    batch_size = 20
    marine_parts: List[pd.DataFrame] = []
    weather_parts: List[pd.DataFrame] = []
    vars_csv = ",".join(HISTORICAL_MARINE_VARIABLES)

    logger.info(f"Fetching Open-Meteo marine + weather for {year} ({len(centroids)} cells)...")
    for i in range(0, len(centroids), batch_size):
        batch = centroids[i : i + batch_size]
        lats = ",".join(str(b[0]) for b in batch)
        lons = ",".join(str(b[1]) for b in batch)

        w_url = f"{OPEN_METEO_WEATHER_URL}?latitude={lats}&longitude={lons}&hourly=wind_speed_10m&start_date={start_d}&end_date={end_d}&timezone=UTC"
        try:
            w_raw = _http_json_retry(w_url, timeout=90)
            w_df = _parse_openmeteo_daily(w_raw, batch, ["wind_speed_10m"]).rename(columns={"wind_speed_10m": "wind_speed"})
            if not w_df.empty:
                weather_parts.append(w_df)
        except Exception as exc:
            logger.error(f"Open-Meteo weather batch {year} [{i}] failed: {exc}")

        time.sleep(0.5)

        m_url = f"{OPEN_METEO_MARINE_URL}?latitude={lats}&longitude={lons}&hourly={vars_csv}&start_date={start_d}&end_date={end_d}&timezone=UTC"
        try:
            m_raw = _http_json_retry(m_url, timeout=90)
            m_df = _parse_openmeteo_daily(m_raw, batch, HISTORICAL_MARINE_VARIABLES)
            if not m_df.empty:
                marine_parts.append(m_df)
        except Exception as exc:
            logger.warning(f"Open-Meteo marine batch {year} [{i}] skipped/partial: {exc}")

        time.sleep(0.5)

    w_all = pd.concat(weather_parts, ignore_index=True) if weather_parts else pd.DataFrame(columns=["grid_cell_id", "observation_date", "wind_speed"])
    m_all = pd.concat(marine_parts, ignore_index=True) if marine_parts else pd.DataFrame(columns=["grid_cell_id", "observation_date"] + HISTORICAL_MARINE_VARIABLES)

    all_dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(start_d, end_d, freq="D")]
    base_idx = pd.MultiIndex.from_product([[c["grid_cell_id"] for c in cells], all_dates], names=["grid_cell_id", "observation_date"])
    env_df = pd.DataFrame(index=base_idx).reset_index()
    env_df = env_df.merge(m_all, on=["grid_cell_id", "observation_date"], how="left")
    env_df = env_df.merge(w_all, on=["grid_cell_id", "observation_date"], how="left")
    env_df["env_source"] = "open-meteo-historical"
    env_df["env_matched_date"] = env_df["observation_date"]
    env_df["env_temporal_offset_hours"] = 0

    for col in HISTORICAL_MARINE_VARIABLES + ["wind_speed"]:
        if col in env_df.columns:
            env_df[col] = env_df[col].round(4)

    env_df.to_parquet(out_path, index=False)
    logger.info(
        f"Saved Open-Meteo {year}: {len(env_df)} rows | "
        f"wind={env_df['wind_speed'].notna().mean():.2%}, wave={env_df['wave_height'].notna().mean():.2%}, curr={env_df['ocean_current_velocity'].notna().mean():.2%}"
    )
    return out_path


def _fetch_sst_year(year: int, cells: List[Dict[str, Any]], ing: GriddedOceanIngestor) -> Path:
    out_path = OCEAN_CACHE_DIR / f"sst_{year}-01-01_{year}-12-31.parquet"
    if out_path.exists():
        logger.info(f"Using cached SST for {year}: {out_path}")
        return out_path

    valid_ids = {c["grid_cell_id"] for c in cells}
    dataset_id = "jplMURSST41"
    stride = 15  # ~0.15 deg spacing (~16.6 km) -> fast, clean multi-point average per 0.25-deg cell
    chunk_frames: List[pd.DataFrame] = []
    logger.info(f"Fetching NOAA jplMURSST41 daily SST for {year}...")
    for q_start, q_end in ing._quarterly_ranges(f"{year}-01-01", f"{year}-12-31", max_days=44):
        url = (
            f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{dataset_id}.csv"
            f"?analysed_sst[({q_start}T09:00:00Z):1:({q_end}T09:00:00Z)][({ing.min_lat}):{stride}:({ing.max_lat})][({ing.min_lon}):{stride}:({ing.max_lon})]"
        )
        csv_text = None
        for attempt in range(3):
            try:
                csv_text = ing._http_get_text(url, timeout=90)
                break
            except Exception as exc:
                logger.warning(f"  SST {q_start}..{q_end} attempt {attempt+1} failed: {exc}")
                time.sleep(2.0 * (attempt + 1))
        if csv_text is None:
            continue
        sub = pd.read_csv(io.StringIO(csv_text), skiprows=[1])
        sub.columns = [c.strip() for c in sub.columns]
        sub["observation_date"] = pd.to_datetime(sub["time"].astype(str).str[:10])
        sub["latitude"] = pd.to_numeric(sub["latitude"], errors="coerce")
        sub["longitude"] = pd.to_numeric(sub["longitude"], errors="coerce")
        sub["sst"] = pd.to_numeric(sub["analysed_sst"], errors="coerce")
        sub = sub.dropna(subset=["observation_date", "latitude", "longitude"])
        sub["grid_cell_id"] = ing._snap_points_to_cells(sub["latitude"].values, sub["longitude"].values, valid_ids, res=ing.resolution)
        sub = sub[sub["grid_cell_id"] != ""]
        if not sub.empty:
            chunk_frames.append(sub.groupby(["grid_cell_id", "observation_date"], as_index=False)["sst"].mean())
            logger.info(f"  SST {q_start}..{q_end}: {len(chunk_frames[-1])} records")

    sst_df = pd.concat(chunk_frames, ignore_index=True) if chunk_frames else pd.DataFrame(columns=["grid_cell_id", "observation_date", "sst"])
    if not sst_df.empty:
        sst_df = sst_df.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        sst_df["sst"] = sst_df["sst"].round(4)
        sst_df["sst_source"] = "NOAA_ERDDAP:jplMURSST41"
        sst_df = sst_df.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)
    sst_df.to_parquet(out_path, index=False)
    logger.info(f"Saved SST {year}: {len(sst_df)} rows (valid={int(sst_df['sst'].notna().sum())})")
    return out_path


def _fetch_chla_year(year: int, cells: List[Dict[str, Any]], ing: GriddedOceanIngestor, force: bool = False) -> Path:
    out_path = OCEAN_CACHE_DIR / f"chla_{year}-01-01_{year}-12-31.parquet"
    if out_path.exists() and not force:
        logger.info(f"Using cached Chl-a for {year}: {out_path}")
        return out_path

    valid_ids = {c["grid_cell_id"] for c in cells}
    stride = 3  # ~0.125 deg on 0.0417 deg ESA CCI grid
    causal_shift_days = 8  # ESA CCI 8-day timestamp marks composite start; +8d guarantees causal history <= observation_date
    req_start = pd.Timestamp(f"{year}-01-01")
    req_end = pd.Timestamp(f"{year}-12-31")
    fetch_start = (req_start - pd.Timedelta(days=causal_shift_days)).strftime("%Y-%m-%d")

    logger.info(f"Fetching causal +8d shifted ESA Ocean Colour CCI v6.0 8-day Chl-a for {year}...")
    chunk_frames: List[pd.DataFrame] = []
    for q_start, q_end in ing._quarterly_ranges(fetch_start, f"{year}-12-31", max_days=90):
        urls = [
            (
                f"https://oceanwatch.pifsc.noaa.gov/erddap/griddap/esa-cci-chla-8d-v6-0.csv"
                f"?chlor_a[({q_start}T00:00:00Z):1:({q_end}T00:00:00Z)][({ing.max_lat}):{stride}:({ing.min_lat})][({ing.min_lon}):{stride}:({ing.max_lon})]"
            ),
            (
                f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/pmlEsaCCI60OceanColor8Day.csv"
                f"?chlor_a[({q_start}T00:00:00Z):1:({q_end}T00:00:00Z)][({ing.max_lat}):{stride}:({ing.min_lat})][({ing.min_lon}):{stride}:({ing.max_lon})]"
            ),
        ]
        csv_text = None
        for attempt in range(3):
            for url in urls:
                try:
                    csv_text = ing._http_get_text(url, timeout=90)
                    break
                except Exception as exc:
                    logger.warning(f"  Chl-a {q_start}..{q_end} attempt {attempt+1} ({url.split('/')[2]}) failed: {exc}")
            if csv_text is not None:
                break
            time.sleep(2.0 * (attempt + 1))
        if csv_text is None:
            continue
        sub = pd.read_csv(io.StringIO(csv_text), skiprows=[1])
        sub.columns = [c.strip() for c in sub.columns]
        obs_dt = pd.to_datetime(sub["time"].astype(str).str[:10]) + pd.Timedelta(days=causal_shift_days)
        sub["observation_date"] = obs_dt
        sub["latitude"] = pd.to_numeric(sub["latitude"], errors="coerce")
        sub["longitude"] = pd.to_numeric(sub["longitude"], errors="coerce")
        sub["chl_a"] = pd.to_numeric(sub["chlor_a"], errors="coerce")
        sub.loc[sub["chl_a"] <= 0, "chl_a"] = np.nan
        sub = sub.dropna(subset=["observation_date", "latitude", "longitude"])
        sub["grid_cell_id"] = ing._snap_points_to_cells(sub["latitude"].values, sub["longitude"].values, valid_ids, res=ing.resolution)
        sub = sub[sub["grid_cell_id"] != ""]
        if not sub.empty:
            chunk_frames.append(sub.groupby(["grid_cell_id", "observation_date"], as_index=False)["chl_a"].mean())
            logger.info(f"  Chl-a {q_start}..{q_end}: {len(chunk_frames[-1])} records (valid={int(chunk_frames[-1]['chl_a'].notna().sum())})")

    chl_df = pd.concat(chunk_frames, ignore_index=True) if chunk_frames else pd.DataFrame(columns=["grid_cell_id", "observation_date", "chl_a"])
    if not chl_df.empty:
        chl_df = chl_df[(chl_df["observation_date"] >= req_start) & (chl_df["observation_date"] <= req_end)]
        chl_df = chl_df.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")
        chl_df["chl_a"] = chl_df["chl_a"].round(4)
        chl_df["chl_a_source"] = f"ESA_CCI_v6.0:esa-cci-chla-8d-v6-0_shift{causal_shift_days}d"
        chl_df = chl_df.sort_values(["observation_date", "grid_cell_id"]).reset_index(drop=True)
    chl_df.to_parquet(out_path, index=False)
    logger.info(f"Saved Chl-a {year}: {len(chl_df)} rows (valid={int(chl_df['chl_a'].notna().sum())})")
    return out_path


def fetch_all_env_and_ocean(years: List[int], force_chla: bool = False) -> None:
    _, cells, _ = _load_canonical_cells()
    ing = GriddedOceanIngestor()
    for y in years:
        _fetch_openmeteo_year(y, cells)
        _fetch_sst_year(y, cells, ing)
        _fetch_chla_year(y, cells, ing, force=force_chla)


def build_multiyear_parquet() -> Path:
    """Join GFW 2020-2024 + all yearly Open-Meteo caches into historical_multiyear_2020_2024.parquet."""
    if not GFW_MULTIYEAR_PATH.exists():
        raise FileNotFoundError(f"Run --extract-gfw first: missing {GFW_MULTIYEAR_PATH}")

    cells_df, _, _ = _load_canonical_cells()
    gfw_df = pd.read_parquet(GFW_MULTIYEAR_PATH)
    gfw_df["observation_date"] = gfw_df["observation_date"].astype(str).str[:10]

    env_frames: List[pd.DataFrame] = []
    for y in YEARS:
        ep = ENV_RAW_CACHE_DIR / f"env_{y}-01-01_{y}-12-31.parquet"
        if not ep.exists():
            raise FileNotFoundError(f"Missing env cache {ep}; run --fetch-env-ocean first.")
        part = pd.read_parquet(ep)
        part["observation_date"] = part["observation_date"].astype(str).str[:10]
        env_frames.append(part)

    env_df = pd.concat(env_frames, ignore_index=True)
    env_df = env_df.drop_duplicates(subset=["grid_cell_id", "observation_date"], keep="last")

    merged = gfw_df.merge(cells_df, on="grid_cell_id", how="left")
    merged = merged.merge(env_df, on=["grid_cell_id", "observation_date"], how="left")

    dates = pd.to_datetime(merged["observation_date"])
    merged["day_of_year"] = dates.dt.dayofyear
    merged["month"] = dates.dt.month
    merged["day_of_week"] = dates.dt.dayofweek
    merged["sin_day_of_year"] = np.sin(2 * np.pi * merged["day_of_year"] / 365.25)
    merged["cos_day_of_year"] = np.cos(2 * np.pi * merged["day_of_year"] / 365.25)

    merged["wave_height_isna"] = merged["wave_height"].isna().astype(float)
    merged["ocean_current_isna"] = merged["ocean_current_velocity"].isna().astype(float)
    merged["wind_speed_isna"] = merged["wind_speed"].isna().astype(float)
    merged["wave_direction_sin"] = np.sin(np.radians(merged["wave_direction"]))
    merged["wave_direction_cos"] = np.cos(np.radians(merged["wave_direction"]))

    merged = merged.sort_values(["grid_cell_id", "observation_date"]).reset_index(drop=True)
    merged.to_parquet(MULTIYEAR_PARQUET_PATH, index=False)
    logger.info(
        f"Saved {MULTIYEAR_PARQUET_PATH}: {len(merged)} rows, "
        f"{merged['grid_cell_id'].nunique()} cells, "
        f"{merged['observation_date'].min()}..{merged['observation_date'].max()}"
    )
    return MULTIYEAR_PARQUET_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="MatsyaAI Multi-Year (2020-2024) Dataset Builder")
    parser.add_argument("--extract-gfw", action="store_true")
    parser.add_argument("--fetch-env-ocean", action="store_true")
    parser.add_argument("--force-chla", action="store_true")
    parser.add_argument("--build-parquet", action="store_true")
    parser.add_argument("--years", nargs="+", type=int, default=[2020, 2021, 2022, 2024])
    args = parser.parse_args()

    if args.extract_gfw:
        extract_gfw_multiyear()
    if args.fetch_env_ocean:
        fetch_all_env_and_ocean(args.years, force_chla=args.force_chla)
    if args.build_parquet:
        build_multiyear_parquet()


if __name__ == "__main__":
    main()
