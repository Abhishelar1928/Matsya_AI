/**
 * MatsyaAI Maharashtra — API Service
 *
 * All frontend-to-backend communication goes through here.
 * The Vite proxy handles routing /api/* to the backend service.
 */

import type { HealthResponse } from '../types/health';
import type { MapSummaryResponse, MarineForecast, MarineWarnings } from '../types/map';

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
export async function fetchMapSummary(demo: boolean = false): Promise<MapSummaryResponse> {
  const url = `${API_BASE}/map/summary${demo ? '?demo=true' : ''}`;
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
