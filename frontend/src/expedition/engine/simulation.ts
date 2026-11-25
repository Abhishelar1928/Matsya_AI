/**
 * MatsyaAI Maharashtra — Isolated Navigation Simulation Engine.
 *
 * Strictly for testing & desktop verification without GPS hardware.
 * Every generated fix is tagged `simulated: true` and MUST NEVER be persisted
 * as real voyage telemetry or synced to production databases.
 */

import { destinationPoint, haversineKm, initialBearingDeg, intermediatePoint } from './geodesy';
import type { NavFix, RoutePoint } from './navigationEngine';

export type SimulationScenario =
  | 'normal'
  | 'stationary'
  | 'gps_loss'
  | 'poor_accuracy'
  | 'position_jump'
  | 'route_deviation'
  | 'waypoint_arrival'
  | 'north_wrap'
  | 'null_speed_heading';

export interface ScenarioDescriptor {
  id: SimulationScenario;
  labelEn: string;
  labelMr: string;
}

export const SIMULATION_SCENARIOS: ScenarioDescriptor[] = [
  { id: 'normal', labelEn: 'Normal voyage along route', labelMr: 'मार्गावरून सामान्य प्रवास' },
  { id: 'stationary', labelEn: 'Stationary vessel (anchored)', labelMr: 'स्थिर बोट (नांगरलेली)' },
  { id: 'gps_loss', labelEn: 'GPS signal loss after 5s', labelMr: '५ सेकंदांनंतर GPS सिग्नल खंडित' },
  { id: 'poor_accuracy', labelEn: 'Poor GPS accuracy (>120 m)', labelMr: 'कमकुवत GPS अचूकता (>120 m)' },
  { id: 'position_jump', labelEn: 'Sudden GPS jump spike', labelMr: 'अचानक GPS स्थान झेप' },
  { id: 'route_deviation', labelEn: 'Off-track drift (1.2 km)', labelMr: 'मार्गापासून बाजूला सरकणे (1.2 km)' },
  { id: 'waypoint_arrival', labelEn: 'Waypoint arrival sequence', labelMr: 'मार्गबिंदू आगमन क्रम' },
  { id: 'north_wrap', labelEn: '359° ↔ 0° North compass wrap', labelMr: '359° ↔ 0° उत्तर दिशा संक्रमण' },
  { id: 'null_speed_heading', labelEn: 'Null speed & heading fallback', labelMr: 'गती व दिशा उपलब्ध नसणे' },
];

export interface SimulationConfig {
  points: RoutePoint[];
  scenario: SimulationScenario;
  speedKnots?: number;
}

function interpolateSpherical(
  points: RoutePoint[],
  km: number,
): { lat: number; lon: number; brg: number; done: boolean } {
  if (points.length === 0) return { lat: 18.9, lon: 72.7, brg: 0, done: true };
  if (points.length === 1) return { lat: points[0].latitude, lon: points[0].longitude, brg: 0, done: true };

  let remaining = Math.max(0, km);
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const leg = haversineKm(a.latitude, a.longitude, b.latitude, b.longitude);
    const brg = initialBearingDeg(a.latitude, a.longitude, b.latitude, b.longitude);
    if (remaining <= leg || i === points.length - 2) {
      const f = leg === 0 ? 1 : Math.min(1, remaining / leg);
      const pt = intermediatePoint(a.latitude, a.longitude, b.latitude, b.longitude, f);
      return {
        lat: pt.latitude,
        lon: pt.longitude,
        brg,
        done: i === points.length - 2 && f >= 1,
      };
    }
    remaining -= leg;
  }
  const last = points[points.length - 1];
  return { lat: last.latitude, lon: last.longitude, brg: 0, done: true };
}

/**
 * Pure deterministic step generator for simulation scenarios.
 * `tickIndex` increments by 1 per second.
 */
