/**
 * MatsyaAI Maharashtra — Offline safety evaluation.
 *
 * TypeScript port of backend/app/ml/safety_gate.py `_determine_safety`, evaluated
 * on the packaged IMD warnings and the packaged forecast for the current hour.
 *
 * Invariant: expired or missing data NEVER yields SAFE_CONFIRMED.
 */

import type {
  ExpeditionPackage,
  ForecastPoint,
  OfflineSafetyResult,
  PackagedWarnings,
  SafetyRules,
} from './types';
import { haversineKm } from './geo';

const parse = (ts: string | null | undefined): number | null => {
  if (!ts) return null;
  const n = Date.parse(ts);
  return Number.isNaN(n) ? null : n;
};

/** Pick the forecast point nearest to (lat, lon); falls back to first. */
export function nearestForecastPoint(
  points: ForecastPoint[],
  lat: number | null,
  lon: number | null,
): ForecastPoint | null {
  if (points.length === 0) return null;
  if (lat === null || lon === null) return points[0];
  let best = points[0];
  let bestD = Infinity;
  for (const p of points) {
    const d = haversineKm(lat, lon, p.latitude, p.longitude);
    if (d < bestD) {
      bestD = d;
      best = p;
    }
  }
  return best;
}

/** Index of the hourly slot covering `now`, or -1 if outside the forecast window. */
export function forecastIndexAt(times: string[], now: number): number {
  if (times.length === 0) return -1;
  for (let i = times.length - 1; i >= 0; i--) {
    const t = parse(times[i]);
    if (t !== null && t <= now) {
      return now - t < 3600_000 * 1.5 ? i : -1;
    }
  }
  return -1;
}

export interface CurrentConditions {
  wave_height_m: number | null;
  wind_speed_kmh: number | null;
  forecast_time: string | null;
  expired: boolean;
}

export function currentConditions(
  pkg: Pick<ExpeditionPackage, 'forecast'>,
  lat: number | null,
  lon: number | null,
  now: number = Date.now(),
): CurrentConditions {
  const point = nearestForecastPoint(pkg.forecast.points, lat, lon);
  if (!point) return { wave_height_m: null, wind_speed_kmh: null, forecast_time: null, expired: true };
  const idx = forecastIndexAt(point.hourly.time, now);
  if (idx < 0) return { wave_height_m: null, wind_speed_kmh: null, forecast_time: null, expired: true };
  return {
    wave_height_m: point.hourly.wave_height_m[idx] ?? null,
    wind_speed_kmh: point.hourly.wind_speed_kmh[idx] ?? null,
    forecast_time: point.hourly.time[idx],
    expired: false,
  };
}

export function evaluateOfflineSafety(
  warnings: PackagedWarnings,
  rules: SafetyRules,
  conditions: CurrentConditions,
  now: number = Date.now(),
): OfflineSafetyResult {
  const active = warnings.items.filter((w) => {
    const from = parse(w.valid_from);
    const until = parse(w.valid_until);
    return from !== null && until !== null && from <= now && now <= until;
  });
  const sev = (w: { severity: string }) => (w.severity || '').toUpperCase();

  const severe = active.filter((w) => rules.severe_severities.includes(sev(w)));
  const caution = active.filter((w) => rules.caution_severities.includes(sev(w)));
  const normal = active.some((w) => rules.normal_severities.includes(sev(w)));
  const warningsExpired = warnings.items.length > 0 && active.length === 0;

  const base = {
    wave_height_m: conditions.wave_height_m,
    wind_speed_kmh: conditions.wind_speed_kmh,
    warnings_expired: warningsExpired,
    forecast_expired: conditions.expired,
  };

  if (severe.length) {
    return { ...base, status: 'UNSAFE', reason: 'Active severe marine warning from authoritative source' };
  }
  if (caution.length) {
    return { ...base, status: 'CAUTION', reason: 'Active caution-level marine warning from authoritative source' };
  }
  const { wave_height_m: wave, wind_speed_kmh: wind } = conditions;
  if (wave !== null && wave > rules.wave_height_threshold_m) {
    return { ...base, status: 'CAUTION', reason: `Forecast wave height ${wave.toFixed(1)} m exceeds ${rules.wave_height_threshold_m} m threshold` };
  }
  if (wind !== null && wind > rules.wind_speed_threshold_kmh) {
    return { ...base, status: 'CAUTION', reason: `Forecast wind ${wind.toFixed(0)} km/h exceeds ${rules.wind_speed_threshold_kmh} km/h threshold` };
  }
  if (normal) {
    if (wave === null || wind === null || conditions.expired) {
      return { ...base, status: 'NO_WARNING_DATA', reason: 'Forecast data missing or expired; cannot confirm safety' };
    }
    return { ...base, status: 'SAFE_CONFIRMED', reason: 'Active authoritative bulletin confirms normal conditions' };
  }
  return {
    ...base,
    status: 'NO_WARNING_DATA',
    reason: warningsExpired
      ? 'Packaged marine warnings have expired; reconnect to refresh'
      : 'No current authoritative marine warning data available to confirm safety',
  };
}

export function evaluatePackageSafety(
  pkg: ExpeditionPackage,
  lat: number | null,
  lon: number | null,
  now: number = Date.now(),
): OfflineSafetyResult {
  return evaluateOfflineSafety(pkg.warnings, pkg.safety_rules, currentConditions(pkg, lat, lon, now), now);
}
