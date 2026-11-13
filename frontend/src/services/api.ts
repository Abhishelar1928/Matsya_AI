/**
 * MatsyaAI Maharashtra — API Service
 *
 * All frontend-to-backend communication goes through here.
 * The Vite proxy handles routing /api/* to the backend service.
 */

import type { HealthResponse } from '../types/health';
import type { MapSummaryResponse } from '../types/map';

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
