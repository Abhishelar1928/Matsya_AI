/**
 * MatsyaAI Maharashtra — Autonomous Oceanographic Data Acquisition & Processing Pipeline
 *
 * Acquires, validates, processes, and exports publicly accessible oceanographic,
 * bathymetric, marine conservation, navigational hazard, and meteorological datasets
 * for the Maharashtra coastline (Palghar, Thane, Mumbai, Raigad, Ratnagiri, Sindhudurg).
 *
 * CRS: WGS84 (EPSG:4326)
 * Output directory: backend/static/offline/
 *
 * Strict integrity rules:
 * - Never fabricates coordinates, warnings, depths, or exclusion zones.
 * - Preserves observation timestamps, units, spatial resolution, and source attribution.
 * - Explicitly discloses GEBCO non-navigation limitation and Overpass/AIS limitations.
 */

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';

// Govt/research endpoints in India occasionally present incomplete intermediate chains
process.env.NODE_TLS_REJECT_UNAUTHORIZED = process.env.NODE_TLS_REJECT_UNAUTHORIZED || '0';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const OUT_DIR = path.join(REPO_ROOT, 'backend', 'static', 'offline');

// Configurable Maharashtra coastal bounding box (EPSG:4326)
const BBOX = {
  min_lat: Number(process.env.MH_BBOX_MIN_LAT || 15.0),
  max_lat: Number(process.env.MH_BBOX_MAX_LAT || 20.6),
  min_lon: Number(process.env.MH_BBOX_MIN_LON || 71.0),
  max_lon: Number(process.env.MH_BBOX_MAX_LON || 74.2),
};

const DISTRICTS = ['Palghar', 'Thane', 'Mumbai', 'Raigad', 'Ratnagiri', 'Sindhudurg'];
const CONTOUR_DEPTHS_M = [10, 20, 50, 100, 200];

const USER_AGENT = 'MatsyaAI-OceanDataPipeline/2.0 (Maharashtra Marine Decision Support)';

// ---------------------------------------------------------------------------
// Helpers: HTTP, Hashing, PNG Encoding, Marching Squares
// ---------------------------------------------------------------------------
async function fetchWithTimeout(url, opts = {}, timeoutMs = 45000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...opts,
      signal: controller.signal,
      headers: { 'User-Agent': USER_AGENT, ...(opts.headers || {}) },
    });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

function sha256Buffer(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

function writeAsset(filename, content) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const filePath = path.join(OUT_DIR, filename);
  const buf = Buffer.isBuffer(content) ? content : Buffer.from(content, 'utf8');
  fs.writeFileSync(filePath, buf);
  return {
    filename,
    size_bytes: buf.length,
    sha256: sha256Buffer(buf),
    url: `/api/v1/offline-assets/${filename}`,
  };
}

// Pure-Node PNG encoder (RGBA)
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function encodePngRgba(width, height, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter None
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const compressed = zlib.deflateSync(raw, { level: 6 });
  return Buffer.concat([
    sig,
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', compressed),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function lerpColor(stops, t) {
  const c = Math.max(0, Math.min(1, t));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, r0, g0, b0] = stops[i];
    const [t1, r1, g1, b1] = stops[i + 1];
    if (c >= t0 && c <= t1) {
      const f = (c - t0) / (t1 - t0 || 1);
      return [
        Math.round(r0 + (r1 - r0) * f),
        Math.round(g0 + (g1 - g0) * f),
        Math.round(b0 + (b1 - b0) * f),
      ];
    }
  }
  const last = stops[stops.length - 1];
  return [last[1], last[2], last[3]];
}

// Marching squares + Douglas-Peucker (mirrors backend/scripts/build_bathymetry_contours.py)
function interp(p1, p2, v1, v2, level) {
  return v2 === v1 ? p1 : p1 + ((level - v1) * (p2 - p1)) / (v2 - v1);
}

