/**
 * MatsyaAI Maharashtra — Map & Prediction Types
 */

export type SafetyStatus = 'SAFE_CONFIRMED' | 'CAUTION' | 'UNSAFE' | 'NO_WARNING_DATA';

export interface CellPrediction {
  grid_cell_id: string;
  latitude: number;
  longitude: number;
  distance_to_coast_km: number;
  is_coastal: boolean;
  predicted_apparent_fishing_probability: number;
  predicted_apparent_fishing_binary: number;
  prediction_label: string;
  target_interpretation: string;
  decision_threshold: number;
  model_version: string;
  prediction_timestamp: string;
  data_freshness_status: string;
  disclaimer: string;
  current_wave_height_m: number | null;
  current_wind_speed_kmh: number | null;
  safety_status: SafetyStatus;
  safety_override: boolean;
}

export interface PFZLocation {
  landing_centre: string;
  direction: string;
  bearing_degrees: number;
  distance_km: number | string;
  latitude: number;
  longitude: number;
}

export interface PFZAdvisory {
  status: string;
  advisory_date: string | null;
  validity_date: string | null;
  count: number;
  locations: PFZLocation[];
  source: string;
}

export interface MarineSafety {
  overall_status: SafetyStatus;
  message: string;
  independent_of_ml: boolean;
  authority: string;
}

export interface LandingCentre {
  name: string;
  district: string;
  latitude: number;
  longitude: number;
}

export interface MapMetadata {
  application: string;
  model_version: string;
  prediction_timestamp: string;
  target_interpretation: string;
  data_freshness_status: string;
  demo_mode: boolean;
  disclaimer: string;
}

// Source freshness types — mirrors backend SourceFreshnessTracker output
export interface SourceFreshnessState {
  status: string;
  data_timestamp: string | null;
  age_days?: number | null;
  age_minutes?: number | null;
}

export interface SourceFreshness {
  incois_pfz: SourceFreshnessState;
  imd_marine_warnings: SourceFreshnessState;
  open_meteo_marine: SourceFreshnessState;
  global_fishing_watch: SourceFreshnessState;
}

// Prediction provenance — mirrors backend prediction_provenance structure
export interface GFWContextSource {
  status: string;
  observation_date: string | null;
  age_days: number | null;
}

export interface EnvironmentalSource {
  status: string;
  retrieved_at: string | null;
  data_timestamp: string | null;
  age_minutes: number | null;
}

export interface IncoisPFZSource {
  status: string;
  advisory_date: string | null;
  valid_until: string | null;
  age_minutes: number | null;
}

export interface MarineSafetySource {
  overall_status: string;
  imd_status: string;
  data_timestamp: string | null;
  valid_until: string | null;
  independent_of_ml: boolean;
}

export interface PredictionProvenanceSources {
  gfw_context: GFWContextSource;
  environmental: EnvironmentalSource;
  incois_pfz: IncoisPFZSource;
  marine_safety: MarineSafetySource;
}

export interface PredictionProvenance {
  overall_data_status: string;
  prediction_timestamp: string | null;
  sources: PredictionProvenanceSources;
}

export interface MapSummaryResponse {
  metadata: MapMetadata;
  marine_safety: MarineSafety;
  predictions: CellPrediction[];
  pfz_advisory: PFZAdvisory;
  landing_centres: LandingCentre[];
  source_freshness?: SourceFreshness;
  prediction_provenance?: PredictionProvenance;
}
