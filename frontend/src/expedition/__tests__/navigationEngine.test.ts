import { describe, expect, it } from 'vitest';
import { destinationPoint } from '../engine/geodesy';
import { createNavigationState, processFix, type NavFix } from '../engine/navigationEngine';
import { generateSimulatedFix } from '../engine/simulation';

const wps = [
  { index: 0, latitude: 18.0, longitude: 72.8, name: 'Start' },
  { index: 1, latitude: 18.0, longitude: 72.5, name: 'WP1' },
  { index: 2, latitude: 18.0, longitude: 72.2, name: 'Dest' },
];

const mkFix = (lat: number, lon: number, overrides: Partial<NavFix> = {}): NavFix => ({
  latitude: lat,
  longitude: lon,
  accuracy_m: 6,
  speed_mps: 5,
  heading_deg: 270,
  timestamp: 1_700_000_000_000,
  ...overrides,
});

describe('navigationEngine', () => {
  it('suppresses noisy COG when vessel is stationary while keeping physical compass separate', () => {
    const s0 = createNavigationState(wps);
    const fix = mkFix(18.0, 72.8, { speed_mps: 0.1, heading_deg: 123 });
    const { snapshot } = processFix(s0, fix, 265, fix.timestamp);
    expect(snapshot.stationary).toBe(true);
    expect(snapshot.cogDeg).toBeNull();
    expect(snapshot.compassHeadingDeg).toBe(265);
    expect(snapshot.etaMinutes).toBeNull();
    expect(snapshot.etaReliability).toBe('unavailable');
  });

  it('tracks live movement, separates COG vs compass heading, and calculates smoothed ETA', () => {
    let state = createNavigationState(wps);
    const t0 = 1_700_000_000_000;
    const f1 = mkFix(18.0, 72.75, { timestamp: t0, speed_mps: 6, heading_deg: 272 });
    ({ state } = processFix(state, f1, 268, t0));
    const f2 = mkFix(18.0, 72.70, { timestamp: t0 + 10_000, speed_mps: 6, heading_deg: 272 });
    const { snapshot } = processFix(state, f2, 268, t0 + 10_000);

    expect(snapshot.gpsHealth).toBe('LIVE');
    expect(snapshot.cogDeg).toBe(272);
    expect(snapshot.compassHeadingDeg).toBe(268);
    expect(snapshot.headingCogDiffDeg).toBe(4);
    expect(snapshot.etaMinutes).toBeGreaterThan(0);
    expect(snapshot.etaReliability).toBe('reliable');
  });

  it('flags GPS LOST on stale fix (>30 s) and GPS WEAK on poor accuracy (>50 m)', () => {
    const s0 = createNavigationState(wps);
    const t0 = 1_700_000_000_000;
    const weak = mkFix(18.0, 72.75, { accuracy_m: 120, timestamp: t0 });
    const rWeak = processFix(s0, weak, null, t0 + 1000);
    expect(rWeak.snapshot.gpsHealth).toBe('WEAK');
    expect(rWeak.snapshot.etaReliability).toBe('low_confidence');

    const rLost = processFix(rWeak.state, null, null, t0 + 45_000);
    expect(rLost.snapshot.gpsHealth).toBe('LOST');
    expect(rLost.snapshot.etaReliability).toBe('unavailable');
  });

  it('rejects single-sample impossible teleport jumps and emits GPS_JUMP_REJECTED', () => {
    const t0 = 1_700_000_000_000;
    let state = createNavigationState(wps);
    ({ state } = processFix(state, mkFix(18.0, 72.75, { timestamp: t0 }), null, t0));
    const jump = mkFix(18.0, 71.5, { timestamp: t0 + 2000 }); // >130 km in 2s
    const res = processFix(state, jump, null, t0 + 2000);

    expect(res.snapshot.jumpRejectedThisSample).toBe(true);
    expect(res.snapshot.rejectedJumpCount).toBe(1);
    expect(res.snapshot.fix?.longitude).toBe(72.75);
    expect(res.emittedEvents.some((e) => e.type === 'GPS_JUMP_REJECTED')).toBe(true);
  });

  it('detects waypoint arrival and route deviation with turn guidance', () => {
    const t0 = 1_700_000_000_000;
    let state = createNavigationState(wps);

    // Move ~1.5 km north of leg (starboard of westbound track -> right of track)
    const offPt = destinationPoint(18.0, 72.65, 0, 1.5);
    const devRes = processFix(state, mkFix(offPt.latitude, offPt.longitude, { timestamp: t0, heading_deg: 270 }), null, t0);
    expect(devRes.snapshot.isOffTrack).toBe(true);
    expect(devRes.emittedEvents.some((e) => e.type === 'ROUTE_DEVIATION')).toBe(true);
    expect(devRes.snapshot.turnInstruction.action).toBe('TURN_LEFT');

    // Arrive within 100 m of WP1 (realistic 1 hour later, not a 10s teleport jump)
    const nearWp1 = destinationPoint(18.0, 72.5, 90, 0.1);
    const arrRes = processFix(devRes.state, mkFix(nearWp1.latitude, nearWp1.longitude, { timestamp: t0 + 3600_000 }), null, t0 + 3600_000);
    expect(arrRes.emittedEvents.some((e) => e.type === 'WAYPOINT_ARRIVED')).toBe(true);
    expect(arrRes.snapshot.nextWaypointIndex).toBe(2);
  });

  it('handles 359-to-0 degree north wrap and null speed/heading cleanly', () => {
    const northWps = [
      { index: 0, latitude: 18.0, longitude: 72.5 },
      { index: 1, latitude: 19.0, longitude: 72.5 },
    ];
    let state = createNavigationState(northWps);
    const t0 = 1_700_000_000_000;
    const fWrap = mkFix(18.2, 72.5, { heading_deg: 358, speed_mps: 5, timestamp: t0 });
    const resWrap = processFix(state, fWrap, null, t0);
    expect(resWrap.snapshot.turnInstruction.action).toBe('ON_COURSE');

    const simNull = generateSimulatedFix({ points: northWps, scenario: 'null_speed_heading' }, 2, t0 + 2000)!;
    expect(simNull.speed_mps).toBeNull();
    expect(simNull.heading_deg).toBeNull();
    const resNull = processFix(createNavigationState(northWps), simNull, null, t0 + 2000);
    expect(resNull.snapshot.turnInstruction.action).toBe('NO_HEADING');
  });
});
