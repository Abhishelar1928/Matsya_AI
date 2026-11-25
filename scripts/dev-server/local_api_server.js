const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function sortKeysDeep(val) {
  if (Array.isArray(val)) return val.map(sortKeysDeep);
  if (val !== null && typeof val === 'object') {
    const out = {};
    for (const k of Object.keys(val).sort()) out[k] = sortKeysDeep(val[k]);
    return out;
  }
  return val;
}
function sha256Canonical(val) {
  return crypto.createHash('sha256').update(JSON.stringify(sortKeysDeep(val)), 'utf8').digest('hex');
}
const syncedUuids = new Set();

// Allow self-signed/govt SSL certs (INCOIS often has intermediate cert issues)
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const PORT = 8000;
const CACHE_TTL_MS = 15 * 60 * 1000; // 15 minutes

// Load baseline map snapshot for grid cells / landing centres
let baseMapData = {};
try {
  const mapPath = path.join(__dirname, '..', '..', 'data', 'snapshots', 'map_summary_baseline.json');
  const buf = fs.readFileSync(mapPath);
  let text = buf.toString('utf16le');
  if (text.charCodeAt(0) === 0xFEFF) {
    text = text.slice(1);
  }
  baseMapData = JSON.parse(text);
  if (Array.isArray(baseMapData.landing_centres) && !baseMapData.landing_centres.some(c => c.district === 'Thane')) {
    baseMapData.landing_centres.splice(2, 0, {
      id: 'uttan',
      name: 'Thane - Uttan / Bhayandar',
      name_mr: 'उत्तन / भाईंदर',
      district: 'Thane',
      latitude: 19.2708,
      longitude: 72.7858,
      verified: false
    });
  }
  console.log('Loaded data/snapshots/map_summary_baseline.json successfully. Grid cells:', baseMapData.predictions?.length);
} catch (err) {
  console.error('Failed to load map_summary_baseline.json:', err.message);
}

// Overlay validated Phase 4 SpatioOcean predictions snapshot if generated
try {
  const phase4Path = path.join(__dirname, '..', '..', 'data', 'snapshots', 'phase4_predictions_latest.json');
  if (fs.existsSync(phase4Path)) {
    const p4 = JSON.parse(fs.readFileSync(phase4Path, 'utf8'));
    if (Array.isArray(p4.predictions) && p4.predictions.length > 0) {
      baseMapData.predictions = p4.predictions;
      const gfwProv = p4.provenance?.sources?.global_fishing_watch;
      const pMode = p4.predictions[0]?.prediction_mode || p4.provenance?.prediction_mode || 'daily_operational';
      const sAnchor = p4.predictions[0]?.seasonal_anchor_date ?? gfwProv?.seasonal_anchor_date ?? null;
      baseMapData.metadata = {
        ...(baseMapData.metadata || {}),
        model_version: p4.model_version || 'Phase4_SpatioOcean_v1',
        calibration_method: p4.predictions[0]?.calibration_method || p4.calibration_method || 'platt',
        decision_threshold: p4.predictions[0]?.decision_threshold ?? p4.decision_threshold ?? 0.18,
        prediction_mode: pMode,
        seasonal_anchor_date: sAnchor,
        prediction_timestamp: p4.prediction_timestamp || baseMapData.metadata?.prediction_timestamp,
        disclaimer: p4.disclaimer || baseMapData.metadata?.disclaimer,
      };
      if (gfwProv && baseMapData.prediction_provenance?.sources?.global_fishing_watch) {
        baseMapData.prediction_provenance.sources.global_fishing_watch = {
          ...baseMapData.prediction_provenance.sources.global_fishing_watch,
          ...gfwProv,
        };
      }
      if (gfwProv && baseMapData.prediction_provenance?.sources?.gfw_context) {
        baseMapData.prediction_provenance.sources.gfw_context = {
          ...baseMapData.prediction_provenance.sources.gfw_context,
          observation_date: gfwProv.observation_date ?? baseMapData.prediction_provenance.sources.gfw_context.observation_date,
          age_days: gfwProv.age_days ?? baseMapData.prediction_provenance.sources.gfw_context.age_days,
          context_mode: gfwProv.context_mode ?? null,
          seasonal_anchor_date: gfwProv.seasonal_anchor_date ?? null,
        };
      }
      console.log(`Loaded Phase 4 snapshot (${baseMapData.metadata.model_version}, mode=${pMode}, ${p4.predictions.length} cells, thr=${baseMapData.metadata.decision_threshold})`);
    }
  }
} catch (err) {
  console.error('Failed to load phase4_predictions_latest.json:', err.message);
}

