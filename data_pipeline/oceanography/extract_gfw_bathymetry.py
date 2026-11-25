"""
MatsyaAI Maharashtra — Streaming GeoTIFF Extractor & Quality Comparator for GFW bathymetry.zip.

Reads `bathymetry.tif` directly from `data/gfw_bulk/bathymetry.zip` using pure Python
stdlib (`struct`, `zlib`, `zipfile`) + `numpy` without requiring GDAL or rasterio.
Extracts only strips overlapping Maharashtra coastal waters (15.0..20.6 N, 71.0..74.2 E),
computes per-cell `depth_m` and `seabed_slope` (m/km) across all 97 canonical cells,
compares against the existing 0.05-deg ERDDAP cache, and upgrades if strictly finer & consistent.
"""

from __future__ import annotations

import json
import math
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = REPO_ROOT / "data" / "gfw_bulk" / "bathymetry.zip"
TIF_NAME = "bathymetry.tif"
OCEAN_CACHE_DIR = REPO_ROOT / "backend" / "app" / "ml" / "data" / "ocean_cache"
CUR_BATHY_PATH = OCEAN_CACHE_DIR / "gebco_bathymetry_grid.parquet"
BACKUP_BATHY_PATH = OCEAN_CACHE_DIR / "gebco_bathymetry_grid_erddap_0.05deg_backup.parquet"
REPORT_PATH = OCEAN_CACHE_DIR / "bathymetry_comparison.json"
HIST_2023_PATH = REPO_ROOT / "backend" / "app" / "ml" / "data" / "historical_full_year_2023.parquet"

BBOX_MIN_LAT, BBOX_MAX_LAT = 15.0, 20.6
BBOX_MIN_LON, BBOX_MAX_LON = 71.0, 74.2
GRID_RES = 0.25

_TYPE_FMT = {
    1: ("B", 1),  # BYTE
    2: ("s", 1),  # ASCII
    3: ("H", 2),  # SHORT
    4: ("I", 4),  # LONG
    5: ("II", 8), # RATIONAL
    11: ("f", 4), # FLOAT
    12: ("d", 8), # DOUBLE
}


