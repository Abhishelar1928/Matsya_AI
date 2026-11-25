"""
MatsyaAI — Build GEBCO depth contours for Offline Expedition Mode.

Input : a GEBCO grid subset for the Maharashtra coast, downloaded from
        https://download.gebco.net/  (bbox lon 71.5–74.0, lat 15.5–20.5)
        as **Esri ASCII** (.asc)  — or netCDF (.nc) if `netCDF4` is installed.
Output: backend/static/offline/bathymetry-contours.geojson
        LineStrings with property `depth_m` (positive metres below sea level).

Usage:
    python backend/scripts/build_bathymetry_contours.py path/to/gebco_subset.asc
    python backend/scripts/build_bathymetry_contours.py gebco.nc --levels 10 20 30 50 100 200

Pure numpy marching squares — no GDAL/matplotlib dependency.
Attribution: GEBCO Compilation Group (2024) GEBCO 2024 Grid. Not for navigation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

DEFAULT_LEVELS = [10, 20, 50, 100, 200]
OUT_PATH = Path(__file__).resolve().parents[1] / "static" / "offline" / "bathymetry-contours.geojson"
ERDDAP_GEBCO_CSV = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/GEBCO_2020.csv"
    "?elevation[({min_lat}):{stride}:({max_lat})][({min_lon}):{stride}:({max_lon})]"
)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------
def read_asc(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Esri ASCII grid → (elevation[rows, cols], lons[cols], lats[rows]) with lats ascending."""
    header: Dict[str, float] = {}
    with path.open() as f:
        lines = []
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0].lower() in ("ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "nodata_value"):
                header[parts[0].lower()] = float(parts[1])
            else:
                lines.append(line)
                break
        lines.extend(f)
    ncols, nrows, cell = int(header["ncols"]), int(header["nrows"]), header["cellsize"]
    x0 = header.get("xllcorner", header.get("xllcenter", 0) - cell / 2) + cell / 2
    y0 = header.get("yllcorner", header.get("yllcenter", 0) - cell / 2) + cell / 2
    nodata = header.get("nodata_value", -9999)
    z = np.loadtxt(lines).reshape(nrows, ncols)[::-1]  # ASCII rows go north→south; flip to ascending lat
    z = np.where(z == nodata, np.nan, z).astype(float)
    return z, x0 + cell * np.arange(ncols), y0 + cell * np.arange(nrows)


def read_nc(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        import netCDF4  # type: ignore
    except ImportError:
        sys.exit("netCDF input needs `pip install netCDF4`, or download the GEBCO subset as Esri ASCII (.asc).")
    ds = netCDF4.Dataset(path)
    z = np.array(ds.variables["elevation"][:], dtype=float)
    lons = np.array(ds.variables["lon"][:])
    lats = np.array(ds.variables["lat"][:])
    if lats[0] > lats[-1]:
        z, lats = z[::-1], lats[::-1]
    return z, lons, lats


# ---------------------------------------------------------------------------
# Marching squares (iso-lines of a 2-D grid)
# ---------------------------------------------------------------------------
def _interp(p1: float, p2: float, v1: float, v2: float, level: float) -> float:
    return p1 if v2 == v1 else p1 + (level - v1) * (p2 - p1) / (v2 - v1)


def marching_squares(z: np.ndarray, xs: np.ndarray, ys: np.ndarray, level: float) -> List[List[Tuple[float, float]]]:
    """Return polylines (lists of (lon, lat)) along z == level. NaNs are skipped."""
    rows, cols = z.shape
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            tl, tr, bl, br = z[i + 1, j], z[i + 1, j + 1], z[i, j], z[i, j + 1]
            if np.isnan([tl, tr, bl, br]).any():
                continue
            idx = (tl > level) << 3 | (tr > level) << 2 | (br > level) << 1 | (bl > level)
            if idx in (0, 15):
                continue
            x0, x1, y0, y1 = xs[j], xs[j + 1], ys[i], ys[i + 1]
            top = (_interp(x0, x1, tl, tr, level), y1)
            bottom = (_interp(x0, x1, bl, br, level), y0)
            left = (x0, _interp(y0, y1, bl, tl, level))
            right = (x1, _interp(y0, y1, br, tr, level))
            table = {
                1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(top, right)],
                5: [(left, top), (bottom, right)], 6: [(top, bottom)], 7: [(left, top)], 8: [(left, top)],
                9: [(top, bottom)], 10: [(left, bottom), (top, right)], 11: [(top, right)], 12: [(left, right)],
                13: [(bottom, right)], 14: [(left, bottom)],
            }
            segments.extend(table[idx])

    # Chain segments into polylines
    key = lambda p: (round(p[0], 7), round(p[1], 7))
    adj: Dict[Tuple[float, float], List[int]] = {}
    for n, (a, b) in enumerate(segments):
        adj.setdefault(key(a), []).append(n)
        adj.setdefault(key(b), []).append(n)
    used = [False] * len(segments)
    lines: List[List[Tuple[float, float]]] = []
    for n in range(len(segments)):
        if used[n]:
            continue
        used[n] = True
        a, b = segments[n]
        line = [a, b]
        for end_is_tail in (True, False):
            while True:
                tip = line[-1] if end_is_tail else line[0]
                nxt = next((m for m in adj.get(key(tip), []) if not used[m]), None)
                if nxt is None:
                    break
                used[nxt] = True
                c, d = segments[nxt]
                other = d if key(c) == key(tip) else c
                if end_is_tail:
                    line.append(other)
                else:
                    line.insert(0, other)
        lines.append(line)
    return lines


def simplify(line: List[Tuple[float, float]], tol: float) -> List[Tuple[float, float]]:
    """Douglas–Peucker."""
    if len(line) < 3:
        return line
    (x1, y1), (x2, y2) = line[0], line[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(line) - 1):
        px, py = line[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > tol:
        return simplify(line[: idx + 1], tol)[:-1] + simplify(line[idx:], tol)
    return [line[0], line[-1]]


# ---------------------------------------------------------------------------
def read_tif(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        import rasterio  # type: ignore
    except ImportError:
        sys.exit("GeoTIFF input needs `pip install rasterio`, or download as Esri ASCII / netCDF.")
    with rasterio.open(path) as src:
        z = src.read(1).astype(float)
        if src.nodata is not None:
            z = np.where(z == src.nodata, np.nan, z)
        transform = src.transform
        lons = transform.c + transform.a * (np.arange(src.width) + 0.5)
        lats = transform.f + transform.e * (np.arange(src.height) + 0.5)
        if lats[0] > lats[-1]:
            z, lats = z[::-1], lats[::-1]
        return z, lons, lats


def fetch_erddap_gebco(min_lat: float, max_lat: float, min_lon: float, max_lon: float, stride: int = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    import urllib.request
    url = ERDDAP_GEBCO_CSV.format(min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, stride=stride)
    raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8").splitlines()[2:]
    pts = [line.split(",") for line in raw if line.strip()]
    lats = np.array(sorted({float(p[0]) for p in pts}))
    lons = np.array(sorted({float(p[1]) for p in pts}))
    lat_i = {v: i for i, v in enumerate(lats)}
    lon_i = {v: i for i, v in enumerate(lons)}
    z = np.full((len(lats), len(lons)), np.nan, dtype=float)
    for la, lo, el in pts:
        z[lat_i[float(la)], lon_i[float(lo)]] = float(el)
    return z, lons, lats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("grid", type=Path, nargs="?", help="GEBCO subset (.asc, .nc, or .tif)")
    ap.add_argument("--fetch-erddap", action="store_true", help="Fetch Maharashtra subset directly from CoastWatch ERDDAP GEBCO_2020")
    ap.add_argument("--bbox", type=float, nargs=4, default=[15.0, 20.6, 71.0, 74.2], metavar=("MIN_LAT", "MAX_LAT", "MIN_LON", "MAX_LON"))
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--levels", type=float, nargs="+", default=DEFAULT_LEVELS, help="depths in metres")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--tolerance", type=float, default=0.002, help="simplification tolerance in degrees")
    ap.add_argument("--min-points", type=int, default=4, help="drop contours shorter than this")
    args = ap.parse_args()

    if args.fetch_erddap:
        z, lons, lats = fetch_erddap_gebco(*args.bbox, stride=args.stride)
    else:
        if not args.grid or not args.grid.exists():
            sys.exit(f"Input not found: {args.grid}")
        suf = args.grid.suffix.lower()
        if suf == ".nc":
            z, lons, lats = read_nc(args.grid)
        elif suf in (".tif", ".tiff"):
            z, lons, lats = read_tif(args.grid)
        else:
            z, lons, lats = read_asc(args.grid)
    print(f"Grid {z.shape[1]}x{z.shape[0]}  lon {lons[0]:.3f}..{lons[-1]:.3f}  lat {lats[0]:.3f}..{lats[-1]:.3f}  "
          f"elev {np.nanmin(z):.0f}..{np.nanmax(z):.0f} m")

    features = []
    for depth in args.levels:
        lines = marching_squares(z, lons, lats, -abs(depth))  # GEBCO elevation is negative below sea level
        kept = 0
        for line in lines:
            line = simplify(line, args.tolerance)
            if len(line) < args.min_points:
                continue
            kept += 1
            features.append({
                "type": "Feature",
                "properties": {"depth_m": abs(depth)},
                "geometry": {"type": "LineString", "coordinates": [[round(x, 5), round(y, 5)] for x, y in line]},
            })
        print(f"  {depth:>6.0f} m: {kept} contour lines")

    geo = {
        "type": "FeatureCollection",
        "name": "GEBCO depth contours — Maharashtra coast",
        "attribution": "GEBCO Compilation Group (2024) GEBCO 2024 Grid (doi:10.5285/1c44ce99-0a0d-5f4f-e063-7086abc0ea0f). Not for navigation.",
        "features": features,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(geo, separators=(",", ":")))
    print(f"Wrote {len(features)} features → {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
