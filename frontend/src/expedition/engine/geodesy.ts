/**
 * MatsyaAI Maharashtra — Pure geodesy helpers for at-sea navigation.
 * Mirrors backend/app/services/expedition/routing.py so client and server agree.
 */

export const EARTH_RADIUS_KM = 6371.0088;
export const KM_PER_NM = 1.852;

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

/** Normalize an angle in degrees into [0, 360). */
export function normalizeDeg(angle: number): number {
  return ((angle % 360) + 360) % 360;
}

/** Shortest signed angular difference (to - from) in (-180, 180]. */
export function angularDiffDeg(fromDeg: number, toDeg: number): number {
  return ((toDeg - fromDeg + 540) % 360) - 180;
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dphi = p2 - p1;
  const dlmb = rad(lon2 - lon1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Initial bearing from point 1 to point 2, degrees [0, 360). */
export function initialBearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dlmb = rad(lon2 - lon1);
  const y = Math.sin(dlmb) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dlmb);
  return normalizeDeg(deg(Math.atan2(y, x)));
}

/** Spherical intermediate point at fraction [0..1] along the great circle between A and B. */
export function intermediatePoint(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
  fraction: number,
): { latitude: number; longitude: number } {
  const f = Math.max(0, Math.min(1, fraction));
  const d = haversineKm(lat1, lon1, lat2, lon2) / EARTH_RADIUS_KM;
  if (d < 1e-12) return { latitude: lat1, longitude: lon1 };
  const p1 = rad(lat1);
  const l1 = rad(lon1);
  const p2 = rad(lat2);
  const l2 = rad(lon2);
  const sinD = Math.sin(d);
  const a = Math.sin((1 - f) * d) / sinD;
  const b = Math.sin(f * d) / sinD;
  const x = a * Math.cos(p1) * Math.cos(l1) + b * Math.cos(p2) * Math.cos(l2);
  const y = a * Math.cos(p1) * Math.sin(l1) + b * Math.cos(p2) * Math.sin(l2);
  const z = a * Math.sin(p1) + b * Math.sin(p2);
  return {
    latitude: deg(Math.atan2(z, Math.hypot(x, y))),
    longitude: deg(Math.atan2(y, x)),
  };
}

