import { describe, expect, it } from 'vitest';
import { DISTRICTS } from '../../lib/districts';
import {
  alongTrackKm,
  angularDiffDeg,
  compassPoint,
  crossTrackKm,
  destinationPoint,
  estimateCurrentDrift,
  etaMinutes,
  formatDms,
  haversineKm,
  headingError,
  initialBearingDeg,
  intermediatePoint,
  isPointOnLand,
  minDistanceToShallowContoursKm,
  normalizeDeg,
  routeProgress,
} from '../engine/geodesy';

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
    expect(Math.abs(xt)).toBeCloseTo(10.6, 0);
    expect(crossTrackKm(17, 72, 18, 72, 17.5, 71.9)).toBeLessThan(0);
  });

  it('along-track distance: midpoint is halfway, behind-start is negative', () => {
    const total = haversineKm(17, 72, 18, 72);
    expect(alongTrackKm(17, 72, 18, 72, 17.5, 72.05)).toBeCloseTo(total / 2, 0);
    expect(alongTrackKm(17, 72, 18, 72, 16.9, 72.0)).toBeLessThan(0);
  });

  it('compass points, normalizeDeg, and 359-to-0 heading wrapping', () => {
    expect(compassPoint(0)).toBe('N');
    expect(compassPoint(45)).toBe('NE');
    expect(compassPoint(359)).toBe('N');
    expect(compassPoint(292.5)).toBe('WNW');
    expect(normalizeDeg(-15)).toBe(345);
    expect(normalizeDeg(370)).toBe(10);
    expect(headingError(350, 10)).toBe(20);
    expect(headingError(10, 350)).toBe(-20);
    expect(angularDiffDeg(359, 1)).toBe(2);
    expect(angularDiffDeg(1, 359)).toBe(-2);
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

  it('intermediatePoint, destinationPoint, dateline crossing, and formatDms', () => {
    const mid = intermediatePoint(17, 179, 17, -179, 0.5);
    expect(Math.abs(mid.longitude)).toBeGreaterThan(179.9);
    const dst = destinationPoint(18, 72, 90, 50);
    expect(haversineKm(18, 72, dst.latitude, dst.longitude)).toBeCloseTo(50, 1);
    expect(formatDms(18.9172, 72.8258)).toContain('18°55\'');
  });

  it('isPointOnLand distinguishes Maharashtra land from Arabian Sea', () => {
    expect(isPointOnLand(19.076, 72.8777)).toBe(true); // Mumbai inland
    expect(isPointOnLand(18.5204, 73.8567)).toBe(true); // Pune
    expect(isPointOnLand(16.9902, 73.312)).toBe(true); // Ratnagiri town
    expect(isPointOnLand(18.9, 72.2)).toBe(false); // Arabian Sea off Mumbai
    expect(isPointOnLand(17.0, 72.8)).toBe(false); // Arabian Sea off Ratnagiri
  });

  it('estimateCurrentDrift computes knots, bearing, and 1h drift from U/V components', () => {
    expect(estimateCurrentDrift(null, 0.5)).toBeNull();
    const east = estimateCurrentDrift(0.5, 0, 1)!;
    expect(east.bearingDeg).toBeCloseTo(90, 1);
    expect(east.compass).toBe('E');
    expect(east.distanceKm).toBeCloseTo(1.8, 2);
    expect(east.speedKnots).toBeCloseTo(0.97, 2);

    const se = estimateCurrentDrift(0.3, -0.3, 2)!;
    expect(se.bearingDeg).toBeCloseTo(135, 1);
    expect(se.compass).toBe('SE');
  });

  it('minDistanceToShallowContoursKm measures distance to nearest GEBCO shallow contour', () => {
    const contours = [{ depth_m: 10, coordinates: [[72.75, 19.0], [72.76, 19.05]] as [number, number][] }];
    const hit = minDistanceToShallowContoursKm(19.0, 72.75, contours)!;
    expect(hit.depthM).toBe(10);
    expect(hit.distanceKm).toBeCloseTo(0, 3);
    expect(minDistanceToShallowContoursKm(19.0, 72.75, [])).toBeNull();
  });

  it('includes all 6 Maharashtra coastal districts', () => {
    expect(DISTRICTS).toEqual(['Palghar', 'Thane', 'Mumbai', 'Raigad', 'Ratnagiri', 'Sindhudurg']);
  });
});
