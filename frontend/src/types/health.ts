/**
 * MatsyaAI Maharashtra — Health API Response Types
 */

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  version: string;
  environment: string;
  database: 'connected' | 'disconnected';
  timestamp: string;
}
