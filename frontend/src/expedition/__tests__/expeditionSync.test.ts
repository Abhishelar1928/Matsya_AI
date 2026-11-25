import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExpeditionPackage, SyncResponse } from '../types/expeditionTypes';

// Mock the IndexedDB layer and the HTTP client so the batching/ack logic is tested in isolation.
const state = {
  outbox: { track_points: [] as any[], catches: [] as any[], observations: [] as any[] },
  synced: [] as string[],
  failed: [] as string[],
  saved: null as ExpeditionPackage | null,
};
vi.mock('../services/expeditionDb', () => ({
  getDeviceId: async () => 'device-1',
  newUuid: () => 'batch-uuid-1',
  getOutbox: async () => ({
    track_points: state.outbox.track_points.filter((r) => !state.synced.includes(r.client_uuid)),
    catches: state.outbox.catches.filter((r) => !state.synced.includes(r.client_uuid)),
    observations: state.outbox.observations.filter((r) => !state.synced.includes(r.client_uuid)),
  }),
  markSynced: async (ids: string[]) => { state.synced.push(...ids); },
  markSyncFailed: async (ids: string[]) => { state.failed.push(...ids); },
  getPackage: async () => basePkg,
  savePackage: async (p: ExpeditionPackage) => { state.saved = p; },
}));
const postSync = vi.fn();
vi.mock('../services/expeditionApi', () => ({ postSync: (...a: unknown[]) => postSync(...a) }));

const { applyDelta, syncExpedition } = await import('../services/expeditionSync');

const basePkg = {
  manifest: { package_id: 'exp-1', valid_until: '2026-01-01T00:00:00Z', component_expiry: { warnings: null, forecast: null, predictions: null, pfz: null } },
  warnings: { status: 'LIVE', valid_until: '2026-01-02T00:00:00Z', items: [] },
  forecast: { status: 'LIVE', valid_until: '2026-01-03T00:00:00Z', points: [] },
  predictions: { status: 'LIVE', valid_until: '2026-01-01T12:00:00Z', cells: [] },
  pfz: { status: 'LIVE', validity_date: '2026-01-04T00:00:00Z', locations: [] },
} as unknown as ExpeditionPackage;

const tp = (i: number) => ({ client_uuid: `tp-${i}`, expedition_id: 'exp-1', recorded_at: 'x', latitude: 0, longitude: 0, speed_mps: null, heading_deg: null, accuracy_m: null, synced: 0 });

beforeEach(() => {
  state.outbox = { track_points: [], catches: [], observations: [] };
  state.synced = [];
  state.failed = [];
  state.saved = null;
  postSync.mockReset();
});

describe('applyDelta', () => {
  it('replaces components with fresh data and recomputes the earliest expiry', () => {
    const next = applyDelta(basePkg, {
      warnings: { status: 'LIVE', valid_until: '2026-01-05T00:00:00Z', items: [], source: '', issued_at: null },
      predictions: { status: 'LIVE', valid_until: '2026-01-02T06:00:00Z', cells: [], model_version: null, prediction_timestamp: null },
      pfz: { status: 'UNAVAILABLE', validity_date: null, locations: [], count: 0, advisory_date: null, source: '' },
    });
    expect(next.warnings.valid_until).toBe('2026-01-05T00:00:00Z');
    expect(next.pfz.validity_date).toBe('2026-01-04T00:00:00Z'); // UNAVAILABLE delta never overwrites good data
    expect(next.manifest.valid_until).toBe('2026-01-02T06:00:00.000Z');
  });
});

describe('syncExpedition', () => {
  it('uploads in batches, marks acknowledged records, applies delta once', async () => {
    state.outbox.track_points = Array.from({ length: 2500 }, (_, i) => tp(i));
    postSync.mockImplementation(async (_d: string, _e: string, outbox: any, includeDelta: boolean): Promise<SyncResponse> => ({
      received: {}, inserted: { track_points: outbox.track_points.length, catches: 0, observations: 0 },
      duplicates: { track_points: 0, catches: 0, observations: 0 },
      acknowledged_uuids: outbox.track_points.map((t: any) => t.client_uuid),
      synced_at: 'now',
      delta: includeDelta ? { warnings: basePkg.warnings, predictions: basePkg.predictions, pfz: basePkg.pfz } : undefined,
    }));
    const r = await syncExpedition('exp-1');
    expect(r.ok).toBe(true);
    expect(r.uploaded).toBe(2500);
    expect(postSync).toHaveBeenCalledTimes(2);
    expect(postSync.mock.calls[0][3]).toBe(false); // delta only requested on last batch
    expect(postSync.mock.calls[1][3]).toBe(true);
    expect(state.synced.length).toBe(2500);
    expect(r.deltaApplied).toBe(true);
  });

  it('keeps records unsynced when the request fails and tracks failed UUIDs', async () => {
    state.outbox.catches = [{ client_uuid: 'c-1', expedition_id: 'exp-1', synced: 0 }];
    postSync.mockRejectedValue(new Error('offline'));
    const r = await syncExpedition('exp-1');
    expect(r.ok).toBe(false);
    expect(r.error).toBe('offline');
    expect(state.synced).toEqual([]);
    expect(state.failed).toEqual(['c-1']);
  });

  it('prevents concurrent duplicate syncs via in-flight mutex and guards against 0-ack infinite loop', async () => {
    state.outbox.catches = [{ client_uuid: 'c-2', expedition_id: 'exp-mutex', synced: 0 }];
    let resolveReq!: (v: SyncResponse) => void;
    postSync.mockImplementationOnce(
      () => new Promise<SyncResponse>((res) => { resolveReq = res; }),
    );
    const p1 = syncExpedition('exp-mutex');
    const p2 = syncExpedition('exp-mutex');
    const r2 = await p2;
    expect(r2.skippedConcurrent).toBe(true);
    await new Promise((r) => setTimeout(r, 0));

    resolveReq({
      received: {}, inserted: { catches: 0 }, duplicates: {},
      acknowledged_uuids: [],
      synced_at: 'now',
    });
    const r1 = await p1;
    expect(r1.ok).toBe(false);
    expect(r1.error).toContain('acknowledged 0');
  });
});
