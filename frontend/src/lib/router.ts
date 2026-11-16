/**
 * Minimal hash router — no dependency, works offline and on static hosting.
 * Format: #/<route>?key=value  (legacy "#expedition" maps to navigation).
 */

import { useEffect, useState } from 'react';

export type RouteId = 'overview' | 'zones' | 'map' | 'safety' | 'weather' | 'navigation' | 'districts';

export const ROUTES: RouteId[] = ['overview', 'zones', 'map', 'safety', 'weather', 'navigation', 'districts'];

export interface Location {
  route: RouteId;
  params: URLSearchParams;
}

export function parseHash(hash: string): Location {
  const raw = hash.replace(/^#\/?/, '');
  if (raw === 'expedition') return { route: 'navigation', params: new URLSearchParams() };
  const [path, query = ''] = raw.split('?');
  const route = (ROUTES as string[]).includes(path) ? (path as RouteId) : 'overview';
  return { route, params: new URLSearchParams(query) };
}

export function href(route: RouteId, params?: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => { if (v !== undefined) q.set(k, String(v)); });
  const qs = q.toString();
  return `#/${route}${qs ? `?${qs}` : ''}`;
}

export function navigate(route: RouteId, params?: Record<string, string | number | undefined>): void {
  window.location.hash = href(route, params);
}

export function useLocation(): Location {
  const [loc, setLoc] = useState<Location>(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => {
      setLoc(parseHash(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return loc;
}
