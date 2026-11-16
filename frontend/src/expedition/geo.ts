/**
 * MatsyaAI Maharashtra — Pure geodesy helpers for at-sea navigation.
 * Mirrors backend/app/services/expedition/routing.py so client and server agree.
 */

export const EARTH_RADIUS_KM = 6371.0088;
export const KM_PER_NM = 1.852;

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dphi = p2 - p1;
  const dlmb = rad(lon2 - lon1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Initial bearing from point 1 to point 2, degrees 0..360. */
export function initialBearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dlmb = rad(lon2 - lon1);
  const y = Math.sin(dlmb) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dlmb);
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

/**
 * Signed cross-track distance (km) of point P from the great-circle path A→B.
 * Negative = left of track, positive = right of track.
 */
export function crossTrackKm(
  latA: number, lonA: number, latB: number, lonB: number, latP: number, lonP: number,
): number {
  const d13 = haversineKm(latA, lonA, latP, lonP) / EARTH_RADIUS_KM;
  const b13 = rad(initialBearingDeg(latA, lonA, latP, lonP));
  const b12 = rad(initialBearingDeg(latA, lonA, latB, lonB));
  return Math.asin(Math.sin(d13) * Math.sin(b13 - b12)) * EARTH_RADIUS_KM;
}

/** Along-track distance (km) from A toward B of the projection of P. */
export function alongTrackKm(
  latA: number, lonA: number, latB: number, lonB: number, latP: number, lonP: number,
): number {
  const d13 = haversineKm(latA, lonA, latP, lonP) / EARTH_RADIUS_KM;
  const xt = crossTrackKm(latA, lonA, latB, lonB, latP, lonP) / EARTH_RADIUS_KM;
  const cosRatio = Math.cos(d13) / Math.cos(xt);
  return Math.acos(Math.max(-1, Math.min(1, cosRatio))) * EARTH_RADIUS_KM;
}

export function compassPoint(bearing: number): string {
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return points[Math.round(((bearing % 360) + 360) % 360 / 22.5) % 16];
}

/** Smallest signed angular difference target − current, in −180..180. */
export function headingError(currentDeg: number, targetDeg: number): number {
  return ((targetDeg - currentDeg + 540) % 360) - 180;
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
  distanceToNextKm: number;
  distanceToEndKm: number;
}

/**
 * Determine which leg of a polyline route the vessel is on and how far off-track it is.
 * Chooses the leg with the smallest cross-track distance whose projection lies within it.
 */
export function routeProgress(
  waypoints: { latitude: number; longitude: number }[],
  lat: number,
  lon: number,
): LegProgress | null {
  if (waypoints.length < 2) return null;
  let best: LegProgress | null = null;
  let bestAbs = Infinity;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const legLen = haversineKm(a.latitude, a.longitude, b.latitude, b.longitude);
    const along = alongTrackKm(a.latitude, a.longitude, b.latitude, b.longitude, lat, lon);
    const xt = crossTrackKm(a.latitude, a.longitude, b.latitude, b.longitude, lat, lon);
    const inside = along >= -0.001 && along <= legLen + 0.001;
    const metric = inside ? Math.abs(xt) : Math.min(
      haversineKm(a.latitude, a.longitude, lat, lon),
      haversineKm(b.latitude, b.longitude, lat, lon),
    );
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
      best = { nextWaypointIndex: i + 1, crossTrackKm: xt, distanceToNextKm: toNext, distanceToEndKm: remaining };
    }
  }
  return best;
}