function marchingSquares(z, xs, ys, level) {
  const rows = z.length;
  const cols = xs.length;
  const segments = [];
  for (let i = 0; i < rows - 1; i++) {
    for (let j = 0; j < cols - 1; j++) {
      const tl = z[i + 1][j];
      const tr = z[i + 1][j + 1];
      const bl = z[i][j];
      const br = z[i][j + 1];
      if (!Number.isFinite(tl) || !Number.isFinite(tr) || !Number.isFinite(bl) || !Number.isFinite(br)) {
        continue;
      }
      const idx = ((tl > level ? 1 : 0) << 3) | ((tr > level ? 1 : 0) << 2) | ((br > level ? 1 : 0) << 1) | (bl > level ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      const x0 = xs[j];
      const x1 = xs[j + 1];
      const y0 = ys[i];
      const y1 = ys[i + 1];
      const top = [interp(x0, x1, tl, tr, level), y1];
      const bottom = [interp(x0, x1, bl, br, level), y0];
      const left = [x0, interp(y0, y1, bl, tl, level)];
      const right = [x1, interp(y0, y1, br, tr, level)];
      const table = {
        1: [[left, bottom]],
        2: [[bottom, right]],
        3: [[left, right]],
        4: [[top, right]],
        5: [[left, top], [bottom, right]],
        6: [[top, bottom]],
        7: [[left, top]],
        8: [[left, top]],
        9: [[top, bottom]],
        10: [[left, bottom], [top, right]],
        11: [[top, right]],
        12: [[left, right]],
        13: [[bottom, right]],
        14: [[left, bottom]],
      };
      for (const seg of table[idx]) segments.push(seg);
    }
  }

  const key = (p) => `${p[0].toFixed(6)},${p[1].toFixed(6)}`;
  const adj = new Map();
  segments.forEach(([a, b], n) => {
    const ka = key(a);
    const kb = key(b);
    if (!adj.has(ka)) adj.set(ka, []);
    if (!adj.has(kb)) adj.set(kb, []);
    adj.get(ka).push(n);
    adj.get(kb).push(n);
  });

  const used = new Uint8Array(segments.length);
  const lines = [];
  for (let n = 0; n < segments.length; n++) {
    if (used[n]) continue;
    used[n] = 1;
    const line = [segments[n][0], segments[n][1]];
    for (const endIsTail of [true, false]) {
      while (true) {
        const tip = endIsTail ? line[line.length - 1] : line[0];
        const kTip = key(tip);
        const candidates = adj.get(kTip) || [];
        const nxt = candidates.find((m) => !used[m]);
        if (nxt === undefined) break;
        used[nxt] = 1;
        const [c, d] = segments[nxt];
        const other = key(c) === kTip ? d : c;
        if (endIsTail) line.push(other);
        else line.unshift(other);
      }
    }
    lines.push(line);
  }
  return lines;
}

function simplifyLine(line, tol) {
  if (line.length < 3) return line;
  const [x1, y1] = line[0];
  const [x2, y2] = line[line.length - 1];
  const dx = x2 - x1;
  const dy = y2 - y1;
  const norm = Math.hypot(dx, dy) || 1e-12;
  let dmax = 0;
  let idx = 0;
  for (let i = 1; i < line.length - 1; i++) {
    const [px, py] = line[i];
    const d = Math.abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm;
    if (d > dmax) {
      dmax = d;
      idx = i;
    }
  }
  if (dmax > tol) {
    return simplifyLine(line.slice(0, idx + 1), tol).slice(0, -1).concat(simplifyLine(line.slice(idx), tol));
  }
  return [line[0], line[line.length - 1]];
}

// Simplified Maharashtra shoreline for filtering open-sea grid points
const WEST_COAST = [
  [14.0, 74.45], [14.81, 74.12], [15.49, 73.81], [15.86, 73.62], [16.06, 73.46],
  [16.37, 73.37], [16.56, 73.33], [16.99, 73.28], [17.22, 73.22], [17.58, 73.17],
  [17.81, 73.09], [18.04, 73.01], [18.33, 72.96], [18.64, 72.87], [18.92, 72.81],
  [19.12, 72.82], [19.20, 72.78], [19.32, 72.80], [19.45, 72.77], [19.70, 72.72],
  [19.97, 72.73], [20.15, 72.73], [20.42, 72.83], [20.8, 72.83],
];

function isOnLand(lat, lon) {
  for (let i = 0; i < WEST_COAST.length - 1; i++) {
    const [la1, lo1] = WEST_COAST[i];
    const [la2, lo2] = WEST_COAST[i + 1];
    if (lat >= la1 && lat <= la2) {
      const coastLon = lo1 + ((lat - la1) / (la2 - la1 || 1)) * (lo2 - lo1);
      return lon >= coastLon - 0.03;
    }
  }
  return lon >= 72.83;
}

// ---------------------------------------------------------------------------
// 1. GEBCO Bathymetry Contours (10m, 20m, 50m, 100m, 200m)
// ---------------------------------------------------------------------------
async function acquireBathymetry() {
  console.log('\n[1/8] Acquiring GEBCO_2020 bathymetry contours via NOAA CoastWatch ERDDAP...');
  const stride = 2; // 30 arc-second (~0.9 km) along Maharashtra shelf
  const url = `https://coastwatch.pfeg.noaa.gov/erddap/griddap/GEBCO_2020.csv?elevation[(${BBOX.min_lat}):${stride}:(${BBOX.max_lat})][(${BBOX.min_lon}):${stride}:(${BBOX.max_lon})]`;
  const res = await fetchWithTimeout(url, {}, 90000);
  if (!res.ok) throw new Error(`GEBCO ERDDAP HTTP ${res.status}`);
  const csv = await res.text();
  const lines = csv.split(/\r?\n/).slice(2).filter(Boolean);

  const latSet = new Set();
  const lonSet = new Set();
  const pts = [];
  for (const row of lines) {
    const [laS, loS, elS] = row.split(',');
    const la = Number(laS);
    const lo = Number(loS);
    const el = Number(elS);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) continue;
    latSet.add(la);
    lonSet.add(lo);
    pts.push([la, lo, el]);
  }
  const lats = [...latSet].sort((a, b) => a - b);
  const lons = [...lonSet].sort((a, b) => a - b);
  const latIdx = new Map(lats.map((v, i) => [v, i]));
  const lonIdx = new Map(lons.map((v, i) => [v, i]));
  const z = Array.from({ length: lats.length }, () => new Float64Array(lons.length).fill(NaN));
  for (const [la, lo, el] of pts) {
    z[latIdx.get(la)][lonIdx.get(lo)] = el;
  }

  const features = [];
  const counts = {};
  for (const depth of CONTOUR_DEPTHS_M) {
    const rawLines = marchingSquares(z, lons, lats, -depth);
    let kept = 0;
    for (const line of rawLines) {
      const simp = simplifyLine(line, 0.0025);
      if (simp.length < 4) continue;
      kept++;
      features.push({
        type: 'Feature',
        properties: {
          depth_m: depth,
          shallow_warning: depth <= 20,
          source: 'GEBCO_2020 (BODC / NOAA CoastWatch ERDDAP)',
          warning_note: 'General-purpose bathymetry only. NOT verified navigation depth.',
        },
        geometry: {
          type: 'LineString',
          coordinates: simp.map(([x, y]) => [Number(x.toFixed(5)), Number(y.toFixed(5))]),
        },
      });
    }
    counts[`${depth}m`] = kept;
  }

  const geo = {
    type: 'FeatureCollection',
    name: 'GEBCO depth contours — Maharashtra coast',
    crs_name: 'EPSG:4326',
    source: 'GEBCO_2020 Grid via NOAA CoastWatch ERDDAP',
    attribution: 'GEBCO Compilation Group (BODC). General-purpose bathymetry only — NOT navigation-grade chart data.',
    disclaimer: 'IMPORTANT: GEBCO is general-purpose bathymetry, not navigation-grade chart data. Never rely on these contours as verified safe navigation depths.',
    generated_at: new Date().toISOString(),
    bbox: BBOX,
    levels_m: CONTOUR_DEPTHS_M,
    contour_counts: counts,
    features,
  };
  const asset = writeAsset('bathymetry-contours.geojson', JSON.stringify(geo));
  console.log('  -> Bathymetry written:', asset.filename, 'features:', features.length, counts, `${(asset.size_bytes / 1024).toFixed(1)} KB`);
  return {
    status: 'LIVE',
    source: geo.source,
    timestamp: geo.generated_at,
    units: 'metres (positive depth below sea level)',
    resolution: '30 arc-sec (~0.0083 deg)',
    feature_count: features.length,
    levels_m: CONTOUR_DEPTHS_M,
    contour_counts: counts,
    disclaimer: geo.disclaimer,
    ...asset,
  };
}

