"""
MatsyaAI Maharashtra — ML Pipeline Configuration.

Central configuration for all ML pipeline parameters.
All thresholds, paths, feature lists, and API settings are defined here.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ML_DIR = Path(__file__).parent
DATA_DIR = ML_DIR / "data"
ARTIFACTS_DIR = ML_DIR / "artifacts"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Cache files
HISTORICAL_CACHE_PATH = DATA_DIR / "historical_full_year_2023.parquet"
GFW_RAW_CACHE_DIR = DATA_DIR / "gfw_raw"
ENV_RAW_CACHE_DIR = DATA_DIR / "env_raw"

# Model artifacts (Phase 3 Validated XGBoost Artifacts)
MODEL_PATH = ARTIFACTS_DIR / "phase3_xgboost_model.joblib"
IMPUTER_PATH = ARTIFACTS_DIR / "phase3_imputer.joblib"
SCALER_PATH = ARTIFACTS_DIR / "phase3_scaler.joblib"
THRESHOLD_PATH = ARTIFACTS_DIR / "phase3_threshold.json"
FEATURE_COLUMNS_PATH = ARTIFACTS_DIR / "phase3_feature_columns.json"
METADATA_PATH = ARTIFACTS_DIR / "phase3_metadata.json"

# ---------------------------------------------------------------------------
# Spatial Grid Configuration
# ---------------------------------------------------------------------------
GRID_RESOLUTION = 0.25  # degrees

# Maharashtra marine area bounds
GRID_MIN_LAT = 15.50
GRID_MAX_LAT = 20.00
GRID_MIN_LON = 72.00
GRID_MAX_LON = 74.00

# GFW filtering bounds (West Coast India, broader for GFW capture)
GFW_MIN_LAT = 15.50
GFW_MAX_LAT = 20.00
GFW_MIN_LON = 72.00
GFW_MAX_LON = 74.00

# ---------------------------------------------------------------------------
# GFW Configuration
# ---------------------------------------------------------------------------
GFW_API_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
GFW_DATASET = "public-global-fishing-effort:latest"
GFW_REGION_DATASET = "public-eez-areas"
GFW_REGION_ID = "8480"  # India EEZ MRGID
GFW_SPATIAL_RESOLUTION = "HIGH"  # 0.01 degree
GFW_TEMPORAL_RESOLUTION = "DAILY"

# Historical date range (Full year 2023)
GFW_START_DATE = "2023-01-01"
GFW_END_DATE = "2023-12-31"

# ---------------------------------------------------------------------------
# Copernicus Marine Service (CMEMS) Configuration
# ---------------------------------------------------------------------------
CMEMS_USERNAME = os.environ.get("COPERNICUS_MARINE_SERVICE_USERNAME")
CMEMS_PASSWORD = os.environ.get("COPERNICUS_MARINE_SERVICE_PASSWORD")

# Global Ocean Physics Analysis and Forecast (0.083 deg ~ 8km)
CMEMS_PRODUCT_PHYSICS = "cmems_mod_glo_phy_anfc_0.083deg_P1D-m"
# Global Ocean Waves Analysis and Forecast (0.083 deg ~ 8km)
CMEMS_PRODUCT_WAVES = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
# Global Ocean Biogeochemistry Analysis and Forecast (0.25 deg ~ 25km)
CMEMS_PRODUCT_BGC = "cmems_mod_glo_bgc_anfc_0.25deg_P1D-m"

# ---------------------------------------------------------------------------
# Open-Meteo Configuration (Legacy / Fallback)
# ---------------------------------------------------------------------------
OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_MARINE_CURRENT_URL = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_WEATHER_CURRENT_URL = "https://api.open-meteo.com/v1/forecast"

# Historical marine variables (verified available for Oct 2023)
HISTORICAL_MARINE_VARIABLES = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "ocean_current_velocity",
]

# Historical weather variables
HISTORICAL_WEATHER_VARIABLES = [
    "wind_speed_10m",
]

# Max coordinates per Open-Meteo request
OPEN_METEO_MAX_LOCATIONS = 10

# ---------------------------------------------------------------------------
# Feature Configuration
# ---------------------------------------------------------------------------
# Environmental features from APIs (must match what's fetchable)
ENV_FEATURE_COLUMNS = [
    "wave_height",
    "wave_period",
    "wave_direction_sin",
    "wave_direction_cos",
    "swell_wave_height",
    "ocean_current_velocity",
    "wind_speed",
    "wave_height_isna",
    "ocean_current_isna",
    "wind_speed_isna",
]

# Spatial features (static, derived from grid)
SPATIAL_FEATURE_COLUMNS = [
    "latitude",
    "longitude",
    "distance_to_coast_km",
    "is_coastal",
]

# Temporal features (derived from observation_date)
TEMPORAL_FEATURE_COLUMNS = [
    "day_of_year",
    "month",
    "day_of_week",
    "sin_day_of_year",
    "cos_day_of_year",
]

# GFW Lag Features
LAG_FEATURE_COLUMNS = [
    "fishing_hours_recent",
    "fishing_hours_lag_1",
    "fishing_hours_lag_2",
    "fishing_hours_lag_3",
    "fishing_hours_7d_mean",
    "fishing_hours_7d_max",
    "fishing_hours_7d_std",
    "fishing_hours_7d_pos_freq",
    "fishing_hours_14d_mean",
    "regional_fishing_hours_T",
]

# Complete ordered feature list for model
ALL_FEATURE_COLUMNS = (
    LAG_FEATURE_COLUMNS
    + ENV_FEATURE_COLUMNS
    + SPATIAL_FEATURE_COLUMNS
    + TEMPORAL_FEATURE_COLUMNS
)

# Features explicitly EXCLUDED with documented reasons
EXCLUDED_FEATURES = {
    "sst": "Not available on Open-Meteo marine historical API",
    "temperature_2m": "Excluded by design: air temp is not SST proxy",
    "chlorophyll": "No free historical API available",
    "salinity": "No free historical API available",
    "ocean_current_direction": "Circular variable requires special encoding; excluded from PoC",
}

# ---------------------------------------------------------------------------
# Target Configuration
# ---------------------------------------------------------------------------
TARGET_COLUMN = "target"
FISHING_HOURS_COLUMN = "fishing_hours"
TARGET_THRESHOLD_PERCENTILE = 0.75  # 75th percentile of non-zero training effort
TARGET_DESCRIPTION = "predicted apparent fishing activity (derived from GFW AIS data)"

# ---------------------------------------------------------------------------
# Train / Validation / Test Split
# ---------------------------------------------------------------------------
TRAIN_FRACTION = 0.60
VAL_FRACTION = 0.20
TEST_FRACTION = 0.20

# ---------------------------------------------------------------------------
# Safety Gate Configuration
# ---------------------------------------------------------------------------
# These are APPLICATION-LEVEL thresholds, NOT official government thresholds.
# They require domain expert validation before production use.
SAFETY_WAVE_HEIGHT_THRESHOLD = 4.0  # meters
SAFETY_WIND_SPEED_THRESHOLD = 50.0  # km/h

SAFETY_STATUSES = {
    "SAFE_CONFIRMED": "Current safety data confirms safe conditions",
    "NO_WARNING_DATA": "No marine warning data available to confirm safety",
    "CAUTION": "Environmental conditions suggest caution",
    "UNSAFE": "Active severe marine warning for this area",
    "BLOCKED": "Grid cell is in a restricted/no-go zone",
}

# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------
MODEL_LABEL = "2023 historical model"
MODEL_DISCLAIMER = (
    "This model predicts apparent fishing activity based on GFW historical "
    "patterns for the full year 2023. It does NOT predict fish presence, "
    "biomass, catch probability, or safety."
)

# Environmental aggregation method for daily features
ENV_DAILY_AGGREGATION = "mean"  # daily mean of hourly observations

# Temporal matching tolerance
TEMPORAL_MATCH_TOLERANCE_HOURS = 0  # exact same-date match
