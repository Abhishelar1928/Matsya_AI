/**
 * Mirrors the seven SafetyGate cases in backend/tests/test_safety_gate_phase6.py,
 * plus the offline-specific expiry rules.
 */
import { describe, expect, it } from 'vitest';
import { evaluateOfflineSafety, forecastIndexAt, currentConditions, type CurrentConditions } from './offlineSafety';
import type { PackagedWarnings, SafetyRules, PackagedWarningItem } from './types';

const rules: SafetyRules = {
  wave_height_threshold_m: 4.0,
  wind_speed_threshold_kmh: 50.0,
  severe_severities: ['SEVERE', 'VERY_SEVERE', 'EXTREMELY_SEVERE'],
  caution_severities: ['MODERATE', 'CAUTION', 'WARNING', 'ROUGH_SEA'],
  normal_severities: ['NONE', 'NORMAL', 'NIL', 'ALL_CLEAR', 'SAFE'],
  statuses: [],
  rule: '',
};

const NOW = Date.parse('2026-11-16T10:00:00Z');
const H = 3600_000;

function warn(severity: string, fromOffsetH = -2, untilOffsetH = 24): PackagedWarningItem {
  return {
    warning_type: 'test', severity, description: '', source_name: 'IMD',
    issued_at: new Date(NOW - 3 * H).toISOString(),
    valid_from: new Date(NOW + fromOffsetH * H).toISOString(),
    valid_until: new Date(NOW + untilOffsetH * H).toISOString(),
  };
}
const warnings = (items: PackagedWarningItem[]): PackagedWarnings => ({ status: 'LIVE', source: 'IMD', issued_at: null, valid_until: null, items });
const ok: CurrentConditions = { wave_height_m: 1.2, wind_speed_kmh: 20, forecast_time: new Date(NOW).toISOString(), expired: false };
const missing: CurrentConditions = { wave_height_m: null, wind_speed_kmh: null, forecast_time: null, expired: true };

describe('offline safety (mirrors SafetyGate)', () => {
  it('A: normal bulletin + verified env → SAFE_CONFIRMED', () => {
    expect(evaluateOfflineSafety(warnings([warn('NORMAL')]), rules, ok, NOW).status).toBe('SAFE_CONFIRMED');
  });
  it('B: no warning data → NO_WARNING_DATA (never safe)', () => {
    expect(evaluateOfflineSafety(warnings([]), rules, ok, NOW).status).toBe('NO_WARNING_DATA');
  });
  it('C: stale (expired) warning → NO_WARNING_DATA and flags expiry', () => {
    const r = evaluateOfflineSafety(warnings([warn('NORMAL', -30, -2)]), rules, ok, NOW);
    expect(r.status).toBe('NO_WARNING_DATA');
    expect(r.warnings_expired).toBe(true);
  });
  it('D: severe warning → UNSAFE', () => {
    expect(evaluateOfflineSafety(warnings([warn('SEVERE')]), rules, ok, NOW).status).toBe('UNSAFE');
  });
  it('E: caution warning → CAUTION', () => {
    expect(evaluateOfflineSafety(warnings([warn('ROUGH_SEA')]), rules, ok, NOW).status).toBe('CAUTION');
  });
  it('F: normal bulletin but forecast thresholds exceeded → CAUTION', () => {
    expect(evaluateOfflineSafety(warnings([warn('NORMAL')]), rules, { ...ok, wave_height_m: 4.5 }, NOW).status).toBe('CAUTION');
    expect(evaluateOfflineSafety(warnings([warn('NORMAL')]), rules, { ...ok, wind_speed_kmh: 60 }, NOW).status).toBe('CAUTION');
  });
  it('G: normal bulletin but env missing/expired → NO_WARNING_DATA', () => {
    expect(evaluateOfflineSafety(warnings([warn('NORMAL')]), rules, missing, NOW).status).toBe('NO_WARNING_DATA');
  });
  it('a warning that starts in the future is not yet active', () => {
    expect(evaluateOfflineSafety(warnings([warn('SEVERE', 5, 30)]), rules, ok, NOW).status).toBe('NO_WARNING_DATA');
  });
});

describe('forecast slot lookup', () => {
  const times = [0, 1, 2, 3].map((h) => new Date(NOW - 2 * H + h * H).toISOString());
  it('finds the hour covering now', () => {
    expect(forecastIndexAt(times, NOW)).toBe(2);
    expect(forecastIndexAt(times, NOW + 0.5 * H)).toBe(2);
  });
  it('returns -1 before the window and after it expires', () => {
    expect(forecastIndexAt(times, NOW - 10 * H)).toBe(-1);
    expect(forecastIndexAt(times, NOW + 10 * H)).toBe(-1);
    expect(forecastIndexAt([], NOW)).toBe(-1);
  });
  it('currentConditions uses the nearest point and reports expiry', () => {
    const pkg = {
      forecast: {
        status: 'LIVE', provider: '', retrieved_at: '', valid_from: null, valid_until: null, error: null,
        points: [
          { waypoint_index: 0, latitude: 17, longitude: 73, hourly: { time: times, wave_height_m: [1, 1, 1, 1], wave_period_s: [], wave_direction_deg: [], swell_wave_height_m: [], wind_speed_kmh: [10, 10, 10, 10], wind_direction_deg: [], wind_gusts_kmh: [] } },
          { waypoint_index: 5, latitude: 16, longitude: 72, hourly: { time: times, wave_height_m: [3, 3, 3, 3], wave_period_s: [], wave_direction_deg: [], swell_wave_height_m: [], wind_speed_kmh: [40, 40, 40, 40], wind_direction_deg: [], wind_gusts_kmh: [] } },
        ],
      },
    };
    expect(currentConditions(pkg, 16.1, 72.1, NOW).wave_height_m).toBe(3);
    expect(currentConditions(pkg, 17, 73, NOW).wave_height_m).toBe(1);
    expect(currentConditions(pkg, 17, 73, NOW + 10 * H).expired).toBe(true);
  });
});