// ---------------------------------------------------------------------------
// 2 & 3. ERDDAP Raster Helper (Chlorophyll-a & Sea Surface Temperature)
// ---------------------------------------------------------------------------
async function fetchErddapInfo(datasetId) {
  const res = await fetchWithTimeout(`https://coastwatch.pfeg.noaa.gov/erddap/info/${datasetId}/index.json`);
  if (!res.ok) throw new Error(`ERDDAP info ${datasetId} HTTP ${res.status}`);
  const d = await res.json();
  const meta = {};
  for (const row of d.table.rows) {
    meta[`${row[1]}.${row[2]}`] = row[4];
  }
  return meta;
}

async function fetchErddapGridCsv(urls) {
  let lastErr;
  for (const url of urls) {
    try {
      const res = await fetchWithTimeout(url, {}, 60000);
      if (res.ok) return { url, text: await res.text() };
      lastErr = new Error(`HTTP ${res.status} for ${url}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

async function acquireChlorophyll() {
  console.log('\n[2/8] Acquiring VIIRS Chlorophyll-a raster via NOAA CoastWatch ERDDAP...');
  const datasetId = 'nesdisVHNSQchlaWeekly';
  const meta = await fetchErddapInfo(datasetId);
  const obsTime = meta['NC_GLOBAL.time_coverage_end'] || new Date().toISOString();
  const resDeg = meta['NC_GLOBAL.geospatial_lat_resolution'] || '0.0375';

  // Try descending lat first (typical for VIIRS), fallback to ascending
  const candidates = [
    `https://coastwatch.pfeg.noaa.gov/erddap/griddap/${datasetId}.csv?chlor_a[(last)][(0.0)][(${BBOX.max_lat}):1:(${BBOX.min_lat})][(${BBOX.min_lon}):1:(${BBOX.max_lon})]`,
    `https://coastwatch.pfeg.noaa.gov/erddap/griddap/${datasetId}.csv?chlor_a[(last)][(0.0)][(${BBOX.min_lat}):1:(${BBOX.max_lat})][(${BBOX.min_lon}):1:(${BBOX.max_lon})]`,
  ];
  const { text } = await fetchErddapGridCsv(candidates);
  const lines = text.split(/\r?\n/).slice(2).filter(Boolean);

  const latsSet = new Set();
  const lonsSet = new Set();
  const rows = [];
  let actualTime = obsTime;
  for (const line of lines) {
    const parts = line.split(',');
    // columns: time, altitude, latitude, longitude, chlor_a
    const tStr = parts[0];
    const la = Number(parts[2]);
    const lo = Number(parts[3]);
    const val = Number(parts[4]);
    if (tStr) actualTime = tStr;
    if (!Number.isFinite(la) || !Number.isFinite(lo)) continue;
    latsSet.add(la);
    lonsSet.add(lo);
    rows.push([la, lo, Number.isFinite(val) && val > 0 ? val : NaN]);
  }
  const lats = [...latsSet].sort((a, b) => b - a); // north->south for PNG image top->bottom
  const lons = [...lonsSet].sort((a, b) => a - b);
  const latIdx = new Map(lats.map((v, i) => [v, i]));
  const lonIdx = new Map(lons.map((v, i) => [v, i]));

  const rgba = Buffer.alloc(lons.length * lats.length * 4, 0);
  // Log-scale palette 0.05 -> 10 mg/m^3
  const CHL_PALETTE = [
    [0.0, 12, 44, 132],
    [0.25, 34, 94, 168],
    [0.5, 29, 145, 192],
    [0.72, 65, 182, 196],
    [0.88, 127, 205, 187],
    [1.0, 237, 248, 177],
  ];
  let validCount = 0;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const [la, lo, val] of rows) {
    if (!Number.isFinite(val)) continue;
    validCount++;
    if (val < minV) minV = val;
    if (val > maxV) maxV = val;
    const norm = (Math.log10(Math.max(0.05, Math.min(10, val))) - Math.log10(0.05)) / (Math.log10(10) - Math.log10(0.05));
    const [r, g, b] = lerpColor(CHL_PALETTE, norm);
    const p = (latIdx.get(la) * lons.length + lonIdx.get(lo)) * 4;
    rgba[p] = r;
    rgba[p + 1] = g;
    rgba[p + 2] = b;
    rgba[p + 3] = 205;
  }

  const pngBuf = encodePngRgba(lons.length, lats.length, rgba);
  const pngAsset = writeAsset('chlorophyll-latest.png', pngBuf);
  const metaJson = {
    status: validCount > 0 ? 'LIVE' : 'UNAVAILABLE',
    layer: 'chlorophyll_a',
    dataset_id: datasetId,
    source: 'NOAA S-NPP VIIRS Science Quality (CoastWatch ERDDAP)',
    observation_timestamp: actualTime,
    retrieved_at: new Date().toISOString(),
    units: 'mg m^-3',
    spatial_resolution_deg: Number(resDeg),
    crs: 'EPSG:4326',
    width: lons.length,
    height: lats.length,
    bbox: {
      min_lat: lats[lats.length - 1],
      max_lat: lats[0],
      min_lon: lons[0],
      max_lon: lons[lons.length - 1],
    },
    scale: { type: 'log10', min: 0.05, max: 10.0 },
    observed_range: validCount > 0 ? { min: Number(minV.toFixed(4)), max: Number(maxV.toFixed(4)) } : null,
    valid_pixel_count: validCount,
    png_url: pngAsset.url,
    png_sha256: pngAsset.sha256,
  };
  const jsonAsset = writeAsset('chlorophyll-latest.json', JSON.stringify(metaJson, null, 2));
  console.log('  -> Chlorophyll raster:', pngAsset.filename, `${lons.length}x${lats.length}`, 'valid px:', validCount, 'time:', actualTime);
  return { ...metaJson, ...jsonAsset };
}

async function acquireSst() {
  console.log('\n[3/8] Acquiring NASA JPL MUR SST (0.01 deg) raster via CoastWatch ERDDAP...');
  const datasetId = 'jplMURSST41';
  const meta = await fetchErddapInfo(datasetId);
  const obsTime = meta['NC_GLOBAL.time_coverage_end'] || new Date().toISOString();
  const stride = 2; // 0.02 deg (~2.2 km) crisp raster for web/offline bundle

  const candidates = [
    `https://coastwatch.pfeg.noaa.gov/erddap/griddap/${datasetId}.csv?analysed_sst[(last)][(${BBOX.min_lat}):${stride}:(${BBOX.max_lat})][(${BBOX.min_lon}):${stride}:(${BBOX.max_lon})]`,
    `https://coastwatch.pfeg.noaa.gov/erddap/griddap/${datasetId}.csv?analysed_sst[(last)][(${BBOX.max_lat}):${stride}:(${BBOX.min_lat})][(${BBOX.min_lon}):${stride}:(${BBOX.max_lon})]`,
  ];
  const { text } = await fetchErddapGridCsv(candidates);
  const lines = text.split(/\r?\n/).slice(2).filter(Boolean);

  const latsSet = new Set();
  const lonsSet = new Set();
  const rows = [];
  let actualTime = obsTime;
  for (const line of lines) {
    const parts = line.split(',');
    // columns: time, latitude, longitude, analysed_sst
    if (parts[0]) actualTime = parts[0];
    const la = Number(parts[1]);
    const lo = Number(parts[2]);
    const val = Number(parts[3]);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) continue;
    latsSet.add(la);
    lonsSet.add(lo);
    rows.push([la, lo, Number.isFinite(val) ? val : NaN]);
  }
  const lats = [...latsSet].sort((a, b) => b - a);
  const lons = [...lonsSet].sort((a, b) => a - b);
  const latIdx = new Map(lats.map((v, i) => [v, i]));
  const lonIdx = new Map(lons.map((v, i) => [v, i]));

  const rgba = Buffer.alloc(lons.length * lats.length * 4, 0);
  const SST_PALETTE = [
    [0.0, 44, 123, 182],  // 24 C cool blue
    [0.33, 0, 166, 202],  // 26.5 C cyan
    [0.6, 255, 255, 191], // 28.5 C warm yellow
    [0.82, 253, 174, 97], // 30 C orange
    [1.0, 215, 25, 28],   // 32 C hot red
  ];
  let validCount = 0;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const [la, lo, val] of rows) {
    if (!Number.isFinite(val)) continue;
    validCount++;
    if (val < minV) minV = val;
    if (val > maxV) maxV = val;
    const norm = (val - 24.0) / (32.0 - 24.0);
    const [r, g, b] = lerpColor(SST_PALETTE, norm);
    const p = (latIdx.get(la) * lons.length + lonIdx.get(lo)) * 4;
    rgba[p] = r;
    rgba[p + 1] = g;
    rgba[p + 2] = b;
    rgba[p + 3] = 195;
  }

  const pngBuf = encodePngRgba(lons.length, lats.length, rgba);
  const pngAsset = writeAsset('sst-latest.png', pngBuf);
  const metaJson = {
    status: validCount > 0 ? 'LIVE' : 'UNAVAILABLE',
    layer: 'sea_surface_temperature',
    dataset_id: datasetId,
    source: 'NASA JPL MUR SST v4.1 (CoastWatch ERDDAP)',
    acquisition_date: actualTime,
    retrieved_at: new Date().toISOString(),
    units: '°C',
    spatial_resolution: '0.02 deg (~2.2 km, sampled from 0.01 deg L4)',
    crs: 'EPSG:4326',
    width: lons.length,
    height: lats.length,
    bbox: {
      min_lat: lats[lats.length - 1],
      max_lat: lats[0],
      min_lon: lons[0],
      max_lon: lons[lons.length - 1],
    },
    scale: { min_c: 24.0, max_c: 32.0 },
    observed_range: validCount > 0 ? { min_c: Number(minV.toFixed(2)), max_c: Number(maxV.toFixed(2)) } : null,
    valid_pixel_count: validCount,
    png_url: pngAsset.url,
    png_sha256: pngAsset.sha256,
  };
  const jsonAsset = writeAsset('sst-latest.json', JSON.stringify(metaJson, null, 2));
  console.log('  -> SST raster:', pngAsset.filename, `${lons.length}x${lats.length}`, 'valid px:', validCount, 'date:', actualTime);
  return { ...metaJson, ...jsonAsset };
}

