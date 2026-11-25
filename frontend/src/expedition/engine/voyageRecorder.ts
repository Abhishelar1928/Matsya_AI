/**
 * MatsyaAI Maharashtra — Voyage Black Box Recorder & Export (GPX / CSV).
 *
 * Implements adaptive track sampling based on vessel movement, time elapsed,
 * heading changes, and GPS accuracy, plus offline GPX 1.1 and CSV export.
 */

import { angularDiffDeg, haversineKm } from './geodesy';
import type { NavFix, NavigationSnapshot } from './navigationEngine';
import type { CatchRecord, ExpeditionPackage, TrackPoint, VoyageEvent } from '../types/expeditionTypes';

export interface SampledPointRef {
  timestamp: number;
  latitude: number;
  longitude: number;
  cogDeg: number | null;
}

/**
 * Adaptive black-box sampling predicate.
 * - Rejects severe accuracy spikes (> 100 m) unless > 120 s have passed without any fix.
 * - Records immediately on ≥ 50 m displacement when moving.
 * - Records every 15 s at higher speed (>= 4 m/s), 30 s cruising, or 120 s when stationary.
 * - Records on >= 15° heading change when displacement >= 15 m.
 */
export function shouldRecordTrackPoint(
  last: SampledPointRef | null,
  fix: NavFix,
  snapshot: Pick<NavigationSnapshot, 'stationary' | 'cogDeg' | 'smoothedSogMps'>,
  now: number = fix.timestamp,
): boolean {
  if (fix.simulated) return false;

  const elapsedMs = last ? Math.max(0, now - last.timestamp) : Infinity;

  // Reject low-accuracy spikes unless we've had a 2-minute recording drought
  if (fix.accuracy_m !== null && fix.accuracy_m > 100 && elapsedMs < 120_000) {
    return false;
  }

  if (!last) return true;

  const distKm = haversineKm(last.latitude, last.longitude, fix.latitude, fix.longitude);
  if (distKm >= 0.05) return true; // >= 50 m moved

  if (
    last.cogDeg !== null &&
    snapshot.cogDeg !== null &&
    distKm >= 0.015 &&
    Math.abs(angularDiffDeg(last.cogDeg, snapshot.cogDeg)) >= 15
  ) {
    return true;
  }

  const speed = snapshot.smoothedSogMps ?? fix.speed_mps ?? 0;
  const timeThresholdMs = snapshot.stationary
    ? 120_000
    : speed >= 4.0
      ? 15_000
      : 30_000;

  return elapsedMs >= timeThresholdMs;
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function escapeCsv(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = String(v);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function exportVoyageGpx(
  pkg: ExpeditionPackage,
  track: TrackPoint[],
  events: VoyageEvent[],
  catches: CatchRecord[],
): string {
  const lines: string[] = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<gpx version="1.1" creator="MatsyaAI Maharashtra" xmlns="http://www.topografix.com/GPX/1/1">',
    '  <metadata>',
    `    <name>${escapeXml(`${pkg.landing_centre.name} to ${pkg.destination.name}`)}</name>`,
    `    <time>${escapeXml(pkg.manifest.created_at)}</time>`,
    '  </metadata>',
    `  <wpt lat="${pkg.landing_centre.latitude}" lon="${pkg.landing_centre.longitude}"><name>${escapeXml(pkg.landing_centre.name)} (Start)</name></wpt>`,
    `  <wpt lat="${pkg.destination.latitude}" lon="${pkg.destination.longitude}"><name>${escapeXml(pkg.destination.name)} (Target)</name></wpt>`,
  ];

  for (const c of catches) {
    if (c.latitude !== null && c.longitude !== null) {
      const desc = `${c.weight_kg !== null ? `${c.weight_kg} kg` : ''} ${c.notes ?? ''}`.trim();
      lines.push(
        `  <wpt lat="${c.latitude}" lon="${c.longitude}"><time>${escapeXml(c.recorded_at)}</time><name>${escapeXml(`Catch: ${c.species}`)}</name>${desc ? `<desc>${escapeXml(desc)}</desc>` : ''}</wpt>`,
      );
    }
  }

  for (const ev of events) {
    if (ev.latitude !== null && ev.longitude !== null && (ev.event_type === 'MOB_MARKED' || ev.event_type === 'ANCHOR_SET')) {
      lines.push(
        `  <wpt lat="${ev.latitude}" lon="${ev.longitude}"><time>${escapeXml(ev.recorded_at)}</time><name>${escapeXml(ev.event_type)}</name><desc>${escapeXml(ev.detail)}</desc></wpt>`,
      );
    }
  }

  lines.push('  <trk>');
  lines.push(`    <name>${escapeXml(`Expedition ${pkg.manifest.package_id}`)}</name>`);
  lines.push('    <trkseg>');
  for (const pt of track) {
    lines.push(`      <trkpt lat="${pt.latitude}" lon="${pt.longitude}"><time>${escapeXml(pt.recorded_at)}</time></trkpt>`);
  }
  lines.push('    </trkseg>');
  lines.push('  </trk>');
  lines.push('</gpx>');
  return lines.join('\n');
}

export function exportVoyageCsv(
  track: TrackPoint[],
  events: VoyageEvent[],
  catches: CatchRecord[],
): string {
  const rows: string[] = [
    ['record_type', 'recorded_at', 'latitude', 'longitude', 'accuracy_m', 'speed_mps', 'cog_deg', 'compass_heading_deg', 'xte_km', 'detail_or_species', 'weight_kg', 'notes'].join(','),
  ];

  for (const pt of track) {
    rows.push(
      [
        'TRACK',
        pt.recorded_at,
        pt.latitude,
        pt.longitude,
        pt.accuracy_m ?? '',
        pt.speed_mps ?? '',
        pt.cog_deg ?? pt.heading_deg ?? '',
        pt.compass_heading_deg ?? '',
        pt.xte_km ?? '',
        '',
        '',
        '',
      ]
        .map(escapeCsv)
        .join(','),
    );
  }

  for (const ev of events) {
    rows.push(
      ['EVENT', ev.recorded_at, ev.latitude ?? '', ev.longitude ?? '', '', '', '', '', '', ev.event_type, '', ev.detail]
        .map(escapeCsv)
        .join(','),
    );
  }

  for (const c of catches) {
    rows.push(
      ['CATCH', c.recorded_at, c.latitude ?? '', c.longitude ?? '', '', '', '', '', '', c.species, c.weight_kg ?? '', c.notes ?? '']
        .map(escapeCsv)
        .join(','),
    );
  }

  return rows.join('\n');
}
