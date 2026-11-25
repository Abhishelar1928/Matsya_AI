/**
 * MatsyaAI Maharashtra — Device GPS & Compass hook for at-sea navigation.
 *
 * Uses navigator.geolocation.watchPosition (works offline — GPS needs no network),
 * optional DeviceOrientationEvent for physical compass heading (strictly separated
 * from GPS Course Over Ground), and the Screen Wake Lock API.
 *
 * Tracks foreground/visibility interruptions explicitly because browser PWAs
 * suspend JS execution when backgrounded or locked.
 */

import { useEffect, useRef, useState } from 'react';
import { normalizeDeg } from '../engine/geodesy';
import type { NavFix } from '../engine/navigationEngine';
import { generateSimulatedFix, type SimulationScenario } from '../engine/simulation';

export type Fix = NavFix;

export type GeoErrorCode =
  | 'PERMISSION_DENIED'
  | 'POSITION_UNAVAILABLE'
  | 'TIMEOUT'
  | 'INSECURE_CONTEXT'
  | 'UNSUPPORTED'
  | null;
export type PermissionStateX = 'granted' | 'denied' | 'prompt' | 'unknown';

export interface GeoState {
  fix: Fix | null;
  error: string | null;
  errorCode: GeoErrorCode;
  supported: boolean;
  secure: boolean;
  permission: PermissionStateX;
  highAccuracy: boolean;
  wakeLock: boolean;
  simulated: boolean;
  attempts: number;
  compassSupported: boolean;
  compassHeadingDeg: number | null;
  compassSource: 'absolute' | 'webkit' | 'unavailable';
  visibilityState: DocumentVisibilityState;
  lastInterruptedAt: number | null;
  lastResumedAt: number | null;
}

export interface SimulationRoute {
  points: { latitude: number; longitude: number }[];
  speedKnots?: number;
  scenario?: SimulationScenario;
}

const CODE_MAP: Record<number, GeoErrorCode> = {
  1: 'PERMISSION_DENIED',
  2: 'POSITION_UNAVAILABLE',
  3: 'TIMEOUT',
};

export function useGeolocation(enabled: boolean, simulation: SimulationRoute | null = null): GeoState {
  const supported = typeof navigator !== 'undefined' && 'geolocation' in navigator;
  const secure = typeof window === 'undefined' ? true : window.isSecureContext;

  const [state, setState] = useState<GeoState>({
    fix: null,
    error: null,
    errorCode: !supported ? 'UNSUPPORTED' : !secure ? 'INSECURE_CONTEXT' : null,
    supported,
    secure,
    permission: 'unknown',
    highAccuracy: true,
    wakeLock: false,
    simulated: false,
    attempts: 0,
    compassSupported: false,
    compassHeadingDeg: null,
    compassSource: 'unavailable',
    visibilityState: typeof document !== 'undefined' ? document.visibilityState : 'visible',
    lastInterruptedAt: null,
    lastResumedAt: null,
  });

  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);
  const [highAccuracy, setHighAccuracy] = useState(true);

  // Permission state
  useEffect(() => {
    if (!enabled || !navigator.permissions?.query) return;
    let status: PermissionStatus | null = null;
    navigator.permissions
      .query({ name: 'geolocation' as PermissionName })
      .then((s) => {
        status = s;
        setState((st) => ({ ...st, permission: s.state as PermissionStateX }));
        s.onchange = () => setState((st) => ({ ...st, permission: s.state as PermissionStateX }));
      })
      .catch(() => { /* not supported */ });
    return () => {
      if (status) status.onchange = null;
    };
  }, [enabled]);

  // Wake lock & explicit visibility interruption tracking
  useEffect(() => {
    if (!enabled) return;
    const requestWakeLock = async () => {
      try {
        const nav = navigator as Navigator & {
          wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> };
        };
        if (nav.wakeLock && document.visibilityState === 'visible') {
          wakeLockRef.current = await nav.wakeLock.request('screen');
          setState((s) => ({ ...s, wakeLock: true }));
        }
      } catch {
        setState((s) => ({ ...s, wakeLock: false }));
      }
    };
    void requestWakeLock();

    const onVisibility = () => {
      const vis = document.visibilityState;
      const now = Date.now();
      if (vis === 'hidden') {
        setState((s) => ({ ...s, visibilityState: vis, wakeLock: false, lastInterruptedAt: now }));
      } else {
        setState((s) => ({ ...s, visibilityState: vis, lastResumedAt: now }));
        void requestWakeLock();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      void wakeLockRef.current?.release();
      wakeLockRef.current = null;
      setState((s) => ({ ...s, wakeLock: false }));
    };
  }, [enabled]);

  // Separate physical/magnetic compass listener (DeviceOrientation)
  useEffect(() => {
    if (!enabled || typeof window === 'undefined' || !('DeviceOrientationEvent' in window)) return;
    const handleOrientation = (ev: Event) => {
      const e = ev as DeviceOrientationEvent & { webkitCompassHeading?: number };
      if (typeof e.webkitCompassHeading === 'number' && Number.isFinite(e.webkitCompassHeading)) {
        setState((s) => ({
          ...s,
          compassSupported: true,
          compassHeadingDeg: normalizeDeg(e.webkitCompassHeading!),
          compassSource: 'webkit',
        }));
      } else if (e.absolute && typeof e.alpha === 'number' && Number.isFinite(e.alpha)) {
        setState((s) => ({
          ...s,
          compassSupported: true,
          compassHeadingDeg: normalizeDeg(360 - e.alpha!),
          compassSource: 'absolute',
        }));
      }
    };
    window.addEventListener('deviceorientationabsolute', handleOrientation, true);
    window.addEventListener('deviceorientation', handleOrientation, true);
    return () => {
      window.removeEventListener('deviceorientationabsolute', handleOrientation, true);
      window.removeEventListener('deviceorientation', handleOrientation, true);
    };
  }, [enabled]);

  // Simulation mode (isolated from production GPS)
  useEffect(() => {
    if (!enabled || !simulation || simulation.points.length < 1) return;
    let tickIdx = 0;
    setState((s) => ({ ...s, simulated: true, error: null, errorCode: null }));
    const step = () => {
      const generated = generateSimulatedFix(
        {
          points: simulation.points,
          scenario: simulation.scenario ?? 'normal',
          speedKnots: simulation.speedKnots,
        },
        tickIdx,
        Date.now(),
      );
      tickIdx += 1;
      if (generated) {
        setState((s) => ({ ...s, fix: generated }));
      }
    };
    step();
    const id = setInterval(step, 1000);
    return () => {
      clearInterval(id);
      setState((s) => ({ ...s, simulated: false, fix: null }));
    };
  }, [enabled, simulation]);

  // Real GPS watchPosition
  useEffect(() => {
    if (!enabled || simulation || !supported || !secure) return;

    setState((s) => ({ ...s, highAccuracy, attempts: s.attempts + 1 }));
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords;
        const rawHeading = c.heading !== null && Number.isFinite(c.heading) ? normalizeDeg(c.heading) : null;
        const rawSpeed = c.speed !== null && Number.isFinite(c.speed) && c.speed >= 0 ? c.speed : null;
        const fix: Fix = {
          latitude: c.latitude,
          longitude: c.longitude,
          accuracy_m: c.accuracy !== null && Number.isFinite(c.accuracy) ? c.accuracy : null,
          speed_mps: rawSpeed,
          heading_deg: rawHeading,
          timestamp: pos.timestamp || Date.now(),
        };
        setState((s) => ({ ...s, fix, error: null, errorCode: null, permission: 'granted' }));
      },
      (err) => {
        const code = CODE_MAP[err.code] ?? 'POSITION_UNAVAILABLE';
        setState((s) => ({
          ...s,
          error: err.message,
          errorCode: code,
          ...(code === 'PERMISSION_DENIED' ? { permission: 'denied' as const } : {}),
        }));
        if (code !== 'PERMISSION_DENIED' && highAccuracy) setHighAccuracy(false);
      },
      highAccuracy
        ? { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
        : { enableHighAccuracy: false, maximumAge: 60000, timeout: 60000 },
    );

    return () => navigator.geolocation.clearWatch(id);
  }, [enabled, simulation, supported, secure, highAccuracy]);

  return state;
}

