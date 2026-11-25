/**
 * MatsyaAI Maharashtra — IndexedDB store (v2) for Offline Expedition Mode.
 *
 * Stores: packages, track_points, catches, observations, voyage_events,
 * voyage_state (for crash/reload recovery), and settings.
 * Device-originated records carry a `synced` flag (0 | 1) and are NEVER deleted
 * before confirmed server acknowledgement.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type {
  CatchRecord,
  ExpeditionPackage,
  FieldObservation,
  PersistedVoyageState,
  TrackPoint,
  VoyageEvent,
} from '../types/expeditionTypes';

interface MatsyaDB extends DBSchema {
  packages: { key: string; value: ExpeditionPackage & { stored_at: string } };
  track_points: {
    key: string;
    value: TrackPoint;
    indexes: { by_expedition: string; by_synced: number };
  };
  catches: {
    key: string;
    value: CatchRecord;
    indexes: { by_expedition: string; by_synced: number };
  };
  observations: {
    key: string;
    value: FieldObservation;
    indexes: { by_expedition: string; by_synced: number };
  };
  voyage_events: {
    key: string;
    value: VoyageEvent;
    indexes: { by_expedition: string; by_synced: number };
  };
  voyage_state: {
    key: string;
    value: PersistedVoyageState;
  };
  settings: { key: string; value: string };
}

const DB_NAME = 'matsya-expedition';
const DB_VERSION = 2;

let dbPromise: Promise<IDBPDatabase<MatsyaDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<MatsyaDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MatsyaDB>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        if (oldVersion < 1) {
          db.createObjectStore('packages', { keyPath: 'manifest.package_id' });
          for (const name of ['track_points', 'catches', 'observations'] as const) {
            const store = db.createObjectStore(name, { keyPath: 'client_uuid' });
            store.createIndex('by_expedition', 'expedition_id');
            store.createIndex('by_synced', 'synced');
          }
          db.createObjectStore('settings');
        }
        if (oldVersion < 2) {
          if (!db.objectStoreNames.contains('voyage_events')) {
            const ev = db.createObjectStore('voyage_events', { keyPath: 'client_uuid' });
            ev.createIndex('by_expedition', 'expedition_id');
            ev.createIndex('by_synced', 'synced');
          }
          if (!db.objectStoreNames.contains('voyage_state')) {
            db.createObjectStore('voyage_state', { keyPath: 'expedition_id' });
          }
        }
      },
    });
  }
  return dbPromise;
}

export function newUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// --- Storage & Integrity ----------------------------------------------------
export interface StorageEstimateInfo {
  supported: boolean;
  usageBytes: number | null;
  quotaBytes: number | null;
  percentUsed: number | null;
  persisted: boolean | null;
}

export async function getStorageEstimate(): Promise<StorageEstimateInfo> {
  let usageBytes: number | null = null;
  let quotaBytes: number | null = null;
  let persisted: boolean | null = null;
  const supported = typeof navigator !== 'undefined' && !!navigator.storage;
  if (supported) {
    try {
      if (navigator.storage.estimate) {
        const est = await navigator.storage.estimate();
        usageBytes = est.usage ?? null;
        quotaBytes = est.quota ?? null;
      }
      if (navigator.storage.persisted) {
        persisted = await navigator.storage.persisted();
      }
    } catch {
      /* ignore */
    }
  }
  const percentUsed =
    usageBytes !== null && quotaBytes && quotaBytes > 0
      ? Number(((usageBytes / quotaBytes) * 100).toFixed(1))
      : null;
  return { supported, usageBytes, quotaBytes, percentUsed, persisted };
}

function sortKeysDeep(val: unknown): unknown {
  if (Array.isArray(val)) return val.map(sortKeysDeep);
  if (val !== null && typeof val === 'object') {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(val as Record<string, unknown>).sort()) {
      out[k] = sortKeysDeep((val as Record<string, unknown>)[k]);
    }
    return out;
  }
  return val;
}

export async function sha256Canonical(val: unknown): Promise<string | null> {
  if (typeof crypto === 'undefined' || !crypto.subtle) return null;
  const json = JSON.stringify(sortKeysDeep(val));
  const bytes = new TextEncoder().encode(json);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export interface PackageIntegrityResult {
  status: 'VERIFIED' | 'MISMATCH' | 'UNVERIFIABLE';
  checked: string[];
  mismatched: string[];
}

export async function verifyPackageIntegrity(pkg: ExpeditionPackage): Promise<PackageIntegrityResult> {
  const checksums = pkg.manifest.checksums;
  if (!checksums || Object.keys(checksums).length === 0 || typeof crypto === 'undefined' || !crypto.subtle) {
    return { status: 'UNVERIFIABLE', checked: [], mismatched: [] };
  }
  const checked: string[] = [];
  const mismatched: string[] = [];
  const sections = ['route', 'emergency_returns', 'pfz', 'warnings', 'forecast', 'predictions', 'safety_rules'] as const;
  for (const sec of sections) {
    const expected = checksums[sec];
    if (!expected) continue;
    checked.push(sec);
    const actual = await sha256Canonical(pkg[sec]);
    if (actual && actual !== expected) {
      mismatched.push(sec);
    }
  }
  if (checked.length === 0) return { status: 'UNVERIFIABLE', checked, mismatched };
  return {
    status: mismatched.length === 0 ? 'VERIFIED' : 'MISMATCH',
    checked,
    mismatched,
  };
}

// --- settings ---------------------------------------------------------------
export async function getDeviceId(): Promise<string> {
  const db = await getDB();
  let id = await db.get('settings', 'device_id');
  if (!id) {
    id = newUuid();
    await db.put('settings', id, 'device_id');
  }
  return id;
}

export async function getActivePackageId(): Promise<string | null> {
  return (await (await getDB()).get('settings', 'active_package_id')) ?? null;
}

export async function setActivePackageId(id: string | null): Promise<void> {
  const db = await getDB();
  if (id) await db.put('settings', id, 'active_package_id');
  else await db.delete('settings', 'active_package_id');
}

// --- packages ---------------------------------------------------------------
export async function savePackage(pkg: ExpeditionPackage): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['packages', 'settings'], 'readwrite');
  await tx.objectStore('packages').put({ ...pkg, stored_at: new Date().toISOString() });
  await tx.objectStore('settings').put(pkg.manifest.package_id, 'active_package_id');
  await tx.done;
}