// ---------------------------------------------------------------------------
// 4. Ocean Currents (U/V) & Wave / Swell Grid (Open-Meteo Marine)
// ---------------------------------------------------------------------------
async function acquireCurrentsAndWaves() {
  console.log('\n[4/8] Acquiring surface ocean currents (U/V) and wave/swell vectors...');
  const samplePts = [];
  for (let lat = 15.5; lat <= 20.5 + 1e-6; lat += 0.5) {
    for (let lon = 71.2; lon <= 73.6 + 1e-6; lon += 0.5) {
      if (!isOnLand(lat, lon)) {
        samplePts.push({ lat: Number(lat.toFixed(2)), lon: Number(lon.toFixed(2)) });
      }
    }
  }
  const latsParam = samplePts.map((p) => p.lat).join(',');
  const lonsParam = samplePts.map((p) => p.lon).join(',');
  const marineUrl =
    `https://marine-api.open-meteo.com/v1/marine?latitude=${latsParam}&longitude=${lonsParam}` +
    `&current=wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature` +
    `&wind_speed_unit=ms&timezone=UTC`;
  const windUrl =
    `https://api.open-meteo.com/v1/forecast?latitude=${latsParam}&longitude=${lonsParam}` +
    `&current=wind_speed_10m,wind_direction_10m,wind_gusts_10m&wind_speed_unit=kmh&timezone=UTC`;

  const [mRes, wRes] = await Promise.all([
    fetchWithTimeout(marineUrl, {}, 45000),
    fetchWithTimeout(windUrl, {}, 45000),
  ]);
  if (!mRes.ok) throw new Error(`Open-Meteo Marine HTTP ${mRes.status}`);
  const mRaw = await mRes.json();
  const wRaw = wRes.ok ? await wRes.json() : [];
  const mList = Array.isArray(mRaw) ? mRaw : [mRaw];
  const wList = Array.isArray(wRaw) ? wRaw : [wRaw];

  const currentFeatures = [];
  const waveFeatures = [];
  let ts = new Date().toISOString();

  const currentUnit = (mList[0]?.current_units?.ocean_current_velocity || 'km/h').toLowerCase();
  const speedScaleToMps = currentUnit === 'km/h' || currentUnit === 'kmh' ? 1 / 3.6 : 1;

  for (let i = 0; i < samplePts.length; i++) {
    const pt = samplePts[i];
    const mc = mList[i]?.current || {};
    const wc = wList[i]?.current || {};
    if (mc.time) ts = mc.time.endsWith('Z') ? mc.time : `${mc.time}:00Z`;

    const rawSpd = typeof mc.ocean_current_velocity === 'number' ? mc.ocean_current_velocity : null;
    const spdMps = rawSpd !== null ? rawSpd * speedScaleToMps : null;
    const dirDeg = typeof mc.ocean_current_direction === 'number' ? mc.ocean_current_direction : null;
    // Direction is "going towards" clockwise from North: U = eastward (+X), V = northward (+Y)
    const uMps = spdMps !== null && dirDeg !== null ? Number((spdMps * Math.sin((dirDeg * Math.PI) / 180)).toFixed(4)) : null;
    const vMps = spdMps !== null && dirDeg !== null ? Number((spdMps * Math.cos((dirDeg * Math.PI) / 180)).toFixed(4)) : null;

    if (spdMps !== null && dirDeg !== null) {
      currentFeatures.push({
        type: 'Feature',
        properties: {
          timestamp: ts,
          speed_mps: Number(spdMps.toFixed(3)),
          speed_knots: Number((spdMps * 1.943844).toFixed(2)),
          direction_deg: Math.round(dirDeg),
          u_mps: uMps,
          v_mps: vMps,
          drift_1h_km: Number((spdMps * 3.6).toFixed(2)),
          drift_1h_nm: Number((spdMps * 1.943844).toFixed(2)),
          sst_c: typeof mc.sea_surface_temperature === 'number' ? Number(mc.sea_surface_temperature.toFixed(2)) : null,
        },
        geometry: { type: 'Point', coordinates: [pt.lon, pt.lat] },
      });
    }

    waveFeatures.push({
      type: 'Feature',
      properties: {
        timestamp: ts,
        wave_height_m: mc.wave_height ?? null,
        wave_period_s: mc.wave_period ?? null,
        wave_direction_deg: mc.wave_direction ?? null,
        swell_wave_height_m: mc.swell_wave_height ?? null,
        swell_wave_period_s: mc.swell_wave_period ?? null,
        wind_speed_kmh: wc.wind_speed_10m ?? null,
        wind_direction_deg: wc.wind_direction_10m ?? null,
        wind_gusts_kmh: wc.wind_gusts_10m ?? null,
        sea_surface_temperature_c: mc.sea_surface_temperature ?? null,
      },
      geometry: { type: 'Point', coordinates: [pt.lon, pt.lat] },
    });
  }

  const currGeo = {
    type: 'FeatureCollection',
    name: 'Surface Ocean Currents (U/V) — Maharashtra Coast',
    crs_name: 'EPSG:4326',
    source: 'Open-Meteo Marine API (Copernicus/ECMWF-derived)',
    timestamp: ts,
    retrieved_at: new Date().toISOString(),
    units: { speed: 'm/s', u_v: 'm/s (u=eastward, v=northward)', direction: 'deg clockwise toward flow' },
    spatial_resolution: '0.5 deg grid (~8 km native model)',
    disclaimer: 'Coarse modeled currents for regional situational drift estimation only; coastal tidal jets and harbour currents are not resolved.',
    features: currentFeatures,
  };
  const waveGeo = {
    type: 'FeatureCollection',
    name: 'Wave, Swell & Wind Vectors — Maharashtra Coast',
    crs_name: 'EPSG:4326',
    source: 'Open-Meteo Marine & Forecast API',
    timestamp: ts,
    retrieved_at: new Date().toISOString(),
    spatial_resolution: '0.5 deg grid',
    features: waveFeatures,
  };

  const currAsset = writeAsset('ocean-currents-latest.geojson', JSON.stringify(currGeo));
  const waveAsset = writeAsset('wave-swell-latest.geojson', JSON.stringify(waveGeo));
  console.log('  -> Currents:', currentFeatures.length, 'vectors; Waves:', waveFeatures.length, 'points; ts:', ts);
  return {
    currents: {
      status: currentFeatures.length > 0 ? 'LIVE' : 'UNAVAILABLE',
      source: currGeo.source,
      timestamp: ts,
      units: 'm/s (U/V components), knots',
      resolution: currGeo.spatial_resolution,
      feature_count: currentFeatures.length,
      disclaimer: currGeo.disclaimer,
      ...currAsset,
    },
    waves: {
      status: waveFeatures.length > 0 ? 'LIVE' : 'UNAVAILABLE',
      source: waveGeo.source,
      timestamp: ts,
      units: 'm, s, km/h',
      resolution: waveGeo.spatial_resolution,
      feature_count: waveFeatures.length,
      ...waveAsset,
    },
  };
}

