/**
 * MatsyaAI Maharashtra — Offline Expedition Mode types.
 * Mirrors backend/app/services/expedition/package_builder.py (schema_version 1).
 */

import type { SafetyStatus } from '../../types/map';
import type { SpeciesEntry } from '../services/speciesCatalogue';

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
  is_direct_reference_only?: boolean;
  coverage_disclosures?: string[];
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
    swell_wave_period_s?: (number | null)[];
    ocean_current_velocity_mps?: (number | null)[];
    ocean_current_direction_deg?: (number | null)[];
    ocean_current_u_mps?: (number | null)[];
    ocean_current_v_mps?: (number | null)[];
    sea_surface_temperature_c?: (number | null)[];
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

export interface PackageManifest {
  schema_version: number;
  package_id: string;
  device_id: string;
  created_at: string;
  generated_at?: string;
  valid_from?: string | null;
  valid_until: string | null;
  planned_departure: string | null;
  planned_return: string | null;
  source?: string;
  version?: string;
  coverage?: { min_lat: number; max_lat: number; min_lon: number; max_lon: number; region?: string };
  component_versions?: Record<string, string>;
  checksums?: Record<string, string>;
  component_expiry: {
    warnings: string | null;
    forecast: string | null;
    predictions: string | null;
    pfz: string | null;
  };
  disclaimers: string[];
}

export interface ExpeditionPackage {
  manifest: PackageManifest;
  landing_centre: LandingCentreInfo;
  destination: Destination;
  route: Route;
  emergency_returns: EmergencyReturn[];
  pfz: PackagedPFZ;
  warnings: PackagedWarnings;
  forecast: PackagedForecast;
  predictions: PackagedPredictions;
  safety_rules: SafetyRules;
  species_catalogue?: SpeciesEntry[];
  offline_assets: {
    basemap: OfflineAsset;
    bathymetry: OfflineAsset;
    marine_protected_areas?: OfflineAsset;
    offshore_installations?: OfflineAsset;
    shipping_lanes?: OfflineAsset;
    ocean_currents?: OfflineAsset;
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
  cog_deg?: number | null;
  compass_heading_deg?: number | null;
  xte_km?: number | null;
  accuracy_m: number | null;
  synced: 0 | 1;
  sync_error?: string | null;
}

export interface CatchRecord {
  client_uuid: string;
  expedition_id: string;
  recorded_at: string;
  latitude: number | null;
  longitude: number | null;
  species: string;
  species_id?: string | null;
  weight_kg: number | null;
  quantity?: number | null;
  fishing_duration_min?: number | null;
  estimated_value_inr?: number | null;
  notes: string | null;
  synced: 0 | 1;
  sync_error?: string | null;
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
  sync_error?: string | null;
}

export type VoyageEventType =
  | 'VOYAGE_START'
  | 'VOYAGE_RESUME'
  | 'WAYPOINT_ARRIVED'
  | 'DESTINATION_ARRIVED'
  | 'ROUTE_DEVIATION'
  | 'ROUTE_RECOVERED'
  | 'SAFETY_CHANGE'
  | 'GPS_LOST'
  | 'GPS_RESTORED'
  | 'GPS_JUMP_REJECTED'
  | 'VISIBILITY_INTERRUPTED'
  | 'VISIBILITY_RESUMED'
  | 'MOB_MARKED'
  | 'MOB_CLEARED'
  | 'ANCHOR_SET'
  | 'ANCHOR_DRIFT_ALERT'
  | 'ANCHOR_CLEARED';

export interface VoyageEvent {
  client_uuid: string;
  expedition_id: string;
  recorded_at: string;
  event_type: VoyageEventType;
  latitude: number | null;
  longitude: number | null;
  detail: string;
  synced: 0 | 1;
}

export interface MobMarker {
  latitude: number;
  longitude: number;
  marked_at: string;
}

export interface AnchorWatchState {
  latitude: number;
  longitude: number;
  radius_m: number;
  set_at: string;
}

export interface PersistedVoyageState {
  expedition_id: string;
  active_waypoint_index: number;
  arrived_destination: boolean;
  last_safety_state: string | null;
  mob: MobMarker | null;
  anchor_watch: AnchorWatchState | null;
  started_at: string;
  updated_at: string;
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
