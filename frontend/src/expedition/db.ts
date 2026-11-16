/**
 * MatsyaAI Maharashtra — IndexedDB store for Offline Expedition Mode.
 *
 * Stores: packages (one per expedition), track points, catches, observations,
 * and settings (device_id, active package). Device-originated records carry a
 * `synced` flag; the outbox is simply every record with synced === 0.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { CatchRecord, ExpeditionPackage, FieldObservation, TrackPoint } from './types';

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
  settings: { key: string; value: string };
}

const DB_NAME = 'matsya-expedition';
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<MatsyaDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<MatsyaDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MatsyaDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        db.createObjectStore('packages', { keyPath: 'manifest.package_id' });
        for (const name of ['track_points', 'catches', 'observations'] as const) {
          const store = db.createObjectStore(name, { keyPath: 'client_uuid' });
          store.createIndex('by_expedition', 'expedition_id');
          store.createIndex('by_synced', 'synced');
        }
        db.createObjectStore('settings');
      },
    });
  }
  return dbPromise;
}

export function newUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  // Fallback for very old WebViews
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
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
  await db.put('packages', { ...pkg, stored_at: new Date().toISOString() });
  await setActivePackageId(pkg.manifest.package_id);
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
  await db.delete('packages', id);
  if ((await getActivePackageId()) === id) await setActivePackageId(null);
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

export async function listTrack(expeditionId: string): Promise<TrackPoint[]> {
  const pts = await (await getDB()).getAllFromIndex('track_points', 'by_expedition', expeditionId);
  return pts.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
}

export async function listCatches(expeditionId: string): Promise<CatchRecord[]> {
  const rows = await (await getDB()).getAllFromIndex('catches', 'by_expedition', expeditionId);
  return rows.sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
}

export interface Outbox {
  track_points: TrackPoint[];
  catches: CatchRecord[];
  observations: FieldObservation[];
}

export async function getOutbox(expeditionId: string): Promise<Outbox> {
  const db = await getDB();
  const only = <T extends { expedition_id: string }>(rows: T[]) => rows.filter((r) => r.expedition_id === expeditionId);
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

export async function markSynced(uuids: string[]): Promise<void> {
  if (uuids.length === 0) return;
  const db = await getDB();
  const set = new Set(uuids);
  const tx = db.transaction(['track_points', 'catches', 'observations'], 'readwrite');
  for (const name of ['track_points', 'catches', 'observations'] as const) {
    const store = tx.objectStore(name);
    let cursor = await store.index('by_synced').openCursor(0);
    while (cursor) {
      if (set.has(cursor.value.client_uuid)) {
        await cursor.update({ ...cursor.value, synced: 1 });
      }
      cursor = await cursor.continue();
    }
  }
  await tx.done;
}