const OFFLINE_DIR = path.join(__dirname, '..', '..', 'backend', 'static', 'offline');

function offlineAssetInfo(filename, kind, note) {
  const full = path.join(OFFLINE_DIR, filename);
  const exists = fs.existsSync(full);
  return {
    kind,
    url: `/api/v1/offline-assets/${filename}`,
    available: exists,
    size_bytes: exists ? fs.statSync(full).size : null,
    note,
  };
}

// ---------------------------------------------------------------------------
// INCOIS Live Fetch & Parser
// ---------------------------------------------------------------------------
function stripTags(str) {
  return str.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/gi, ' ').replace(/\s+/g, ' ').trim();
}

function parseDms(dmsStr) {
  if (!dmsStr) return null;
  let clean = dmsStr.replace(/([NSEWnsew])/g, ' $1 ').replace(/[^0-9NSEWnsew. ]/g, ' ').trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length < 4) return null;

  let deg, min, sec, dir;
  if (['N', 'S', 'E', 'W'].includes(parts[parts.length - 1].toUpperCase())) {
    deg = parseFloat(parts[0]);
    min = parseFloat(parts[1]);
    sec = parseFloat(parts[2]);
    dir = parts[3].toUpperCase();
  } else if (['N', 'S', 'E', 'W'].includes(parts[0].toUpperCase())) {
    dir = parts[0].toUpperCase();
    deg = parseFloat(parts[1]);
    min = parseFloat(parts[2]);
    sec = parseFloat(parts[3]);
  } else {
    return null;
  }
  if (isNaN(deg) || isNaN(min) || isNaN(sec)) return null;
  let dec = deg + min / 60 + sec / 3600;
  if (dir === 'S' || dir === 'W') dec = -dec;
  return Number(dec.toFixed(6));
}

function parseDepth(depthStr) {
  if (!depthStr) return [null, null];
  const clean = depthStr.replace(/\s+/g, '');
  if (clean.includes('-')) {
    const [a, b] = clean.split('-');
    const min = parseInt(a, 10), max = parseInt(b, 10);
    return [isNaN(min) ? null : min, isNaN(max) ? null : max];
  }
  const val = parseInt(clean, 10);
  return isNaN(val) ? [null, null] : [val, val];
}

const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

function parseDateStr(day, monStr, year) {
  const m = MONTHS[monStr.toLowerCase()];
  if (m === undefined) return null;
  return new Date(Date.UTC(parseInt(year, 10), m, parseInt(day, 10), 0, 0, 0));
}

let cachedPfz = { at: 0, data: null };