/** Destination point given start, initial bearing (deg), and distance (km). */
export function destinationPoint(
  lat: number,
  lon: number,
  bearingDeg: number,
  distanceKm: number,
): { latitude: number; longitude: number } {
  const delta = distanceKm / EARTH_RADIUS_KM;
  const theta = rad(bearingDeg);
  const p1 = rad(lat);
  const l1 = rad(lon);
  const sinP2 = Math.sin(p1) * Math.cos(delta) + Math.cos(p1) * Math.sin(delta) * Math.cos(theta);
  const p2 = Math.asin(Math.max(-1, Math.min(1, sinP2)));
  const y = Math.sin(theta) * Math.sin(delta) * Math.cos(p1);
  const x = Math.cos(delta) - Math.sin(p1) * Math.sin(p2);
  let l2 = l1 + Math.atan2(y, x);
  l2 = ((l2 + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
  return { latitude: deg(p2), longitude: deg(l2) };
}

/**
 * Signed cross-track distance (km) of point P from the great-circle path A→B.
 * Negative = left of track, positive = right of track.
 */
export function crossTrackKm(
  latA: number, lonA: number, latB: number, lonB: number, latP: number, lonP: number,
): number {
  const d13 = haversineKm(latA, lonA, latP, lonP) / EARTH_RADIUS_KM;
  if (d13 < 1e-12) return 0;
  const b13 = rad(initialBearingDeg(latA, lonA, latP, lonP));
  const b12 = rad(initialBearingDeg(latA, lonA, latB, lonB));
  const sinXt = Math.max(-1, Math.min(1, Math.sin(d13) * Math.sin(b13 - b12)));
  return Math.asin(sinXt) * EARTH_RADIUS_KM;
}

/**
 * Signed along-track distance (km) from A toward B of the projection of P.
 * Negative when P lies behind A relative to the A→B bearing.
 */
export function alongTrackKm(
  latA: number, lonA: number, latB: number, lonB: number, latP: number, lonP: number,
): number {
  const d13 = haversineKm(latA, lonA, latP, lonP) / EARTH_RADIUS_KM;
  if (d13 < 1e-12) return 0;
  const b13 = rad(initialBearingDeg(latA, lonA, latP, lonP));
  const b12 = rad(initialBearingDeg(latA, lonA, latB, lonB));
  return Math.atan2(Math.sin(d13) * Math.cos(b13 - b12), Math.cos(d13)) * EARTH_RADIUS_KM;
}

export function compassPoint(bearing: number): string {
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return points[Math.round(normalizeDeg(bearing) / 22.5) % 16];
}

/** Smallest signed angular difference target − current, in −180..180. */
export function headingError(currentDeg: number, targetDeg: number): number {
  return angularDiffDeg(currentDeg, targetDeg);
}

/** Format decimal coordinates into marine Degrees-Minutes-Seconds string. */
export function formatDms(lat: number, lon: number): string {
  const fmt = (v: number, pos: string, neg: string) => {
    const hemi = v >= 0 ? pos : neg;
    const abs = Math.abs(v);
    const d = Math.floor(abs);
    const mFloat = (abs - d) * 60;
    const m = Math.floor(mFloat);
    const s = Math.round((mFloat - m) * 60);
    const adjS = s === 60 ? 0 : s;
    const adjM = s === 60 ? m + 1 : m;
    return `${d}°${String(adjM).padStart(2, '0')}'${String(adjS).padStart(2, '0')}"${hemi}`;
  };
  return `${fmt(lat, 'N', 'S')} ${fmt(lon, 'E', 'W')}`;
}

export function kmToNm(km: number): number {
  return km / KM_PER_NM;
}

export function mpsToKnots(mps: number): number {
  return mps * 1.943844;
}

/** ETA in minutes; null when not moving. */
export function etaMinutes(distanceKm: number, speedMps: number | null): number | null {
  if (!speedMps || speedMps < 0.3) return null;
  return (distanceKm * 1000) / speedMps / 60;
}

export interface LegProgress {
  /** Index of the waypoint being approached. */
  nextWaypointIndex: number;
  crossTrackKm: number;
  alongTrackKm: number;
  legLengthKm: number;
  distanceToNextKm: number;
  distanceToEndKm: number;
}

/**
 * Determine which leg of a polyline route the vessel is on and how far off-track it is.
 * Uses signed along-track distance so positions behind a leg start are not misclassified.
 */
export function routeProgress(
  waypoints: { latitude: number; longitude: number }[],
  lat: number,
  lon: number,
  minWaypointIndex: number = 1,
): LegProgress | null {
  if (waypoints.length < 2) return null;
  const startLeg = Math.max(0, Math.min(waypoints.length - 2, minWaypointIndex - 1));
  let best: LegProgress | null = null;
  let bestAbs = Infinity;
  for (let i = startLeg; i < waypoints.length - 1; i++) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const legLen = haversineKm(a.latitude, a.longitude, b.latitude, b.longitude);
    const along = alongTrackKm(a.latitude, a.longitude, b.latitude, b.longitude, lat, lon);
    const xt = crossTrackKm(a.latitude, a.longitude, b.latitude, b.longitude, lat, lon);
    const inside = along >= -0.05 && along <= legLen + 0.05;
    const metric = inside
      ? Math.abs(xt)
      : Math.min(haversineKm(a.latitude, a.longitude, lat, lon), haversineKm(b.latitude, b.longitude, lat, lon)) + 0.01;
    if (metric < bestAbs) {
      bestAbs = metric;
      const toNext = haversineKm(lat, lon, b.latitude, b.longitude);
      let remaining = toNext;
      for (let j = i + 1; j < waypoints.length - 1; j++) {
        remaining += haversineKm(
          waypoints[j].latitude, waypoints[j].longitude,
          waypoints[j + 1].latitude, waypoints[j + 1].longitude,
        );
      }
      best = {
        nextWaypointIndex: i + 1,
        crossTrackKm: xt,
        alongTrackKm: along,
        legLengthKm: legLen,
        distanceToNextKm: toNext,
        distanceToEndKm: remaining,
      };
    }
  }
  return best;
}

/**
 * Simplified West Coast India / Maharashtra shoreline (south → north).
 * Points east of this line (within Indian landmass bounds) are on land;
 * points west are in the Arabian Sea.
 */
const WEST_COAST_INDIA: readonly [number, number][] = [
  [14.0, 74.45],
  [14.81, 74.12],
  [15.49, 73.81],
  [15.86, 73.62],
  [16.06, 73.46],
  [16.37, 73.37],
  [16.56, 73.33],
  [16.99, 73.28],
  [17.22, 73.22],
  [17.58, 73.17],
  [17.81, 73.09],
  [18.04, 73.01],
  [18.33, 72.96],
  [18.64, 72.87],
  [18.92, 72.81],
  [19.12, 72.82],
  [19.20, 72.78],
  [19.32, 72.80],
  [19.45, 72.77],
  [19.70, 72.72],
  [19.97, 72.73],
  [20.15, 72.73],
  [20.42, 72.83],
];

/**
 * Returns true when a coordinate lies on land along the Maharashtra / West India
 * coast (east of the shoreline), and false when in the Arabian Sea.
 */
export function isPointOnLand(lat: number, lon: number): boolean {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
  if (lon > 88.0 || lon < 68.0 || lat < 8.0 || lat > 24.0) return false;
  if (lat >= WEST_COAST_INDIA[WEST_COAST_INDIA.length - 1][0]) {
    return lon > WEST_COAST_INDIA[WEST_COAST_INDIA.length - 1][1];
  }
  if (lat <= WEST_COAST_INDIA[0][0]) {
    return lon > WEST_COAST_INDIA[0][1];
  }
  for (let i = 0; i < WEST_COAST_INDIA.length - 1; i++) {
    const [lat1, lon1] = WEST_COAST_INDIA[i];
    const [lat2, lon2] = WEST_COAST_INDIA[i + 1];
    if (lat >= lat1 && lat <= lat2) {
      const f = (lat - lat1) / (lat2 - lat1 || 1);
      const coastLon = lon1 + f * (lon2 - lon1);
      return lon > coastLon;
    }
  }
  return false;
}

export interface DriftEstimate {
  speedMps: number;
  speedKnots: number;
  bearingDeg: number;
  compass: string;
  distanceKm: number;
  distanceNm: number;
}

/**
 * Estimate boat surface drift from eastward (u) and northward (v) ocean current components (m/s).
 * Returns null when either component is missing.
 */
export function estimateCurrentDrift(
  uMps: number | null | undefined,
  vMps: number | null | undefined,
  hours: number = 1,
): DriftEstimate | null {
  if (uMps == null || vMps == null || !Number.isFinite(uMps) || !Number.isFinite(vMps)) {
    return null;
  }
  const speedMps = Math.hypot(uMps, vMps);
  const bearingDeg = speedMps < 1e-6 ? 0 : normalizeDeg(deg(Math.atan2(uMps, vMps)));
  const distanceKm = (speedMps * 3600 * hours) / 1000;
  return {
    speedMps,
    speedKnots: speedMps * 1.943844,
    bearingDeg,
    compass: compassPoint(bearingDeg),
    distanceKm,
    distanceNm: distanceKm / KM_PER_NM,
  };
}

export interface ShallowContourLine {
  depth_m: number;
  coordinates: [number, number][]; // [lon, lat]
}

/**
 * Compute minimum distance (km) from a point to a set of GEBCO shallow contour polylines.
 */
export function minDistanceToShallowContoursKm(
  lat: number,
  lon: number,
  contours: ShallowContourLine[],
): { distanceKm: number; depthM: number } | null {
  let bestDist = Infinity;
  let bestDepth = Infinity;
  for (const line of contours) {
    for (const [cLon, cLat] of line.coordinates) {
      const d = haversineKm(lat, lon, cLat, cLon);
      if (d < bestDist) {
        bestDist = d;
        bestDepth = line.depth_m;
      }
    }
  }
  return Number.isFinite(bestDist) ? { distanceKm: bestDist, depthM: bestDepth } : null;
}
