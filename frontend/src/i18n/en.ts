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

  // Expedition mode
  exp_title: 'Offline Expedition',
  exp_tab_dashboard: 'Dashboard',
  exp_tab_expedition: 'Expedition',
  exp_plan: 'Plan',
  exp_download: 'Download',
  exp_at_sea: 'At Sea',
  exp_catch: 'Catch Log',
  exp_sync: 'Sync',
  exp_landing_centre: 'Departure landing centre',
  exp_destination: 'Fishing destination',
  exp_pick_pfz: 'Pick an INCOIS fishing zone',
  exp_or_tap_map: 'or tap a point on the map',
  exp_route_preview: 'Route preview',
  exp_distance: 'Distance',
  exp_bearing: 'Bearing',
  exp_route_crosses_land: 'Direct line crosses land — plan your own passage',
  exp_build_package: 'Build expedition package',
  exp_building: 'Building package…',
  exp_package_ready: 'Package ready for offline use',
  exp_valid_until: 'Valid until',
  exp_component: 'Component',
  exp_expires: 'Expires',
  exp_basemap: 'Coastal map',
  exp_bathymetry: 'Depth contours',
  exp_charts: 'Nautical charts',
  exp_not_available: 'Not available',
  exp_download_assets: 'Download offline map',
  exp_start: 'Start expedition',
  exp_position: 'Position',
  exp_heading: 'Heading',
  exp_speed: 'Speed',
  exp_to_target: 'To target',
  exp_off_track: 'Off track',
  exp_eta: 'ETA',
  exp_nearest_return: 'Nearest return harbour',
  exp_waiting_gps: 'Waiting for GPS fix…',
  exp_gps_unsupported: 'GPS not available on this device',
  exp_offline: 'Offline',
  exp_online: 'Online',
  exp_log_catch: 'Log catch',
  exp_species: 'Species',
  exp_weight: 'Weight (kg)',
  exp_notes: 'Notes',
  exp_save: 'Save',
  exp_pending: 'Pending upload',
  exp_last_sync: 'Last sync',
  exp_sync_now: 'Sync now',
  exp_never: 'Never',
  exp_safety_expired: 'Warning data expired — safety cannot be confirmed',
  exp_end: 'End expedition',
  exp_not_chart: 'Not a navigational chart. Follow official IMD/INCOIS advisories.',
  exp_no_package: 'No expedition package on this device. Plan one while you have signal.',
  exp_waypoint: 'Waypoint',
  exp_track_points: 'Track points',
  exp_night_mode: 'Night mode',
  exp_emergency: 'Emergency / MOB',
  exp_black_box: 'Voyage Black Box',
} as const;

export type TranslationKey = keyof typeof en;
export default en;
