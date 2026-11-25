"""
MatsyaAI Maharashtra — Application Configuration.

Uses Pydantic BaseSettings for type-safe, environment-based configuration.
All secrets and service URLs are loaded from environment variables / .env file.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "MatsyaAI Maharashtra"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://matsya:matsya_dev@db:5432/matsya_ai"
    POSTGRES_DB: str | None = None

    # --- External APIs ---
    IMD_API_KEY: str | None = None
    IMD_DISTRICT_API_URL: str = "https://api.imd.gov.in/api/v1/districtwarning"
    GFW_API_TOKEN: str | None = None
    PROTECTED_PLANET_API_TOKEN: str | None = None

    # --- Maharashtra Coastal Bounding Box (WGS84 / EPSG:4326) ---
    MAHARASHTRA_MIN_LAT: float = 15.0
    MAHARASHTRA_MAX_LAT: float = 20.6
    MAHARASHTRA_MIN_LON: float = 71.0
    MAHARASHTRA_MAX_LON: float = 74.2

    # --- CORS ---
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # --- Data Sources (placeholders — never fabricate) ---
    INCOIS_BASE_URL: str = ""
    IMD_BASE_URL: str = ""
    MAHARASHTRA_FISHERIES_BASE_URL: str = ""

    # --- Scheduler Intervals (minutes) ---
    INCOIS_PFZ_INTERVAL_MINUTES: int = 24 * 60  # Daily
    IMD_MARINE_INTERVAL_MINUTES: int = 4 * 60   # Every 4 hours
    OPEN_METEO_INTERVAL_MINUTES: int = 60       # Hourly
    GFW_CONTEXT_INTERVAL_MINUTES: int = 7 * 24 * 60 # Weekly

    # --- Logging ---
    LOG_LEVEL: str = "INFO"


# Singleton settings instance
settings = Settings()