/** Human-readable help for a GPS problem, in English or Marathi. */
export function gpsHelp(state: GeoState, mr: boolean): { title: string; steps: string[] } | null {
  if (state.fix) return null;
  switch (state.errorCode) {
    case 'UNSUPPORTED':
      return {
        title: mr ? 'या ब्राउझरमध्ये GPS उपलब्ध नाही' : 'This browser has no location support',
        steps: [mr ? 'Chrome किंवा Edge वापरा.' : 'Use Chrome or Edge.'],
      };
    case 'INSECURE_CONTEXT':
      return {
        title: mr ? 'GPS साठी सुरक्षित (HTTPS) कनेक्शन आवश्यक' : 'GPS is blocked on an insecure (HTTP) address',
        steps: mr
          ? [`सध्याचा पत्ता: ${location.origin}`, 'संगणकावर http://localhost:5173 उघडा, किंवा फोनसाठी HTTPS वापरा.']
          : [`Current address: ${location.origin}`, 'On this PC open http://localhost:5173 instead, or serve over HTTPS for phones.'],
      };
    case 'PERMISSION_DENIED':
      return {
        title: mr ? 'स्थान परवानगी नाकारली आहे' : 'Location permission is blocked',
        steps: mr
          ? ['पत्ता-पट्टीतील 🔒/ⓘ चिन्हावर क्लिक करा → Location → Allow.', 'पान रीलोड करा.', 'Windows: Settings → Privacy & security → Location चालू असल्याची खात्री करा.']
          : ['Click the 🔒/ⓘ icon in the address bar → Location → Allow.', 'Reload the page.', 'Windows: Settings → Privacy & security → Location must be On.'],
      };
    case 'TIMEOUT':
    case 'POSITION_UNAVAILABLE':
      return {
        title: mr ? 'स्थान मिळत नाही' : 'No position fix yet',
        steps: mr
          ? ['Wi-Fi / GPS चालू ठेवा.', 'Windows: Settings → Privacy & security → Location चालू करा.', 'चाचणीसाठी खालील "चाचणी सिम्युलेशन" वापरा.']
          : ['Keep GPS / Wi-Fi ON.', 'Windows: Settings → Privacy & security → Location must be On.', 'For testing, use the Simulation test panel below.'],
      };
    default:
      if (state.permission === 'prompt') {
        return {
          title: mr ? 'स्थान परवानगी द्या' : 'Allow location access',
          steps: [mr ? 'ब्राउझरच्या पॉप-अपमध्ये "Allow" दाबा.' : 'Press "Allow" in the browser prompt.'],
        };
      }
      return null;
  }
}
