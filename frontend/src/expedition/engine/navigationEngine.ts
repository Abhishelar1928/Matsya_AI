/**
 * MatsyaAI Maharashtra — Centralized Marine Navigation Engine.
 *
 * Pure state machine that processes raw GPS fixes + optional physical device
 * compass heading into clean, reliable navigation telemetry:
 *  - Separates GPS Course Over Ground (COG) from physical/magnetic heading
 *  - Rejects single-sample GPS teleport jumps while confirming genuine moves
 *  - Monitors fix freshness (WAITING / LIVE / WEAK / LOST) and stationary state
 *  - Smooths Speed Over Ground (SOG) with EMA for reliable ETA estimation
 *  - Tracks waypoint progression, arrival events, XTE, and route deviation
 */

import {
  angularDiffDeg,
  compassPoint,
  etaMinutes,
  haversineKm,
  initialBearingDeg,
  normalizeDeg,
  routeProgress,
} from './geodesy';
import type { SimulationScenario } from './simulation';

export interface NavFix {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  speed_mps: number | null;
  /** Raw browser coords.heading (GPS Course Over Ground). Never treated as physical compass heading. */
  heading_deg: number | null;
  timestamp: number;
  simulated?: boolean;
  simulationScenario?: SimulationScenario;
}

export interface RoutePoint {
  index?: number;
  latitude: number;
  longitude: number;
  name?: string | null;
}

export type GpsHealth = 'WAITING' | 'LIVE' | 'WEAK' | 'LOST';
export type EtaReliability = 'reliable' | 'low_confidence' | 'unavailable';

export interface TurnInstruction {
  action: 'ON_COURSE' | 'TURN_LEFT' | 'TURN_RIGHT' | 'ARRIVED' | 'NO_HEADING';
  degrees: number;
  referenceSource: 'COG' | 'COMPASS' | 'NONE';
}

export interface NavEmittedEvent {
  type: 'WAYPOINT_ARRIVED' | 'ROUTE_DEVIATION' | 'ROUTE_RECOVERED' | 'GPS_JUMP_REJECTED' | 'DESTINATION_ARRIVED';
  timestamp: number;
  latitude: number;
  longitude: number;
  detail: string;
}

export interface NavigationConfig {
  maxAccuracyWeakM: number;
  staleFixMs: number;
  stationarySpeedMps: number;
  maxPlausibleSpeedMps: number;
  waypointArrivalKm: number;
  offTrackThresholdKm: number;
  offTrackClearKm: number;
  sogEmaAlpha: number;
  minCogStepKm: number;
}

export const DEFAULT_NAV_CONFIG: NavigationConfig = {
  maxAccuracyWeakM: 50,
  staleFixMs: 30_000,
  stationarySpeedMps: 0.5, // ~1 knot
  maxPlausibleSpeedMps: 40, // ~78 knots — anything faster in one jump is a GPS spike
  waypointArrivalKm: 0.25, // 250 m capture radius
  offTrackThresholdKm: 0.5, // 500 m XTE alert
  offTrackClearKm: 0.35, // hysteresis clear
  sogEmaAlpha: 0.35,
  minCogStepKm: 0.015, // 15 m minimum displacement to derive COG
};

export interface NavigationState {
  waypoints: RoutePoint[];
  activeWaypointIndex: number;
  arrivedDestination: boolean;
  lastAcceptedFix: NavFix | null;
  pendingJumpFix: NavFix | null;
  smoothedSogMps: number | null;
  lastCogDeg: number | null;
  isOffTrack: boolean;
  rejectedJumpCount: number;
}

export interface NavigationSnapshot {
  gpsHealth: GpsHealth;
  fixAgeMs: number | null;
  fix: NavFix | null;
  sogMps: number | null;
  smoothedSogMps: number | null;
  stationary: boolean;
  /** GPS Course Over Ground (degrees 0..360), null when stationary or unreliable. */
  cogDeg: number | null;
  cogCompass: string | null;
  /** Physical device compass heading (degrees 0..360), null when unsupported/unavailable. */
  compassHeadingDeg: number | null;
  compassHeadingCompass: string | null;
  /** Signed difference (cogDeg - compassHeadingDeg) in (-180, 180]. */
  headingCogDiffDeg: number | null;
  targetBearingDeg: number;
  targetCompass: string;
  nextWaypointBearingDeg: number;
  nextWaypointCompass: string;
  nextWaypointIndex: number;
  totalWaypoints: number;
  distanceToNextWaypointKm: number;
  remainingDistanceKm: number;
  totalRouteKm: number;
  crossTrackKm: number;
  alongTrackKm: number;
  isOffTrack: boolean;
  arrivedDestination: boolean;
  etaMinutes: number | null;
  etaReliability: EtaReliability;
  turnInstruction: TurnInstruction;
  rejectedJumpCount: number;
  jumpRejectedThisSample: boolean;
}

