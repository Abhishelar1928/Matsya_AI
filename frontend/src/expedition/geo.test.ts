import { describe, expect, it } from 'vitest';
import {
  alongTrackKm, compassPoint, crossTrackKm, etaMinutes, haversineKm, headingError, initialBearingDeg, routeProgress,
} from './geo';

describe('geo', () => {
  it('haversine: one degree of latitude is ~111.2 km', () => {
    expect(haversineKm(18, 72, 19, 72)).toBeCloseTo(111.2, 0);
    expect(haversineKm(18, 72, 18, 72)).toBe(0);
  });

  it('initial bearing: north = 0, west = 270', () => {
    expect(initialBearingDeg(18, 72, 19, 72)).toBeCloseTo(0, 1);
    expect(initialBearingDeg(18, 72, 18, 71)).toBeCloseTo(270, 0);
  });

  it('cross-track distance: point east of a northbound track is to the right (positive)', () => {
    const xt = crossTrackKm(17, 72, 18, 72, 17.5, 72.1);
    expect(xt).toBeGreaterThan(0);
    expect(Math.abs(xt)).toBeCloseTo(10.6, 0); // 0.1° lon at 17.5°N ≈ 10.6 km
    expect(crossTrackKm(17, 72, 18, 72, 17.5, 71.9)).toBeLessThan(0);
  });

  it('along-track distance: midpoint is halfway', () => {
    const total = haversineKm(17, 72, 18, 72);
    expect(alongTrackKm(17, 72, 18, 72, 17.5, 72.05)).toBeCloseTo(total / 2, 0);
  });

  it('compass points and heading error', () => {
    expect(compassPoint(0)).toBe('N');
    expect(compassPoint(45)).toBe('NE');
    expect(compassPoint(359)).toBe('N');
    expect(compassPoint(292.5)).toBe('WNW');
    expect(headingError(350, 10)).toBe(20);
    expect(headingError(10, 350)).toBe(-20);
  });

  it('eta: null when stationary', () => {
    expect(etaMinutes(10, 0)).toBeNull();
    expect(etaMinutes(10, null)).toBeNull();
    expect(etaMinutes(3.6, 1)).toBeCloseTo(60, 5);
  });

  it('routeProgress picks the right leg and remaining distance', () => {
    const wps = [
      { latitude: 17.0, longitude: 73.0 },
      { latitude: 17.0, longitude: 72.5 },
      { latitude: 17.0, longitude: 72.0 },
    ];
    const p = routeProgress(wps, 17.01, 72.3)!;
    expect(p.nextWaypointIndex).toBe(2);
    expect(p.distanceToEndKm).toBeCloseTo(haversineKm(17.01, 72.3, 17.0, 72.0), 1);
    expect(Math.abs(p.crossTrackKm)).toBeLessThan(1.5);
    expect(routeProgress([wps[0]], 17, 72)).toBeNull();
  });
});
