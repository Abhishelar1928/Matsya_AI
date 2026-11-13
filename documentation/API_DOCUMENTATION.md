# 6. API Documentation

This document provides a comprehensive REST API specification for all internal endpoints exposed by the MatsyaAI FastAPI backend, as well as the external APIs consumed by the ingestion and inference pipelines.

---

## 6.1 Internal API Endpoints Catalog

| Endpoint | HTTP Method | Router Tag | Summary | Authentication |
| :--- | :--- | :--- | :--- | :--- |
| [`/`](#1-root-endpoint) | `GET` | Root | Application discovery and health links | None (Public) |
| [`/api/v1/health`](#2-application-health-check) | `GET` | Health | Service liveness and database connectivity | None (Public) |
| [`/api/v1/map/summary`](#3-consolidated-map-summary) | `GET` | Map | Consolidated map payload (Grid, PFZ, Safety, HUD) | None (Public) |
| [`/api/v1/predictions/latest`](#4-latest-predictions) | `GET` | Predictions | Latest ML apparent fishing activity batch | None (Public) |
| [`/api/v1/pfz/latest`](#5-latest-incois-pfz-advisories) | `GET` | PFZ | Latest official INCOIS PFZ records | None (Public) |
| [`/api/v1/sources/freshness`](#6-source-freshness-and-health) | `GET` | Sources | Live freshness, validity, and latency across sources | None (Public) |

---

## 6.2 Internal API Detailed Specifications

### 1. Root Endpoint
- **Endpoint:** `/`
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/main.py` (lines 87–95)
- **Purpose:** Quick operational check confirming the API gateway is alive and providing links to interactive documentation.
- **Request Parameters:** None.
- **Request Headers:** None.
- **Response Structure (200 OK):**
```json
{
  "app": "MatsyaAI Maharashtra",
  "version": "0.1.0",
  "docs": "/docs",
  "health": "/api/v1/health"
}
```

---

### 2. Application Health Check
- **Endpoint:** `/api/v1/health`
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/api/v1/health.py` (lines 37–54)
- **Purpose:** Probes application health and executes an active database ping (`SELECT 1`) to verify PostgreSQL/PostGIS connectivity. Used by Docker Compose health checks and the frontend header.
- **Request Parameters:** None.
- **Response Schema (`HealthResponse`):**
  - `status` (string): `"healthy"` if database connected, `"degraded"` if database unreachable.
  - `version` (string): Semantic application version (`"0.1.0"`).
  - `environment` (string): Application environment (e.g., `"development"`, `"production"`).
  - `database` (string): `"connected"` or `"disconnected"`.
  - `timestamp` (string): ISO-8601 UTC timestamp.
- **Example Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "database": "connected",
  "timestamp": "2026-11-13T14:30:00.123456+00:00"
}
```
- **Error Handling:** Returns `status: "degraded"` and `database: "disconnected"` with HTTP 200 rather than crashing, enabling graceful diagnostic display.

---

### 3. Consolidated Map Summary
- **Endpoint:** `/api/v1/map/summary`
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/api/v1/map.py` (lines 43–241)
- **Purpose:** Primary API driving the fisherman-facing interactive UI. Aggregates the 171-cell prediction grid, official INCOIS PFZ advisory points, independent marine safety alert, coastal harbours, and real-time source freshness.
- **Query Parameters:**
  - `demo` (boolean, optional, default: `false`): When `true`, enables demo mode with cached historical real data fallback if live external feeds are unavailable.
- **Response Structure:**
```json
{
  "metadata": {
    "application": "MatsyaAI Maharashtra",
    "model_version": "Phase3_XGBoost_v1",
    "prediction_timestamp": "2026-09-15T21:00:00+00:00",
    "target_interpretation": "next-calendar-day apparent fishing activity (>1.0 fishing hours)",
    "data_freshness_status": "LIVE",
    "demo_mode": false,
    "disclaimer": "Predictions indicate apparent fishing activity derived from historical vessel tracking patterns..."
  },
  "marine_safety": {
    "overall_status": "CAUTION",
    "message": "Rough sea or high wind conditions observed in certain marine sectors. Exercise caution.",
    "independent_of_ml": true,
    "authority": "IMD / INCOIS Official Marine Weather Guidelines"
  },
  "source_freshness": {
    "incois_pfz": {
      "source_name": "INCOIS Potential Fishing Zone (PFZ)",
      "status": "LIVE",
      "data_timestamp": "2026-09-15T00:00:00+00:00",
      "valid_until": "2026-09-16T23:59:59+00:00",
      "age_minutes": 1273.4,
      "record_count": 120
    },
    "imd_marine_warnings": {
      "source_name": "IMD Mumbai Fishermen Warning Bulletin",
      "status": "LIVE",
      "data_timestamp": "2026-09-15T15:30:00+00:00",
      "valid_until": "2026-09-19T23:59:59+00:00",
      "age_minutes": 343.4,
      "record_count": 7
    },
    "open_meteo_marine": {
      "source_name": "Open-Meteo Marine Forecast",
      "status": "LIVE",
      "data_timestamp": "2026-09-15T21:00:00+00:00",
      "valid_until": "2026-09-16T00:00:00+00:00",
      "age_minutes": 13.4,
      "record_count": 18
    },
    "global_fishing_watch": {
      "source_name": "Global Fishing Watch (GFW AIS)",
      "status": "UNAVAILABLE",
      "data_timestamp": null,
      "age_days": null,
      "record_count": 0
    }
  },
  "predictions": [
    {
      "grid_cell_id": "cell_17.75_72.75_0.25",
      "latitude": 17.875,
      "longitude": 72.875,
      "distance_to_coast_km": 42.15,
      "is_coastal": true,
      "predicted_apparent_fishing_probability": 0.6842,
      "predicted_apparent_fishing_binary": 1,
      "prediction_label": "High Apparent Fishing Effort",
      "safety_status": "CAUTION",
      "safety_override": false
    }
  ],
  "pfz_advisory": {
    "status": "LIVE",
    "advisory_date": "2026-09-15T00:00:00+00:00",
    "validity_date": "2026-09-16T23:59:59+00:00",
    "count": 120,
    "locations": [
      {
        "landing_centre": "Ratnagiri - Mirkarwada",
        "direction": "SW",
        "bearing_degrees": 225,
        "distance_km": "32.5",
        "latitude": 17.85,
        "longitude": 73.05
      }
    ],
    "source": "INCOIS (Official Government Advisory)"
  },
  "landing_centres": [
    {
      "name": "Mumbai - Sassoon Dock",
      "district": "Mumbai",
      "latitude": 19.0760,
      "longitude": 72.8777
    }
  ]
}
```

---

### 4. Latest Predictions
- **Endpoint:** `/api/v1/predictions/latest` (also mapped to `/api/v1/predictions`)
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/api/v1/predictions.py` (lines 97–115)
- **Purpose:** Fetches the most recent scheduled batch prediction records from PostgreSQL.
- **Query Parameters:**
  - `demo` (boolean, optional, default: `false`).
- **Response Structure (200 OK):** Array of `CellPrediction` dictionaries.
- **Status Codes:**
  - `200 OK`: Successful retrieval.
  - `500 Internal Server Error`: Database connection failure.

---

### 5. Latest INCOIS PFZ Advisories
- **Endpoint:** `/api/v1/pfz/latest`
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/api/v1/pfz.py` (lines 50–144)
- **Purpose:** Returns the latest official INCOIS Potential Fishing Zone locations ingested from the government portal.
- **Query Parameters:**
  - `demo` (boolean, optional, default: `false`): Falls back to cached historical demonstration coordinates if the database contains no active records.
- **Response Schema (`PFZLatestResponse`):**
```json
{
  "source": "INCOIS",
  "source_type": "OFFICIAL_PFZ_ADVISORY",
  "sector": "Maharashtra",
  "status": "LIVE",
  "advisory_date": "2026-09-15T00:00:00+00:00",
  "validity_date": "2026-09-16T23:59:59+00:00",
  "retrieved_at": "2026-09-15T21:04:51.202049+00:00",
  "count": 120,
  "locations": [
    {
      "landing_centre": "Sindhudurg - Malvan",
      "direction": "WNW",
      "bearing_degrees": 290,
      "distance_km": "28.0",
      "depth_min_m": 35,
      "depth_max_m": 50,
      "latitude": 16.15,
      "longitude": 73.20
    }
  ],
  "error": null
}
```

---

### 6. Source Freshness and Health
- **Endpoint:** `/api/v1/sources/freshness`
- **HTTP Method:** `GET`
- **Source Code Location:** `backend/app/api/v1/sources.py` (lines 24–41)
- **Purpose:** Returns operational status, real observation timestamps, expiration dates, record counts, and data age across all four authoritative feeds.
- **Response Structure (200 OK):**
```json
{
  "sources": {
    "incois_pfz": {
      "source_name": "INCOIS Potential Fishing Zone (PFZ)",
      "status": "LIVE",
      "last_successful_fetch": "2026-09-15T21:04:51.202049+00:00",
      "data_timestamp": "2026-09-15T00:00:00+00:00",
      "valid_until": "2026-09-16T23:59:59+00:00",
      "age_minutes": 1273.4,
      "record_count": 120,
      "error": null
    },
    "imd_marine_warnings": {
      "source_name": "IMD Mumbai Fishermen Warning Bulletin",
      "status": "LIVE",
      "last_successful_fetch": "2026-09-15T21:05:22.577742+00:00",
      "data_timestamp": "2026-09-15T15:30:00+00:00",
      "valid_until": "2026-09-19T23:59:59+00:00",
      "age_minutes": 343.4,
      "record_count": 7,
      "error": null
    },
    "open_meteo_marine": {
      "source_name": "Open-Meteo Marine Forecast",
      "status": "LIVE",
      "last_successful_fetch": "2026-09-15T21:09:51.638516+00:00",
      "data_timestamp": "2026-09-15T21:00:00+00:00",
      "valid_until": "2026-09-16T00:00:00+00:00",
      "age_minutes": 13.4,
      "record_count": 18,
      "error": null
    },
    "global_fishing_watch": {
      "source_name": "Global Fishing Watch (GFW AIS)",
      "status": "UNAVAILABLE",
      "last_successful_fetch": null,
      "data_timestamp": null,
      "valid_until": null,
      "age_minutes": null,
      "age_days": null,
      "record_count": 0,
      "error": null
    }
  }
}
```

---

## 6.3 External APIs Consumed by the System

### 1. INCOIS TextData Session & Advisory Endpoints
- **Endpoints:**
  - Session Handshake: `GET https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
  - Maharashtra PFZ Data: `GET https://incois.gov.in/MarineFisheries/TextData?secid=SEC002`
- **Protocol:** HTTPS (Port 443)
- **Authentication:** Session cookie (`JSESSIONID`). Acquired from `TextDataHome` and transmitted in request header.
- **Payload Format:** Server-rendered HTML tables.
- **Handling File:** `backend/app/services/ingestion/incois_pfz_provider.py`

### 2. IMD Mumbai Fishermen Warning Bulletin
- **Endpoint:** `GET https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf`
- **Protocol:** HTTPS
- **Authentication:** None (Public document).
- **Payload Format:** Binary PDF (`application/pdf`).
- **Handling File:** `backend/app/services/ingestion/imd_marine_provider.py`

### 3. Open-Meteo Marine API
- **Endpoint:** `GET https://marine-api.open-meteo.com/v1/marine`
- **Query Parameters:**
  - `latitude`: Comma-delimited latitudes (e.g., `"19.0,17.0,16.0"`).
  - `longitude`: Comma-delimited longitudes (e.g., `"72.8,73.2,73.4"`).
  - `current`: `"wave_height,wave_period,wave_direction,swell_wave_height"`.
  - `timezone`: `"UTC"`.
- **Authentication:** None (Public REST).
- **Rate Limiting:** Managed via 15-minute in-memory caching and 40-coordinate batching.
- **Handling File:** `backend/app/ml/inference.py` and `backend/app/services/ingestion/providers.py`

### 4. Open-Meteo Forecast API
- **Endpoint:** `GET https://api.open-meteo.com/v1/forecast`
- **Query Parameters:**
  - `latitude`, `longitude`, `current=wind_speed_10m`, `timezone=UTC`.
- **Handling File:** `backend/app/ml/inference.py`

### 5. Global Fishing Watch (GFW) 4Wings Report API
- **Endpoint:** `GET https://gateway.api.globalfishingwatch.org/v3/4wings/report`
- **Authentication:** HTTP Header `Authorization: Bearer <GFW_API_TOKEN>`.
- **Query Parameters:** `datasets[0]=public-global-fishing-effort:latest`, `date-range=YYYY-MM-DD,YYYY-MM-DD`, `spatial-resolution=HIGH`, `temporal-resolution=DAILY`, `region-id=8480` (India EEZ).
- **Handling File:** `backend/app/services/ingestion/gfw_provider.py`