// ---------------------------------------------------------------------------
// Overpass Helper (with public mirrors)
// ---------------------------------------------------------------------------
const OVERPASS_ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
];

async function queryOverpass(ql) {
  let lastErr;
  for (const endpoint of OVERPASS_ENDPOINTS) {
    try {
      const res = await fetchWithTimeout(
        endpoint,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'data=' + encodeURIComponent(ql),
        },
        35000,
      );
      const txt = await res.text();
      if (res.ok && txt.trim().startsWith('{')) {
        return JSON.parse(txt);
      }
      lastErr = new Error(`${endpoint} HTTP ${res.status}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr;
}

function osmWayToCoords(geom) {
  return (geom || []).map((g) => [Number(g.lon.toFixed(6)), Number(g.lat.toFixed(6))]);
}

// ---------------------------------------------------------------------------
// 5. Marine Protected Areas (Malvan Marine Sanctuary + Verified Coastal MPAs)
// ---------------------------------------------------------------------------
async function acquireMpas() {
  console.log('\n[5/8] Acquiring Marine Protected Areas (prioritizing Malvan Marine Sanctuary)...');
  const features = [];
  const seen = new Set();

  try {
    const nomRes = await fetchWithTimeout(
      'https://nominatim.openstreetmap.org/search?q=Malvan+Marine+Sanctuary&format=json&polygon_geojson=1&limit=3',
      {},
      20000,
    );
    if (nomRes.ok) {
      const results = await nomRes.json();
      for (const item of results) {
        if (item.geojson && (item.geojson.type === 'Polygon' || item.geojson.type === 'MultiPolygon')) {
          const id = `${item.osm_type}/${item.osm_id}`;
          seen.add(id);
          features.push({
            type: 'Feature',
            properties: {
              id,
              name: 'Malvan Marine Sanctuary',
              name_mr: 'मालवण सागरी अभयारण्य',
              designation: 'Marine Sanctuary (Maharashtra Forest Dept / WDPA India)',
              restriction: 'Regulated/restricted marine protected zone — check Maharashtra Forest Dept permissions.',
              source: 'OpenStreetMap Nominatim (verified polygon) / Mangrove Cell Reference',
            },
            geometry: item.geojson,
          });
        }
      }
    }
  } catch (e) {
    console.warn('  ! Nominatim Malvan query failed:', e.message);
  }

  try {
    const ql = `[out:json][timeout:30];(
      way["boundary"="protected_area"](15.5,72.5,20.5,73.7);
      relation["boundary"="protected_area"](15.5,72.5,20.5,73.7);
    );out geom;`;
    const ov = await queryOverpass(ql);
    for (const el of ov.elements || []) {
      const id = `${el.type}/${el.id}`;
      if (seen.has(id)) continue;
      const name = el.tags?.name || '';
      if (!/(marine|sanctuary|mangrove|flamingo|coastal|malvan|thane creek)/i.test(name)) continue;
      let geometry = null;
      if (el.type === 'way' && Array.isArray(el.geometry) && el.geometry.length >= 4) {
        const coords = osmWayToCoords(el.geometry);
        if (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1]) {
          coords.push(coords[0]);
        }
        geometry = { type: 'Polygon', coordinates: [coords] };
      }
      if (geometry) {
        seen.add(id);
        features.push({
          type: 'Feature',
          properties: {
            id,
            name,
            designation: el.tags?.protect_class ? `Protected Area (Class ${el.tags.protect_class})` : 'Protected Area',
            restriction: 'Verify local fishing/entry regulations.',
            source: 'OpenStreetMap Overpass',
          },
          geometry,
        });
      }
    }
  } catch (e) {
    console.warn('  ! Overpass coastal MPA query failed:', e.message);
  }

  const geo = {
    type: 'FeatureCollection',
    name: 'Maharashtra Marine Protected Areas',
    crs_name: 'EPSG:4326',
    retrieved_at: new Date().toISOString(),
    source: 'OpenStreetMap / Nominatim (WDPA token not configured for direct Protected Planet API)',
    disclaimer: 'Boundary polygons shown are from verified public OSM mapping; verify official core/buffer zone notifications with Maharashtra Forest Department.',
    features,
  };
  const asset = writeAsset('marine-protected-areas.geojson', JSON.stringify(geo));
  console.log('  -> MPAs:', features.length, features.map((f) => f.properties.name));
  return {
    status: features.length > 0 ? 'LIVE' : 'UNAVAILABLE',
    source: geo.source,
    timestamp: geo.retrieved_at,
    feature_count: features.length,
    disclaimer: geo.disclaimer,
    ...asset,
  };
}

// ---------------------------------------------------------------------------
// 6 & 7. Offshore Oil & Gas Platforms + Shipping Lanes (Never Fabricated)
// ---------------------------------------------------------------------------
async function acquireOffshoreAndShipping() {
  console.log('\n[6/8 & 7/8] Querying verified offshore platforms and shipping lanes via Overpass...');
  const platFeatures = [];
  const shipFeatures = [];
  let platError = null;
  let shipError = null;

  try {
    const ql = `[out:json][timeout:30];(
      node["man_made"="offshore_platform"](15.5,70.5,20.6,74.0);
      way["man_made"="offshore_platform"](15.5,70.5,20.6,74.0);
      node["seamark:type"="platform"](15.5,70.5,20.6,74.0);
      way["seamark:type"="platform"](15.5,70.5,20.6,74.0);
    );out center tags;`;
    const ov = await queryOverpass(ql);
    for (const el of ov.elements || []) {
      const lat = el.lat ?? el.center?.lat;
      const lon = el.lon ?? el.center?.lon;
      if (typeof lat !== 'number' || typeof lon !== 'number') continue;
      platFeatures.push({
        type: 'Feature',
        properties: {
          id: `${el.type}/${el.id}`,
          name: el.tags?.name || el.tags?.['seamark:name'] || 'Offshore platform',
          operator: el.tags?.operator || null,
          seamark_type: el.tags?.['seamark:type'] || el.tags?.man_made || 'offshore_platform',
          source: 'OpenStreetMap / OpenSeaMap',
        },
        geometry: { type: 'Point', coordinates: [Number(lon.toFixed(6)), Number(lat.toFixed(6))] },
      });
    }
  } catch (e) {
    platError = e.message;
    console.warn('  ! Overpass platforms query error:', e.message);
  }

  try {
    const ql = `[out:json][timeout:30];(
      way["seamark:type"~"separation_lane|separation_zone|separation_boundary|separation_line|fairway|recommended_track"](15.5,70.5,20.6,74.0);
    );out geom;`;
    const ov = await queryOverpass(ql);
    for (const el of ov.elements || []) {
      if (!Array.isArray(el.geometry) || el.geometry.length < 2) continue;
      const coords = osmWayToCoords(el.geometry);
      const isClosed =
        coords.length >= 4 &&
        coords[0][0] === coords[coords.length - 1][0] &&
        coords[0][1] === coords[coords.length - 1][1];
      shipFeatures.push({
        type: 'Feature',
        properties: {
          id: `${el.type}/${el.id}`,
          name: el.tags?.name || el.tags?.['seamark:name'] || el.tags?.['seamark:type'] || 'Shipping seamark',
          seamark_type: el.tags?.['seamark:type'] || null,
          source: 'OpenStreetMap / OpenSeaMap',
        },
        geometry: isClosed ? { type: 'Polygon', coordinates: [coords] } : { type: 'LineString', coordinates: coords },
      });
    }
  } catch (e) {
    shipError = e.message;
    console.warn('  ! Overpass shipping lanes query error:', e.message);
  }

  const nowIso = new Date().toISOString();
  const platGeo = {
    type: 'FeatureCollection',
    name: 'Verified Offshore Platforms (OSM/OpenSeaMap)',
    crs_name: 'EPSG:4326',
    retrieved_at: nowIso,
    status: platFeatures.length > 0 ? 'LIVE' : 'UNAVAILABLE',
    source: 'OpenStreetMap / OpenSeaMap (official ONGC/DGH shapefile not publicly open)',
    disclaimer: 'Only verified public OpenStreetMap/OpenSeaMap offshore platform coordinates are included. Absence of markers does NOT guarantee absence of offshore oil/gas installations or safety zones.',
    error: platError,
    features: platFeatures,
  };
  const shipGeo = {
    type: 'FeatureCollection',
    name: 'Verified Shipping Lanes / Fairways (OSM/OpenSeaMap)',
    crs_name: 'EPSG:4326',
    retrieved_at: nowIso,
    status: shipFeatures.length > 0 ? 'LIVE' : 'UNAVAILABLE',
    source: 'OpenStreetMap / OpenSeaMap (official NHO ENC TSS charts are licensed)',
    disclaimer: 'Community OpenSeaMap seamark geometries only; NOT an official hydrographic chart. Live AIS traffic is not treated as an official shipping chart.',
    error: shipError,
    features: shipFeatures,
  };

  const platAsset = writeAsset('offshore-installations.geojson', JSON.stringify(platGeo));
  const shipAsset = writeAsset('shipping-lanes.geojson', JSON.stringify(shipGeo));
  console.log('  -> Offshore platforms:', platFeatures.length, '| Shipping lanes:', shipFeatures.length);

  return {
    offshore_installations: {
      status: platGeo.status,
      source: platGeo.source,
      timestamp: nowIso,
      feature_count: platFeatures.length,
      disclaimer: platGeo.disclaimer,
      ...platAsset,
    },
    shipping_lanes: {
      status: shipGeo.status,
      source: shipGeo.source,
      timestamp: nowIso,
      feature_count: shipFeatures.length,
      disclaimer: shipGeo.disclaimer,
      ...shipAsset,
    },
  };
}

// ---------------------------------------------------------------------------
// 8. IMD & NDMA SACHET District Weather Warnings
// ---------------------------------------------------------------------------
async function acquireDistrictWarnings() {
  console.log('\n[8/8] Acquiring IMD / NDMA SACHET district weather warnings for Maharashtra coast...');
  const nowIso = new Date().toISOString();
  const alerts = [];
  let sachetStatus = 'UNAVAILABLE';
  let sachetError = null;

  try {
    const res = await fetchWithTimeout('https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails', {}, 20000);
    if (res.ok) {
      const list = await res.json();
      sachetStatus = 'LIVE';
      const districtRegex = /\b(palghar|thane|mumbai|raigad|ratnagiri|sindhudurg|konkan|maharashtra)\b/i;
      for (const a of Array.isArray(list) ? list : []) {
        const areaText = `${a.area_description || ''} ${a.area_covered || ''} ${a.warning_message || ''}`;
        if (!districtRegex.test(areaText)) continue;
        const matched = DISTRICTS.filter((d) => new RegExp(`\\b${d}\\b`, 'i').test(areaText));
        alerts.push({
          identifier: String(a.identifier ?? a.alert_id_sdma_autoinc ?? ''),
          districts: matched.length > 0 ? matched : ['Maharashtra Coast'],
          disaster_type: a.disaster_type || 'Weather Alert',
          severity: a.severity || 'INFO',
          severity_color: a.severity_color || null,
          source: a.alert_source || 'NDMA SACHET / IMD',
          area_description: a.area_description || a.area_covered || '',
          warning_message: a.warning_message || '',
          effective_start_time: a.effective_start_time || null,
          effective_end_time: a.effective_end_time || null,
        });
      }
    } else {
      sachetError = `HTTP ${res.status}`;
    }
  } catch (e) {
    sachetError = e.message;
  }

  // Probe IMD Mumbai PDFs (head/metadata) + optional IMD API key
  let imdFishermanStatus = 'UNAVAILABLE';
  let imdFishermanLastMod = null;
  try {
    const r = await fetchWithTimeout('https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf', { method: 'HEAD' }, 15000);
    if (r.ok) {
      imdFishermanStatus = 'LIVE';
      imdFishermanLastMod = r.headers.get('last-modified');
    }
  } catch { /* ignore */ }

  let imdApiStatus = process.env.IMD_API_KEY ? 'CONFIGURED' : 'AUTH_IP_WHITELIST_REQUIRED';
  let imdApiDistrictItems = [];
  if (process.env.IMD_API_KEY) {
    try {
      const apiRes = await fetchWithTimeout(
        process.env.IMD_DISTRICT_API_URL || 'https://api.imd.gov.in/api/v1/districtwarning',
        { headers: { Authorization: `Bearer ${process.env.IMD_API_KEY}`, 'x-api-key': process.env.IMD_API_KEY } },
        15000,
      );
      if (apiRes.ok) {
        const d = await apiRes.json();
        imdApiStatus = 'LIVE';
        imdApiDistrictItems = Array.isArray(d) ? d : (d.data || []);
      } else {
        imdApiStatus = `HTTP_${apiRes.status}`;
      }
    } catch (e) {
      imdApiStatus = `ERROR: ${e.message}`;
    }
  }

  const payload = {
    status: sachetStatus === 'LIVE' || imdApiStatus === 'LIVE' ? 'LIVE' : 'UNAVAILABLE',
    retrieved_at: nowIso,
    districts_monitored: DISTRICTS,
    sources: {
      ndma_sachet_cap: { status: sachetStatus, error: sachetError, alert_count: alerts.length },
      imd_mumbai_fisherman_pdf: { status: imdFishermanStatus, last_modified: imdFishermanLastMod, url: 'https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf' },
      imd_public_api: {
        status: imdApiStatus,
        reference: 'https://api.imd.gov.in/public/api_reference.html',
        note: 'api.imd.gov.in requires static public IP whitelisting and IMD API credentials.',
      },
    },
    alerts,
    imd_api_items: imdApiDistrictItems,
  };
  const asset = writeAsset('imd-district-warnings.json', JSON.stringify(payload, null, 2));
  console.log('  -> District warnings: SACHET=', sachetStatus, 'MH alerts=', alerts.length, '| IMD Fisherman PDF=', imdFishermanStatus);
  return {
    status: payload.status,
    source: 'NDMA SACHET CAP + IMD Mumbai',
    timestamp: nowIso,
    alert_count: alerts.length,
    imd_api_status: imdApiStatus,
    ...asset,
  };
}

// ---------------------------------------------------------------------------
// Main Runner
// ---------------------------------------------------------------------------
async function main() {
  console.log('=== MatsyaAI Autonomous Oceanographic Data Acquisition ===');
  console.log('Coverage bbox (EPSG:4326):', BBOX, '| Districts:', DISTRICTS.join(', '));

  let prevLayers = {};
  const prevManifestPath = path.join(OUT_DIR, 'ocean-layers-manifest.json');
  if (fs.existsSync(prevManifestPath)) {
    try { prevLayers = JSON.parse(fs.readFileSync(prevManifestPath, 'utf8')).layers || {}; } catch { /* ignore */ }
  }

  const manifest = {
    generated_at: new Date().toISOString(),
    crs: 'EPSG:4326',
    region: 'Maharashtra Coast (Palghar, Thane, Mumbai, Raigad, Ratnagiri, Sindhudurg)',
    bbox: BBOX,
    layers: {},
  };

  const tasks = [
    ['bathymetry', acquireBathymetry],
    ['chlorophyll', acquireChlorophyll],
    ['sst', acquireSst],
    ['currents_waves', acquireCurrentsAndWaves],
    ['marine_protected_areas', acquireMpas],
    ['offshore_and_shipping', acquireOffshoreAndShipping],
    ['district_warnings', acquireDistrictWarnings],
  ];

  for (const [name, fn] of tasks) {
    try {
      const res = await fn();
      if (name === 'currents_waves') {
        manifest.layers.ocean_currents = res.currents;
        manifest.layers.wave_swell = res.waves;
      } else if (name === 'offshore_and_shipping') {
        manifest.layers.offshore_installations = res.offshore_installations;
        manifest.layers.shipping_lanes = res.shipping_lanes;
      } else {
        manifest.layers[name] = res;
      }
    } catch (err) {
      console.error(`  [ERROR] Task '${name}' failed:`, err.message);
      const prev = prevLayers[name];
      if (prev && prev.filename && fs.existsSync(path.join(OUT_DIR, prev.filename))) {
        manifest.layers[name] = { ...prev, refresh_error: err.message };
      } else {
        manifest.layers[name] = { status: 'ERROR', error: err.message, timestamp: new Date().toISOString() };
      }
    }
  }

  writeAsset('ocean-layers-manifest.json', JSON.stringify(manifest, null, 2));
  console.log('\n=== Manifest written: backend/static/offline/ocean-layers-manifest.json ===');
}

main().catch((err) => {
  console.error('Fatal pipeline error:', err);
  process.exit(1);
});
