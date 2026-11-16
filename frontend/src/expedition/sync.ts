/**
 * MatsyaAI Maharashtra — Outbox sync.
 *
 * Flushes unsynced track points / catches / observations when connectivity
 * returns, marks them synced using the server's acknowledged UUIDs, and merges
 * the server's "delta" (fresh warnings, forecast, predictions, PFZ) into the
 * stored package. Retries with exponential backoff; never loses records.
 */

import { getDeviceId, getOutbox, getPackage, markSynced, savePackage } from './db';
import { postSync } from './api';
import type { ExpeditionPackage, SyncResponse } from './types';

export interface SyncResult {
  ok: boolean;
  uploaded: number;
  duplicates: number;
  deltaApplied: boolean;
  error?: string;
}

const BATCH_TRACK_POINTS = 2000;

export function applyDelta(pkg: ExpeditionPackage, delta: NonNullable<SyncResponse['delta']>): ExpeditionPackage {
  const next: ExpeditionPackage = {
    ...pkg,
    warnings: delta.warnings?.status === 'UNAVAILABLE' ? pkg.warnings : delta.warnings ?? pkg.warnings,
    predictions: delta.predictions?.status === 'UNAVAILABLE' ? pkg.predictions : delta.predictions ?? pkg.predictions,
    pfz: delta.pfz?.status === 'UNAVAILABLE' ? pkg.pfz : delta.pfz ?? pkg.pfz,
    forecast: delta.forecast && delta.forecast.status !== 'UNAVAILABLE' ? delta.forecast : pkg.forecast,
  };
  const expiry = {
    warnings: next.warnings.valid_until,
    forecast: next.forecast.valid_until,
    predictions: next.predictions.valid_until,
    pfz: next.pfz.validity_date,
  };
  const valid = Object.values(expiry).filter((v): v is string => !!v).map((v) => Date.parse(v)).filter((n) => !Number.isNaN(n));
  next.manifest = {
    ...pkg.manifest,
    component_expiry: expiry,
    valid_until: valid.length ? new Date(Math.min(...valid)).toISOString() : pkg.manifest.valid_until,
  };
  return next;
}

export async function syncExpedition(expeditionId: string, includeDelta = true): Promise<SyncResult> {
  const deviceId = await getDeviceId();
  let uploaded = 0;
  let duplicates = 0;
  let deltaApplied = false;

  try {
    // Upload in bounded batches so a long track never exceeds request limits.
    for (;;) {
      const outbox = await getOutbox(expeditionId);
      const pending = outbox.track_points.length + outbox.catches.length + outbox.observations.length;
      const batch = { ...outbox, track_points: outbox.track_points.slice(0, BATCH_TRACK_POINTS) };
      const last = batch.track_points.length === outbox.track_points.length;

      const res = await postSync(deviceId, expeditionId, batch, includeDelta && last);
      await markSynced(res.acknowledged_uuids);
      uploaded += Object.values(res.inserted).reduce((a, b) => a + b, 0);
      duplicates += Object.values(res.duplicates).reduce((a, b) => a + b, 0);

      if (res.delta) {
        const pkg = await getPackage(expeditionId);
        if (pkg) {
          await savePackage(applyDelta(pkg, res.delta));
          deltaApplied = true;
        }
      }
      if (last || pending === 0) break;
    }
    return { ok: true, uploaded, duplicates, deltaApplied };
  } catch (e) {
    return { ok: false, uploaded, duplicates, deltaApplied, error: e instanceof Error ? e.message : String(e) };
  }
}

/**
 * Background syncer: runs on `online` events and on an interval, with backoff on failure.
 * Returns a stop function.
 */
export function startAutoSync(
  getActiveId: () => Promise<string | null>,
  onResult: (r: SyncResult) => void,
  baseIntervalMs = 60_000,
): () => void {
  let stopped = false;
  let failures = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const schedule = () => {
    if (stopped) return;
    const delay = Math.min(baseIntervalMs * 2 ** failures, 15 * 60_000);
    timer = setTimeout(run, delay);
  };

  const run = async () => {
    if (stopped) return;
    if (!navigator.onLine) { schedule(); return; }
    const id = await getActiveId();
    if (id) {
      const r = await syncExpedition(id);
      failures = r.ok ? 0 : failures + 1;
      onResult(r);
    }
    schedule();
  };

  const onOnline = () => { failures = 0; if (timer) clearTimeout(timer); void run(); };
  window.addEventListener('online', onOnline);
  void run();

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    window.removeEventListener('online', onOnline);
  };
}