export function totalPolylineKm(waypoints: RoutePoint[]): number {
  let sum = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    sum += haversineKm(
      waypoints[i].latitude,
      waypoints[i].longitude,
      waypoints[i + 1].latitude,
      waypoints[i + 1].longitude,
    );
  }
  return sum;
}

export function createNavigationState(
  waypoints: RoutePoint[],
  initialWaypointIndex: number = 1,
): NavigationState {
  const maxIdx = Math.max(0, waypoints.length - 1);
  return {
    waypoints,
    activeWaypointIndex: Math.min(Math.max(1, initialWaypointIndex), maxIdx || 0),
    arrivedDestination: false,
    lastAcceptedFix: null,
    pendingJumpFix: null,
    smoothedSogMps: null,
    lastCogDeg: null,
    isOffTrack: false,
    rejectedJumpCount: 0,
  };
}

export function evaluateGpsHealth(
  fix: NavFix | null,
  now: number,
  config: NavigationConfig = DEFAULT_NAV_CONFIG,
): { gpsHealth: GpsHealth; fixAgeMs: number | null } {
  if (!fix) return { gpsHealth: 'WAITING', fixAgeMs: null };
  const fixAgeMs = Math.max(0, now - fix.timestamp);
  if (fixAgeMs > config.staleFixMs) {
    return { gpsHealth: 'LOST', fixAgeMs };
  }
  if (fix.accuracy_m === null || !Number.isFinite(fix.accuracy_m) || fix.accuracy_m > config.maxAccuracyWeakM) {
    return { gpsHealth: 'WEAK', fixAgeMs };
  }
  return { gpsHealth: 'LIVE', fixAgeMs };
}

function isJump(prev: NavFix, next: NavFix, cfg: NavigationConfig): boolean {
  const dt = (next.timestamp - prev.timestamp) / 1000;
  if (dt <= 0) return false;
  const distM = haversineKm(prev.latitude, prev.longitude, next.latitude, next.longitude) * 1000;
  const impliedSpeed = distM / dt;
  // Only treat as spike if displacement exceeds accuracy uncertainty + plausible speed
  const tolM = (prev.accuracy_m ?? 25) + (next.accuracy_m ?? 25) + 150;
  return distM > tolM && impliedSpeed > cfg.maxPlausibleSpeedMps;
}

