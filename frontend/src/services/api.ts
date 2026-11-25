/**
 * MatsyaAI Maharashtra — API Service
 *
 * All frontend-to-backend communication goes through here.
 * The Vite proxy handles routing /api/* to the backend service.
 */

import type { HealthResponse } from '../types/health';
import type {
  DistrictWarningsResponse,
  MapSummaryResponse,
  MarineForecast,
  MarineWarnings,
  OceanLayersManifest,
} from '../types/map';

const API_BASE = '/api/v1';

/**
 * Fetch application health status from the backend.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`);

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<HealthResponse>;
}

/**
 * Fetch consolidated map summary payload from the backend.
 */
export async function fetchMapSummary(): Promise<MapSummaryResponse> {
  const url = `${API_BASE}/map/summary`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Map summary failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<MapSummaryResponse>;
}

/**
 * Active IMD marine warnings with issue / validity timestamps.
 */
export async function fetchMarineWarnings(): Promise<MarineWarnings> {
  const response = await fetch(`${API_BASE}/marine/warnings`);
  if (!response.ok) throw new Error(`Marine warnings failed: ${response.status}`);
  return response.json() as Promise<MarineWarnings>;
}

/**
 * 72 h hourly wave/wind forecast for one offshore point per coastal district.
 */
export async function fetchMarineForecast(): Promise<MarineForecast> {
  const response = await fetch(`${API_BASE}/marine/forecast`);
  if (!response.ok) throw new Error(`Marine forecast failed: ${response.status}`);
  return response.json() as Promise<MarineForecast>;
}

/**
 * Acquired oceanographic, bathymetric, MPA, and hazard layers manifest (EPSG:4326).
 */
export async function fetchOceanLayers(): Promise<OceanLayersManifest> {
  const response = await fetch(`${API_BASE}/marine/ocean-layers`);
  if (!response.ok) throw new Error(`Ocean layers failed: ${response.status}`);
  return response.json() as Promise<OceanLayersManifest>;
}

/**
 * Live district weather warnings from NDMA SACHET CAP and IMD (when configured).
 */
export async function fetchDistrictWarnings(): Promise<DistrictWarningsResponse> {
  const response = await fetch(`${API_BASE}/marine/district-warnings`);
  if (!response.ok) throw new Error(`District warnings failed: ${response.status}`);
  return response.json() as Promise<DistrictWarningsResponse>;
}
