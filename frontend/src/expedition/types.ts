/**
 * MatsyaAI Maharashtra — Offline Expedition Mode types.
 * Mirrors backend/app/services/expedition/package_builder.py (schema_version 1).
 */

import type { SafetyStatus } from '../types/map';

export interface LandingCentreInfo {
  id: string;
  name: string;
  name_mr: string;
  district: string;
  latitude: number;
  longitude: number;
  verified: boolean;
  source: string;
}

export interface Waypoint {
  index: number;
  latitude: number;
  longitude: number;
  km_from_start: number;
  name: string | null;
}

export interface Route {
  type: string;
  distance_km: number;
  distance_nm: number;
  initial_bearing_deg: number;
  initial_bearing_compass: string;
  waypoints: Waypoint[];
  land_crossings: { latitude: number; longitude: number; km_from_start: number }[];
  warnings: string[];
  is_navigable_direct: boolean;
  disclaimer: string;
}

export interface Destination {
  latitude: number;
  longitude: number;
  name: string;
  source: 'USER_SELECTED' | 'INCOIS_PFZ';
  pfz_index?: number;
}

export interface EmergencyReturn extends LandingCentreInfo {
  distance_from_destination_km: number;
  bearing_from_destination_deg: number;
  bearing_from_destination_compass: string;
  distance_from_route_midpoint_km: number;
}

export interface PackagedPFZ {
  status: string;
  advisory_date: string | null;
  validity_date: string | null;
  count: number;
  locations: {
    landing_centre: string;
    direction: string;
    bearing_degrees: number;
    distance_km: number | string;
    depth_min_m?: number | null;
    depth_max_m?: number | null;
    latitude: number;
    longitude: number;
  }[];
  source: string;
}

export interface PackagedWarningItem {
  warning_type: string;
  severity: string;
  description: string;
  valid_from: string;
  valid_until: string;
  issued_at: string;
  source_name: string;
}

export interface PackagedWarnings {
  status: 'LIVE' | 'NO_ACTIVE_BULLETIN' | 'UNAVAILABLE' | string;
  source: string;
  issued_at: string | null;
  valid_until: string | null;
  items: PackagedWarningItem[];
}

export interface ForecastPoint {
  waypoint_index: number | null;
  latitude: number;
  longitude: number;
  hourly: {
    time: string[];
    wave_height_m: (number | null)[];
    wave_period_s: (number | null)[];
    wave_direction_deg: (number | null)[];
    swell_wave_height_m: (number | null)[];
    wind_speed_kmh: (number | null)[];
    wind_direction_deg: (number | null)[];
    wind_gusts_kmh: (number | null)[];
  };
}

export interface PackagedForecast {
  status: string;
  provider: string;
  retrieved_at: string;
  valid_from: string | null;
  valid_until: string | null;
  points: ForecastPoint[];
  error: string | null;
}

export interface PackagedPredictions {
  status: string;
  model_version: string | null;
  prediction_timestamp: string | null;
  valid_until: string | null;
  target_interpretation?: string;
  decision_threshold?: number;
  grid_resolution_deg?: number;
  cells: { lat: number; lon: number; p: number; high: number }[];
  disclaimer?: string;
}

export interface SafetyRules {
  wave_height_threshold_m: number;
  wind_speed_threshold_kmh: number;
  severe_severities: string[];
  caution_severities: string[];
  normal_severities: string[];
  statuses: string[];
  rule: string;
}

export interface OfflineAsset {
  kind: string;
  url?: string;
  available: boolean;
  size_bytes?: number | null;
  note: string;
}

export interface ExpeditionPackage {
  manifest: {
    schema_version: number;
    package_id: string;
    device_id: string;
    created_at: string;
    valid_until: string | null;
    planned_departure: string | null;
    planned_return: string | null;
    component_expiry: {
      warnings: string | null;
      forecast: string | null;
      predictions: string | null;
      pfz: string | null;
    };
    disclaimers: string[];
  };
  landing_centre: LandingCentreInfo;
  destination: Destination;
  route: Route;
  emergency_returns: EmergencyReturn[];
  pfz: PackagedPFZ;
  warnings: PackagedWarnings;
  forecast: PackagedForecast;
  predictions: PackagedPredictions;
  safety_rules: SafetyRules;
  offline_assets: {
    basemap: OfflineAsset;
    bathymetry: OfflineAsset;
    nautical_charts: OfflineAsset;
    bbox: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  };
}

// ---------------------------------------------------------------------------
// Device-side records (stored in IndexedDB, synced later)
// ---------------------------------------------------------------------------
export interface TrackPoint {
  client_uuid: string;
  expedition_id: string;
  recorded_at: string;
  latitude: number;
  longitude: number;
  speed_mps: number | null;
  heading_deg: number | null;
  accuracy_m: number | null;
  synced: 0 | 1;
}

export interface CatchRecord {
  client_uuid: string;
  expedition_id: string;
  recorded_at: string;
  latitude: number | null;
  longitude: number | null;
  species: string;
  weight_kg: number | null;
  notes: string | null;
  synced: 0 | 1;
}

export interface FieldObservation {
  client_uuid: string;
  expedition_id: string;
  recorded_at: string;
  latitude: number | null;
  longitude: number | null;
  observation_type: string;
  value: string | null;
  notes: string | null;
  synced: 0 | 1;
}

export interface SyncResponse {
  received: Record<string, number>;
  inserted: Record<string, number>;
  duplicates: Record<string, number>;
  acknowledged_uuids: string[];
  synced_at: string;
  delta?: {
    warnings: PackagedWarnings;
    predictions: PackagedPredictions;
    pfz: PackagedPFZ;
    forecast?: PackagedForecast;
  };
}

export interface OfflineSafetyResult {
  status: SafetyStatus;
  reason: string;
  wave_height_m: number | null;
  wind_speed_kmh: number | null;
  warnings_expired: boolean;
  forecast_expired: boolean;
}
