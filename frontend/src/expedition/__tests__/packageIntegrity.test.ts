import { describe, expect, it } from 'vitest';
import { sha256Canonical, verifyPackageIntegrity } from '../services/expeditionDb';
import { SIMULATION_SCENARIOS, generateSimulatedFix } from '../engine/simulation';
import type { ExpeditionPackage } from '../types/expeditionTypes';

describe('package integrity & simulation scenarios', () => {
  it('verifies SHA-256 manifest checksums and detects tampering', async () => {
    const route = { type: 'DIRECT_GREAT_CIRCLE', distance_km: 12.5, waypoints: [] };
    const safety_rules = { wave_height_threshold_m: 2.5 };
    const hashRoute = await sha256Canonical(route);
    const hashRules = await sha256Canonical(safety_rules);

    // Skip assertion if WebCrypto subtle is absent in an older runtime
    if (!hashRoute || !hashRules) return;

    const pkg = {
      manifest: {
        schema_version: 2,
        package_id: 'p1',
        checksums: { route: hashRoute, safety_rules: hashRules },
      },
      route,
      safety_rules,
    } as unknown as ExpeditionPackage;

    const ok = await verifyPackageIntegrity(pkg);
    expect(ok.status).toBe('VERIFIED');
    expect(ok.checked).toEqual(['route', 'safety_rules']);

    const tampered = { ...pkg, route: { ...route, distance_km: 999 } } as unknown as ExpeditionPackage;
    const bad = await verifyPackageIntegrity(tampered);
    expect(bad.status).toBe('MISMATCH');
    expect(bad.mismatched).toEqual(['route']);
  });

  it('generates all simulation scenarios cleanly and tags every fix simulated=true', () => {
    const pts = [
      { latitude: 18.0, longitude: 72.8 },
      { latitude: 18.0, longitude: 72.4 },
    ];
    for (const sc of SIMULATION_SCENARIOS) {
      const fix = generateSimulatedFix({ points: pts, scenario: sc.id }, 2, 1_700_000_000_000);
      expect(fix).not.toBeNull();
      expect(fix?.simulated).toBe(true);
      expect(fix?.simulationScenario).toBe(sc.id);
    }
    // gps_loss returns null after tick 5
    expect(generateSimulatedFix({ points: pts, scenario: 'gps_loss' }, 6, 1_700_000_006_000)).toBeNull();
  });
});
