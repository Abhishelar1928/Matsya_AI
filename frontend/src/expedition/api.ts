/**
 * MatsyaAI Maharashtra — Expedition API client.
 * All calls go through the same /api/v1 proxy as services/api.ts.
 */

import type { ExpeditionPackage, LandingCentreInfo, SyncResponse } from './types';
import type { Outbox } from './db';

const API_BASE = '/api/v1/expedition';

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchLandingCentres(): Promise<LandingCentreInfo[]> {
  const data = await handle<{ landing_centres: LandingCentreInfo[] }>(await fetch(`${API_BASE}/landing-centres`));
  return data.landing_centres;
}

export interface PackageRequest {
  device_id: string;
  landing_centre_id: string;
  destination?: { latitude: number; longitude: number; name?: string };
  pfz_index?: number;
  planned_departure?: string;
  planned_return?: string;
}

export async function requestPackage(req: PackageRequest): Promise<ExpeditionPackage> {
  return handle<ExpeditionPackage>(await fetch(`${API_BASE}/packages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }));
}

export async function postSync(
  deviceId: string,
  expeditionId: string,
  outbox: Outbox,
  includeDelta: boolean,
): Promise<SyncResponse> {
  const strip = <T extends { synced: 0 | 1; expedition_id: string }>(rows: T[]) =>
    rows.map(({ synced: _s, expedition_id: _e, ...rest }) => rest);
  return handle<SyncResponse>(await fetch(`${API_BASE}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      device_id: deviceId,
      expedition_id: expeditionId,
      track_points: strip(outbox.track_points),
      catches: strip(outbox.catches),
      observations: strip(outbox.observations),
      include_delta: includeDelta,
    }),
  }));
}

/** Download a static offline asset with progress; returns the bytes (cached by the service worker too). */
export async function downloadAsset(
  url: string,
  onProgress?: (loaded: number, total: number | null) => void,
): Promise<Blob> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Asset ${url}: ${res.status}`);
  const total = Number(res.headers.get('content-length')) || null;
  if (!res.body) return res.blob();
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.length;
    onProgress?.(loaded, total);
  }
  return new Blob(chunks as BlobPart[]);
}
