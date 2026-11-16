/**
 * MatsyaAI Maharashtra — Device GPS hook for at-sea navigation.
 *
 * Uses navigator.geolocation.watchPosition (works offline — GPS needs no network)
 * and the Screen Wake Lock API so tracking continues while the screen stays on.
 * Course-over-ground is derived from successive fixes when the device does not
 * report heading.
 *
 * Robustness:
 * - Starts with high accuracy; after a timeout / unavailable error it retries in
 *   low-accuracy mode (laptops without a GPS chip only have Wi-Fi positioning).
 * - Reports permission state, insecure context (HTTP on a LAN IP) and a clear
 *   error code so the UI can tell the user exactly what to fix.
 * - Optional simulation mode (desktop testing): moves a fake vessel along a route.
 *   Simulated fixes are flagged and never recorded as real track points.
 *
 * Capacitor note: swap `navigator.geolocation` for @capacitor/geolocation +
 * a background-geolocation plugin to keep tracking with the screen off.
 */

import { useEffect, useRef, useState } from 'react';
import { haversineKm, initialBearingDeg } from './geo';

export interface Fix {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
  speed_mps: number | null;
  heading_deg: number | null;
  timestamp: number;
  simulated?: boolean;
}

export type GeoErrorCode = 'PERMISSION_DENIED' | 'POSITION_UNAVAILABLE' | 'TIMEOUT' | 'INSECURE_CONTEXT' | 'UNSUPPORTED' | null;
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
}

export interface SimulationRoute {
  points: { latitude: number; longitude: number }[];
  /** Simulated speed in knots */
  speedKnots?: number;
}

const CODE_MAP: Record<number, GeoErrorCode> = { 1: 'PERMISSION_DENIED', 2: 'POSITION_UNAVAILABLE', 3: 'TIMEOUT' };

