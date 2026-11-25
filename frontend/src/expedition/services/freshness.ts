/**
 * MatsyaAI Maharashtra — Package component freshness.
 */

import type { ExpeditionPackage } from '../types/expeditionTypes';

export type FreshnessLevel = 'VALID' | 'EXPIRING' | 'EXPIRED' | 'UNAVAILABLE';

export interface ComponentFreshness {
  key: 'warnings' | 'forecast' | 'predictions' | 'pfz';
  level: FreshnessLevel;
  valid_until: string | null;
  minutes_left: number | null;
}

const EXPIRING_WINDOW_MIN = 6 * 60;

export function freshnessOf(validUntil: string | null, now: number = Date.now()): Omit<ComponentFreshness, 'key'> {
  if (!validUntil) return { level: 'UNAVAILABLE', valid_until: null, minutes_left: null };
  const t = Date.parse(validUntil);
  if (Number.isNaN(t)) return { level: 'UNAVAILABLE', valid_until: validUntil, minutes_left: null };
  const minutes = (t - now) / 60_000;
  if (minutes <= 0) return { level: 'EXPIRED', valid_until: validUntil, minutes_left: 0 };
  return { level: minutes <= EXPIRING_WINDOW_MIN ? 'EXPIRING' : 'VALID', valid_until: validUntil, minutes_left: Math.round(minutes) };
}

export function packageFreshness(pkg: ExpeditionPackage, now: number = Date.now()): ComponentFreshness[] {
  const e = pkg.manifest.component_expiry;
  return (['warnings', 'forecast', 'predictions', 'pfz'] as const).map((key) => ({
    key,
    ...freshnessOf(e[key], now),
  }));
}

export function formatRemaining(minutes: number | null): string {
  if (minutes === null) return '—';
  if (minutes <= 0) return 'expired';
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  if (h < 48) return `${h} h ${minutes % 60} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}
