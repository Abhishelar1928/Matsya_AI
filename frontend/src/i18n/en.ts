/**
 * MatsyaAI Maharashtra — English Translations
 */

const en = {
  app_name: 'MatsyaAI',
  app_region: 'Maharashtra',
  app_tagline: 'Marine Decision Support',

  // Status
  fishing_condition: "Today's Fishing Condition",
  status_safe: 'Good',
  status_caution: 'Caution',
  status_danger: 'Do Not Go',

  // Conditions
  sea: 'Sea',
  wind: 'Wind',
  waves: 'Waves',
  rain: 'Rain',
  calm: 'Calm',
  moderate: 'Moderate',
  low: 'Low',

  // Warnings
  fishermen_warning: 'Fishermen Warning',
  no_active_warning: 'No active warning',

  // Actions
  find_spots: 'Find Best Fishing Spots',
  navigate: 'Navigate to this Zone',

  // Connection
  backend_connected: 'Backend Connected',
  backend_disconnected: 'Backend Disconnected',
  checking_connection: 'Checking Connection…',
  data_sources: 'Data: INCOIS + IMD',

  // General
  loading: 'Loading…',
  error: 'Error',
  updated: 'Updated',
  version: 'Version',
} as const;

export type TranslationKey = keyof typeof en;
export default en;
