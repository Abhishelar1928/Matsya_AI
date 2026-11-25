/**
 * District helpers. Points (PFZ advisories, prediction cells) are attributed to the
 * district of the nearest canonical landing centre.
 */

import { haversineKm } from '../expedition/engine/geodesy';
import type { LandingCentre } from '../types/map';

export const DISTRICTS = ['Palghar', 'Thane', 'Mumbai', 'Raigad', 'Ratnagiri', 'Sindhudurg'] as const;
export type District = (typeof DISTRICTS)[number];

export const DISTRICT_MR: Record<District, string> = {
  Palghar: 'पालघर',
  Thane: 'ठाणे',
  Mumbai: 'मुंबई',
  Raigad: 'रायगड',
  Ratnagiri: 'रत्नागिरी',
  Sindhudurg: 'सिंधुदुर्ग',
};

export function districtLabel(d: string, mr: boolean): string {
  return mr && d in DISTRICT_MR ? DISTRICT_MR[d as District] : d;
}

export function nearestCentre(
  centres: LandingCentre[], lat: number, lon: number,
): { centre: LandingCentre; km: number } | null {
  let best: { centre: LandingCentre; km: number } | null = null;
  for (const c of centres) {
    const km = haversineKm(lat, lon, c.latitude, c.longitude);
    if (!best || km < best.km) best = { centre: c, km };
  }
  return best;
}

export function districtOf(centres: LandingCentre[], lat: number, lon: number): string | null {
  return nearestCentre(centres, lat, lon)?.centre.district ?? null;
}