def _read_exact(stream, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            raise EOFError(f"Unexpected EOF after {len(buf)}/{n} bytes")
        buf.extend(chunk)
    return bytes(buf)


def _decode_tag_values(buf: bytes, endian: str, typ: int, cnt: int, val_off_bytes: bytes) -> List[Any]:
    fmt_char, item_sz = _TYPE_FMT[typ]
    total_sz = cnt * item_sz
    if total_sz <= 4:
        raw = val_off_bytes[:total_sz]
    else:
        off = struct.unpack(endian + "I", val_off_bytes)[0]
        raw = buf[off : off + total_sz]
    if typ == 2:
        return [raw.decode("ascii", errors="ignore").rstrip("\x00")]
    if typ == 5:
        vals = struct.unpack(endian + "II" * cnt, raw)
        return [vals[2 * k] / max(1, vals[2 * k + 1]) for k in range(cnt)]
    return list(struct.unpack(endian + fmt_char * cnt, raw))


def extract_and_compare() -> Dict[str, Any]:
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"Missing {ZIP_PATH}")

    # Load canonical 97 cells
    hist_df = pd.read_parquet(HIST_2023_PATH)
    valid_cells = (
        hist_df[["grid_cell_id", "latitude", "longitude"]]
        .drop_duplicates(subset=["grid_cell_id"])
        .sort_values("grid_cell_id")
        .reset_index(drop=True)
    )
    valid_ids = set(valid_cells["grid_cell_id"])

    with zipfile.ZipFile(ZIP_PATH) as zf:
        with zf.open(TIF_NAME, "r") as stream:
            # Buffer initial 1 MB sequentially to read IFD + StripOffsets/ByteCounts + GeoTIFF tags
            head_buf = _read_exact(stream, 1_000_000)
            pos = len(head_buf)

            endian = "<" if head_buf[:2] == b"II" else ">"
            magic, ifd_off = struct.unpack(endian + "HI", head_buf[2:8])
            if magic != 42:
                raise ValueError(f"Unsupported TIFF magic {magic}")

            n_entries = struct.unpack(endian + "H", head_buf[ifd_off : ifd_off + 2])[0]
            raw_tags: Dict[int, Tuple[int, int, bytes]] = {}
            max_meta_end = ifd_off + 2 + 12 * n_entries + 4
            for i in range(n_entries):
                e_off = ifd_off + 2 + i * 12
                tag, typ, cnt = struct.unpack(endian + "HHI", head_buf[e_off : e_off + 8])
                val_bytes = head_buf[e_off + 8 : e_off + 12]
                raw_tags[tag] = (typ, cnt, val_bytes)
                if typ in _TYPE_FMT:
                    tsz = cnt * _TYPE_FMT[typ][1]
                    if tsz > 4:
                        off = struct.unpack(endian + "I", val_bytes)[0]
                        max_meta_end = max(max_meta_end, off + tsz)

            if max_meta_end > len(head_buf):
                head_buf += _read_exact(stream, max_meta_end - len(head_buf))
                pos = len(head_buf)

            def get_tag(tag: int, default: Any = None):
                if tag not in raw_tags:
                    return default
                typ, cnt, vb = raw_tags[tag]
                return _decode_tag_values(head_buf, endian, typ, cnt, vb)

            width = int(get_tag(256)[0])
            height = int(get_tag(257)[0])
            bits = int(get_tag(258)[0])
            comp = int(get_tag(259)[0])
            sample_fmt = int(get_tag(339, [1])[0])
            predictor = int(get_tag(317, [1])[0])
            rows_per_strip = int(get_tag(278, [height])[0])
            strip_offsets = get_tag(273)
            strip_counts = get_tag(279)
            pixel_scale = get_tag(33550)
            tiepoint = get_tag(33922)
            nodata_raw = get_tag(42113, [None])[0]

            if rows_per_strip != 1 or comp != 8 or bits != 32 or sample_fmt != 2:
                raise ValueError(
                    f"Unexpected TIFF layout: rows_per_strip={rows_per_strip}, comp={comp}, bits={bits}, sample_fmt={sample_fmt}"
                )

            sx, sy = float(pixel_scale[0]), float(pixel_scale[1])
            origin_lon, origin_lat = float(tiepoint[3]), float(tiepoint[4])

            # Row/col slices for Maharashtra bbox (raster typically top-to-bottom from +90 to -90)
            row_top = max(0, int(math.floor((origin_lat - BBOX_MAX_LAT) / sy)) - 2)
            row_bot = min(height - 1, int(math.ceil((origin_lat - BBOX_MIN_LAT) / sy)) + 2)
            col_left = max(0, int(math.floor((BBOX_MIN_LON - origin_lon) / sx)) - 2)
            col_right = min(width - 1, int(math.ceil((BBOX_MAX_LON - origin_lon) / sx)) + 2)

            # Skip unused northern rows sequentially in bounded chunks
            target_start_off = int(strip_offsets[row_top])
            to_skip = target_start_off - pos
            if to_skip < 0:
                raise RuntimeError(f"Stream already past strip {row_top}: pos={pos}, off={target_start_off}")
            while to_skip > 0:
                skipped = len(stream.read(min(to_skip, 8 * 1024 * 1024)))
                if skipped == 0:
                    raise EOFError("Unexpected EOF while skipping northern hemisphere")
                to_skip -= skipped
                pos += skipped

            n_rows = row_bot - row_top + 1
            n_cols = col_right - col_left + 1
            elev_sub = np.empty((n_rows, n_cols), dtype=np.float64)

            for idx, r in enumerate(range(row_top, row_bot + 1)):
                s_off = int(strip_offsets[r])
                s_cnt = int(strip_counts[r])
                if s_off > pos:
                    _ = _read_exact(stream, s_off - pos)
                    pos = s_off
                comp_bytes = _read_exact(stream, s_cnt)
                pos += s_cnt
                raw_row = zlib.decompress(comp_bytes)
                arr = np.frombuffer(raw_row, dtype=np.dtype(endian + "i4")).copy()
                if predictor == 2:
                    # Horizontal differencing undo in int32 modular arithmetic
                    arr = np.cumsum(arr, dtype=np.int32)
                elev_sub[idx, :] = arr[col_left : col_right + 1].astype(np.float64)

    if nodata_raw is not None:
        try:
            nd = float(nodata_raw)
            elev_sub[elev_sub == nd] = np.nan
        except Exception:
            pass

    # Coordinate vectors (flip south->north so latitude ascends)
    lats_desc = origin_lat - (np.arange(row_top, row_bot + 1) + 0.5) * sy
    lons = origin_lon + (np.arange(col_left, col_right + 1) + 0.5) * sx
    elev = elev_sub[::-1, :]
    lats = lats_desc[::-1]

    # Compute 2D finite-difference seabed slope in m/km
    mean_lat_rad = math.radians(float(np.mean(lats)))
    dy_km = sy * 111.32
    dx_km = sx * 111.32 * math.cos(mean_lat_rad)
    dz_dy, dz_dx = np.gradient(elev, dy_km, dx_km)
    slope_grid = np.hypot(dz_dx, dz_dy)

    # Detect sign convention: check ocean points at 16.5N, 72.0E (deep shelf)
    deep_r = int(np.argmin(np.abs(lats - 16.5)))
    deep_c = int(np.argmin(np.abs(lons - 72.0)))
    deep_sample = float(elev[deep_r, deep_c])
    # Elevation is negative underwater (or positive depth if depth-encoded)
    is_neg_elev = deep_sample < 0

    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    flat_elev = elev.ravel()
    flat_slope = slope_grid.ravel()

    g_lat = np.floor(flat_lat / GRID_RES + 1e-9) * GRID_RES
    g_lon = np.floor(flat_lon / GRID_RES + 1e-9) * GRID_RES
    cids = np.array([f"cell_{la:.2f}_{lo:.2f}_{GRID_RES}" for la, lo in zip(g_lat, g_lon)], dtype=object)

    pts = pd.DataFrame(
        {
            "grid_cell_id": cids,
            "depth_sounding": -flat_elev if is_neg_elev else flat_elev,
            "slope": flat_slope,
        }
    )
    pts = pts[pts["grid_cell_id"].isin(valid_ids)]

    new_rows: List[Dict[str, Any]] = []
    soundings_per_cell: List[int] = []
    for cid in sorted(valid_ids):
        sub = pts[(pts["grid_cell_id"] == cid) & (pts["depth_sounding"] > 0)]
        soundings_per_cell.append(int(len(sub)))
        if sub.empty:
            new_rows.append(
                {
                    "grid_cell_id": cid,
                    "depth_m": np.nan,
                    "seabed_slope": np.nan,
                    "bathy_source": "GFW_GEBCO_30arcsec_bathymetry.tif",
                }
            )
        else:
            valid_slopes = sub["slope"].dropna()
            new_rows.append(
                {
                    "grid_cell_id": cid,
                    "depth_m": round(float(sub["depth_sounding"].mean()), 3),
                    "seabed_slope": round(float(valid_slopes.mean()), 4) if not valid_slopes.empty else np.nan,
                    "bathy_source": "GFW_GEBCO_30arcsec_bathymetry.tif",
                }
            )

    new_df = pd.DataFrame(new_rows)
    old_df = pd.read_parquet(CUR_BATHY_PATH)
    comp_df = old_df.merge(new_df, on="grid_cell_id", suffixes=("_old", "_new"))

    valid_pair = comp_df.dropna(subset=["depth_m_old", "depth_m_new"])
    depth_corr = float(np.corrcoef(valid_pair["depth_m_old"], valid_pair["depth_m_new"])[0, 1])
    depth_mae = float(np.mean(np.abs(valid_pair["depth_m_old"] - valid_pair["depth_m_new"])))
    slope_corr = float(
        np.corrcoef(
            valid_pair["seabed_slope_old"].fillna(0),
            valid_pair["seabed_slope_new"].fillna(0),
        )[0, 1]
    )

    upgraded = False
    if depth_corr >= 0.98 and int(new_df["depth_m"].notna().sum()) == len(valid_ids):
        if not BACKUP_BATHY_PATH.exists():
            old_df.to_parquet(BACKUP_BATHY_PATH, index=False)
        new_df.to_parquet(CUR_BATHY_PATH, index=False)
        upgraded = True

    report = {
        "tif_dimensions": [width, height],
        "tif_resolution_deg": round(sx, 6),
        "tif_resolution_arcsec": round(sx * 3600.0, 2),
        "tif_predictor": predictor,
        "deep_sample_16.5N_72.0E_raw": deep_sample,
        "old_source": str(old_df["bathy_source"].iloc[0]),
        "old_resolution_deg": 0.05,
        "new_source": "GFW_GEBCO_30arcsec_bathymetry.tif",
        "new_resolution_deg": round(sx, 6),
        "soundings_per_cell_min": int(min(soundings_per_cell)),
        "soundings_per_cell_mean": round(float(np.mean(soundings_per_cell)), 1),
        "soundings_per_cell_max": int(max(soundings_per_cell)),
        "valid_cells_old": int(old_df["depth_m"].notna().sum()),
        "valid_cells_new": int(new_df["depth_m"].notna().sum()),
        "depth_pearson_corr": round(depth_corr, 6),
        "depth_mae_m": round(depth_mae, 3),
        "slope_pearson_corr": round(slope_corr, 6),
        "old_slope_median_m_per_km": round(float(old_df["seabed_slope"].median()), 4),
        "new_slope_median_m_per_km": round(float(new_df["seabed_slope"].median()), 4),
        "upgraded_cur_cache": upgraded,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    extract_and_compare()
