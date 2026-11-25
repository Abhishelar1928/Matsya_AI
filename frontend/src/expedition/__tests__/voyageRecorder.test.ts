import { describe, expect, it } from 'vitest';
import { destinationPoint } from '../engine/geodesy';
import type { NavFix } from '../engine/navigationEngine';
import type { CatchRecord, ExpeditionPackage, TrackPoint, VoyageEvent } from '../types/expeditionTypes';
import { exportVoyageCsv, exportVoyageGpx, shouldRecordTrackPoint } from '../engine/voyageRecorder';

const baseFix: NavFix = {
  latitude: 18.0,
  longitude: 72.5,
  accuracy_m: 8,
  speed_mps: 3.0,
  heading_deg: 270,
  timestamp: 1_700_000_000_000,
};

describe('voyageRecorder', () => {
  it('filters simulated fixes and high-inaccuracy spikes', () => {
    expect(
      shouldRecordTrackPoint(null, { ...baseFix, simulated: true }, { stationary: false, cogDeg: 270, smoothedSogMps: 3 }, baseFix.timestamp),
    ).toBe(false);

    const last = { timestamp: baseFix.timestamp, latitude: 18.0, longitude: 72.5, cogDeg: 270 };
    expect(
      shouldRecordTrackPoint(last, { ...baseFix, accuracy_m: 150, timestamp: baseFix.timestamp + 20_000 }, { stationary: false, cogDeg: 270, smoothedSogMps: 3 }, baseFix.timestamp + 20_000),
    ).toBe(false);
  });

  it('triggers adaptive recording on >=50m move, >=15deg turn, or speed-scaled interval', () => {
    const last = { timestamp: baseFix.timestamp, latitude: 18.0, longitude: 72.5, cogDeg: 270 };
    const moved60m = destinationPoint(18.0, 72.5, 270, 0.06);
    expect(
      shouldRecordTrackPoint(last, { ...baseFix, latitude: moved60m.latitude, longitude: moved60m.longitude, timestamp: baseFix.timestamp + 5_000 }, { stationary: false, cogDeg: 270, smoothedSogMps: 3 }, baseFix.timestamp + 5_000),
    ).toBe(true);

    // Stationary: skips at 40s, records at 120s
    expect(
      shouldRecordTrackPoint(last, { ...baseFix, timestamp: baseFix.timestamp + 40_000 }, { stationary: true, cogDeg: null, smoothedSogMps: 0 }, baseFix.timestamp + 40_000),
    ).toBe(false);
    expect(
      shouldRecordTrackPoint(last, { ...baseFix, timestamp: baseFix.timestamp + 125_000 }, { stationary: true, cogDeg: null, smoothedSogMps: 0 }, baseFix.timestamp + 125_000),
    ).toBe(true);
  });

  it('exports valid GPX 1.1 XML and RFC-4180 CSV', () => {
    const pkg = {
      manifest: { package_id: 'exp-123', created_at: '2026-11-24T00:00:00Z' },
      landing_centre: { name: 'Mirkarwada', latitude: 16.9958, longitude: 73.2758 },
      destination: { name: 'PFZ & Zone', latitude: 16.9, longitude: 72.8 },
    } as unknown as ExpeditionPackage;
    const track: TrackPoint[] = [
      { client_uuid: 't1', expedition_id: 'exp-123', recorded_at: '2026-11-24T01:00:00Z', latitude: 16.95, longitude: 73.1, speed_mps: 3, heading_deg: 260, accuracy_m: 5, synced: 0 },
    ];
    const events: VoyageEvent[] = [
      { client_uuid: 'e1', expedition_id: 'exp-123', recorded_at: '2026-11-24T01:05:00Z', event_type: 'MOB_MARKED', latitude: 16.94, longitude: 73.05, detail: 'MOB', synced: 0 },
    ];
    const catches: CatchRecord[] = [
      { client_uuid: 'c1', expedition_id: 'exp-123', recorded_at: '2026-11-24T02:00:00Z', latitude: 16.9, longitude: 72.8, species: 'Silver Pomfret', weight_kg: 12.5, notes: 'Good, haul', synced: 0 },
    ];

    const gpx = exportVoyageGpx(pkg, track, events, catches);
    expect(gpx).toContain('<gpx version="1.1"');
    expect(gpx).toContain('PFZ &amp; Zone');
    expect(gpx).toContain('<trkpt lat="16.95" lon="73.1">');
    expect(gpx).toContain('MOB_MARKED');

    const csv = exportVoyageCsv(track, events, catches);
    expect(csv).toContain('TRACK,2026-11-24T01:00:00Z,16.95,73.1');
    expect(csv).toContain('"Good, haul"');
  });
});
