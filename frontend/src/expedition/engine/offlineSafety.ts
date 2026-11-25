/**
 * MatsyaAI Maharashtra — Marine Safety Intelligence Engine.
 *
 * Preserves `evaluateOfflineSafety` / `evaluatePackageSafety` parity with
 * backend/app/ml/safety_gate.py, and adds `evaluateMarineSafety`:
 *  - 4 explicit states: SAFE_DATA | CAUTION | UNSAFE | UNKNOWN
 *  - Spatial + temporal corridor evaluation (current + upcoming voyage horizon)
 *  - Per-source provenance (type, issue/valid-from/expiry times, coverage)
 *  - Explicit UNAVAILABLE disclosure for unintegrated feeds (e.g. INCOIS OSF)
 *  - Configurable user safety limits clamped strictly >= official thresholds
 *
 * Invariants:
 *  - Missing or expired data NEVER yields SAFE_DATA / SAFE_CONFIRMED.
 *  - Forecasts are never labelled as live observations.
 *  - Application never claims to guarantee marine safety.
 */

import type {
  ExpeditionPackage,
  ForecastPoint,
  OfflineSafetyResult,
  PackagedWarnings,
  SafetyRules,
} from '../types/expeditionTypes';
import { haversineKm } from './geodesy';

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
    return {
      ...base,
      status: 'CAUTION',
      reason: `Forecast wave height ${wave.toFixed(1)} m exceeds ${rules.wave_height_threshold_m} m threshold`,
    };
  }
  if (wind !== null && wind > rules.wind_speed_threshold_kmh) {
    return {
      ...base,
      status: 'CAUTION',
      reason: `Forecast wind ${wind.toFixed(0)} km/h exceeds ${rules.wind_speed_threshold_kmh} km/h threshold`,
    };
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

// ---------------------------------------------------------------------------
// Phase 4: Marine Safety Intelligence Engine
// ---------------------------------------------------------------------------

export type ExpeditionSafetyState = 'SAFE_DATA' | 'CAUTION' | 'UNSAFE' | 'UNKNOWN';

export interface SafetySourceReport {
  id: 'imd_warnings' | 'marine_forecast' | 'incois_pfz' | 'incois_osf';
  name: string;
  dataType: 'OFFICIAL_BULLETIN' | 'FORECAST' | 'ADVISORY' | 'OCEAN_STATE_FORECAST';
  status: 'VALID' | 'EXPIRED' | 'UNAVAILABLE';
  issuedAt: string | null;
  validFrom: string | null;
  validUntil: string | null;
  coverage: string;
  note: string;
}

export interface SafetyEvaluationOptions {
  /** Optional stricter user wave limit (m). Cannot relax official safety_rules threshold. */
  customWaveThresholdM?: number;
  /** Optional stricter user wind limit (km/h). Cannot relax official safety_rules threshold. */
  customWindThresholdKmh?: number;
  /** Horizon ahead along route + return corridor to scan for deteriorating conditions (hours). */
  corridorHorizonHours?: number;
}

export interface MarineSafetyReport {
  state: ExpeditionSafetyState;
  legacyStatus: OfflineSafetyResult['status'];
  reason: string;
  activeWarnings: {
    warning_type: string;
    severity: string;
    source_name: string;
    description: string;
    valid_from: string;
    valid_until: string;
  }[];
  upcomingHazard: {
    detected: boolean;
    time: string | null;
    reason: string | null;
    maxWaveM: number | null;
    maxWindKmh: number | null;
  };
  currentConditions: CurrentConditions;
  effectiveThresholds: {
    wave_height_m: number;
    wind_speed_kmh: number;
  };
  warningsExpired: boolean;
  forecastExpired: boolean;
  sources: SafetySourceReport[];
  disclaimer: string;
}

const SAFETY_DISCLAIMER =
  'Decision support only. This application cannot guarantee marine safety. Always verify official IMD/INCOIS advisories and local port signals.';

export function evaluateMarineSafety(
  pkg: ExpeditionPackage,
  pos: { latitude: number; longitude: number } | null,
  now: number = Date.now(),
  options: SafetyEvaluationOptions = {},
): MarineSafetyReport {
  const lat = pos?.latitude ?? null;
  const lon = pos?.longitude ?? null;
  const horizonH = options.corridorHorizonHours ?? 12;

  // Enforce strict-only configurable limits (cannot be made looser than authoritative rules)
  const effectiveWaveLimit =
    options.customWaveThresholdM !== undefined && options.customWaveThresholdM > 0
      ? Math.min(pkg.safety_rules.wave_height_threshold_m, options.customWaveThresholdM)
      : pkg.safety_rules.wave_height_threshold_m;
  const effectiveWindLimit =
    options.customWindThresholdKmh !== undefined && options.customWindThresholdKmh > 0
      ? Math.min(pkg.safety_rules.wind_speed_threshold_kmh, options.customWindThresholdKmh)
      : pkg.safety_rules.wind_speed_threshold_kmh;

  const effectiveRules: SafetyRules = {
    ...pkg.safety_rules,
    wave_height_threshold_m: effectiveWaveLimit,
    wind_speed_threshold_kmh: effectiveWindLimit,
  };

  const cond = currentConditions(pkg, lat, lon, now);
  const legacy = evaluateOfflineSafety(pkg.warnings, effectiveRules, cond, now);

  // Active warnings at `now`
  const activeWarnings = pkg.warnings.items.filter((w) => {
    const from = parse(w.valid_from);
    const until = parse(w.valid_until);
    return from !== null && until !== null && from <= now && now <= until;
  });

  // Temporal & spatial corridor scan (all packaged route forecast points over next horizonH hours)
  const horizonEnd = now + horizonH * 3600_000;
  let maxWaveM: number | null = null;
  let maxWindKmh: number | null = null;
  let hazardTime: string | null = null;
  let hazardReason: string | null = null;

  for (const pt of pkg.forecast.points) {
    const times = pt.hourly.time;
    for (let i = 0; i < times.length; i++) {
      const t = parse(times[i]);
      if (t === null || t < now || t > horizonEnd) continue;
      const w = pt.hourly.wave_height_m[i];
      const wind = pt.hourly.wind_speed_kmh[i];
      if (w !== null && w !== undefined && (maxWaveM === null || w > maxWaveM)) maxWaveM = w;
      if (wind !== null && wind !== undefined && (maxWindKmh === null || wind > maxWindKmh)) maxWindKmh = wind;

      if (!hazardReason) {
        if (w !== null && w !== undefined && w > effectiveWaveLimit) {
          hazardTime = times[i];
          hazardReason = `Forecast wave ${w.toFixed(1)} m along route/return corridor exceeds ${effectiveWaveLimit} m`;
        } else if (wind !== null && wind !== undefined && wind > effectiveWindLimit) {
          hazardTime = times[i];
          hazardReason = `Forecast wind ${wind.toFixed(0)} km/h along route/return corridor exceeds ${effectiveWindLimit} km/h`;
        }
      }
    }
  }

  // Also check upcoming severe warning starting within horizonH
  if (!hazardReason) {
    for (const w of pkg.warnings.items) {
      const from = parse(w.valid_from);
      const sev = (w.severity || '').toUpperCase();
      if (from !== null && from > now && from <= horizonEnd &&
        (effectiveRules.severe_severities.includes(sev) || effectiveRules.caution_severities.includes(sev))) {
        hazardTime = w.valid_from;
        hazardReason = `Upcoming ${sev} warning (${w.warning_type}) starts within ${horizonH}h`;
        break;
      }
    }
  }

  let state: ExpeditionSafetyState;
  let reason = legacy.reason;
  if (legacy.status === 'UNSAFE') {
    state = 'UNSAFE';
  } else if (legacy.status === 'CAUTION') {
    state = 'CAUTION';
  } else if (hazardReason) {
    state = 'CAUTION';
    reason = hazardReason;
  } else if (legacy.status === 'SAFE_CONFIRMED') {
    state = 'SAFE_DATA';
  } else {
    state = 'UNKNOWN';
  }

  // Per-source provenance reports
  const warnUntil = parse(pkg.warnings.valid_until);
  const warnStatus: SafetySourceReport['status'] =
    pkg.warnings.status === 'UNAVAILABLE'
      ? 'UNAVAILABLE'
      : warnUntil !== null && warnUntil < now
        ? 'EXPIRED'
        : pkg.warnings.items.length > 0 && activeWarnings.length === 0
          ? 'EXPIRED'
          : pkg.warnings.items.length > 0
            ? 'VALID'
            : 'UNAVAILABLE';

  const fcUntil = parse(pkg.forecast.valid_until);
  const fcStatus: SafetySourceReport['status'] =
    pkg.forecast.status === 'UNAVAILABLE' || pkg.forecast.points.length === 0
      ? 'UNAVAILABLE'
      : (fcUntil !== null && fcUntil < now) || cond.expired
        ? 'EXPIRED'
        : 'VALID';

  const pfzUntil = parse(pkg.pfz.validity_date);
  const pfzStatus: SafetySourceReport['status'] =
    pkg.pfz.status === 'UNAVAILABLE'
      ? 'UNAVAILABLE'
      : pfzUntil !== null && pfzUntil < now
        ? 'EXPIRED'
        : 'VALID';

  const sources: SafetySourceReport[] = [
    {
      id: 'imd_warnings',
      name: pkg.warnings.source || 'IMD Mumbai Fishermen Warning Bulletin',
      dataType: 'OFFICIAL_BULLETIN',
      status: warnStatus,
      issuedAt: pkg.warnings.issued_at,
      validFrom: activeWarnings[0]?.valid_from ?? null,
      validUntil: pkg.warnings.valid_until,
      coverage: 'Maharashtra Coastal & High Sea Sectors',
      note:
        warnStatus === 'VALID'
          ? `${activeWarnings.length} active bulletin item(s)`
          : warnStatus === 'EXPIRED'
            ? 'Packaged bulletin expired; safety cannot be confirmed'
            : 'No active warning bulletin packaged',
    },
    {
      id: 'marine_forecast',
      name: pkg.forecast.provider || 'Open-Meteo Marine & Wind Forecast',
      dataType: 'FORECAST',
      status: fcStatus,
      issuedAt: pkg.forecast.retrieved_at,
      validFrom: pkg.forecast.valid_from,
      validUntil: pkg.forecast.valid_until,
      coverage: `${pkg.forecast.points.length} route waypoint(s)`,
      note: 'Model forecast (not a live ocean buoy observation)',
    },
    {
      id: 'incois_pfz',
      name: 'INCOIS Potential Fishing Zone (PFZ)',
      dataType: 'ADVISORY',
      status: pfzStatus,
      issuedAt: pkg.pfz.advisory_date,
      validFrom: pkg.pfz.advisory_date,
      validUntil: pkg.pfz.validity_date,
      coverage: 'Maharashtra SEC002',
      note: `${pkg.pfz.count} advisory location(s); fishery advisory only, not a safety clearance`,
    },
    {
      id: 'incois_osf',
      name: 'INCOIS Ocean State Forecast (OSF) & High-Wave Alerts',
      dataType: 'OCEAN_STATE_FORECAST',
      status: 'UNAVAILABLE',
      issuedAt: null,
      validFrom: null,
      validUntil: null,
      coverage: 'Maharashtra Coast',
      note: 'Direct INCOIS OSF ingestion is not integrated; rely on IMD bulletins and packaged marine forecast',
    },
  ];

  return {
    state,
    legacyStatus: legacy.status,
    reason,
    activeWarnings: activeWarnings.map((w) => ({
      warning_type: w.warning_type,
      severity: w.severity,
      source_name: w.source_name,
      description: w.description,
      valid_from: w.valid_from,
      valid_until: w.valid_until,
    })),
    upcomingHazard: {
      detected: !!hazardReason,
      time: hazardTime,
      reason: hazardReason,
      maxWaveM,
      maxWindKmh,
    },
    currentConditions: cond,
    effectiveThresholds: {
      wave_height_m: effectiveWaveLimit,
      wind_speed_kmh: effectiveWindLimit,
    },
    warningsExpired: legacy.warnings_expired,
    forecastExpired: legacy.forecast_expired,
    sources,
    disclaimer: SAFETY_DISCLAIMER,
  };
}