function interpolate(points: { latitude: number; longitude: number }[], km: number): { lat: number; lon: number; brg: number; done: boolean } {
  let remaining = km;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const leg = haversineKm(a.latitude, a.longitude, b.latitude, b.longitude);
    const brg = initialBearingDeg(a.latitude, a.longitude, b.latitude, b.longitude);
    if (remaining <= leg || i === points.length - 2) {
      const f = leg === 0 ? 1 : Math.min(1, remaining / leg);
      return {
        lat: a.latitude + (b.latitude - a.latitude) * f,
        lon: a.longitude + (b.longitude - a.longitude) * f,
        brg,
        done: i === points.length - 2 && f >= 1,
      };
    }
    remaining -= leg;
  }
  const last = points[points.length - 1];
  return { lat: last.latitude, lon: last.longitude, brg: 0, done: true };
}

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
  });
  const lastFix = useRef<Fix | null>(null);
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);
  const [highAccuracy, setHighAccuracy] = useState(true);

  // Permission state (Chrome/Edge/Firefox support querying 'geolocation')
  useEffect(() => {
    if (!enabled || !navigator.permissions?.query) return;
    let status: PermissionStatus | null = null;
    navigator.permissions.query({ name: 'geolocation' as PermissionName }).then((s) => {
      status = s;
      setState((st) => ({ ...st, permission: s.state as PermissionStateX }));
      s.onchange = () => setState((st) => ({ ...st, permission: s.state as PermissionStateX }));
    }).catch(() => { /* not supported */ });
    return () => { if (status) status.onchange = null; };
  }, [enabled]);

  // Wake lock while navigating
  useEffect(() => {
    if (!enabled) return;
    const requestWakeLock = async () => {
      try {
        const nav = navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } };
        if (nav.wakeLock && document.visibilityState === 'visible') {
          wakeLockRef.current = await nav.wakeLock.request('screen');
          setState((s) => ({ ...s, wakeLock: true }));
        }
      } catch {
        setState((s) => ({ ...s, wakeLock: false }));
      }
    };
    void requestWakeLock();
    const onVisible = () => { if (document.visibilityState === 'visible') void requestWakeLock(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      void wakeLockRef.current?.release();
      wakeLockRef.current = null;
      setState((s) => ({ ...s, wakeLock: false }));
    };
  }, [enabled]);

  // Simulation mode
  useEffect(() => {
    if (!enabled || !simulation || simulation.points.length < 2) return;
    const speedMps = (simulation.speedKnots ?? 60) * 0.514444; // accelerated default so progress is visible
    const start = Date.now();
    setState((s) => ({ ...s, simulated: true, error: null, errorCode: null }));
    const tick = () => {
      const elapsed = (Date.now() - start) / 1000;
      const p = interpolate(simulation.points, (speedMps * elapsed) / 1000);
      const fix: Fix = {
        latitude: p.lat, longitude: p.lon, accuracy_m: 5,
        speed_mps: p.done ? 0 : speedMps, heading_deg: p.brg, timestamp: Date.now(), simulated: true,
      };
      lastFix.current = fix;
      setState((s) => ({ ...s, fix }));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      clearInterval(id);
      lastFix.current = null;
      setState((s) => ({ ...s, simulated: false, fix: null }));
    };
  }, [enabled, simulation]);

  // Real GPS
  useEffect(() => {
    if (!enabled || simulation || !supported || !secure) return;

    setState((s) => ({ ...s, highAccuracy, attempts: s.attempts + 1 }));
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords;
        let heading = c.heading !== null && !Number.isNaN(c.heading) ? c.heading : null;
        let speed = c.speed !== null && !Number.isNaN(c.speed) ? c.speed : null;
        const prev = lastFix.current;
        if (prev && !prev.simulated) {
          const dKm = haversineKm(prev.latitude, prev.longitude, c.latitude, c.longitude);
          const dt = (pos.timestamp - prev.timestamp) / 1000;
          if (dKm > 0.015 && dt > 0) {
            if (heading === null) heading = initialBearingDeg(prev.latitude, prev.longitude, c.latitude, c.longitude);
            if (speed === null) speed = (dKm * 1000) / dt;
          }
        }
        const fix: Fix = {
          latitude: c.latitude,
          longitude: c.longitude,
          accuracy_m: c.accuracy ?? null,
          speed_mps: speed,
          heading_deg: heading,
          timestamp: pos.timestamp,
        };
        lastFix.current = fix;
        setState((s) => ({ ...s, fix, error: null, errorCode: null, permission: 'granted' }));
      },
      (err) => {
        const code = CODE_MAP[err.code] ?? 'POSITION_UNAVAILABLE';
        setState((s) => ({ ...s, error: err.message, errorCode: code, ...(code === 'PERMISSION_DENIED' ? { permission: 'denied' as const } : {}) }));
        // No GPS chip (laptops) or poor sky view: fall back to Wi-Fi/cell positioning.
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
      return { title: mr ? 'या ब्राउझरमध्ये GPS उपलब्ध नाही' : 'This browser has no location support', steps: [mr ? 'Chrome किंवा Edge वापरा.' : 'Use Chrome or Edge.'] };
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
          : ['Click the 🔒/ⓘ icon in the address bar → Location → Allow.', 'Reload the page.', 'Windows: Settings → Privacy & security → Location must be On (incl. "Let desktop apps access your location").'],
      };
    case 'TIMEOUT':
    case 'POSITION_UNAVAILABLE':
      return {
        title: mr ? 'स्थान मिळत नाही' : 'No position fix yet',
        steps: mr
          ? ['या संगणकात GPS चिप नाही; Wi-Fi चालू ठेवा (Wi-Fi द्वारे अंदाजे स्थान मिळते).', 'Windows: Settings → Privacy & security → Location चालू करा.', 'चाचणीसाठी खालील "GPS सिम्युलेशन" वापरा.']
          : ['This computer has no GPS chip — keep Wi-Fi ON (position is estimated from nearby Wi-Fi networks).', 'Windows: Settings → Privacy & security → Location must be On.', 'For testing, use "Simulate GPS" below, or Chrome DevTools → ⋮ → More tools → Sensors → Location.'],
      };
    default:
      if (state.permission === 'prompt') {
        return { title: mr ? 'स्थान परवानगी द्या' : 'Allow location access', steps: [mr ? 'ब्राउझरच्या पॉप-अपमध्ये "Allow" दाबा.' : 'Press "Allow" in the browser prompt.'] };
      }
      return null;
  }
}
