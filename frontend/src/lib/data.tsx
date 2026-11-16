/**
 * App-wide data provider. Fetches the map summary, health, warnings and the
 * coastal forecast once and shares them across pages; refreshes periodically.
 * The service worker keeps the last good response for offline viewing.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { fetchHealth, fetchMapSummary, fetchMarineForecast, fetchMarineWarnings } from '../services/api';
import type { HealthResponse } from '../types/health';
import type { MapSummaryResponse, MarineForecast, MarineWarnings } from '../types/map';

interface DataValue {
  summary: MapSummaryResponse | null;
  health: HealthResponse | null;
  warnings: MarineWarnings | null;
  forecast: MarineForecast | null;
  loading: boolean;
  error: string | null;
  demo: boolean;
  setDemo: (d: boolean) => void;
  refresh: () => void;
  lastUpdated: string | null;
}

const DataContext = createContext<DataValue | null>(null);
const REFRESH_MS = 5 * 60_000;

export function DataProvider({ children }: { children: ReactNode }) {
  const [summary, setSummary] = useState<MapSummaryResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [warnings, setWarnings] = useState<MarineWarnings | null>(null);
  const [forecast, setForecast] = useState<MarineForecast | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      const [s, h, w, f] = await Promise.allSettled([
        fetchMapSummary(demo), fetchHealth(), fetchMarineWarnings(), fetchMarineForecast(),
      ]);
      if (cancelled) return;
      if (s.status === 'fulfilled') { setSummary(s.value); setError(null); }
      else setError(s.reason instanceof Error ? s.reason.message : 'Could not reach the MatsyaAI service.');
      if (h.status === 'fulfilled') setHealth(h.value);
      if (w.status === 'fulfilled') setWarnings(w.value);
      if (f.status === 'fulfilled') setForecast(f.value);
      setLastUpdated(new Date().toISOString());
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [demo, tick]);

  useEffect(() => {
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const value = useMemo<DataValue>(() => ({
    summary, health, warnings, forecast, loading, error, demo, setDemo, refresh, lastUpdated,
  }), [summary, health, warnings, forecast, loading, error, demo, refresh, lastUpdated]);

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): DataValue {
  const v = useContext(DataContext);
  if (!v) throw new Error('useData must be used inside <DataProvider>');
  return v;
}

/** Index into an hourly series for "now" (latest slot not in the future), or -1. */
export function hourIndexNow(times: string[], now: number = Date.now()): number {
  for (let i = times.length - 1; i >= 0; i--) {
    const t = Date.parse(times[i]);
    if (!Number.isNaN(t) && t <= now) return now - t < 2 * 3600_000 ? i : -1;
  }
  return -1;
}

export interface Conditions {
  time: string;
  wave: number | null;
  period: number | null;
  swell: number | null;
  wind: number | null;
  gust: number | null;
  windDir: number | null;
}

export function conditionsAt(f: MarineForecast | null, district: string, now: number = Date.now()): Conditions | null {
  const d = f?.districts.find((x) => x.district === district);
  if (!d?.hourly) return null;
  const i = hourIndexNow(d.hourly.time, now);
  if (i < 0) return null;
  return {
    time: d.hourly.time[i],
    wave: d.hourly.wave_height_m[i] ?? null,
    period: d.hourly.wave_period_s[i] ?? null,
    swell: d.hourly.swell_wave_height_m[i] ?? null,
    wind: d.hourly.wind_speed_kmh[i] ?? null,
    gust: d.hourly.wind_gusts_kmh[i] ?? null,
    windDir: d.hourly.wind_direction_deg[i] ?? null,
  };
}

/** Max of a series over the next `hours` from now. */
export function peakAhead(series: (number | null)[], times: string[], hours: number, now: number = Date.now()): number | null {
  let max: number | null = null;
  const end = now + hours * 3600_000;
  times.forEach((t, i) => {
    const ts = Date.parse(t);
    const v = series[i];
    if (ts >= now - 3600_000 && ts <= end && v !== null && v !== undefined) max = max === null ? v : Math.max(max, v);
  });
  return max;
}
