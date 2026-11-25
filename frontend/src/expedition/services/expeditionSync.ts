/**
 * MatsyaAI Maharashtra — Reliable Outbox Sync.
 *
 * Guarantees:
 * - Single in-flight mutex per expeditionId (prevents duplicate concurrent uploads)
 * - Per-batch idempotency key (`batchId`)
 * - Never deletes or marks synced any local record before server acknowledgement
 * - Guards against zero-ack infinite loops
 * - Best-effort Background Sync registration without relying on it exclusively
 */

import { getDeviceId, getOutbox, getPackage, markSyncFailed, markSynced, newUuid, savePackage } from './expeditionDb';
import { postSync } from './expeditionApi';
import type { ExpeditionPackage, SyncResponse } from '../types/expeditionTypes';

export interface SyncResult {
  ok: boolean;
  uploaded: number;
  duplicates: number;
  deltaApplied: boolean;
  error?: string;
  skippedConcurrent?: boolean;
}

const BATCH_TRACK_POINTS = 2000;
const inFlight = new Set<string>();

export function isSyncInFlight(expeditionId: string): boolean {
  return inFlight.has(expeditionId);
}

export async function registerBackgroundSync(tag: string = 'matsya-expedition-sync'): Promise<boolean> {
  try {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return false;
    const reg = await navigator.serviceWorker.ready;
    const syncMgr = (reg as ServiceWorkerRegistration & { sync?: { register: (t: string) => Promise<void> } }).sync;
    if (!syncMgr) return false;
    await syncMgr.register(tag);
    return true;
  } catch {
    return false;
  }
}

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
  const valid = Object.values(expiry)
    .filter((v): v is string => !!v)
    .map((v) => Date.parse(v))
    .filter((n) => !Number.isNaN(n));
  next.manifest = {
    ...pkg.manifest,
    component_expiry: expiry,
    valid_until: valid.length ? new Date(Math.min(...valid)).toISOString() : pkg.manifest.valid_until,
  };
  return next;
}

export async function syncExpedition(expeditionId: string, includeDelta = true): Promise<SyncResult> {
  if (inFlight.has(expeditionId)) {
    return { ok: true, uploaded: 0, duplicates: 0, deltaApplied: false, skippedConcurrent: true };
  }

  inFlight.add(expeditionId);
  const deviceId = await getDeviceId();
  let uploaded = 0;
  let duplicates = 0;
  let deltaApplied = false;
  let lastBatchUuids: string[] = [];

  try {
    for (;;) {
      const outbox = await getOutbox(expeditionId);
      const pending = outbox.track_points.length + outbox.catches.length + outbox.observations.length;
      const batch = {
        ...outbox,
        track_points: outbox.track_points.slice(0, BATCH_TRACK_POINTS),
      };
      const batchUuids = [
        ...batch.track_points.map((r) => r.client_uuid),
        ...batch.catches.map((r) => r.client_uuid),
        ...batch.observations.map((r) => r.client_uuid),
      ];
      lastBatchUuids = batchUuids;
      const last = batch.track_points.length === outbox.track_points.length;

      const batchId = newUuid();
      const res = await postSync(deviceId, expeditionId, batch, includeDelta && last, batchId);
      const acks = Array.isArray(res.acknowledged_uuids) ? res.acknowledged_uuids : [];

      if (batchUuids.length > 0 && acks.length === 0) {
        const msg = 'Server acknowledged 0 records in non-empty batch';
        await markSyncFailed(batchUuids, msg);
        return { ok: false, uploaded, duplicates, deltaApplied, error: msg };
      }

      await markSynced(acks);
      uploaded += Object.values(res.inserted || {}).reduce((a, b) => a + b, 0);
      duplicates += Object.values(res.duplicates || {}).reduce((a, b) => a + b, 0);

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
    const msg = e instanceof Error ? e.message : String(e);
    if (lastBatchUuids.length > 0) {
      await markSyncFailed(lastBatchUuids, msg).catch(() => {});
    }
    void registerBackgroundSync();
    return { ok: false, uploaded, duplicates, deltaApplied, error: msg };
  } finally {
    inFlight.delete(expeditionId);
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
    if (!navigator.onLine) {
      schedule();
      return;
    }
    const id = await getActiveId();
    if (id) {
      const r = await syncExpedition(id);
      if (!r.skippedConcurrent) {
        failures = r.ok ? 0 : failures + 1;
        onResult(r);
      }
    }
    schedule();
  };

  const onOnline = () => {
    failures = 0;
    if (timer) clearTimeout(timer);
    void run();
  };
  window.addEventListener('online', onOnline);
  void run();

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    window.removeEventListener('online', onOnline);
  };
}