export function processFix(
  prevState: NavigationState,
  incomingFix: NavFix | null,
  compassHeadingDeg: number | null,
  now: number = Date.now(),
  config: NavigationConfig = DEFAULT_NAV_CONFIG,
): { state: NavigationState; snapshot: NavigationSnapshot; emittedEvents: NavEmittedEvent[] } {
  const emittedEvents: NavEmittedEvent[] = [];
  const wps = prevState.waypoints;
  const totalRouteKm = totalPolylineKm(wps);
  const dest = wps[wps.length - 1] ?? { latitude: 0, longitude: 0 };
  const start = wps[0] ?? dest;

  let state = { ...prevState };
  let jumpRejectedThisSample = false;

  if (incomingFix) {
    const prev = state.lastAcceptedFix;
    const sameSample = prev && prev.timestamp === incomingFix.timestamp &&
      prev.latitude === incomingFix.latitude && prev.longitude === incomingFix.longitude;

    if (!sameSample) {
      if (prev && !incomingFix.simulated && isJump(prev, incomingFix, config)) {
        // Check if a pending jump already exists near this new location (confirms real relocation)
        const pending = state.pendingJumpFix;
        if (pending && !isJump(pending, incomingFix, config)) {
          state.pendingJumpFix = null;
          state.lastAcceptedFix = incomingFix;
        } else {
          state.pendingJumpFix = incomingFix;
          state.rejectedJumpCount += 1;
          jumpRejectedThisSample = true;
          emittedEvents.push({
            type: 'GPS_JUMP_REJECTED',
            timestamp: incomingFix.timestamp,
            latitude: incomingFix.latitude,
            longitude: incomingFix.longitude,
            detail: 'Single-sample GPS position jump rejected',
          });
        }
      } else {
        state.pendingJumpFix = null;

        // Derive SOG
        let rawSog = incomingFix.speed_mps !== null && Number.isFinite(incomingFix.speed_mps) && incomingFix.speed_mps >= 0
          ? incomingFix.speed_mps
          : null;
        if (rawSog === null && prev) {
          const dt = (incomingFix.timestamp - prev.timestamp) / 1000;
          const dKm = haversineKm(prev.latitude, prev.longitude, incomingFix.latitude, incomingFix.longitude);
          if (dt > 0.5 && dKm > 0.003) {
            rawSog = (dKm * 1000) / dt;
          } else if (dt > 0.5) {
            rawSog = 0;
          }
        }

        if (rawSog !== null) {
          state.smoothedSogMps = state.smoothedSogMps === null
            ? rawSog
            : config.sogEmaAlpha * rawSog + (1 - config.sogEmaAlpha) * state.smoothedSogMps;
        }

        // Derive COG strictly when moving meaningfully and accuracy is acceptable
        const accOk = incomingFix.accuracy_m !== null && incomingFix.accuracy_m <= config.maxAccuracyWeakM;
        const speedForCog = state.smoothedSogMps ?? rawSog ?? 0;
        const isMoving = speedForCog >= config.stationarySpeedMps;
        let cog: number | null = null;

        if (isMoving && (accOk || incomingFix.simulated)) {
          if (incomingFix.heading_deg !== null && Number.isFinite(incomingFix.heading_deg)) {
            cog = normalizeDeg(incomingFix.heading_deg);
          } else if (prev) {
            const stepKm = haversineKm(prev.latitude, prev.longitude, incomingFix.latitude, incomingFix.longitude);
            if (stepKm >= config.minCogStepKm) {
              cog = initialBearingDeg(prev.latitude, prev.longitude, incomingFix.latitude, incomingFix.longitude);
            } else {
              cog = state.lastCogDeg;
            }
          }
        }
        state.lastCogDeg = cog;
        state.lastAcceptedFix = incomingFix;
      }
    }
  }

  const activeFix = state.lastAcceptedFix;
  const { gpsHealth, fixAgeMs } = evaluateGpsHealth(activeFix, now, config);
  const normCompass = compassHeadingDeg !== null && Number.isFinite(compassHeadingDeg)
    ? normalizeDeg(compassHeadingDeg)
    : null;

  const refLat = activeFix ? activeFix.latitude : start.latitude;
  const refLon = activeFix ? activeFix.longitude : start.longitude;

  const targetBearingDeg = initialBearingDeg(refLat, refLon, dest.latitude, dest.longitude);
  const remainingDirectKm = haversineKm(refLat, refLon, dest.latitude, dest.longitude);

  let nextWpIdx = Math.min(state.activeWaypointIndex, Math.max(0, wps.length - 1));
  let xteKm = 0;
  let alongKm = 0;
  let distToNextKm = remainingDirectKm;
  let remainingRouteKm = remainingDirectKm;

  if (wps.length >= 2) {
    const prog = routeProgress(wps, refLat, refLon, Math.max(1, state.activeWaypointIndex));
    if (prog) {
      nextWpIdx = Math.max(state.activeWaypointIndex, prog.nextWaypointIndex);
      xteKm = prog.crossTrackKm;
      alongKm = prog.alongTrackKm;
      distToNextKm = prog.distanceToNextKm;
      remainingRouteKm = prog.distanceToEndKm;

      // Advance waypoint upon entering capture radius
      if (activeFix && gpsHealth !== 'LOST') {
        while (nextWpIdx < wps.length - 1 &&
          haversineKm(activeFix.latitude, activeFix.longitude, wps[nextWpIdx].latitude, wps[nextWpIdx].longitude) <= config.waypointArrivalKm) {
          emittedEvents.push({
            type: 'WAYPOINT_ARRIVED',
            timestamp: activeFix.timestamp,
            latitude: activeFix.latitude,
            longitude: activeFix.longitude,
            detail: `Arrived at waypoint ${nextWpIdx}`,
          });
          nextWpIdx += 1;
        }
        state.activeWaypointIndex = nextWpIdx;
        distToNextKm = haversineKm(activeFix.latitude, activeFix.longitude, wps[nextWpIdx].latitude, wps[nextWpIdx].longitude);

        if (!state.arrivedDestination &&
          haversineKm(activeFix.latitude, activeFix.longitude, dest.latitude, dest.longitude) <= config.waypointArrivalKm) {
          state.arrivedDestination = true;
          emittedEvents.push({
            type: 'DESTINATION_ARRIVED',
            timestamp: activeFix.timestamp,
            latitude: activeFix.latitude,
            longitude: activeFix.longitude,
            detail: 'Arrived at destination zone',
          });
        }
      }
    }
  }

  // Off-track hysteresis
  if (activeFix && wps.length >= 2) {
    const absXte = Math.abs(xteKm);
    if (!state.isOffTrack && absXte > config.offTrackThresholdKm) {
      state.isOffTrack = true;
      emittedEvents.push({
        type: 'ROUTE_DEVIATION',
        timestamp: activeFix.timestamp,
        latitude: activeFix.latitude,
        longitude: activeFix.longitude,
        detail: `Off track by ${absXte.toFixed(2)} km`,
      });
    } else if (state.isOffTrack && absXte <= config.offTrackClearKm) {
      state.isOffTrack = false;
      emittedEvents.push({
        type: 'ROUTE_RECOVERED',
        timestamp: activeFix.timestamp,
        latitude: activeFix.latitude,
        longitude: activeFix.longitude,
        detail: 'Returned within route corridor',
      });
    }
  }

  const nextWp = wps[nextWpIdx] ?? dest;
  const nextWaypointBearingDeg = initialBearingDeg(refLat, refLon, nextWp.latitude, nextWp.longitude);

  const rawSogMps = activeFix?.speed_mps ?? null;
  const effectiveSog = state.smoothedSogMps;
  const stationary = effectiveSog === null ? true : effectiveSog < config.stationarySpeedMps;
  const cogDeg = !stationary && gpsHealth !== 'LOST' ? state.lastCogDeg : null;

  const headingCogDiffDeg =
    cogDeg !== null && normCompass !== null ? angularDiffDeg(normCompass, cogDeg) : null;

  // ETA & reliability
  let etaMin: number | null = null;
  let etaReliability: EtaReliability = 'unavailable';
  if (gpsHealth !== 'LOST' && !stationary && effectiveSog !== null) {
    etaMin = etaMinutes(remainingRouteKm, effectiveSog);
    if (etaMin !== null) {
      etaReliability = gpsHealth === 'LIVE' ? 'reliable' : 'low_confidence';
    }
  }

  // Turn instruction (prefers live COG when moving, falls back to physical compass)
  let turnInstruction: TurnInstruction;
  if (state.arrivedDestination) {
    turnInstruction = { action: 'ARRIVED', degrees: 0, referenceSource: 'NONE' };
  } else {
    const refDir = cogDeg ?? normCompass;
    const refSource: 'COG' | 'COMPASS' | 'NONE' = cogDeg !== null ? 'COG' : normCompass !== null ? 'COMPASS' : 'NONE';
    if (refDir === null) {
      turnInstruction = { action: 'NO_HEADING', degrees: 0, referenceSource: 'NONE' };
    } else {
      const diff = angularDiffDeg(refDir, nextWaypointBearingDeg);
      if (Math.abs(diff) < 5) {
        turnInstruction = { action: 'ON_COURSE', degrees: Math.round(Math.abs(diff)), referenceSource: refSource };
      } else if (diff > 0) {
        turnInstruction = { action: 'TURN_RIGHT', degrees: Math.round(diff), referenceSource: refSource };
      } else {
        turnInstruction = { action: 'TURN_LEFT', degrees: Math.round(Math.abs(diff)), referenceSource: refSource };
      }
    }
  }

  return {
    state,
    emittedEvents,
    snapshot: {
      gpsHealth,
      fixAgeMs,
      fix: activeFix,
      sogMps: rawSogMps,
      smoothedSogMps: effectiveSog,
      stationary,
      cogDeg,
      cogCompass: cogDeg !== null ? compassPoint(cogDeg) : null,
      compassHeadingDeg: normCompass,
      compassHeadingCompass: normCompass !== null ? compassPoint(normCompass) : null,
      headingCogDiffDeg,
      targetBearingDeg,
      targetCompass: compassPoint(targetBearingDeg),
      nextWaypointBearingDeg,
      nextWaypointCompass: compassPoint(nextWaypointBearingDeg),
      nextWaypointIndex: nextWpIdx,
      totalWaypoints: wps.length,
      distanceToNextWaypointKm: distToNextKm,
      remainingDistanceKm: remainingRouteKm,
      totalRouteKm,
      crossTrackKm: xteKm,
      alongTrackKm: alongKm,
      isOffTrack: state.isOffTrack,
      arrivedDestination: state.arrivedDestination,
      etaMinutes: etaMin,
      etaReliability,
      turnInstruction,
      rejectedJumpCount: state.rejectedJumpCount,
      jumpRejectedThisSample,
    },
  };
}