export async function getPackage(id: string): Promise<ExpeditionPackage | null> {
  return (await (await getDB()).get('packages', id)) ?? null;
}

export async function getActivePackage(): Promise<ExpeditionPackage | null> {
  const id = await getActivePackageId();
  return id ? getPackage(id) : null;
}

export async function listPackages(): Promise<ExpeditionPackage[]> {
  return (await getDB()).getAll('packages');
}

export async function deletePackage(id: string): Promise<void> {
  const db = await getDB();
  const active = await db.get('settings', 'active_package_id');
  const tx = db.transaction(['packages', 'settings'], 'readwrite');
  await tx.objectStore('packages').delete(id);
  if (active === id) await tx.objectStore('settings').delete('active_package_id');
  await tx.done;
}

// --- records ----------------------------------------------------------------
export async function addTrackPoint(tp: TrackPoint): Promise<void> {
  await (await getDB()).put('track_points', tp);
}

export async function addCatch(c: CatchRecord): Promise<void> {
  await (await getDB()).put('catches', c);
}

export async function addObservation(o: FieldObservation): Promise<void> {
  await (await getDB()).put('observations', o);
}

export async function addVoyageEvent(ev: VoyageEvent): Promise<void> {
  await (await getDB()).put('voyage_events', ev);
}

export async function listTrack(expeditionId: string): Promise<TrackPoint[]> {
  const pts = await (await getDB()).getAllFromIndex('track_points', 'by_expedition', expeditionId);
  return pts.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
}

export async function listCatches(expeditionId: string): Promise<CatchRecord[]> {
  const rows = await (await getDB()).getAllFromIndex('catches', 'by_expedition', expeditionId);
  return rows.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
}

export async function listAllCatches(): Promise<CatchRecord[]> {
  const rows = await (await getDB()).getAll('catches');
  return rows.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
}

export async function listVoyageEvents(expeditionId: string): Promise<VoyageEvent[]> {
  const rows = await (await getDB()).getAllFromIndex('voyage_events', 'by_expedition', expeditionId);
  return rows.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
}

export async function saveVoyageState(state: PersistedVoyageState): Promise<void> {
  await (await getDB()).put('voyage_state', state);
}

export async function getVoyageState(expeditionId: string): Promise<PersistedVoyageState | null> {
  return (await (await getDB()).get('voyage_state', expeditionId)) ?? null;
}

export interface Outbox {
  track_points: TrackPoint[];
  catches: CatchRecord[];
  observations: FieldObservation[];
}

export async function getOutbox(expeditionId: string): Promise<Outbox> {
  const db = await getDB();
  const only = <T extends { expedition_id: string }>(rows: T[]) =>
    rows.filter((r) => r.expedition_id === expeditionId);
  return {
    track_points: only(await db.getAllFromIndex('track_points', 'by_synced', 0)),
    catches: only(await db.getAllFromIndex('catches', 'by_synced', 0)),
    observations: only(await db.getAllFromIndex('observations', 'by_synced', 0)),
  };
}

export async function pendingCount(expeditionId: string): Promise<number> {
  const o = await getOutbox(expeditionId);
  return o.track_points.length + o.catches.length + o.observations.length;
}

export async function recordCounts(expeditionId: string): Promise<{
  pending: number;
  uploaded: number;
  failed: number;
}> {
  const db = await getDB();
  let pending = 0;
  let uploaded = 0;
  let failed = 0;
  for (const name of ['track_points', 'catches', 'observations'] as const) {
    const rows = await db.getAllFromIndex(name, 'by_expedition', expeditionId);
    for (const r of rows) {
      if (r.synced === 1) uploaded += 1;
      else {
        pending += 1;
        if (r.sync_error) failed += 1;
      }
    }
  }
  return { pending, uploaded, failed };
}

export async function markSynced(uuids: string[]): Promise<void> {
  if (uuids.length === 0) return;
  const db = await getDB();
  const tx = db.transaction(['track_points', 'catches', 'observations'], 'readwrite');
  for (const name of ['track_points', 'catches', 'observations'] as const) {
    const store = tx.objectStore(name);
    for (const id of uuids) {
      const rec = await store.get(id);
      if (rec && rec.synced === 0) {
        await store.put({ ...rec, synced: 1, sync_error: null });
      }
    }
  }
  await tx.done;
}

export async function markSyncFailed(uuids: string[], errorMessage: string): Promise<void> {
  if (uuids.length === 0) return;
  const db = await getDB();
  const tx = db.transaction(['track_points', 'catches', 'observations'], 'readwrite');
  for (const name of ['track_points', 'catches', 'observations'] as const) {
    const store = tx.objectStore(name);
    for (const id of uuids) {
      const rec = await store.get(id);
      if (rec && rec.synced === 0) {
        await store.put({ ...rec, sync_error: errorMessage });
      }
    }
  }
  await tx.done;
}