export function generateSimulatedFix(
  cfg: SimulationConfig,
  tickIndex: number,
  nowMs: number,
): NavFix | null {
  const pts = cfg.points;
  const start = pts[0] ?? { latitude: 18.9172, longitude: 72.8258 };
  const speedMps = (cfg.speedKnots ?? 40) * 0.514444;
  const scenario = cfg.scenario;

  if (scenario === 'stationary') {
    // Tiny GPS jitter (~2 m) while stationary
    const jitterLat = Math.sin(tickIndex) * 0.000015;
    const jitterLon = Math.cos(tickIndex) * 0.000015;
    return {
      latitude: start.latitude + jitterLat,
      longitude: start.longitude + jitterLon,
      accuracy_m: 6,
      speed_mps: 0.05,
      heading_deg: (tickIndex * 47) % 360, // noisy idle heading that engine should ignore
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  if (scenario === 'gps_loss') {
    if (tickIndex >= 5) {
      // Simulate frozen/stale fix timestamp 40 s in the past so engine flags LOST
      return null;
    }
  }

  if (scenario === 'north_wrap') {
    const legStart = start;
    const baseBrg = tickIndex % 2 === 0 ? 357 : 3;
    const dist = (speedMps * tickIndex) / 1000;
    const pos = destinationPoint(legStart.latitude, legStart.longitude, 0, dist);
    return {
      latitude: pos.latitude,
      longitude: pos.longitude,
      accuracy_m: 8,
      speed_mps: speedMps,
      heading_deg: baseBrg,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  if (scenario === 'waypoint_arrival' && pts.length >= 2) {
    // Place vessel approaching waypoint 1 and passing through it
    const wp1 = pts[1];
    const brg = initialBearingDeg(start.latitude, start.longitude, wp1.latitude, wp1.longitude);
    const offsetKm = Math.max(0, 0.8 - tickIndex * 0.15);
    const pos = offsetKm > 0
      ? destinationPoint(wp1.latitude, wp1.longitude, (brg + 180) % 360, offsetKm)
      : { latitude: wp1.latitude, longitude: wp1.longitude };
    return {
      latitude: pos.latitude,
      longitude: pos.longitude,
      accuracy_m: 5,
      speed_mps: 8,
      heading_deg: brg,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  const distKm = (speedMps * tickIndex) / 1000;
  const p = interpolateSpherical(pts, distKm);

  if (scenario === 'position_jump' && tickIndex === 4) {
    // 50 km impossible single-sample spike
    const jumped = destinationPoint(p.lat, p.lon, 270, 50);
    return {
      latitude: jumped.latitude,
      longitude: jumped.longitude,
      accuracy_m: 15,
      speed_mps: speedMps,
      heading_deg: p.brg,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  if (scenario === 'route_deviation' && tickIndex >= 3) {
    // Drift 1.2 km starboard (right of track)
    const deviated = destinationPoint(p.lat, p.lon, (p.brg + 90) % 360, 1.2);
    return {
      latitude: deviated.latitude,
      longitude: deviated.longitude,
      accuracy_m: 10,
      speed_mps: p.done ? 0 : speedMps,
      heading_deg: p.brg,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  if (scenario === 'poor_accuracy') {
    return {
      latitude: p.lat,
      longitude: p.lon,
      accuracy_m: 160,
      speed_mps: p.done ? 0 : speedMps,
      heading_deg: p.brg,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  if (scenario === 'null_speed_heading') {
    return {
      latitude: p.lat,
      longitude: p.lon,
      accuracy_m: 12,
      speed_mps: null,
      heading_deg: null,
      timestamp: nowMs,
      simulated: true,
      simulationScenario: scenario,
    };
  }

  return {
    latitude: p.lat,
    longitude: p.lon,
    accuracy_m: 5,
    speed_mps: p.done ? 0 : speedMps,
    heading_deg: p.brg,
    timestamp: nowMs,
    simulated: true,
    simulationScenario: scenario,
  };
}