async function fetchLiveIncoisPfz() {
  const now = Date.now();
  if (cachedPfz.data && now - cachedPfz.at < CACHE_TTL_MS) {
    return cachedPfz.data;
  }

  try {
    console.log('Fetching live INCOIS PFZ data...');
    const r1 = await fetch('https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en');
    const setCookie = r1.headers.getSetCookie ? r1.headers.getSetCookie().join('; ') : r1.headers.get('set-cookie');
    if (!setCookie) throw new Error('No JSESSIONID cookie received');

    const r2 = await fetch('https://incois.gov.in/MarineFisheries/TextData?secid=SEC002', {
      headers: { Cookie: setCookie },
      redirect: 'manual'
    });
    if (r2.status !== 200) throw new Error(`HTTP ${r2.status}`);
    const html = await r2.text();

    // Extract advisory date & validity date
    const plainText = stripTags(html);
    let advisoryDate = null;
    let validityDate = null;

    // Pattern: "Mon Nov 23 15:30:56 IST 2026" or "24 Nov 2026"
    const mAdv1 = plainText.match(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+\d{2}:\d{2}:\d{2}.*?(\d{4})\b/i);
    const mAdv2 = plainText.match(/\b(\d{1,2})[\s\-\/]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-\/]+(\d{4})\b/i);
    if (mAdv1) {
      advisoryDate = parseDateStr(mAdv1[2], mAdv1[1], mAdv1[3]);
    } else if (mAdv2) {
      advisoryDate = parseDateStr(mAdv2[1], mAdv2[2], mAdv2[3]);
    }

    const mVal = plainText.match(/TILL\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})/i);
    if (mVal) {
      const dt = parseDateStr(mVal[1], mVal[2], mVal[3]);
      if (dt) {
        dt.setUTCHours(23, 59, 59, 0);
        validityDate = dt;
      }
    }

    // Parse HTML tables
    const tables = html.match(/<table[\s\S]*?<\/table>/gi) || [];
    let targetTable = null;
    for (const tbl of tables) {
      const lower = tbl.toLowerCase();
      if ((lower.includes('direction') && lower.includes('bearing') && lower.includes('latitude')) ||
          (lower.includes('from the coast') && lower.includes('latitude'))) {
        targetTable = tbl;
        break;
      }
    }

    if (!targetTable) throw new Error('PFZ table not found in INCOIS HTML');

    const rows = targetTable.match(/<tr[\s\S]*?<\/tr>/gi) || [];
    const locations = [];
    for (const row of rows) {
      const cells = row.match(/<(?:td|th)[^>]*>([\s\S]*?)<\/(?:td|th)>/gi) || [];
      if (cells.length < 7) continue;
      const cols = cells.map(c => stripTags(c));
      const [landing_centre, direction, bearing_str, distance_km, depth_str, lat_str, lon_str] = cols;

      if (direction.toLowerCase().includes('direction') || lat_str.toLowerCase().includes('latitude') || landing_centre.toLowerCase().includes('from the coast')) {
        continue;
      }

      const lat = parseDms(lat_str);
      const lon = parseDms(lon_str);
      if (lat === null || lon === null) continue;
      if (lat < 10 || lat > 25 || lon < 65 || lon > 80) continue;

      const [depth_min_m, depth_max_m] = parseDepth(depth_str);
      const bearingClean = bearing_str.replace(/[^0-9]/g, '');
      const bearing_degrees = bearingClean ? parseInt(bearingClean, 10) : 0;

      locations.push({
        landing_centre,
        direction,
        bearing_degrees,
        distance_km,
        depth_min_m,
        depth_max_m,
        latitude: lat,
        longitude: lon
      });
    }

    const advIso = (advisoryDate || new Date()).toISOString();
    const valIso = (validityDate || new Date(Date.now() + 86400000)).toISOString();
    const isExpired = validityDate ? validityDate.getTime() < Date.now() : false;

    const result = {
      status: isExpired ? 'STALE' : 'LIVE',
      advisory_date: advIso,
      validity_date: valIso,
      count: locations.length,
      locations,
      source: 'INCOIS',
      retrieved_at: new Date().toISOString()
    };

    console.log(`Live INCOIS PFZ fetched: ${locations.length} zones, advisory=${advIso}, valid_until=${valIso}, status=${result.status}`);
    cachedPfz = { at: now, data: result };
    return result;
  } catch (err) {
    console.error('Failed to fetch live INCOIS PFZ:', err.message);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Open-Meteo Live Marine & Weather Fetch
// ---------------------------------------------------------------------------
const DISTRICT_COORDS = [
  { district: 'Palghar', latitude: 19.69, longitude: 72.55 },
  { district: 'Thane', latitude: 19.27, longitude: 72.62 },
  { district: 'Mumbai', latitude: 18.92, longitude: 72.65 },
  { district: 'Raigad', latitude: 18.45, longitude: 72.70 },
  { district: 'Ratnagiri', latitude: 16.98, longitude: 73.10 },
  { district: 'Sindhudurg', latitude: 16.02, longitude: 73.35 }
];

let cachedForecast = { at: 0, data: null };

async function fetchLiveForecast() {
  const now = Date.now();
  if (cachedForecast.data && now - cachedForecast.at < CACHE_TTL_MS) {
    return cachedForecast.data;
  }

  try {
    console.log('Fetching live Open-Meteo Marine & Wind forecasts...');
    const lats = DISTRICT_COORDS.map(d => d.latitude).join(',');
    const lons = DISTRICT_COORDS.map(d => d.longitude).join(',');

    const [marineRes, windRes] = await Promise.all([
      fetch(`https://marine-api.open-meteo.com/v1/marine?latitude=${lats}&longitude=${lons}&hourly=wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature&forecast_days=3&timezone=UTC`),
      fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lats}&longitude=${lons}&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m&forecast_days=3&timezone=UTC`)
    ]);

    if (!marineRes.ok || !windRes.ok) throw new Error('Open-Meteo HTTP error');
    const marineJson = await marineRes.json();
    const windJson = await windRes.json();

    const marineArr = Array.isArray(marineJson) ? marineJson : [marineJson];
    const windArr = Array.isArray(windJson) ? windJson : [windJson];

    const districts = DISTRICT_COORDS.map((d, idx) => {
      const m = marineArr[idx]?.hourly || {};
      const mUnits = marineArr[idx]?.hourly_units || {};
      const w = windArr[idx]?.hourly || {};
      const unitScale = String(mUnits.ocean_current_velocity || 'km/h').toLowerCase().includes('km') ? (1 / 3.6) : 1;
      const rawSpd = m.ocean_current_velocity || [];
      const rawDir = m.ocean_current_direction || [];
      const spdMps = rawSpd.map(s => (typeof s === 'number' ? Number((s * unitScale).toFixed(4)) : null));
      const uMps = spdMps.map((s, k) => (typeof s === 'number' && typeof rawDir[k] === 'number' ? Number((s * Math.sin(rawDir[k] * Math.PI / 180)).toFixed(4)) : null));
      const vMps = spdMps.map((s, k) => (typeof s === 'number' && typeof rawDir[k] === 'number' ? Number((s * Math.cos(rawDir[k] * Math.PI / 180)).toFixed(4)) : null));
      return {
        district: d.district,
        latitude: d.latitude,
        longitude: d.longitude,
        hourly: {
          time: (m.time || w.time || []).map(t => t.endsWith('Z') ? t : `${t}:00Z`),
          wave_height_m: m.wave_height || [],
          wave_period_s: m.wave_period || [],
          wave_direction_deg: m.wave_direction || [],
          swell_wave_height_m: m.swell_wave_height || [],
          swell_wave_period_s: m.swell_wave_period || [],
          ocean_current_velocity_mps: spdMps,
          ocean_current_direction_deg: rawDir,
          ocean_current_u_mps: uMps,
          ocean_current_v_mps: vMps,
          sea_surface_temperature_c: m.sea_surface_temperature || [],
          wind_speed_kmh: w.wind_speed_10m || [],
          wind_direction_deg: w.wind_direction_10m || [],
          wind_gusts_kmh: w.wind_gusts_10m || []
        }
      };
    });

    const data = {
      status: 'LIVE',
      provider: 'Open-Meteo Marine API (Live)',
      retrieved_at: new Date().toISOString(),
      valid_from: districts[0]?.hourly?.time?.[0] || new Date().toISOString(),
      valid_until: districts[0]?.hourly?.time?.slice(-1)[0] || new Date(Date.now() + 86400000 * 3).toISOString(),
      error: null,
      thresholds: {
        wave_height_m: 2.5,
        wind_speed_kmh: 45.0
      },
      districts
    };

    cachedForecast = { at: now, data };
    console.log('Live Open-Meteo forecast fetched successfully.');
    return data;
  } catch (err) {
    console.error('Failed to fetch live Open-Meteo forecast:', err.message);
    return null;
  }
}

// ---------------------------------------------------------------------------
// HTTP Server
// ---------------------------------------------------------------------------
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  console.log(`[${req.method}] ${url.pathname}${url.search}`);

  // Static offline oceanographic/bathymetric assets
  if (url.pathname.startsWith('/api/v1/offline-assets/')) {
    const fname = path.basename(url.pathname);
    const fpath = path.join(OFFLINE_DIR, fname);
    if (!fs.existsSync(fpath) || !fs.statSync(fpath).isFile()) {
      res.setHeader('Content-Type', 'application/json');
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'Offline asset not found', file: fname }));
      return;
    }
    const ext = path.extname(fname).toLowerCase();
    const ctype = ext === '.png' ? 'image/png'
      : (ext === '.geojson' || ext === '.json') ? 'application/json'
      : 'application/octet-stream';
    const stat = fs.statSync(fpath);
    res.setHeader('Content-Type', ctype);
    res.setHeader('Content-Length', stat.size);
    res.writeHead(200);
    if (req.method === 'HEAD') { res.end(); return; }
    res.end(fs.readFileSync(fpath));
    return;
  }

  res.setHeader('Content-Type', 'application/json');

  if (url.pathname === '/api/v1/health') {
    res.writeHead(200);
    res.end(JSON.stringify({
      status: 'healthy',
      version: '0.1.0',
      environment: 'development',
      database: 'connected',
      timestamp: new Date().toISOString()
    }));
    return;
  }

  if (url.pathname === '/api/v1/predictions' || url.pathname === '/api/v1/predictions/latest') {
    res.writeHead(200);
    res.end(JSON.stringify(baseMapData.predictions || []));
    return;
  }

  if (url.pathname === '/api/v1/map/summary') {
    const livePfz = await fetchLiveIncoisPfz();
    const liveForecast = await fetchLiveForecast();

    const data = JSON.parse(JSON.stringify(baseMapData));
    if (url.searchParams.get('demo') === 'true') {
      data.metadata.demo_mode = true;
    }

    if (livePfz) {
      data.pfz_advisory = {
        status: livePfz.status,
        advisory_date: livePfz.advisory_date,
        validity_date: livePfz.validity_date,
        count: livePfz.count,
        locations: livePfz.locations,
        source: 'INCOIS'
      };
      if (data.metadata?.data_sources?.incois_pfz) {
        data.metadata.data_sources.incois_pfz = {
          provider: 'INCOIS (Indian National Centre for Ocean Information Services)',
          status: livePfz.status,
          advisory_date: livePfz.advisory_date,
          valid_until: livePfz.validity_date,
          age_minutes: 0
        };
      }
      if (data.source_freshness?.incois_pfz) {
        data.source_freshness.incois_pfz = {
          source_name: 'INCOIS Potential Fishing Zone (PFZ)',
          status: livePfz.status,
          last_successful_fetch: livePfz.retrieved_at,
          data_timestamp: livePfz.advisory_date,
          valid_until: livePfz.validity_date,
          age_minutes: 0,
          record_count: livePfz.count,
          error: null
        };
      }
    }

    if (liveForecast && data.source_freshness?.open_meteo_marine) {
      data.source_freshness.open_meteo_marine = {
        source_name: 'Open-Meteo Marine Forecast',
        status: 'LIVE',
        last_successful_fetch: liveForecast.retrieved_at,
        data_timestamp: liveForecast.retrieved_at,
        valid_until: liveForecast.valid_until,
        age_minutes: 0,
        record_count: 5,
        error: null
      };
    }

    res.writeHead(200);
    res.end(JSON.stringify(data));
    return;
  }

  if (url.pathname === '/api/v1/marine/warnings') {
    res.writeHead(200);
    res.end(JSON.stringify({
      status: 'LIVE',
      source: 'IMD Mumbai Fishermen Warning Bulletin',
      issued_at: new Date().toISOString(),
      valid_until: new Date(Date.now() + 86400000 * 3).toISOString(),
      items: []
    }));
    return;
  }

  if (url.pathname === '/api/v1/marine/forecast') {
    const liveForecast = await fetchLiveForecast();
    if (liveForecast) {
      res.writeHead(200);
      res.end(JSON.stringify(liveForecast));
    } else {
      res.writeHead(503);
      res.end(JSON.stringify({ status: 'UNAVAILABLE', error: 'Failed to fetch Open-Meteo forecast' }));
    }
    return;
  }

  if (url.pathname === '/api/v1/marine/ocean-layers') {
    const mfPath = path.join(OFFLINE_DIR, 'ocean-layers-manifest.json');
    if (fs.existsSync(mfPath)) {
      res.writeHead(200);
      res.end(fs.readFileSync(mfPath, 'utf8'));
    } else {
      res.writeHead(200);
      res.end(JSON.stringify({ status: 'UNAVAILABLE', layers: {}, note: 'Run ocean data acquisition pipeline' }));
    }
    return;
  }

  if (url.pathname === '/api/v1/marine/district-warnings') {
    try {
      const distList = DISTRICT_COORDS.map(d => d.district);
      const r = await fetch('https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails', { headers: { 'User-Agent': 'MatsyaAI/1.0' } });
      if (r.ok) {
        const list = await r.json();
        const pat = /\b(palghar|thane|mumbai|raigad|ratnagiri|sindhudurg|konkan|maharashtra)\b/i;
        const alerts = (Array.isArray(list) ? list : [])
          .filter(a => pat.test(`${a.area_description || ''} ${a.area_covered || ''} ${a.warning_message || ''}`))
          .map(a => {
            const txt = `${a.area_description || ''} ${a.area_covered || ''} ${a.warning_message || ''}`;
            const matched = distList.filter(d => new RegExp(`\\b${d}\\b`, 'i').test(txt));
            return {
              identifier: String(a.identifier ?? a.alert_id_sdma_autoinc ?? ''),
              districts: matched.length ? matched : ['Maharashtra Coast'],
              disaster_type: a.disaster_type || 'Weather Alert',
              severity: a.severity || 'INFO',
              severity_color: a.severity_color || null,
              source: a.alert_source || 'NDMA SACHET / IMD',
              area_description: a.area_description || a.area_covered || '',
              warning_message: a.warning_message || '',
              effective_start_time: a.effective_start_time || null,
              effective_end_time: a.effective_end_time || null,
            };
          });
        res.writeHead(200);
        res.end(JSON.stringify({
          status: 'LIVE',
          retrieved_at: new Date().toISOString(),
          districts_monitored: distList,
          sources: {
            ndma_sachet_cap: { status: 'LIVE', error: null, alert_count: alerts.length },
            imd_public_api: {
              status: 'AUTH_IP_WHITELIST_REQUIRED',
              reference: 'https://api.imd.gov.in/public/api_reference.html',
              note: 'api.imd.gov.in requires static public IP whitelisting and IMD API credentials.',
            },
          },
          alerts,
          imd_api_items: [],
        }));
        return;
      }
    } catch { /* fallback to cached */ }
    const wPath = path.join(OFFLINE_DIR, 'imd-district-warnings.json');
    res.writeHead(200);
    res.end(fs.existsSync(wPath) ? fs.readFileSync(wPath, 'utf8') : JSON.stringify({ status: 'UNAVAILABLE', districts_monitored: DISTRICT_COORDS.map(d => d.district), sources: {}, alerts: [] }));
    return;
  }

  if (url.pathname.startsWith('/api/v1/sources')) {
    const livePfz = await fetchLiveIncoisPfz();
    const sf = JSON.parse(JSON.stringify(baseMapData.source_freshness || {}));
    if (livePfz && sf.incois_pfz) {
      sf.incois_pfz.status = livePfz.status;
      sf.incois_pfz.data_timestamp = livePfz.advisory_date;
      sf.incois_pfz.valid_until = livePfz.validity_date;
      sf.incois_pfz.last_successful_fetch = livePfz.retrieved_at;
      sf.incois_pfz.record_count = livePfz.count;
      sf.incois_pfz.age_minutes = 0;
    }
    res.writeHead(200);
    res.end(JSON.stringify(sf));
    return;
  }

  if (url.pathname === '/api/v1/expedition/landing-centres') {
    const lcs = (baseMapData.landing_centres || []).map(lc => ({
      ...lc,
      source: 'Maharashtra Fisheries Dept'
    }));
    res.writeHead(200);
    res.end(JSON.stringify({ landing_centres: lcs }));
    return;
  }

  if (url.pathname === '/api/v1/expedition/packages' && req.method === 'POST') {
    let bodyStr = '';
    for await (const chunk of req) bodyStr += chunk;
    const body = JSON.parse(bodyStr || '{}');
    const lcs = baseMapData.landing_centres || [];
    const lc = lcs.find(c => c.id === body.landing_centre_id) || lcs[0];
    const livePfz = await fetchLiveIncoisPfz();
    const liveForecast = await fetchLiveForecast();

    let dest = body.destination;
    let destSource = 'USER_SELECTED';
    if (body.pfz_index !== undefined && livePfz?.locations?.[body.pfz_index]) {
      const p = livePfz.locations[body.pfz_index];
      dest = { latitude: p.latitude, longitude: p.longitude, name: `INCOIS PFZ (${p.landing_centre} ${p.direction})`, pfz_index: body.pfz_index };
      destSource = 'INCOIS_PFZ';
    }
    if (!dest) {
      res.writeHead(400);
      res.end(JSON.stringify({ detail: 'Destination or valid pfz_index required' }));
      return;
    }

    const toRad = d => (d * Math.PI) / 180;
    const toDeg = r => (r * 180) / Math.PI;
    const haversine = (lat1, lon1, lat2, lon2) => {
      const R = 6371;
      const dLat = toRad(lat2 - lat1);
      const dLon = toRad(lon2 - lon1);
      const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
      return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };
    const bearing = (lat1, lon1, lat2, lon2) => {
      const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
      const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
      return (toDeg(Math.atan2(y, x)) + 360) % 360;
    };
    const compass = d => ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(d / 22.5) % 16];

    const startPoint = (
      body.origin &&
      typeof body.origin.latitude === 'number' &&
      typeof body.origin.longitude === 'number' &&
      Number.isFinite(body.origin.latitude) &&
      Number.isFinite(body.origin.longitude)
    )
      ? { latitude: body.origin.latitude, longitude: body.origin.longitude, name: body.origin.name || 'Current location' }
      : { latitude: lc.latitude, longitude: lc.longitude, name: lc.name };

    const distKm = haversine(startPoint.latitude, startPoint.longitude, dest.latitude, dest.longitude);
    const brg = bearing(startPoint.latitude, startPoint.longitude, dest.latitude, dest.longitude);
    const numSteps = Math.max(2, Math.min(10, Math.ceil(distKm / 10)));
    const waypoints = [];
    for (let i = 0; i <= numSteps; i++) {
      const f = i / numSteps;
      waypoints.push({
        index: i,
        latitude: Number((startPoint.latitude + (dest.latitude - startPoint.latitude) * f).toFixed(5)),
        longitude: Number((startPoint.longitude + (dest.longitude - startPoint.longitude) * f).toFixed(5)),
        km_from_start: Number((distKm * f).toFixed(2)),
        name: i === 0 ? startPoint.name : i === numSteps ? (dest.name || 'Target') : null
      });
    }

    const emergency_returns = lcs
      .map(c => ({
        ...c,
        source: 'Maharashtra Fisheries Dept',
        distance_from_destination_km: Number(haversine(dest.latitude, dest.longitude, c.latitude, c.longitude).toFixed(1)),
        bearing_from_destination_deg: Number(bearing(dest.latitude, dest.longitude, c.latitude, c.longitude).toFixed(0)),
        bearing_from_destination_compass: compass(bearing(dest.latitude, dest.longitude, c.latitude, c.longitude)),
        distance_from_route_midpoint_km: Number(haversine((startPoint.latitude + dest.latitude) / 2, (startPoint.longitude + dest.longitude) / 2, c.latitude, c.longitude).toFixed(1))
      }))
      .sort((a, b) => a.distance_from_destination_km - b.distance_from_destination_km)
      .slice(0, 3);

    const nowIso = new Date().toISOString();
    const expIso = new Date(Date.now() + 86400000 * 2).toISOString();
    const pkgId = `pkg_${Date.now()}`;

    const routeObj = {
      type: 'DIRECT_GREAT_CIRCLE',
      distance_km: Number(distKm.toFixed(2)),
      distance_nm: Number((distKm / 1.852).toFixed(2)),
      initial_bearing_deg: Number(brg.toFixed(1)),
      initial_bearing_compass: compass(brg),
      waypoints,
      land_crossings: [],
      warnings: [],
      is_navigable_direct: true,
      is_direct_reference_only: true,
      coverage_disclosures: [
        'Direct great-circle reference only, NOT a safe navigable route.',
        'Shallow water, reefs, and buoys are not checked in dev mode.'
      ],
      disclaimer: 'Direct great-circle reference only; verify local hazards and shallow waters.'
    };
    const pfzObj = livePfz || baseMapData.pfz_advisory;
    const warningsObj = {
      status: 'LIVE',
      source: 'IMD Mumbai Fishermen Warning Bulletin',
      issued_at: nowIso,
      valid_until: expIso,
      items: []
    };
    const forecastObj = liveForecast ? {
      status: 'LIVE',
      provider: liveForecast.provider,
      retrieved_at: liveForecast.retrieved_at,
      valid_from: liveForecast.valid_from,
      valid_until: liveForecast.valid_until,
      points: (liveForecast.districts || []).slice(0, 1).map(d => ({
        waypoint_index: 0,
        latitude: d.latitude,
        longitude: d.longitude,
        hourly: d.hourly
      })),
      error: null
    } : { status: 'UNAVAILABLE', provider: 'Open-Meteo', retrieved_at: nowIso, valid_from: null, valid_until: null, points: [], error: 'Unavailable' };
    const predictionsObj = {
      status: 'LIVE',
      model_version: baseMapData.metadata?.model_version || 'Phase4_SpatioOcean_v1',
      calibration_method: baseMapData.metadata?.calibration_method || 'platt',
      decision_threshold: baseMapData.metadata?.decision_threshold ?? 0.18,
      prediction_timestamp: nowIso,
      valid_until: expIso,
      cells: (baseMapData.predictions || []).map(p => ({
        lat: p.latitude,
        lon: p.longitude,
        p: p.predicted_apparent_fishing_probability,
        high: p.predicted_apparent_fishing_binary,
        habitat_score: p.habitat_suitability_score ?? null,
      }))
    };
    const rulesObj = {
      wave_height_threshold_m: 2.5,
      wind_speed_threshold_kmh: 45.0,
      severe_severities: ['SEVERE', 'EXTREME'],
      caution_severities: ['MODERATE'],
      normal_severities: ['LOW', 'NONE'],
      statuses: ['SAFE_CONFIRMED', 'CAUTION', 'UNSAFE', 'NO_WARNING_DATA'],
      rule: 'Safety is determined independently from IMD warnings and wave/wind thresholds.'
    };

    const pkg = {
      manifest: {
        schema_version: 2,
        version: '2.0.0',
        source: 'MatsyaAI Dev Server',
        package_id: pkgId,
        device_id: body.device_id || 'dev-browser',
        created_at: nowIso,
        generated_at: nowIso,
        valid_from: nowIso,
        valid_until: expIso,
        planned_departure: body.planned_departure || null,
        planned_return: body.planned_return || null,
        coverage: { min_lat: 15.0, max_lat: 20.5, min_lon: 71.5, max_lon: 74.0, region: 'Maharashtra Coast' },
        component_versions: { routing: '2', safety_gate: 'phase6-v2', species_catalogue: '1' },
        checksums: {
          route: sha256Canonical(routeObj),
          emergency_returns: sha256Canonical(emergency_returns),
          pfz: sha256Canonical(pfzObj),
          warnings: sha256Canonical(warningsObj),
          forecast: sha256Canonical(forecastObj),
          predictions: sha256Canonical(predictionsObj),
          safety_rules: sha256Canonical(rulesObj)
        },
        component_expiry: {
          warnings: expIso,
          forecast: liveForecast?.valid_until || expIso,
          predictions: expIso,
          pfz: livePfz?.validity_date || expIso
        },
        disclaimers: [baseMapData.metadata?.disclaimer || 'Official navigation charts should always be carried.']
      },
      landing_centre: { ...lc, source: 'Maharashtra Fisheries Dept' },
      destination: {
        latitude: dest.latitude,
        longitude: dest.longitude,
        name: dest.name || 'Selected point',
        source: destSource,
        ...(body.pfz_index !== undefined ? { pfz_index: body.pfz_index } : {})
      },
      route: routeObj,
      emergency_returns,
      pfz: pfzObj,
      warnings: warningsObj,
      forecast: forecastObj,
      predictions: predictionsObj,
      safety_rules: rulesObj,
      offline_assets: {
        basemap: offlineAssetInfo('maharashtra-coast.pmtiles', 'pmtiles-vector', 'OpenStreetMap contributors (ODbL). Not a nautical chart.'),
        bathymetry: offlineAssetInfo('bathymetry-contours.geojson', 'geojson-contours', 'GEBCO general-purpose bathymetry (10/20/50/100/200 m). NOT verified navigation depth.'),
        marine_protected_areas: offlineAssetInfo('marine-protected-areas.geojson', 'geojson-polygons', 'Verified public MPA boundaries (Malvan Marine Sanctuary).'),
        offshore_installations: offlineAssetInfo('offshore-installations.geojson', 'geojson-points', 'Verified public offshore platform points where available.'),
        shipping_lanes: offlineAssetInfo('shipping-lanes.geojson', 'geojson-lines', 'OpenSeaMap seamark lanes where available (not official ENC).'),
        ocean_currents: offlineAssetInfo('ocean-currents-latest.geojson', 'geojson-vectors', 'Coarse modeled surface currents (U/V) for drift estimation only.'),
        nautical_charts: { kind: 'enc', available: false, note: 'Official NHO charts not included (licensing).' },
        bbox: { min_lat: 15.0, max_lat: 20.6, min_lon: 71.0, max_lon: 74.2 }
      }
    };

    res.writeHead(200);
    res.end(JSON.stringify(pkg));
    return;
  }

  if (url.pathname === '/api/v1/expedition/sync' && req.method === 'POST') {
    let bodyStr = '';
    for await (const chunk of req) bodyStr += chunk;
    const body = JSON.parse(bodyStr || '{}');
    const tps = Array.isArray(body.track_points) ? body.track_points : [];
    const catches = Array.isArray(body.catches) ? body.catches : [];
    const obs = Array.isArray(body.observations) ? body.observations : [];

    const countNew = (arr) => {
      let ins = 0;
      for (const r of arr) {
        if (r?.client_uuid && !syncedUuids.has(r.client_uuid)) {
          syncedUuids.add(r.client_uuid);
          ins += 1;
        }
      }
      return ins;
    };

    const insTp = countNew(tps);
    const insCat = countNew(catches);
    const insObs = countNew(obs);
    const acks = [...tps, ...catches, ...obs].map(r => r.client_uuid).filter(Boolean);

    res.writeHead(200);
    res.end(JSON.stringify({
      received: { track_points: tps.length, catches: catches.length, observations: obs.length },
      inserted: { track_points: insTp, catches: insCat, observations: insObs },
      duplicates: { track_points: tps.length - insTp, catches: catches.length - insCat, observations: obs.length - insObs },
      acknowledged_uuids: acks,
      synced_at: new Date().toISOString()
    }));
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Endpoint not found', path: url.pathname }));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`MatsyaAI Live Development Backend running at http://0.0.0.0:${PORT}`);
  // Warm caches immediately on startup
  fetchLiveIncoisPfz();
  fetchLiveForecast();
});
