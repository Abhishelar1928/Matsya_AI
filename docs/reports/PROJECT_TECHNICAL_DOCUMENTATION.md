# MatsyaAI Maharashtra — Comprehensive Technical Documentation

> **Role & Perspective:** Senior Software Architect, Full-Stack Developer, and Technical Documentation Engineer  
> **Target Project:** MatsyaAI Maharashtra (Marine Decision-Support & Fishing Activity Forecast Platform)  
> **Repository Root:** `D:\Matsya_AI\`  
> **Document Status:** Complete Consolidated Master Technical Specification  
> **Evaluation & Baseline Date:** 2026-11-13  

---

# Table of Contents
1. [Project Overview](#1-project-overview)
2. [Technology Stack Analysis](#2-technology-stack-analysis)
3. [System Architecture](#3-system-architecture)
4. [Algorithms and Core Logic](#4-algorithms-and-core-logic)
5. [Database Analysis and Design](#5-database-analysis-and-design)
6. [API Documentation](#6-api-documentation)
7. [Project Folder Structure](#7-project-folder-structure)
8. [Feature-by-Feature Technical Explanation](#8-feature-by-feature-technical-explanation)
9. [Security Analysis](#9-security-analysis)
10. [Installation and Execution Guide](#10-installation-and-execution-guide)
11. [Testing, Performance, and Observability](#11-testing-performance-and-observability)
12. [Technical Strengths and Improvement Recommendations](#12-technical-strengths-and-improvement-recommendations)

---


---

# 1. Project Overview

## 1.1 Project Identity & Purpose

**Project Name:** MatsyaAI Maharashtra  
**Domain:** Marine Decision Support, Fisheries Informatics, Geospatial Analytics, Causal Machine Learning  
**Geographic Scope:** Maharashtra Coast & Exclusive Economic Zone (EEZ), India (Lat: 15.50°N – 20.00°N, Lon: 72.00°E – 74.00°E)  
**Primary Mission:** To provide a fisherman-first, safety-decoupled decision support platform that empowers artisanal, motorized, and mechanized marine fishers along the Maharashtra coastline to answer three vital operational questions before every sailing:
1. **Can I safely go fishing today?** (Independent marine safety evaluation based on authoritative alerts and sea thresholds)
2. **Where are the most promising potential fishing grounds today?** (Synthesizing official INCOIS Potential Fishing Zones and predictive machine learning models of apparent vessel activity)
3. **How do I safely navigate from my home landing centre to these grounds?** (Geospatial bearing, distance in nautical kilometers, and district harbour context)

---

## 1.2 Problem Statement

Small-scale artisanal and commercial fishermen operating along Maharashtra's 720 km coastline face substantial economic, environmental, and physical safety hurdles:

1. **Fragmented, Unprocessed Authoritative Information:**
   - The **India Meteorological Department (IMD)** publishes marine cyclone and rough-sea warnings as formatted PDF bulletins (`fisherman.pdf`) that require manual reading, domain interpretation of meteorological terminology (e.g., "squally weather with wind speed 45-55 kmph gusting to 65 kmph"), and geographical spatialization.
   - The **Indian National Centre for Ocean Information Services (INCOIS)** generates Potential Fishing Zone (PFZ) advisories based on satellite Ocean Colour Monitor (OCM) chlorophyll-a fronts and Sea Surface Temperature (SST) thermal boundaries. However, these advisories are served as complex HTML tables requiring session cookies, expressed in Degrees-Minutes-Seconds (DMS) bearings from select ports, rendering them difficult to interpret on mobile devices in coastal villages.

2. **Dangerous Confusion Between "Fish Abundance" and "Sea Safety":**
   - High ocean productivity (e.g., thermal fronts and upwelling) frequently coincides with high winds, monsoonal squalls, and steep swells.
   - Conventional commercial tools often present "fish hot spots" without enforcing independent safety overrides, inducing fishermen into hazardous waters during monsoon transitions or cyclonic depressions.

3. **High Operational Fuel Costs & Economic Inefficiencies:**
   - Marine diesel accounts for 60% to 75% of fishing operational trip expenditure. Without targeted navigation vectors and ground-activity forecasts, boats search blindly across shelf waters, wasting hundreds of litres of fuel and increasing carbon emissions.

4. **Digital Divide & Language Barriers:**
   - The majority of Maharashtra's coastal fishing communities (across Palghar, Mumbai, Raigad, Ratnagiri, and Sindhudurg districts) speak Marathi as their primary language. Most scientific portals and GIS tools are published exclusively in technical English or require desktop GIS software.

5. **Data Staleness & Misleading "All-Clear" Signals:**
   - In distributed data systems, if an external source API fails or is unavailable, naive systems default to showing "No active warnings" — which fishers dangerously misinterpret as "Safe to sail".

---

## 1.3 Objectives & Intended Users

### Core Objectives
- **Zero-Harm Maritime Safety:** Decouple safety evaluation entirely from predictive ML algorithms. Ensure that no ML prediction can ever declare a marine zone "SAFE" without authoritative confirmation.
- **Unified Actionable Dashboard:** Ingest, parse, clean, and consolidate disparate government feeds (IMD, INCOIS, Open-Meteo) into a single visual dashboard.
- **Causal Machine Learning for Vessel Activity:** Predict next-calendar-day ($T+1$) apparent fishing effort using strict causal feature boundaries ($\le T$) to prevent data leakage and provide true forward predictive value.
- **Local Language Inclusivity:** Provide full bilingual support (English and Marathi / मराठी) with high-contrast, fisherman-optimized typography and responsive mobile viewports.
- **Complete Operational Transparency:** Expose exact data provenance, timestamp validity, and source health through an intuitive Freshness HUD.

### Intended User Personas

| Persona | Operational Context | Platform Value Delivered |
| :--- | :--- | :--- |
| **Artisanal Canoe / Small Craft Operator** | Operates non-motorized or small outboard motor (OBM) crafts within 5–15 km from shore; highly vulnerable to swells $>2.0$ m and wind $>35$ km/h. | Receives nearshore wave/wind warnings, immediate visual red/amber safety banners, and nearshore PFZ bearings from local landing centres. |
| **Mechanized Trawler / Purse-Seiner Skipper** | Operates 40–70 ft mechanized vessels with inboard engines operating 20–100 km offshore for 2–6 days. | Evaluates offshore 0.25° grid predictions, deep-water PFZ coordinates ($>50$ m depth), high-sea gale warnings, and optimizes fuel burn. |
| **Fisheries Cooperative Leader / Port Nakhawa** | Coordinates departure schedules for dozens of community boats from landing centres like Sassoon Dock, Mirkarwada, or Malvan. | Views statewide district-level overview, verifies source freshness, and issues community-wide advisory notices. |
| **Fisheries Department Official / Scientific Evaluator** | Audits platform operations, reviews model provenance, monitors seasonal monsoon resumption, and tracks data validity. | Accesses REST APIs (`/sources/freshness`, `/map/summary`), provenance metadata, and scientific evaluation reports. |

---

## 1.4 Core Features & Functionalities

1. **Fisherman-First Advisory Banner (Today's Advisory):**
   - Immediate top-level status indicator: `🚨 UNSAFE`, `⚠️ CAUTION`, `🛡️ SAFE CONFIRMED`, or `ℹ️ SAFETY DATA UNAVAILABLE`.
   - Explicit subtext explaining why a status is assigned, preventing dangerous assumptions when warning feeds are down.
   - Aggregate fishing potential metric displaying the count of high-activity cells.

2. **Official INCOIS PFZ Integration:**
   - Automated scraping and DMS parsing of daily advisories for Maharashtra sector (`SEC002`).
   - Renders official government zones on the map with custom green target markers and 4 km radius buffers.
   - Displays landing centre origin, bearing direction, distance in km, and depth contour ranges.

3. **Independent Multi-Tier Safety Gate:**
   - Independent verification against IMD Mumbai Fishermen Warning bulletins.
   - Application-level environmental threshold enforcement: Wave Height limit ($4.0$ m) and Wind Speed limit ($50$ km/h).
   - Strict rule: **Absence of warnings $\neq$ SAFE.** Yields `NO_WARNING_DATA` with slate-grey indicators if the warning feed is stale or unavailable.

4. **Phase 3 Causal Machine Learning Prediction Engine:**
   - Operationalizes an XGBoost classifier trained on full-year 2023 historical data (59,850 observations across 171 marine cells).
   - Predicts next-calendar-day ($T+1$) apparent fishing effort ($>1.0$ hours) using 29 canonical features.
   - Yields a PR-AUC of 0.4898 (+29.2% over best historical persistence baseline).

5. **Live Environmental Weather Ingestion:**
   - Automatically polls the Open-Meteo Marine and Forecast APIs across Maharashtra coastal grid centroids.
   - Ingests wave height, wave period, swell wave height, wave direction, and 10 m wind speed with 15-minute in-memory caching.

6. **Interactive Leaflet Marine Map:**
   - Built on Leaflet with OpenStreetMap tiles, customized for dark ocean aesthetics (`#071220`).
   - Canonical 0.25° grid overlay with dynamic cyan/blue color coding based on predicted probability.
   - Interactive cell inspection modal displaying distance to coast, coastal/offshore classification, environmental parameters, and disclaimer.
   - Layer toggles for Prediction Grid, INCOIS PFZ Advisories, and Coastal Landing Centres.

7. **Source Freshness & Data Health HUD:**
   - Visual heads-up display displaying real-time operational status (`LIVE`, `STALE`, `CACHED_HISTORICAL`, `UNAVAILABLE`) for INCOIS, IMD, Open-Meteo, and Global Fishing Watch.
   - Displays exact data age in minutes or days computed against actual observation/publication dates, never retrieval time alone.

8. **Bilingual Internationalization (EN / MR):**
   - Instant toggle between English and Marathi across all UI elements, labels, buttons, tooltips, and scientific disclaimers.

9. **Deterministic Ingestion & Deduplication Daemon:**
   - Background scheduling daemon (`backend/scripts/run_ingestion.py --daemon`) executing independent ingestion jobs.
   - SHA-256 batch deduplication ensuring idempotent execution.

10. **Demo Mode with Real Historical Fallbacks:**
    - Seamless fallback toggle enabling testing and demonstration without live network access, using verified historical 2023 cache data.

---

## 1.5 How the Complete Application Works: End-to-End Flow

```mermaid
flowchart TD
    subgraph ExternalSources["Authoritative External Sources"]
        IMD["IMD Mumbai Fishermen Bulletin<br/>(PDF via HTTPS)"]
        INCOIS["INCOIS TextData System<br/>(HTML via Session Cookies)"]
        OpenMeteo["Open-Meteo Marine & Forecast<br/>(JSON REST API)"]
        GFW["Global Fishing Watch 4Wings<br/>(AIS Effort / Historical Parquet)"]
    end

    subgraph IngestionEngine["Ingestion & Normalization Layer (Backend Daemon)"]
        IMDParser["IMDMarineProvider<br/>- PyPDF2 Spatial Visitor<br/>- Kerning Cleanup Regex<br/>- Severity Classifier"]
        INCOISParser["INCOISPFZProvider<br/>- Session Handshake<br/>- BeautifulSoup HTML Parsing<br/>- DMS Coordinate Converter"]
        FreshnessTracker["SourceFreshnessTracker<br/>- Actual Data Timestamps<br/>- Expiry Evaluation"]
        Deduplicator["Deterministic SHA-256<br/>Batch Deduplication"]
    end

    subgraph DataPersistence["Database (PostgreSQL 16 + PostGIS 3.4)"]
        T_Warn["marine_warnings"]
        T_PFZ["incois_pfz_advisories<br/>pfz_zones"]
        T_Env["ocean_observations"]
        T_Pred["predictions"]
        T_Grid["spatial_grids (171 Cells)"]
    end

    subgraph PredictionEngine["Inference & Safety Engine"]
        Inference["Phase4InferencePipeline<br/>- Frozen XGBoost Model<br/>- 29 Canonical Features<br/>- Threshold: 0.47"]
        Safety["SafetyGate<br/>- Active Warnings Filter<br/>- Environmental Thresholds<br/>- Independent Decoupling"]
    end

    subgraph APILayer["FastAPI Application (Port 8000)"]
        MapEndpoint["GET /api/v1/map/summary"]
        PredEndpoint["GET /api/v1/predictions/latest"]
        PFZEndpoint["GET /api/v1/pfz/latest"]
        FreshEndpoint["GET /api/v1/sources/freshness"]
    end

    subgraph UserInterface["Client Layer (React 19 + TypeScript + Leaflet)"]
        HUD["Freshness HUD Card"]
        SafetyBanner["Today's Advisory Banner"]
        LeafletMap["Interactive Marine Map<br/>- 0.25° Grid Polygons<br/>- PFZ Points + Buffers<br/>- Harbours & Ports"]
        LanguageToggle["EN / MR Bilingual Switch"]
    end

    IMD --> IMDParser
    INCOIS --> INCOISParser
    OpenMeteo --> Inference
    GFW --> Inference

    IMDParser --> Deduplicator --> T_Warn
    INCOISParser --> Deduplicator --> T_PFZ
    
    T_Warn --> Safety
    T_Grid --> Inference
    Inference --> Safety --> T_Pred

    T_Warn & T_PFZ & T_Pred & T_Env --> FreshnessTracker
    FreshnessTracker --> FreshEndpoint
    
    T_Pred & T_PFZ & T_Warn & FreshnessTracker --> MapEndpoint

    MapEndpoint --> UserInterface
    UserInterface --> HUD
    UserInterface --> SafetyBanner
    UserInterface --> LeafletMap
    UserInterface --> LanguageToggle
```

---

## 1.6 Main Use Cases & Operational Workflows

### Use Case 1: Daily Pre-Sailing Safety Check (Morning Departure)
- **Actor:** Small-scale boat owner in Alibaug (Raigad).
- **Trigger:** Fishers prepare to venture into coastal waters at 05:00 IST.
- **Workflow:**
  1. Fisher opens MatsyaAI mobile browser interface.
  2. The system checks backend `/api/v1/map/summary`.
  3. The top banner immediately renders `🚨 UNSAFE` in high-contrast red if IMD has issued a coastal squall alert, or `⚠️ CAUTION` if offshore wave heights exceed 4.0 m.
  4. If authoritative bulletins confirm calm conditions, `🛡️ SAFE CONFIRMED` is displayed with green indicators.
  5. If the IMD portal was down and data is stale, the system renders `ℹ️ SAFETY DATA UNAVAILABLE` with slate-grey indicators, prompting the fisher to check local physical port signals.

### Use Case 2: Locating High-Probability Grounds & Navigating
- **Actor:** Mechanized trawler skipper at Mirkarwada (Ratnagiri).
- **Trigger:** Safe weather confirmed; planning nightly trawling route.
- **Workflow:**
  1. Skipper views the interactive map and scrolls down to the Maharashtra coastal sector.
  2. The map highlights green circular targets representing official INCOIS PFZ locations. Clicking a marker reveals: "Bearing: 225° SW, Distance: 32.5 km, Depth: 40-55 m".
  3. The skipper inspects the underlying 0.25° grid overlay. Cells with high apparent fishing probability ($>0.47$) glow cyan (`#00e5ff`).
  4. Clicking the cell displays exact latitude/longitude, wave height ($1.8$ m), wind speed ($22$ km/h), and confirmation that the cell is offshore ($62.4$ km from coast).
  5. Skipper aligns compass heading to 225° and navigates directly to the validated waypoint, reducing exploratory fuel consumption by up to 30%.

### Use Case 3: Monsoon Ban Recovery & Seasonal Resumption
- **Actor:** Fisheries cooperative manager in Malvan (Sindhudurg).
- **Trigger:** End of annual monsoon ban (June 1 – July 31); fleet resumption in August/September.
- **Workflow:**
  1. Cooperative leader opens the Freshness HUD.
  2. Observes whether IMD bulletin feeds are active and INCOIS has resumed publishing post-monsoon satellite advisories.
  3. Monitors regional fishing effort (`regional_fishing_hours_T`) to track fleet activity across neighbouring ports.

---

# 2. Technology Stack Analysis

This document provides a comprehensive audit of every technology, language, library, database, API, and tool employed across the MatsyaAI Maharashtra platform. All versions and paths are verified directly from repository configuration and lockfiles (`backend/requirements.txt`, `frontend/package.json`, `docker-compose.yml`, `.env.example`).

---

## 2.1 Technology Stack Matrix

```mermaid
flowchart LR
    subgraph Client["Frontend Client (Port 5173)"]
        React["React 19.2.8"]
        Leaflet["Leaflet 1.9.4"]
        TS["TypeScript ~6.0"]
        Vite["Vite 8.2.2"]
    end

    subgraph Server["Backend Server (Port 8000)"]
        FastAPI["FastAPI 0.115.0"]
        Uvicorn["Uvicorn 0.30.6"]
        SQLAlchemy["SQLAlchemy 2.0.35 (Async)"]
        GeoAlchemy["GeoAlchemy2 0.15.2"]
        Pydantic["Pydantic 2.9.2"]
        Structlog["Structlog 24.4.0"]
    end

    subgraph DataML["Machine Learning & Data Processing"]
        XGBoost["XGBoost 3.2.0"]
        Sklearn["Scikit-Learn 1.6.1"]
        Pandas["Pandas 2.2.3"]
        NumPy["NumPy 1.26.4"]
        PyArrow["PyArrow 15.0.2"]
        GlobalLand["Global-Land-Mask 1.0.0"]
        PyPDF2["PyPDF2 3.0.1"]
        BS4["BeautifulSoup4 4.12.3"]
    end

    subgraph Storage["Database & Persistence (Port 5432)"]
        Postgres["PostgreSQL 16"]
        PostGIS["PostGIS 3.4"]
        Parquet["Parquet Columnar Files"]
    end

    subgraph External["Authoritative External Providers"]
        INCOIS_EXT["INCOIS TextData (JSESSIONID)"]
        IMD_EXT["IMD Mumbai Bulletin (PDF)"]
        OpenMeteo_EXT["Open-Meteo Marine & Forecast API"]
        GFW_EXT["Global Fishing Watch 4Wings API"]
        CMEMS_EXT["Copernicus Marine (CMEMS)"]
    end

    Client --> Server
    Server --> Storage
    Server --> DataML
    Server --> External
```

---

## 2.2 Frontend Technologies

### 1. React
- **Version:** `19.2.8` (Verified in `frontend/package.json`)
- **Purpose:** Core UI library for component-based reactive rendering.
- **Where & How Used:**
  - `frontend/src/App.tsx`: Manages root application state, language selection, polling timers, and metric aggregation.
  - `frontend/src/components/FreshnessHUD.tsx`: Renders real-time data freshness cards for each ingestion feed.
- **Why Relevant:** Provides high-speed virtual DOM reconciliation, allowing seamless updates when real-time marine weather or safety advisories refresh without triggering disruptive full-page reloads.

### 2. Leaflet & @types/leaflet
- **Version:** `leaflet ^1.9.4`, `@types/leaflet ^1.9.22`
- **Purpose:** High-performance, lightweight, mobile-friendly interactive mapping engine.
- **Where & How Used:**
  - `frontend/src/map/MarineMap.tsx`: Constructs the map instance (center: `[17.85, 72.85]`, zoom: 7), renders 0.25° canonical prediction grid bounding boxes (`L.rectangle`), INCOIS PFZ target circles with 4 km buffer rings (`L.circleMarker`, `L.circle`), and harbour markers (`L.divIcon`).
- **Why Relevant:** Leaflet is significantly lighter than MapLibre/Mapbox GL for low-end mobile devices common in coastal Maharashtra villages, requiring no WebGL hardware acceleration dependencies while effortlessly handling hundreds of dynamic polygon overlays.

### 3. Vite & @vitejs/plugin-react
- **Version:** `vite ^8.2.2`, `@vitejs/plugin-react ^6.1.0`
- **Purpose:** Frontend build tool, development server, and reverse proxy bundler.
- **Where & How Used:**
  - `frontend/vite.config.ts`: Configures Vite plugins and dev-server proxy rules (`/api` routed to backend container at `http://backend:8000`).
- **Why Relevant:** Instant hot-module replacement (HMR) and optimized Rollup tree-shaken production builds completed in under 250 milliseconds.

### 4. TypeScript
- **Version:** `~6.0.2` (Verified in `frontend/package.json`)
- **Purpose:** Static type enforcement across the frontend codebase.
- **Where & How Used:**
  - `frontend/src/types/map.ts`: Enforces strict data models for `CellPrediction`, `SafetyStatus`, `MapSummaryResponse`, `SourceFreshness`, and `PredictionProvenance`.
  - `frontend/src/types/health.ts`: Enforces backend health response contracts.
- **Why Relevant:** Prevents runtime `TypeError` issues when processing deeply nested backend geo-payloads and multilingual dictionaries.

---

## 2.3 Backend Technologies

### 1. FastAPI
- **Version:** `0.115.0` (Verified in `backend/requirements.txt`)
- **Purpose:** Modern, asynchronous, high-concurrency web framework for Python.
- **Where & How Used:**
  - `backend/app/main.py`: Creates application instance, mounts lifespan handlers, enables CORS, and includes API routers.
  - `backend/app/api/v1/`: Implements REST endpoints (`health.py`, `map.py`, `predictions.py`, `pfz.py`, `sources.py`).
- **Why Relevant:** Fully native ASGI asynchronous request handling allows the backend to perform external HTTP polling and concurrent database queries without thread-blocking. Automatically generates OpenAPI/Swagger schemas at `/docs`.

### 2. Uvicorn[standard]
- **Version:** `0.30.6`
- **Purpose:** High-performance ASGI web server powered by `uvloop` and `httptools`.
- **Where & How Used:**
  - `docker/backend.Dockerfile`: Entrypoint command running `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`.
- **Why Relevant:** Industry standard for serving async Python web applications with low latency and high request throughput.

### 3. Pydantic & Pydantic-Settings
- **Version:** `pydantic==2.9.2`, `pydantic-settings==2.5.2`
- **Purpose:** Data validation, strict type enforcement, and environment variable parsing.
- **Where & How Used:**
  - `backend/app/core/config.py`: Implements `Settings` class inheriting `BaseSettings`, loading configuration from `.env`.
  - `backend/app/schemas/pfz.py`: Defines request/response models (`PFZLocation`, `PFZLatestResponse`).
  - `backend/app/api/v1/health.py`: Defines `HealthResponse`.
- **Why Relevant:** Guarantees that invalid external configurations or corrupted API payloads fail fast with explicit validation errors rather than silently propagating invalid data.

### 4. Structlog & Logging
- **Version:** `structlog==24.4.0`
- **Purpose:** Structured JSON logging for production observability.
- **Where & How Used:**
  - `backend/app/core/logging.py`: Configures structured context logging.
  - `backend/app/main.py`: Logs application lifecycle events (`application_startup`, `application_shutdown`).
- **Why Relevant:** Structured key-value logs can be effortlessly ingested and parsed by log aggregators (Elasticsearch, CloudWatch, Loki) in production.

---

## 2.4 Programming Languages

1. **Python:**
   - **Version:** `3.12` (Container base: `python:3.12-slim`, local: `3.12.4`)
   - **Usage:** Backend API, database ORM models, data ingestion daemons, web scraping, and machine learning pipeline.
   - **Rationale:** Mature ecosystem for scientific computing, geospatial processing, machine learning (XGBoost, Scikit-learn), and modern asynchronous web services.

2. **TypeScript / JavaScript:**
   - **Version:** TypeScript `~6.0.2`, JavaScript ECMAScript 2022+
   - **Usage:** Complete frontend client application (`frontend/src/`).
   - **Rationale:** Industry standard for robust, responsive single-page applications with compile-time type safety.

3. **SQL & Procedural SQL:**
   - **Version:** PostgreSQL 16 dialect with PostGIS spatial extensions.
   - **Usage:** Database schemas, spatial indexes, spatial queries (`ST_Distance`, `ST_Point`), and Alembic migrations.
   - **Rationale:** Standard language for relational data integrity and geospatial analysis.

---

## 2.5 Database & Storage Technologies

### 1. PostgreSQL
- **Version:** `16` (Image: `postgis/postgis:16-3.4` in `docker-compose.yml`)
- **Purpose:** Primary relational database management system.
- **Where & How Used:**
  - Stores all persistent entities: landing centres, advisories, marine warnings, predictions, and model features.
- **Why Relevant:** ACID compliance, excellent performance under concurrent read/write workloads, and native enterprise-grade support for complex spatial data.

### 2. PostGIS Extension
- **Version:** `3.4`
- **Purpose:** Spatial database extender for PostgreSQL.
- **Where & How Used:**
  - `backend/alembic/versions/01d27f92e854_initial_schema.py`: Enables PostGIS extension (`CREATE EXTENSION IF NOT EXISTS postgis`).
  - `backend/app/models/`: Geometry columns (`Geometry(geometry_type='POINT', srid=4326)` and `Geometry(geometry_type='POLYGON', srid=4326)`).
- **Why Relevant:** Enables spherical distance calculations, spatial indexing (R-Tree / GiST), and polygon intersection checks directly within database queries without loading massive point sets into Python memory.

### 3. SQLAlchemy (Asyncio) & Asyncpg
- **Version:** `sqlalchemy[asyncio]==2.0.35`, `asyncpg==0.29.0`
- **Purpose:** High-performance asynchronous Object Relational Mapper (ORM) and async PostgreSQL database driver.
- **Where & How Used:**
  - `backend/app/core/database.py`: Instantiates `create_async_engine` and `async_sessionmaker`.
  - `backend/app/models/`: Declares mapped ORM entities subclassing `Base`.
- **Why Relevant:** `asyncpg` is the fastest available PostgreSQL driver for Python, executing non-blocking database queries within the FastAPI event loop.

### 4. GeoAlchemy2
- **Version:** `0.15.2`
- **Purpose:** Bridges SQLAlchemy ORM with PostGIS spatial types and functions.
- **Where & How Used:**
  - `backend/app/models/`: Imports and maps `Geometry` column types across `landing_centre.py`, `incois_pfz.py`, `marine_warning.py`, and `prediction.py`.
- **Why Relevant:** Allows transparent handling of Well-Known Text (WKT) and Well-Known Binary (WKB) geometric representations directly within Python ORM instances.

### 5. Alembic
- **Version:** `1.13.3`
- **Purpose:** Database migration tool for SQLAlchemy.
- **Where & How Used:**
  - `backend/alembic/`: Contains migration environment (`env.py`) and version scripts tracking schema revisions from initial setup to Phase 5.
- **Why Relevant:** Provides deterministic, version-controlled database schema evolution that can be safely rolled forward or backward across environments.

### 6. Apache Parquet & PyArrow
- **Version:** `pyarrow==15.0.2`
- **Purpose:** High-efficiency columnar file storage format.
- **Where & How Used:**
  - `backend/app/ml/data/historical_full_year_2023.parquet`: Stores 59,850 observations of historical GFW effort and environmental records.
- **Why Relevant:** Columnar storage reduces disk usage by over 80% compared to raw CSV/JSON and allows sub-second scan and load times during ML training and historical caching.

---

## 2.6 Machine Learning & Data Processing Libraries

### 1. XGBoost
- **Version:** `3.2.0` (Verified in `backend/requirements.txt`)
- **Purpose:** Gradient boosted decision tree framework.
- **Where & How Used:**
  - `ml/training/experiment_phase3.py`: Trains the canonical Phase 3 classifier.
  - `backend/app/ml/artifacts/phase3_xgboost_model.joblib`: Serialized model evaluated during inference in `backend/app/ml/inference.py`.
- **Why Relevant:** State-of-the-art performance on tabular geospatial and environmental features; handles nonlinear feature interactions, missing data indicators, and provides superior Precision-Recall AUC on imbalanced targets.

### 2. Scikit-Learn
- **Version:** `1.6.1`
- **Purpose:** Machine learning preprocessing, scaling, baseline modeling, and evaluation metrics.
- **Where & How Used:**
  - `SimpleImputer` (median strategy) and `StandardScaler` serialized in `backend/app/ml/artifacts/`.
  - `ml/models/baselines.py`: Implements baseline benchmarks (Ridge regression, Logistic Regression, Random Forest).
  - Metric computation: `precision_recall_curve`, `roc_auc_score`, `f1_score`, `average_precision_score`.
- **Why Relevant:** Industry standard for reliable, mathematically sound tabular preprocessing and evaluation.

### 3. Pandas & NumPy
- **Version:** `pandas==2.2.3`, `numpy==1.26.4`
- **Purpose:** Data manipulation, vector math, rolling windows, and tabular aggregation.
- **Where & How Used:**
  - `ml/features/causal_dataset.py`: Builds causal training datasets using group-by operations and temporal lag shifts.
  - `backend/app/ml/dataset_builder.py`: Regrids observations and merges spatial coordinates.
- **Why Relevant:** Vectorized performance for calculating multi-day trailing means, standard deviations, and trigonometry (sine/cosine day of year transformations).

### 4. Global-Land-Mask
- **Version:** `1.0.0`
- **Purpose:** High-speed, numpy-based spatial checking for ocean vs. land coordinates.
- **Where & How Used:**
  - `backend/scripts/generate_spatial_grid.py`: Verifies coordinates with `globe.is_land(lat, lon)` to generate canonical marine cells.
  - `backend/app/ml/inference.py`: Uses `globe.is_ocean` across centroid and corner coordinates to retain only marine grid cells.
- **Why Relevant:** Extremely fast point-in-polygon land mask checking without requiring external GIS servers or heavy GDAL/Shapely dependencies.

### 5. Joblib
- **Version:** `1.4.2`
- **Purpose:** Optimized object serialization for scikit-learn and XGBoost pipelines.
- **Where & How Used:**
  - `ml/models/serialize_phase3_artifacts.py`: Serializes trained models, scalers, and imputers.
  - `backend/app/ml/inference.py`: Deserializes model artifacts during startup.
- **Why Relevant:** Optimized for preserving large NumPy arrays and model trees with zero precision loss.

---

## 2.7 Scraping & Document Ingestion Tools

### 1. BeautifulSoup4
- **Version:** `4.12.3`
- **Purpose:** HTML parsing and web scraping.
- **Where & How Used:**
  - `backend/app/services/ingestion/incois_pfz_provider.py`: Parses raw HTML from INCOIS `TextData?secid=SEC002`, extracts table rows, headers, and date stamps.
- **Why Relevant:** Resilient against poorly formatted government HTML tables, missing closing tags, and inline formatting artifacts.

### 2. PyPDF2
- **Version:** `3.0.1`
- **Purpose:** Spatial text extraction from PDF documents.
- **Where & How Used:**
  - `backend/app/services/ingestion/imd_marine_provider.py`: Extracts raw text lines using spatial visitor callbacks (`visitor_text`) to sort text chunks top-to-bottom and left-to-right, solving font kerning separation issues.
- **Why Relevant:** Pure Python PDF parser requiring no heavy external C libraries like `poppler` or `pdf2image`.

### 3. HTTPX
- **Version:** `0.27.2`
- **Purpose:** Modern asynchronous HTTP client for Python.
- **Where & How Used:**
  - `backend/app/services/ingestion/incois_pfz_provider.py`: Handles HTTP requests with cookies (`JSESSIONID`) and redirection management.
  - `backend/app/services/ingestion/imd_marine_provider.py`: Downloads PDF bulletins with retry backoffs.
  - `backend/tests/`: Used as FastAPI async test client.
- **Why Relevant:** Native async/await support, connection pooling, and seamless SSL configuration.

---

## 2.8 Third-Party APIs & External Integrations

| External Service | Endpoint / Resource | Format | Access Mode | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **INCOIS TextData System** | `https://incois.gov.in/MarineFisheries/TextData?secid=SEC002` | HTML Table | Public (Requires `JSESSIONID` from `TextDataHome`) | Ingests official Potential Fishing Zone advisories for Maharashtra coast. |
| **IMD Mumbai Marine** | `https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf` | PDF Document | Public HTTPS | Ingests daily Fishermen Warning Bulletins (squalls, rough sea, gale warnings). |
| **Open-Meteo Marine API** | `https://marine-api.open-meteo.com/v1/marine` | JSON | Public REST (Rate-limited, cached) | Fetches live wave height, wave period, wave direction, and swell height. |
| **Open-Meteo Forecast API** | `https://api.open-meteo.com/v1/forecast` | JSON | Public REST | Fetches live 10 m wind speed across grid cell centroids. |
| **Global Fishing Watch (GFW)** | `https://gateway.api.globalfishingwatch.org/v3/4wings/report` | JSON | Authenticated (`Bearer GFW_API_TOKEN`) | Captures historical apparent fishing vessel activity from AIS transmissions. |
| **Copernicus Marine (CMEMS)** | `cmems_mod_glo_phy_anfc_0.083deg_P1D-m` | NetCDF / REST | Authenticated (User/Password) | Ocean physics and biogeochemical evaluation (evaluated for future scale-up). |
| **OpenStreetMap** | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | PNG Raster Tiles | Public | Cartographic base tiles for the interactive Leaflet map. |

---

## 2.9 Containerization, Deployment & CI/CD

### 1. Docker & Docker Compose
- **Versions:** Docker Engine v24+, Docker Compose v2+
- **Configuration:** `docker-compose.yml` declaring 4 coordinated services:
  1. `db`: `postgis/postgis:16-3.4` (Postgres database with PostGIS extensions)
  2. `backend`: FastAPI backend running on Python 3.12 slim
  3. `ingestion`: Dedicated background daemon running `run_ingestion.py --daemon`
  4. `frontend`: Node.js 20 Alpine container running Vite dev/preview server
- **Networks & Volumes:**
  - Network: `matsya_net` (bridge driver)
  - Volume: `pgdata` (local driver for persistent PostgreSQL database storage)
- **Why Relevant:** Provides complete platform isolation and deterministic deployment reproducibility across development, staging, and production environments.

---

## 2.10 Testing & Quality Assurance Tooling

1. **Pytest & Pytest-Asyncio:**
   - **Version:** `pytest==8.3.3`, `pytest-asyncio==0.24.0`
   - **Usage:** Executes 15 test suites in `backend/tests/` covering database connections, safety gate rules, ingestion parsing, and ML inference.
2. **Vitest & Testing Library:**
   - **Version:** `vitest ^5.0.1`, `@testing-library/react ^16.3.3`, `@testing-library/jest-dom ^7.0.1`, `jsdom ^29.1.1`
   - **Usage:** Frontend unit and component testing (`frontend/src/App.test.tsx`).
3. **Oxlint:**
   - **Version:** `^1.79.0` (Verified in `frontend/package.json`)
   - **Usage:** Ultra-fast JavaScript/TypeScript linter for enforcing code quality.

---

# 3. System Architecture

## 3.1 High-Level Architecture Overview

MatsyaAI Maharashtra is architected as a decoupled, multi-tier, micro-service platform designed for high fault tolerance, geospatial computing, and independent safety governance.

```mermaid
flowchart TB
    subgraph ExternalEcosystem["External Data Ecosystem"]
        direction TB
        E_IMD["IMD Mumbai Marine<br/>(Fisherman Bulletin PDF)"]
        E_INCOIS["INCOIS Web Portal<br/>(PFZ HTML Advisory SEC002)"]
        E_METEO["Open-Meteo APIs<br/>(Marine & Weather Forecast)"]
        E_GFW["Global Fishing Watch<br/>(AIS Effort Gateway)"]
    end

    subgraph IngestionSubsystem["Ingestion & Normalization Subsystem (Daemon)"]
        direction TB
        I_Runner["Ingestion Runner & Scheduler<br/>(backend/scripts/run_ingestion.py)"]
        P_IMD["IMD Marine Provider<br/>(PyPDF2 Spatial Visitor)"]
        P_INCOIS["INCOIS PFZ Provider<br/>(BeautifulSoup + DMS Parser)"]
        P_METEO["Open-Meteo Marine Provider<br/>(HTTPX Async)"]
        P_Dedupe["SHA-256 Deduplication & Stale Marker"]
    end

    subgraph PersistenceLayer["Data & Persistence Layer (Port 5432)"]
        direction TB
        PG[(PostgreSQL 16 + PostGIS 3.4)]
        subgraph Tables["Relational & Spatial Schemas"]
            T1["marine_warnings"]
            T2["incois_pfz_advisories"]
            T3["pfz_zones"]
            T4["predictions"]
            T5["spatial_grids (171 Cells)"]
            T6["landing_centres"]
        end
        PG --- Tables
    end

    subgraph MLSubsystem["Inference & Safety Subsystem"]
        direction TB
        ML_Pipe["Phase4InferencePipeline<br/>(XGBoost 3.2.0 Model)"]
        ML_Art["Frozen Phase 3 Artifacts<br/>(Imputer, Scaler, Model, Threshold)"]
        SafetyGate["SafetyGate Subsystem<br/>(Independent Decoupled Governance)"]
    end

    subgraph BackendService["FastAPI Application Server (Port 8000)"]
        direction TB
        Router_Health["/api/v1/health"]
        Router_Map["/api/v1/map/summary"]
        Router_Pred["/api/v1/predictions"]
        Router_PFZ["/api/v1/pfz/latest"]
        Router_Src["/api/v1/sources/freshness"]
        Fresh_Tracker["SourceFreshnessTracker Engine"]
    end

    subgraph ClientPresentation["Client Layer (React 19 + TypeScript - Port 5173)"]
        direction TB
        UI_Nav["Top Bar & Language Switcher (EN/MR)"]
        UI_Adv["Today's Advisory Banner (Safety Override)"]
        UI_HUD["Data Freshness HUD"]
        UI_Map["Interactive Marine Map (Leaflet)"]
        UI_Legend["Scientific Disclaimers & Harbour Directory"]
    end

    E_IMD --> P_IMD
    E_INCOIS --> P_INCOIS
    E_METEO --> P_METEO
    
    I_Runner --> P_IMD & P_INCOIS & P_METEO
    P_IMD & P_INCOIS & P_METEO --> P_Dedupe --> PG

    PG --> ML_Pipe
    ML_Art --> ML_Pipe
    ML_Pipe --> SafetyGate
    PG --> SafetyGate
    SafetyGate --> T4

    PG --> BackendService
    Fresh_Tracker --> Router_Src
    Router_Map --> Fresh_Tracker
    
    BackendService <-->|REST over HTTP / JSON| ClientPresentation
```

---

## 3.2 Frontend Architecture

The frontend is a single-page application (SPA) built on **React 19**, **TypeScript**, and **Leaflet**, compiled via **Vite**.

### Component Hierarchy

```mermaid
graph TD
    App["App.tsx (Root Component)"]
    Header["Top Navigation Bar<br/>- Brand & Icon<br/>- Freshness Status Badge<br/>- EN / MR Toggle Button"]
    Main["Main Content Area"]
    
    HeroAdvisory["Today's Advisory Banner<br/>- High-Contrast Safety Label<br/>- Explanatory Subtext<br/>- Aggregate Fishing Potential<br/>- Action Button (Scroll to Map)"]
    MetricsStrip["Technical Metrics Accordion<br/>- PFZ Count<br/>- Model Version"]
    HUD["FreshnessHUD.tsx<br/>- INCOIS Card<br/>- IMD Warning Card<br/>- Marine Weather Card<br/>- GFW Activity Card"]
    MapWrapper["MarineMap.tsx<br/>- Independent Safety Bar Overlay<br/>- Map Layer Controls<br/>- Leaflet Canvas / Tiles<br/>- Selected Cell Inspection Modal"]
    LandingCentres["Landing Centres Directory Grid"]
    Footer["Scientific Disclaimers & Governance Notice"]

    App --> Header
    App --> Main
    Main --> HeroAdvisory
    Main --> MetricsStrip
    Main --> HUD
    Main --> MapWrapper
    Main --> LandingCentres
    Main --> Footer
```

### Key Architectural Characteristics of Frontend:
1. **Unidirectional State Flow:** Root state (`mapData`, `health`, `isMarathi`, `isDemo`, `loading`, `error`) resides in `App.tsx` and cascades down via typed props.
2. **Periodic Polling Synchronization:** An automated 60-second polling interval re-executes `fetchMapSummary()` in the background to ensure fishermen see the latest weather alerts and advisory updates.
3. **Decoupled Safety Presentation:** The frontend explicitly checks `marine_safety.overall_status`. The state `NO_WARNING_DATA` is styled using neutral dark slate-grey (`#37474f` / `#90a4ae`) and is **never** permitted to render green or convey a safe condition.
4. **Resilient Offline/Demo Fallback:** If the live backend or network fails, an error alert provides a single-click fallback to load real cached demonstration data.

---

## 3.3 Backend Architecture

The backend is built on **FastAPI** following a layered architecture that cleanly separates routing, business services, machine learning inference, and data persistence:

```mermaid
graph LR
    subgraph RoutingLayer["API Routing Layer (FastAPI Routers)"]
        R1["backend/app/api/v1/health.py"]
        R2["backend/app/api/v1/map.py"]
        R3["backend/app/api/v1/predictions.py"]
        R4["backend/app/api/v1/pfz.py"]
        R5["backend/app/api/v1/sources.py"]
    end

    subgraph ServiceLayer["Business Logic & Ingestion Services"]
        S1["SourceFreshnessTracker"]
        S2["IngestionRunner"]
        S3["IMDMarineProvider"]
        S4["INCOISPFZProvider"]
        S5["OpenMeteoMarineProvider"]
    end

    subgraph MLService["Machine Learning & Safety Services"]
        M1["Phase4InferencePipeline"]
        M2["SafetyGate"]
        M3["FeatureBuilder"]
    end

    subgraph DataAccess["Data Access & ORM Models"]
        DB["AsyncSession (database.py)"]
        Models["SQLAlchemy Declarative Models<br/>(Base.py)"]
    end

    RoutingLayer --> ServiceLayer
    RoutingLayer --> MLService
    ServiceLayer --> DataAccess
    MLService --> DataAccess
    DataAccess --> DB
```

### Module Responsibilities:
- **`app/api/v1/`:** Pure request deserialization, dependency injection (`Depends(get_db)`), and response serialization via Pydantic.
- **`app/core/`:** Centralized settings singleton (`Settings`), async engine pool management, and structured logging.
- **`app/services/freshness/`:** Real-time source freshness evaluation calculated from true observation dates rather than database retrieval timestamps.
- **`app/services/ingestion/`:** Modular, isolated extract-transform-load (ETL) providers adhering to `BaseProvider`.
- **`app/ml/`:** Model artifact deserialization, 171-cell spatial grid generation, 29-feature alignment, XGBoost inference, and safety gate application.

---

## 3.4 Ingestion Pipeline & Daemon Architecture

The background ingestion worker (`backend/scripts/run_ingestion.py --daemon`) runs asynchronously alongside the web server:

```mermaid
sequenceDiagram
    autonumber
    participant Daemon as Ingestion Scheduler Daemon
    participant Runner as IngestionRunner
    participant IMDProv as IMDMarineProvider
    participant PFZProv as INCOISPFZProvider
    participant DB as PostgreSQL + PostGIS

    loop Ingestion Polling Loop
        Note over Daemon: Every 4 Hours
        Daemon->>Runner: run_imd(db)
        Runner->>IMDProv: ingest_latest_bulletin(db)
        IMDProv->>IMDProv: Download fisherman.pdf via HTTPX
        IMDProv->>IMDProv: Extract lines with PyPDF2 spatial visitor
        IMDProv->>IMDProv: Classify severity (NORMAL, WARNING, SEVERE)
        IMDProv->>DB: Check duplicate hash & Insert marine_warnings
        DB-->>Daemon: Commit & Return Status

        Note over Daemon: Daily (Every 24 Hours)
        Daemon->>Runner: run_incois(db)
        Runner->>PFZProv: ingest_latest_maharashtra_pfz(db)
        PFZProv->>PFZProv: Init session on TextDataHome (get JSESSIONID)
        PFZProv->>PFZProv: Fetch TextData?secid=SEC002
        PFZProv->>PFZProv: Parse HTML table with BeautifulSoup
        PFZProv->>PFZProv: Convert DMS to Decimal Degrees
        PFZProv->>DB: Check batch SHA-256 hash
        PFZProv->>DB: Mark old active records is_stale=True
        PFZProv->>DB: Insert incois_pfz_advisories & pfz_zones
        DB-->>Daemon: Commit & Return Status
    end
```

---

## 3.5 ML Prediction & Safety Pipeline Architecture

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client Request (Map/Predictions)
    participant API as FastAPI Router
    participant DB as PostgreSQL (Predictions Table)
    participant Inf as Phase4InferencePipeline
    participant Gate as SafetyGate
    participant Meteo as Open-Meteo Marine API

    Client->>API: GET /api/v1/map/summary
    API->>DB: Query latest persisted predictions batch
    alt Predictions Exist in DB
        DB-->>API: Return persisted predictions
    else No Batch Found (or Batch Run Triggered)
        API->>Inf: predict()
        Inf->>Inf: Generate 171 canonical marine grid cells (0.25°)
        Inf->>Meteo: Fetch current wave & wind (15-min cache)
        Inf->>Inf: Load historical GFW context (historical_full_year_2023.parquet)
        Inf->>Inf: Assemble 29 canonical features
        Inf->>Inf: Transform via SimpleImputer & StandardScaler
        Inf->>Inf: Run XGBoost predict_proba()[:, 1]
        Inf->>DB: Query active marine warnings
        DB-->>Gate: Active warnings list
        Gate->>Gate: Evaluate safety (Override if UNSAFE/CAUTION)
        Gate-->>Inf: Annotated predictions (probability + safety_status)
    end
    API->>API: Synthesize MapSummaryResponse
    API-->>Client: 200 OK (Consolidated GeoJSON/JSON Payload)
```

---

## 3.6 Client-Server Communication & API Design

- **Transport:** Standard HTTP/1.1 over TCP (Docker internal network / localhost).
- **Format:** Strict JSON REST contracts validated by Pydantic.
- **CORS Policy:** Strict origin whitelisting configured via `Settings.CORS_ORIGINS` (`http://localhost:5173`, `http://localhost:3000`).
- **Proxy Configuration:** Vite dev-server intercepts all `/api/*` frontend calls and transparently proxies them to `http://backend:8000/api/*`, eliminating cross-origin preflight latency in development and containerized deployments.

---

## 3.7 Database Architecture & Spatial Capabilities

```mermaid
erDiagram
    spatial_grids ||--o{ model_features : "contains"
    spatial_grids ||--o{ predictions : "spatial point"
    landing_centres ||--o{ incois_pfz_advisories : "origin reference"

    spatial_grids {
        string id PK "e.g. cell_19.0_72.8"
        float resolution "0.25 deg"
        float latitude
        float longitude
        geometry geom "POLYGON SRID 4326"
        geometry centroid "POINT SRID 4326"
        float distance_to_coast_km
    }

    incois_pfz_advisories {
        int id PK
        string source "INCOIS"
        string source_type "OFFICIAL_PFZ_ADVISORY"
        string sector "Maharashtra"
        string landing_centre
        string direction
        int bearing_degrees
        string distance_km
        int depth_min_m
        int depth_max_m
        float latitude
        float longitude
        geometry geom "POINT SRID 4326"
        datetime advisory_date
        datetime validity_date
        datetime retrieved_at
        string hash_id UK "SHA-256 batch hash"
    }

    marine_warnings {
        int id PK
        string warning_type "COASTAL_FISHERMEN_WARNING"
        string severity "NORMAL, WARNING, SEVERE"
        datetime valid_from
        datetime valid_until
        string description
        geometry geom "POLYGON SRID 4326"
        string source_name "IMD_MUMBAI_FISHERMAN_BULLETIN"
        datetime source_timestamp
        datetime retrieved_at
        boolean is_stale
    }

    predictions {
        int id PK
        datetime prediction_timestamp
        float latitude
        float longitude
        geometry geom "POINT SRID 4326"
        float prediction_probability
        int prediction_class "0 or 1"
        string prediction_label
        string model_version "Phase3_XGBoost_v1"
        datetime env_observation_timestamp
        string env_source "Open-Meteo"
        float data_freshness_seconds
        string safety_status "SAFE_CONFIRMED, CAUTION, UNSAFE, NO_WARNING_DATA"
        boolean safety_override
        string pfz_advisory
    }

    landing_centres {
        int id PK
        string name "e.g. Sassoon Dock"
        string district "Mumbai, Ratnagiri, etc."
        float latitude
        float longitude
        geometry geom "POINT SRID 4326"
        string source
    }
```

---

## 3.8 External Service Integration & Fallback Strategy

| Integration | Primary Ingestion Path | Failure Detection Mechanism | Fallback / Graceful Degradation Strategy |
| :--- | :--- | :--- | :--- |
| **IMD Marine Bulletin** | HTTPS fetch of `fisherman.pdf` from `mausam.imd.gov.in`. | HTTP 4xx/5xx status codes, PDF header validation failure, PyPDF2 extraction empty. | Retains previously stored warnings; marks them `is_stale=True` when expired. Safety gate yields `NO_WARNING_DATA`. **Never assumes calm/safe conditions.** |
| **INCOIS PFZ Feed** | HTTPS session init on `TextDataHome` + GET on `TextData?secid=SEC002`. | HTTP redirect to generic page, missing `JSESSIONID`, missing table in BeautifulSoup parse. | Retains last valid advisory records; marks old records `is_stale=True`. API returns `status="STALE"` with last known valid timestamps. In demo mode, falls back to documented historical reference coordinates. |
| **Open-Meteo Marine & Forecast** | REST API calls batched across 40 centroids with 15-minute in-memory caching. | Network timeout (10s), HTTP error, empty current weather payload. | Switches to `DEMO_MODE` environmental fallback, sourcing representative historical marine observations from `historical_full_year_2023.parquet`. |
| **Global Fishing Watch (GFW)** | GFW 4Wings Report API chunked by calendar month. | Missing `GFW_API_TOKEN`, HTTP 401/403, network unreachable. | Gracefully sets status to `UNAVAILABLE` or `CACHED_HISTORICAL`. Never fabricates vessel AIS effort. Zero AIS effort defaults to $0.0$ hours. |

---

# 4. Algorithms and Core Logic

This document provides a rigorous mathematical and algorithmic analysis of every computational technique implemented in the MatsyaAI Maharashtra codebase. Only algorithms verified in actual source code are included.

---

## 4.1 Summary of Implemented Algorithms

| # | Algorithm Name | Category | Primary Source File & Function | Time Complexity | Space Complexity |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | Haversine Great-Circle Distance | Geodesy / Spatial Math | `backend/app/ml/dataset_builder.py` (`_haversine`)<br/>`backend/app/services/ml/feature_builder.py` (`_haversine_distance`) | $\mathcal{O}(1)$ | $\mathcal{O}(1)$ |
| **2** | DMS to Decimal Degrees Conversion | Geodetic Parsing | `backend/app/services/ingestion/incois_pfz_provider.py` (`parse_dms`) | $\mathcal{O}(K)$ | $\mathcal{O}(1)$ |
| **3** | Spatial Visitor PDF Kerning Reconstruction | Text Mining / Document Parsing | `backend/app/services/ingestion/imd_marine_provider.py` (`extract_structured_lines`, `_clean_token_spacing`) | $\mathcal{O}(N \log N)$ | $\mathcal{O}(N)$ |
| **4** | Meteorological Severity Classification | Rule-Based NLP / Classifier | `backend/app/services/ingestion/imd_marine_provider.py` (`classify_severity`) | $\mathcal{O}(M)$ | $\mathcal{O}(1)$ |
| **5** | Deterministic SHA-256 Batch Deduplication | Cryptographic Hashing | `backend/app/services/ingestion/incois_pfz_provider.py` (`ingest_latest_maharashtra_pfz`) | $\mathcal{O}(L)$ | $\mathcal{O}(1)$ |
| **6** | Causal Lookback Rolling-Window Feature Generation | Feature Engineering / Time Series | `ml/features/causal_dataset.py` (`build_causal_dataset`) | $\mathcal{O}(G \cdot T)$ | $\mathcal{O}(G \cdot T)$ |
| **7** | Spatial Point-in-Polygon Marine Masking & Grid Generation | Computational Geometry | `backend/scripts/generate_spatial_grid.py` (`generate_canonical_grid`)<br/>`backend/app/ml/inference.py` (`_generate_grid`) | $\mathcal{O}(P)$ | $\mathcal{O}(P)$ |
| **8** | Nearest-Neighbor Spatial Regridding | Geospatial Interpolation | `backend/app/services/ml/feature_builder.py` (`map_cmems_to_canonical`) | $\mathcal{O}(C \cdot G)$ | $\mathcal{O}(C)$ |
| **9** | Multi-Tier Safety Gate Evaluation Hierarchy | Decision Logic / Safety Protocol | `backend/app/ml/safety_gate.py` (`_determine_safety`, `apply`) | $\mathcal{O}(P \cdot W)$ | $\mathcal{O}(P)$ |
| **10** | Source-Level Freshness & Age Calculation | Temporal Auditing | `backend/app/services/freshness/source_tracker.py` (`get_all_freshness`) | $\mathcal{O}(S)$ | $\mathcal{O}(S)$ |

---

## 4.2 Detailed Algorithm Specifications

### 1. Haversine Great-Circle Distance
- **Category:** Geodesy / Geospatial Mathematics
- **Mathematical Concept:**
  Given two points on a spherical Earth of radius $R \approx 6371.0\text{ km}$, with latitudes $\phi_1, \phi_2$ and longitudes $\lambda_1, \lambda_2$ in radians:
  $$\Delta \phi = \phi_2 - \phi_1, \quad \Delta \lambda = \lambda_2 - \lambda_1$$
  $$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)$$
  $$c = 2 \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$
  $$d = R \cdot c$$
- **How It Works:** Transforms degree coordinates to radians, calculates the chord length between the points along the spherical surface, and scales by Earth's mean radius.
- **Why Used:** Computes exact distance from each 0.25° marine grid cell centroid to the nearest coastal landing centre (`distance_to_coast_km`), establishing coastal proximity (`is_coastal = 1.0` if $d \le 50\text{ km}$) and fuel travel constraints.
- **Input:** `(lat1: float, lon1: float, lat2: float, lon2: float)`
- **Output:** `distance_km: float`
- **Step-by-Step Execution:**
  1. Convert latitude and longitude deltas to radians using `math.radians()`.
  2. Compute haversine formula component $a$.
  3. Compute angular distance $c$ using `math.atan2` and `math.sqrt`.
  4. Multiply $c$ by Earth radius $6371.0\text{ km}$.
- **Complexity:** Time: $\mathcal{O}(1)$, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/ml/dataset_builder.py` (lines 44–58)
  - `backend/app/services/ml/feature_builder.py` (lines 50–57)

---

### 2. DMS to Decimal Degrees Coordinate Conversion
- **Category:** Geodetic String Parsing & Normalization
- **Mathematical Concept:**
  $$\text{Decimal Degrees} = \text{Degrees} + \frac{\text{Minutes}}{60} + \frac{\text{Seconds}}{3600}$$
  If cardinal direction is South ('S') or West ('W'):
  $$\text{Decimal Degrees} = -1 \cdot \text{Decimal Degrees}$$
- **How It Works:** Extracts numeric degree, minute, and second tokens from unstructured government HTML strings (e.g., `'15 45 28 N'`, `'15°45\'28"N'`, `'71 56 39 E'`), accommodates prefix or suffix cardinal letters, computes fractional degrees, and applies polarity.
- **Why Used:** INCOIS PFZ bulletins publish coordinates in varied legacy human-readable DMS notation. This algorithm normalizes them into standard WGS-84 decimal coordinates for PostGIS geometry creation.
- **Input:** Raw string `dms_str` (e.g., `"15 45 28 N"`)
- **Output:** `Optional[float]` in range $[-180.0, 180.0]$
- **Step-by-Step Execution:**
  1. Pad cardinal letters `[NSEW]` with spaces using regex `re.sub(r'([NSEWnsew])', r' \1 ', dms_str)`.
  2. Strip non-alphanumeric symbols using `re.sub(r'[^0-9NSEWnsew\. ]', ' ', clean_str)`.
  3. Split into whitespace tokens. Verify at least 4 tokens exist.
  4. Identify cardinal direction token (whether located at index 0 or index 3).
  5. Parse degree, minute, and second floats.
  6. Apply conversion formula and invert sign for South/West.
- **Complexity:** Time: $\mathcal{O}(K)$ where $K$ is string length ($\le 50$ chars), Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/incois_pfz_provider.py` (lines 140–184)

---

### 3. Spatial Visitor PDF Kerning Reconstruction & Line Sorting
- **Category:** Document Parsing & Computational Typography
- **Mathematical Concept:** 2D Cartesian transformation matrix coordinate extraction:
  In PDF rendering, text transformation matrix $tm$ yields coordinates:
  $$x = tm[4], \quad y = tm[5]$$
  Sorting elements by primary vertical position $y$ and secondary horizontal position $x$:
  $$\text{key} = (\text{round}(y, 1), \text{round}(x, 1))$$
- **How It Works:** When extracting text from IMD's `fisherman.pdf`, font kerning causes single characters to be printed as isolated tokens separated by tabs or spaces (e.g., `"T h u r s d a y"`). The algorithm intercepts text chunks with their physical page $(x, y)$ coordinates via PyPDF2's `visitor_text` callback, sorts lines in reading order, and iteratively collapses kerned character tokens using regular expressions.
- **Why Used:** Standard PyPDF2 `extract_text()` outputs unreadable fragmented tokens that break regex matchers for dates, wind speeds, and coastal warning headers.
- **Input:** Raw PDF bytes `pdf_bytes`
- **Output:** Ordered, cleaned list of plain-text lines `List[str]`
- **Step-by-Step Execution:**
  1. Instantiate `PyPDF2.PdfReader`.
  2. For each page, register a visitor callback that captures text alongside matrix coordinates $tm[5]$ (vertical $y$) and $tm[4]$ (horizontal $x$).
  3. Sort collected elements top-to-bottom by $y$ coordinate.
  4. Group elements within vertical distance $\Delta y \le 5\text{ pt}$ into single lines.
  5. Sort horizontal chunks within each line by $x$ coordinate.
  6. Execute `_clean_token_spacing` iteratively: `re.sub(r'(?<=[A-Za-z0-9])[\t ](?=[A-Za-z0-9])', '', s)` until string stabilizes.
- **Complexity:** Time: $\mathcal{O}(N \log N)$ where $N$ is text chunk count per page, Space: $\mathcal{O}(N)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/imd_marine_provider.py` (lines 127–182)

---

### 4. IMD Meteorological Bulletin Text Classification
- **Category:** Rule-Based Natural Language Classification
- **How It Works:** Maps unstructured advisory text across 7 coastal and high-sea bulletin sections into discrete safety classifications: `NORMAL`, `WARNING`, or `SEVERE`.
- **Classification Rules:**
  - `NORMAL`: Explicit match for `"nil"`, `"nil."`, `"normal"`, `"no warning"`.
  - `SEVERE`: Detected keywords: `"cyclon"`, `"gale"`, `"extremely severe"`, `"very severe"`, `"super cyclon"`, `"storm surge"`, `"hurricane"`, `"typhoon"`, OR sustained wind speeds $\ge 65\text{ kmph}$ with gusts $\ge 75\text{ kmph}$.
  - `WARNING`: Advisory keywords: `"squall"`, `"rough"`, `"warning"`, `"advised not to venture"`, `"gusting"`, `"caution"`, `"alert"`.
- **Why Used:** Distinguishes calm ocean conditions from advisory-level squalls and life-threatening cyclonic storms to drive the independent Safety Gate.
- **Input:** Cleaned section text string
- **Output:** String (`"NORMAL"`, `"WARNING"`, `"SEVERE"`)
- **Complexity:** Time: $\mathcal{O}(M)$ where $M$ is string length, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/imd_marine_provider.py` (lines 248–285)

---

### 5. Deterministic SHA-256 Batch Ingestion Deduplication
- **Category:** Cryptographic Hash-Based Idempotency
- **Mathematical Concept:**
  $$\text{Hash}_{\text{batch}} = \text{SHA256}\left(\text{"SEC002"} \parallel T_{\text{advisory}} \parallel T_{\text{validity}} \parallel \sum_{i=1}^N \left(\text{lat}_i \parallel \text{lon}_i\right)\right)$$
- **How It Works:** Concatenates sector code, advisory dates, and formatted coordinate strings into a canonical string. Calculates a 64-character hexadecimal SHA-256 digest. Checks the database for the existence of `hash_id = SHA256(Hash_batch || "_0")`. If found, skips insertion.
- **Why Used:** The ingestion daemon runs periodically (hourly/daily). Deduplication prevents table bloat and preserves referential integrity without relying on artificial auto-increment keys.
- **Input:** Extracted advisory records and timestamps
- **Output:** Hexadecimal hash string `str` (64 characters)
- **Complexity:** Time: $\mathcal{O}(L)$ where $L$ is total payload string length, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/incois_pfz_provider.py` (lines 520–534)

---

### 6. Causal Lookback Rolling-Window Feature Generation
- **Category:** Time-Series Feature Engineering / Causal Inference
- **Mathematical Concept:**
  Let $E_{i, t}$ represent apparent fishing hours in grid cell $i$ on date $t$. For prediction made at date $T$ predicting target $Y_{i, T} = \mathbf{1}(E_{i, T+1} > 1.0\text{ h})$:
  - **Lags:** $E_{i, T}, E_{i, T-1}, E_{i, T-2}, E_{i, T-3}$
  - **Trailing 7-Day Mean:** $\mu_{7}(i, T) = \frac{1}{7}\sum_{k=0}^6 E_{i, T-k}$
  - **Trailing 7-Day Max:** $\max_{7}(i, T) = \max_{k \in [0, 6]} E_{i, T-k}$
  - **Trailing 7-Day Standard Deviation:** $\sigma_{7}(i, T) = \sqrt{\frac{1}{7}\sum_{k=0}^6 \left(E_{i, T-k} - \mu_7\right)^2}$
  - **Trailing 7-Day Active Frequency:** $f_{7}(i, T) = \frac{1}{7}\sum_{k=0}^6 \mathbf{1}(E_{i, T-k} > 0)$
  - **Trailing 14-Day Mean:** $\mu_{14}(i, T) = \frac{1}{14}\sum_{k=0}^{13} E_{i, T-k}$
  - **Regional Fleet Effort at $T$:** $R_T = \sum_{j \in \text{All Cells}} E_{j, T}$
  - **Cyclical Day-of-Year Encoding:**
    $$\sin_{\text{doy}} = \sin\left(\frac{2\pi \cdot \text{DOY}}{365.25}\right), \quad \cos_{\text{doy}} = \cos\left(\frac{2\pi \cdot \text{DOY}}{365.25}\right)$$
- **Strict Anti-Leakage Invariant:**
  $$\forall \text{ features } f, \quad \text{temporal\_index}(f) \le T < T+1 = \text{target\_date}$$
- **Why Used:** Solves temporal leakage in fisheries forecasting. Proved zero future contamination by automated test suite (`ml/evaluation/leakage_validator.py`).
- **Input:** Chronologically sorted daily observations per grid cell
- **Output:** Feature DataFrame with 29 aligned predictor columns
- **Complexity:** Time: $\mathcal{O}(G \cdot T)$ where $G$ is cell count (171) and $T$ is time steps (350), Space: $\mathcal{O}(G \cdot T)$.
- **Source Code Location:**
  - `ml/features/causal_dataset.py` (lines 28–252)

---

### 7. Point-in-Polygon Marine Masking & Grid Generation
- **Category:** Computational Geometry / Spatial Indexing
- **How It Works:** Generates bounding polygons across the bounding box ($[15.50^\circ\text{N}, 20.00^\circ\text{N}] \times [72.00^\circ\text{E}, 74.00^\circ\text{E}]$) at step resolution $\Delta = 0.25^\circ$. Evaluates centroid and all four polygon corners using `global_land_mask.globe.is_ocean(lat, lon)`. A cell is classified as a valid marine cell if any evaluated coordinate lies in ocean waters.
- **Why Used:** Filters out Western Ghats / inland landmass points, producing the exact 171 canonical marine cells covering Maharashtra's coastal waters.
- **Input:** Min/Max Lat, Min/Max Lon, Resolution $\Delta$
- **Output:** List of 171 marine grid dictionaries with centroids and coastal distances
- **Complexity:** Time: $\mathcal{O}(P)$ where $P = \frac{\Delta \text{Lat}}{\text{res}} \times \frac{\Delta \text{Lon}}{\text{res}}$ point tests, Space: $\mathcal{O}(P)$.
- **Source Code Location:**
  - `backend/app/ml/inference.py` (lines 116–151)
  - `backend/scripts/generate_spatial_grid.py` (lines 28–58)

---

### 8. Nearest-Neighbor Spatial Regridding
- **Category:** Geospatial Data Resampling
- **Mathematical Concept:**
  $$\text{cell}^*(i) = \arg\min_{c \in \text{Grid}} \mathcal{H}\left(\text{lat}_{\text{obs}}, \text{lon}_{\text{obs}}, \text{lat}_c, \text{lon}_c\right)$$
  where $\mathcal{H}$ is the Haversine distance.
- **How It Works:** Ingests native environmental data from external models with native grids (e.g., Copernicus 0.083° physics or Open-Meteo 0.08° wave grid). For each canonical grid cell, finds the closest external observation point and maps its physical parameters. Enforces temporal availability: $\text{source\_publication\_time} \le T$.
- **Why Used:** Harmonizes disparate external coordinate grids into the single standardized 0.25° canonical prediction grid.
- **Input:** Native observation array, canonical grid definition, prediction epoch $T$
- **Output:** Regridded feature vectors with strict provenance timestamps
- **Complexity:** Time: $\mathcal{O}(C \cdot G)$ where $C$ is external point count and $G$ is canonical cell count (171), Space: $\mathcal{O}(C)$.
- **Source Code Location:**
  - `backend/app/services/ml/feature_builder.py` (lines 70–120)

---

### 9. Multi-Tier Independent Safety Gate Evaluation
- **Category:** Rule-Based Decision Logic / Safety Protocol
- **Priority Hierarchy:**
  ```
  Tier 1: Restricted Zone Check (BLOCKED)
      ↓
  Tier 2: Active Severe Warning Check (UNSAFE)
      ↓
  Tier 3: Environmental Thresholds / Active Caution (CAUTION)
      ↓
  Tier 4: Authoritative Bulletin Confirms Normal (SAFE_CONFIRMED)
      ↓
  Tier 5: Fallthrough / Missing / Stale Warning Feed (NO_WARNING_DATA)
  ```
- **Mathematical Logic:**
  $$\text{Safety}(i) = \begin{cases}
  \text{UNSAFE}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{SEVERE}\} \\
  \text{CAUTION}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{WARNING}, \text{CAUTION}\} \\
  & \lor \left(\text{WaveHeight}_i > 4.0\text{ m}\right) \lor \left(\text{WindSpeed}_i > 50.0\text{ km/h}\right) \\
  \text{SAFE\_CONFIRMED}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{NORMAL}, \text{NIL}\} \\
  & \land \left(\text{WaveHeight}_i \le 4.0\text{ m}\right) \land \left(\text{WindSpeed}_i \le 50.0\text{ km/h}\right) \\
  \text{NO\_WARNING\_DATA}, & \text{otherwise (warning feed missing, expired, or stale)}
  \end{cases}$$
- **Invariant:** The ML model output $\hat{P}(\text{Effort})$ **never** enters the safety function. A high prediction probability ($0.95$) inside a storm sector yields `UNSAFE` with `safety_override = True`.
- **Complexity:** Time: $\mathcal{O}(P \cdot W)$ where $P$ is cell count (171) and $W$ is active warnings count, Space: $\mathcal{O}(P)$.
- **Source Code Location:**
  - `backend/app/ml/safety_gate.py` (lines 46–151)

---

### 10. Source Freshness & Latency Age Calculation
- **Category:** Auditing & Observability
- **Mathematical Concept:**
  $$\text{Age}_{\text{minutes}} = \frac{T_{\text{now}} - T_{\text{actual\_data}}}{60}$$
  $$\text{Status} = \begin{cases}
  \text{LIVE}, & \text{if } T_{\text{now}} \le T_{\text{valid\_until}} \text{ (or } \text{Age} \le \text{Threshold}) \\
  \text{STALE}, & \text{if } T_{\text{now}} > T_{\text{valid\_until}} \\
  \text{CACHED\_HISTORICAL}, & \text{for GFW (due to inherent AIS archival publication latency)} \\
  \text{UNAVAILABLE}, & \text{if record count} = 0 \lor \text{fetch error}
  \end{cases}$$
- **How It Works:** Evaluates database state for each authoritative provider. Compares current UTC time against the actual publication or validity timestamps extracted from the bulletins. Computes real latency in minutes or days.
- **Why Used:** Prevents dangerous "false fresh" labels where an ingestion script successfully downloads a stale 3-day-old bulletin and flags it as current based on download time.
- **Complexity:** Time: $\mathcal{O}(S)$ where $S$ is tracked sources count (4), Space: $\mathcal{O}(S)$.
- **Source Code Location:**
  - `backend/app/services/freshness/source_tracker.py` (lines 43–470)

---

# 5. Database Analysis and Design

This document details the database architecture, schema definitions, spatial extensions, constraints, and data access layer for the MatsyaAI Maharashtra platform.

---

## 5.1 Database Technology Overview

- **RDBMS Engine:** PostgreSQL 16 (Container image: `postgis/postgis:16-3.4`)
- **Spatial Extension:** PostGIS 3.4
- **ORM / Data Access Layer:** SQLAlchemy 2.0.35 with AsyncIO extension (`sqlalchemy.ext.asyncio`)
- **Driver:** AsyncPG 0.29.0 (High-performance binary async driver)
- **Spatial ORM Bridge:** GeoAlchemy2 0.15.2
- **Migration Framework:** Alembic 1.13.3
- **Spatial Reference System (SRID):** `4326` (WGS-84 Geographic Coordinate System)

---

## 5.2 Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    landing_centres ||--o{ incois_pfz_advisories : "geodesic origin"
    spatial_grids ||--o{ model_features : "aggregates"
    spatial_grids ||--o{ predictions : "projects onto"

    landing_centres {
        int id PK "auto-increment"
        varchar(255) name "e.g. Sassoon Dock"
        enum district "Palghar, Mumbai, Raigad, Ratnagiri, Sindhudurg"
        float latitude
        float longitude
        geometry geom "POINT, SRID 4326"
        varchar(255) source "MOCK_DEVELOPMENT_DATA / OFFICIAL"
        timestamptz created_at "UTC"
    }

    incois_pfz_advisories {
        int id PK "auto-increment"
        varchar(50) source "INCOIS"
        varchar(50) source_type "OFFICIAL_PFZ_ADVISORY"
        varchar(50) sector "Maharashtra"
        varchar(100) landing_centre
        varchar(20) direction
        int bearing_degrees
        varchar(50) distance_km
        int depth_min_m
        int depth_max_m
        float latitude
        float longitude
        geometry geom "POINT, SRID 4326"
        timestamptz advisory_date
        timestamptz validity_date
        timestamptz retrieved_at
        varchar(255) source_url
        varchar(64) hash_id UK "SHA-256 Batch Hash"
    }

    pfz_zones {
        int id PK "auto-increment"
        date date
        float latitude
        float longitude
        geometry geom "GEOMETRY, SRID 4326"
        float depth
        varchar(255) source_name "INCOIS"
        varchar(255) dataset_name "OFFICIAL_PFZ_ADVISORY"
        timestamptz source_timestamp
        timestamptz retrieved_at
        varchar(100) spatial_resolution
        varchar(100) temporal_resolution
        varchar(50) data_quality_status
        boolean is_stale
    }

    marine_warnings {
        int id PK "auto-increment"
        varchar(255) warning_type "COASTAL_FISHERMEN_WARNING"
        varchar(100) severity "NORMAL, WARNING, SEVERE"
        timestamptz valid_from
        timestamptz valid_until
        text description
        geometry geom "GEOMETRY, SRID 4326"
        varchar(255) source_name "IMD_MUMBAI_FISHERMAN_BULLETIN"
        varchar(255) dataset_name
        timestamptz source_timestamp
        timestamptz retrieved_at
        varchar(100) spatial_resolution
        varchar(100) temporal_resolution
        varchar(50) data_quality_status
        boolean is_stale
    }

    ocean_observations {
        int id PK "auto-increment"
        timestamptz timestamp "Observation / valid time"
        float latitude
        float longitude
        geometry geom "POINT, SRID 4326"
        float sst
        float sst_anomaly
        float chlorophyll
        float wind_speed
        float wind_direction
        float wave_height
        float wave_period
        float swell_height
        float current_speed
        float current_direction
        varchar(255) source_name "Open-Meteo / CMEMS"
        varchar(255) dataset_name
        timestamptz source_publication_time "Anti-leakage control"
        timestamptz retrieved_at
        varchar(100) spatial_resolution
        varchar(100) temporal_resolution
        varchar(50) data_quality_status
        boolean is_stale
    }

    gfw_fishing_effort {
        int id PK "auto-increment"
        varchar(100) grid_cell_id "INDEXED"
        float latitude
        float longitude
        timestamptz observation_date "INDEXED"
        timestamptz retrieved_at
        float fishing_hours
        varchar(100) vessel_type
        varchar(100) geartype
        varchar(10) flag
        varchar(64) hash_id UK "Unique Content Hash"
    }

    spatial_grids {
        varchar(100) id PK "e.g. cell_19.0_72.8"
        float resolution "0.25 deg"
        float latitude
        float longitude
        geometry geom "POLYGON, SRID 4326"
        geometry centroid "POINT, SRID 4326"
        float distance_to_coast_km
    }

    model_features {
        int id PK "auto-increment"
        varchar(100) grid_cell_id FK
        timestamptz timestamp
        float wave_height
        float wave_period
        float wave_direction
        float wind_speed
        float wind_direction
        float sst
        int hour
        int day_of_year
        varchar(50) season
        boolean is_valid
        varchar(255) provenance
        varchar(255) imputation_flags
    }

    predictions {
        int id PK "auto-increment"
        timestamptz prediction_timestamp
        float latitude
        float longitude
        geometry geom "POINT, SRID 4326"
        float prediction_probability
        int prediction_class
        varchar(200) prediction_label
        varchar(100) model_version
        varchar(100) model_trained_at
        timestamptz env_observation_timestamp
        varchar(100) env_source
        float data_freshness_seconds
        varchar(100) safety_status
        boolean safety_override
        text pfz_advisory
        timestamptz created_at
    }
```

---

## 5.3 Detailed Table Schemas

### 1. `landing_centres`
Stores coastal landing centres, fishing harbours, and major fish landing jetties across Maharashtra.
- **Model File:** `backend/app/models/landing_centre.py`
- **Columns:**
  - `id` (INTEGER, Primary Key, Autoincrement)
  - `name` (VARCHAR(255), NOT NULL): Official name of landing centre (e.g., "Sassoon Dock", "Mirkarwada").
  - `district` (ENUM `DistrictEnum`, NOT NULL): One of `Palghar`, `Mumbai`, `Raigad`, `Ratnagiri`, `Sindhudurg`.
  - `latitude` (FLOAT, NOT NULL): WGS-84 latitude.
  - `longitude` (FLOAT, NOT NULL): WGS-84 longitude.
  - `geom` (GEOMETRY(POINT, 4326), NOT NULL): PostGIS spatial point.
  - `source` (VARCHAR(255), NOT NULL): Ingestion origin.
  - `created_at` (TIMESTAMPTZ, Default: `NOW()` UTC).

---

### 2. `incois_pfz_advisories`
Stores Potential Fishing Zone advisory records extracted from the official INCOIS TextData portal.
- **Model File:** `backend/app/models/incois_pfz.py`
- **Columns:**
  - `id` (INTEGER, Primary Key, Autoincrement)
  - `source` (VARCHAR(50), NOT NULL, Default: `"INCOIS"`).
  - `source_type` (VARCHAR(50), NOT NULL, Default: `"OFFICIAL_PFZ_ADVISORY"`).
  - `sector` (VARCHAR(50), NOT NULL, Default: `"Maharashtra"`).
  - `landing_centre` (VARCHAR(100), NOT NULL): Reference port (e.g., "Talashil", "Arnala").
  - `direction` (VARCHAR(20), NOT NULL): Compass bearing string (e.g., "SW", "WNW").
  - `bearing_degrees` (INTEGER, NOT NULL): Bearing angle $[0^\circ, 360^\circ]$.
  - `distance_km` (VARCHAR(50), NOT NULL): Distance from origin port.
  - `depth_min_m` (INTEGER, Nullable): Shallowest depth contour in metres.
  - `depth_max_m` (INTEGER, Nullable): Deepest depth contour in metres.
  - `latitude` (FLOAT, NOT NULL): Converted decimal latitude.
  - `longitude` (FLOAT, NOT NULL): Converted decimal longitude.
  - `geom` (GEOMETRY(POINT, 4326), NOT NULL): Spatial location point.
  - `advisory_date` (TIMESTAMPTZ, Nullable): Extracted bulletin date.
  - `validity_date` (TIMESTAMPTZ, Nullable): Expiry timestamp (set to 23:59:59 UTC).
  - `retrieved_at` (TIMESTAMPTZ, NOT NULL): Exact download timestamp.
  - `source_url` (VARCHAR(255), NOT NULL).
  - `hash_id` (VARCHAR(64), UNIQUE, INDEXED, NOT NULL): SHA-256 batch deduplication hash.

---

### 3. `marine_warnings`
Stores meteorological marine weather and cyclone warnings parsed from IMD Mumbai bulletins.
- **Model File:** `backend/app/models/marine_warning.py`
- **Columns:**
  - `id` (INTEGER, Primary Key, Autoincrement)
  - `warning_type` (VARCHAR(255), NOT NULL): e.g., `"COASTAL_FISHERMEN_WARNING"`, `"HIGH_SEA_WIND_WARNING"`, `"HIGH_WAVE_WARNING"`.
  - `severity` (VARCHAR(100), NOT NULL): `"NORMAL"`, `"WARNING"`, or `"SEVERE"`.
  - `valid_from` (TIMESTAMPTZ, NOT NULL): Start of validity window.
  - `valid_until` (TIMESTAMPTZ, NOT NULL): End of validity window.
  - `description` (TEXT, NOT NULL): Raw warning text.
  - `geom` (GEOMETRY, 4326, NOT NULL): PostGIS spatial polygon bounding the warning zone.
  - `source_name` (VARCHAR(255), NOT NULL, Default: `"IMD_MUMBAI_FISHERMAN_BULLETIN"`).
  - `dataset_name` (VARCHAR(255), NOT NULL).
  - `source_timestamp` (TIMESTAMPTZ, NOT NULL): Official issue timestamp.
  - `retrieved_at` (TIMESTAMPTZ, NOT NULL): Download timestamp.
  - `spatial_resolution` (VARCHAR(100), Nullable).
  - `temporal_resolution` (VARCHAR(100), Nullable).
  - `data_quality_status` (VARCHAR(50), NOT NULL, Default: `"VALID"`).
  - `is_stale` (BOOLEAN, NOT NULL, Default: `False`).

---

### 4. `predictions`
Stores batch-executed machine learning predictions for the 0.25° Maharashtra marine grid.
- **Model File:** `backend/app/models/prediction.py`
- **Columns:**
  - `id` (INTEGER, Primary Key, Autoincrement)
  - `prediction_timestamp` (TIMESTAMPTZ, NOT NULL): Time the batch inference was executed.
  - `latitude` (FLOAT, NOT NULL): Grid centroid latitude.
  - `longitude` (FLOAT, NOT NULL): Grid centroid longitude.
  - `geom` (GEOMETRY(POINT, 4326), NOT NULL): Centroid geometry.
  - `prediction_probability` (FLOAT, NOT NULL): XGBoost probability $\in [0.0, 1.0]$.
  - `prediction_class` (INTEGER, NOT NULL): Binary classification ($0$ or $1$).
  - `prediction_label` (VARCHAR(200), NOT NULL): `"High Apparent Fishing Effort"` or `"Low/No Apparent Fishing Effort"`.
  - `model_version` (VARCHAR(100), NOT NULL, Default: `"Phase3_XGBoost_v1"`).
  - `model_trained_at` (VARCHAR(100), NOT NULL).
  - `env_observation_timestamp` (TIMESTAMPTZ, NOT NULL): Timestamp of environmental data used.
  - `env_source` (VARCHAR(100), NOT NULL): e.g., `"Open-Meteo"`.
  - `data_freshness_seconds` (FLOAT, NOT NULL): Latency of environmental input.
  - `safety_status` (VARCHAR(100), NOT NULL): `"SAFE_CONFIRMED"`, `"CAUTION"`, `"UNSAFE"`, or `"NO_WARNING_DATA"`.
  - `safety_override` (BOOLEAN, NOT NULL, Default: `False`): `True` if high prediction was overridden by active severe warning.
  - `pfz_advisory` (TEXT, Nullable).
  - `created_at` (TIMESTAMPTZ, Default: `NOW()` UTC).

---

### 5. `spatial_grids`
Represents the canonical marine spatial grid cells covering Maharashtra waters.
- **Model File:** `backend/app/models/feature.py`
- **Columns:**
  - `id` (VARCHAR(100), Primary Key): e.g., `"cell_19.00_72.75_0.25"`.
  - `resolution` (FLOAT, NOT NULL): Step resolution in degrees (`0.25`).
  - `latitude` (FLOAT, NOT NULL): Centroid latitude.
  - `longitude` (FLOAT, NOT NULL): Centroid longitude.
  - `geom` (GEOMETRY(POLYGON, 4326), NOT NULL): Exact bounding polygon.
  - `centroid` (GEOMETRY(POINT, 4326), NOT NULL): Spatial centroid.
  - `distance_to_coast_km` (FLOAT, Nullable): Shortest Haversine distance to coast.

---

### 6. `gfw_fishing_effort`
Stores historical and ingested apparent fishing effort from Global Fishing Watch AIS tracking.
- **Model File:** `backend/app/models/gfw.py`
- **Columns:**
  - `id` (INTEGER, Primary Key, Autoincrement)
  - `grid_cell_id` (VARCHAR(100), INDEXED, Nullable).
  - `latitude` (FLOAT, NOT NULL).
  - `longitude` (FLOAT, NOT NULL).
  - `observation_date` (TIMESTAMPTZ, INDEXED, NOT NULL): Calendar date fishing occurred.
  - `retrieved_at` (TIMESTAMPTZ, NOT NULL).
  - `fishing_hours` (FLOAT, NOT NULL): Apparent fishing effort in hours.
  - `vessel_type` (VARCHAR(100), Nullable).
  - `geartype` (VARCHAR(100), Nullable).
  - `flag` (VARCHAR(10), Nullable): Country flag (e.g., `"IND"`).
  - `hash_id` (VARCHAR(64), UNIQUE, NOT NULL): Deduplication content hash.

---

## 5.4 Database Migration History (Alembic)

The database schema evolution is tracked in `backend/alembic/versions/`:

| Revision ID | Name / Description | Key Schema Modifications |
| :--- | :--- | :--- |
| `01d27f92e854` | `initial_schema.py` | Creates PostGIS extension, `landing_centres`, `ocean_observations`, `pfz_zones`, and `marine_warnings` tables with basic spatial columns. |
| `3799bc745018` | `add_provenance_and_quality_fields.py` | Adds `spatial_resolution`, `temporal_resolution`, `data_quality_status`, `is_stale`, and `retrieved_at` metadata fields to guarantee data provenance. |
| `c75009cfc94b` | `add_feature_engineering_models.py` | Introduces `spatial_grids` and `model_features` tables supporting canonical ML feature engineering. |
| `ef789012gh34` | `add_gfw_model_and_rename_ocean_.py` | Creates `gfw_fishing_effort` table with `hash_id` uniqueness and indexes; renames ocean observation timestamps to `source_publication_time` to eliminate temporal leakage. |
| `abcd1234ef56` | `add_incois_pfz_advisory.py` | Adds dedicated `incois_pfz_advisories` table with `hash_id` index for official web table scraping. |
| `8596d05bae1b` | `update_predictions_schema_for_phase5.py` | Migrates `predictions` table schema to support Phase 4/5 outputs: `prediction_probability`, `model_version`, `env_source`, and decoupled `safety_status`. |

---

## 5.5 Data Access Lifecycle & Async Connection Pooling

```mermaid
sequenceDiagram
    autonumber
    participant App as FastAPI Handler
    participant Dep as get_db Dependency
    participant Pool as AsyncEngine Connection Pool
    participant DB as PostgreSQL Server

    App->>Dep: Request starts: await get_db()
    Dep->>Pool: async_session() acquires connection from pool
    Pool->>DB: Checkout connection (pool_pre_ping=True)
    DB-->>Pool: Connection verified healthy (SELECT 1)
    Dep-->>App: Yields AsyncSession
    App->>DB: Execute async SQL / ORM select query
    DB-->>App: Return records
    App-->>Dep: Request completes / exception handled
    Dep->>Pool: session.close() (Return connection to pool)
```

- **Connection Pool Configuration (`backend/app/core/database.py`):**
  - `pool_size = 5`
  - `max_overflow = 10`
  - `pool_pre_ping = True` (automatically detects and drops severed database sockets)
  - `expire_on_commit = False` (prevents unnecessary re-querying of attributes on committed instances).

---

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

---

# 7. Project Folder Structure

This document provides a comprehensive structural breakdown of the MatsyaAI Maharashtra repository, documenting the responsibilities of each directory, subpackage, configuration file, and entry point.

---

## 7.1 Annotated Repository Tree

```
D:\Matsya_AI\
│
├── .env.example                          # Canonical environment configuration template
├── .gitignore                            # Git exclusion rules (caches, virtualenvs, credentials)
├── docker-compose.yml                    # Multi-container orchestration (db, backend, ingestion, frontend)
├── README.md                             # Repository introductory readme and quick-start instructions
├── FINAL_READINESS_REPORT.md             # Production readiness and verification sign-off report
├── incois_output.html                    # Scraped raw HTML artifact from INCOIS TextData portal
├── map_output.json                       # Sample serialized consolidated map API response
├── predictions.json                      # Sample serialized prediction batch payload
│
├── backend/                              # Python FastAPI Backend & Ingestion Engine
│   ├── alembic.ini                       # Alembic database migration configuration
│   ├── requirements.txt                  # Python dependencies with pinned production versions
│   │
│   ├── alembic/                          # Alembic database schema migration scripts
│   │   ├── env.py                        # Alembic migration runner with AsyncEngine binding
│   │   ├── script.py.mako                # Template for generating new schema revisions
│   │   └── versions/                     # Chronological schema migration scripts
│   │       ├── 01d27f92e854_initial_schema.py
│   │       ├── 3799bc745018_add_provenance_and_quality_fields.py
│   │       ├── c75009cfc94b_add_feature_engineering_models.py
│   │       ├── ef789012gh34_add_gfw_model_and_rename_ocean_.py
│   │       ├── abcd1234ef56_add_incois_pfz_advisory.py
│   │       └── 8596d05bae1b_update_predictions_schema_for_phase5.py
│   │
│   ├── app/                              # Core application package
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI application entrypoint & lifespan handler
│   │   │
│   │   ├── api/                          # REST API routers
│   │   │   └── v1/
│   │   │       ├── health.py             # Liveness and PostgreSQL connectivity check
│   │   │       ├── map.py                # Consolidated map summary endpoint (/api/v1/map/summary)
│   │   │       ├── pfz.py                # Official INCOIS PFZ advisory endpoint (/api/v1/pfz/latest)
│   │   │       ├── predictions.py        # ML apparent fishing predictions endpoint
│   │   │       └── sources.py            # Source freshness & health tracking (/api/v1/sources/freshness)
│   │   │
│   │   ├── core/                         # Infrastructure, database, configuration
│   │   │   ├── config.py                 # Pydantic Settings singleton (environment parsing)
│   │   │   ├── database.py               # Async engine pool, async_session, and get_db dependency
│   │   │   └── logging.py                # Structured logging configuration (structlog)
│   │   │
│   │   ├── models/                       # SQLAlchemy declarative ORM models
│   │   │   ├── feature.py                # SpatialGrid and ModelFeature models
│   │   │   ├── gfw.py                    # GFWFishingEffort model (AIS apparent effort)
│   │   │   ├── incois_pfz.py             # INCOISPFZAdvisory model
│   │   │   ├── landing_centre.py         # LandingCentre model and DistrictEnum
│   │   │   ├── marine_warning.py         # MarineWarning model (IMD squalls and sea alerts)
│   │   │   ├── ocean_observation.py      # OceanObservation model (marine weather parameters)
│   │   │   ├── pfz_zone.py               # PFZZone model
│   │   │   └── prediction.py             # Prediction model (persisted ML batch outputs)
│   │   │
│   │   ├── schemas/                      # Pydantic serialization & request/response schemas
│   │   │   └── pfz.py                    # PFZLocation and PFZLatestResponse schemas
│   │   │
│   │   ├── services/                     # Business logic, ETL ingestion, and tracking
│   │   │   ├── freshness/
│   │   │   │   └── source_tracker.py     # SourceFreshnessTracker (actual observation timestamps)
│   │   │   ├── ingestion/
│   │   │   │   ├── base.py               # BaseProvider abstract base class and ProviderStatus enum
│   │   │   │   ├── copernicusmarine_provider.py # CMEMS provider implementation
│   │   │   │   ├── gfw_provider.py       # Global Fishing Watch 4Wings API provider
│   │   │   │   ├── imd_marine_provider.py# IMD Mumbai Fishermen Bulletin PDF parser
│   │   │   │   ├── incois_pfz_provider.py# INCOIS TextData HTML parser and DMS converter
│   │   │   │   ├── ingestion_runner.py   # IngestionRunner orchestrating independent ingestors
│   │   │   │   ├── pipeline.py           # Ingestion pipeline orchestration
│   │   │   │   └── providers.py          # OpenMeteoMarineProvider implementation
│   │   │   └── ml/
│   │   │       └── feature_builder.py    # Spatial regridding and provenance feature builder
│   │   │
│   │   └── ml/                           # ML inference, safety gate, and training harness
│   │       ├── config.py                 # Central ML configuration (grid bounds, thresholds)
│   │       ├── dataset_builder.py        # Grid generator and historical dataset builder
│   │       ├── inference.py              # Phase 4 Inference Pipeline (XGBoost serving)
│   │       ├── safety_gate.py            # SafetyGate independent multi-tier safety engine
│   │       ├── trainer.py                # Model training utilities
│   │       ├── artifacts/                # Frozen Phase 3 model artifacts
│   │       │   ├── phase3_feature_columns.json # Exact 29 canonical feature names
│   │       │   ├── phase3_imputer.joblib # Scikit-learn SimpleImputer (median)
│   │       │   ├── phase3_scaler.joblib  # Scikit-learn StandardScaler
│   │       │   ├── phase3_threshold.json # Frozen decision threshold (0.47)
│   │       │   ├── phase3_xgboost_model.joblib # Serialized XGBoost classifier
│   │       │   └── phase3_metadata.json  # Model metadata, dates, and baseline metrics
│   │       └── data/                     # Local data caches and Parquet archives
│   │           ├── historical_full_year_2023.parquet # 59,850 observations for full year 2023
│   │           ├── historical_oct2023.parquet
│   │           ├── env_raw/              # Raw environmental observation caches
│   │           └── gfw_raw/              # Raw GFW API response chunks
│   │
│   ├── scripts/                          # Administrative, batch, and diagnostic CLI tools
│   │   ├── generate_spatial_grid.py      # Authoritative 0.1° / 0.25° canonical grid generator
│   │   ├── run_ingestion.py              # Ingestion CLI and continuous background daemon
│   │   ├── run_predictions.py            # Batch ML prediction execution CLI
│   │   └── seed_landing_centres.py       # Seeds Maharashtra coastal landing centres
│   │
│   └── tests/                            # Pytest test suite (15 test modules)
│       ├── test_database.py              # Database connection and PostGIS geometry tests
│       ├── test_imd_marine.py            # IMD PDF parsing, kerning cleanup, and classification
│       ├── test_incois_pfz.py            # INCOIS HTML parsing, DMS conversion, and deduplication
│       ├── test_safety_gate_phase6.py    # SafetyGate multi-tier priority and override tests
│       ├── test_source_freshness.py      # SourceFreshnessTracker observation date tests
│       ├── test_prediction_provenance.py # Prediction provenance and metadata integrity
│       └── fixtures/
│           └── sample_imd_fisherman.pdf  # Genuine historical IMD Mumbai PDF bulletin fixture
│
├── frontend/                             # React 19 + TypeScript + Leaflet Web Application
│   ├── index.html                        # Single-page HTML application entry point
│   ├── package.json                      # Frontend dependencies, scripts, and dev tools
│   ├── tsconfig.json                     # TypeScript project configuration
│   ├── vite.config.ts                    # Vite configuration with backend proxy rules
│   │
│   ├── public/                           # Static public assets (favicons, SVG icons)
│   │
│   └── src/                              # Client application source code
│       ├── main.tsx                      # React root rendering entry point
│       ├── App.tsx                       # Root dashboard component (Hero, banners, metrics)
│       ├── App.css / index.css           # Oceanic theme styles and responsive layout
│       │
│       ├── components/                   # Reusable UI components
│       │   └── FreshnessHUD.tsx          # Real-time Source Freshness Heads-Up Display
│       │
│       ├── map/                          # Geospatial visualization components
│       │   └── MarineMap.tsx             # Interactive Leaflet map (Grid, PFZ, Safety, Ports)
│       │
│       ├── services/                     # HTTP client communication layer
│       │   └── api.ts                    # Typed API client (fetchHealth, fetchMapSummary)
│       │
│       ├── types/                        # TypeScript type definitions
│       │   ├── health.ts                 # HealthResponse contract
│       │   └── map.ts                    # MapSummaryResponse, CellPrediction, SafetyStatus
│       │
│       └── i18n/                         # Internationalization dictionaries
│           ├── index.ts                  # Bilingual language manager
│           ├── en.ts                     # English terminology and disclaimers
│           └── mr.ts                     # Marathi (मराठी) terminology and disclaimers
│
├── ml/                                   # Standalone Machine Learning Research & Validation
│   ├── evaluation/
│   │   └── leakage_validator.py          # Automated temporal leakage validation suite
│   ├── features/
│   │   └── causal_dataset.py             # Causal feature builder for historical datasets
│   ├── models/
│   │   ├── baselines.py                  # Domain baselines (Persistence, Trailing 7D, Spatial)
│   │   └── serialize_phase3_artifacts.py # Serializer generating Phase 3 artifact joblibs
│   └── training/
│       └── experiment_phase3.py          # Phase 3 benchmarking harness (XGBoost, RF, Ridge)
│
├── database/                             # Database provisioning assets
│   ├── migrations/                       # Alembic environment storage
│   └── seeds/                            # Database seed scripts
│       └── landing_centres_mock.py       # Seed data for 10 Maharashtra landing centres
│
├── docker/                               # Containerization build files
│   ├── backend.Dockerfile                # Multi-stage Python 3.12 slim container
│   └── frontend.Dockerfile               # Multi-stage Node 20 Alpine container
│
└── docs/                                 # Technical documentation & scientific reports
    ├── data-sources.md                   # Authoritative data sources registry and status
    └── phase3_scientific_evaluation_report.md # Comprehensive Phase 3 ML scientific report
```

---

## 7.2 Directory Responsibilities

### `backend/`
- **Core Role:** Serves REST APIs, manages database connectivity, executes asynchronous ingestion daemons, and hosts the frozen ML inference pipeline.
- **Entry Points:**
  - `backend/app/main.py`: ASGI web application run via Uvicorn.
  - `backend/scripts/run_ingestion.py`: Standalone CLI or long-running daemon (`--daemon`) executing ingestion jobs.
  - `backend/scripts/run_predictions.py`: Standalone CLI executing scheduled ML prediction batches.

### `frontend/`
- **Core Role:** Presents a fisherman-optimized single-page interface with real-time safety banners, an interactive Leaflet marine map, and bilingual (English/Marathi) support.
- **Entry Points:**
  - `frontend/index.html`: Web template mounting `#root`.
  - `frontend/src/main.tsx`: Renders `<App />` within React strict mode.

### `ml/`
- **Core Role:** Hosts offline scientific research, causal feature engineering, baseline comparisons, temporal leakage validation, and model artifact serialization.
- **Key Modules:**
  - `ml/features/causal_dataset.py`: Enforces causal invariants on historical datasets.
  - `ml/evaluation/leakage_validator.py`: Executes automated tests verifying zero temporal contamination.
  - `ml/training/experiment_phase3.py`: Executes multi-model benchmarking on full-year 2023 data.

### `docker/`
- **Core Role:** Provides standardized container definitions.
- **Key Files:**
  - `backend.Dockerfile`: Installs system build tools (`gcc`, `libpq-dev`), installs Python dependencies from `requirements.txt`, copies backend and ML code, and exposes port 8000.
  - `frontend.Dockerfile`: Installs Node dependencies from `package.json`, copies frontend source, and runs Vite on `0.0.0.0:5173`.

---

# 8. Feature-by-Feature Technical Explanation

This document details the architecture, implementation, frontend components, backend services, database operations, and complete execution flow for each of the eight primary features implemented in the MatsyaAI Maharashtra platform.

---

## 8.1 Feature Index

1. [**Official INCOIS Potential Fishing Zones (PFZ) Ingestion**](#feature-1-official-incois-potential-fishing-zones-pfz-ingestion)
2. [**Official IMD Marine Bulletin Extraction & Classification**](#feature-2-official-imd-marine-bulletin-extraction--classification)
3. [**Independent Multi-Tier Safety Gate Decoupling**](#feature-3-independent-multi-tier-safety-gate-decoupling)
4. [**Next-Calendar-Day Apparent Fishing Effort Forecasting (XGBoost)**](#feature-4-next-calendar-day-apparent-fishing-effort-forecasting-xgboost)
5. [**Real-Time Marine Weather Ingestion (Open-Meteo)**](#feature-5-real-time-marine-weather-ingestion-open-meteo)
6. [**Data Freshness & Provenance Tracking (HUD)**](#feature-6-data-freshness--provenance-tracking-hud)
7. [**Bilingual Fisherman-First Interactive Marine Map (Leaflet)**](#feature-7-bilingual-fisherman-first-interactive-marine-map-leaflet)
8. [**Automated Ingestion Daemon & Batch Scheduling Engine**](#feature-8-automated-ingestion-daemon--batch-scheduling-engine)

---

## Feature 1: Official INCOIS Potential Fishing Zones (PFZ) Ingestion

### Functionality
Automatically discovers, authenticates, scrapes, parses, and persists daily Potential Fishing Zone (PFZ) advisories issued by the Indian National Centre for Ocean Information Services (INCOIS) for the Maharashtra marine sector (`SEC002`).

### Technical Implementation
- **Session Handshake:** INCOIS serves data behind a stateful session check. The provider first performs an HTTP GET on `TextDataHome` using `httpx.AsyncClient` to receive a `JSESSIONID` cookie.
- **Table Scraping:** Issues a GET request to `TextData?secid=SEC002` passing the session cookie. Uses `BeautifulSoup` to locate the table matching key headers (`"Landing Centre"`, `"Direction"`, `"Latitude (dms)"`).
- **DMS Conversion:** Parses Degrees-Minutes-Seconds coordinate strings using `parse_dms()`, which strips punctuation and applies cardinal signs to produce decimal degrees.
- **Deduplication:** Computes a SHA-256 batch hash from advisory dates and coordinate sets. If already ingested, skips re-insertion.
- **Stale Flagging:** Before inserting a new batch, executes an async update marking prior active records in `pfz_zones` as `is_stale = True`.

### Key Code Artifacts
- **Backend Provider:** `backend/app/services/ingestion/incois_pfz_provider.py` (`INCOISPFZProvider`)
- **Database Models:** `backend/app/models/incois_pfz.py` (`INCOISPFZAdvisory`) and `backend/app/models/pfz_zone.py` (`PFZZone`)
- **API Endpoint:** `GET /api/v1/pfz/latest` (`backend/app/api/v1/pfz.py`)
- **Frontend Presentation:** `frontend/src/map/MarineMap.tsx` (renders green target markers and 4 km buffer circles)

### Execution Trace
```
HTTP GET TextDataHome → Extract JSESSIONID → HTTP GET TextData?secid=SEC002 
→ BeautifulSoup table parse → DMS to Decimal Conversion → SHA-256 Hash Check 
→ Mark previous records is_stale=True → Insert incois_pfz_advisories & pfz_zones → Commit
```

---

## Feature 2: Official IMD Marine Bulletin Extraction & Classification

### Functionality
Downloads the daily official IMD Mumbai Fishermen Warning PDF bulletin (`fisherman.pdf`), extracts structured text while correcting character kerning, parses coastal and high-sea advisory sections, and assigns deterministic severity levels (`NORMAL`, `WARNING`, `SEVERE`).

### Technical Implementation
- **Resilient PDF Download:** Fetches `https://mausam.imd.gov.in/mumbai/mcdata/fisherman.pdf` with exponential retry backoff (3 retries).
- **Spatial Line Extraction:** Invokes `PyPDF2.PdfReader` with a coordinate-based spatial visitor callback. Groups text elements by physical vertical line position ($y$) and sorts horizontally ($x$), overcoming PDF kerning artifacts where letters are separated by spaces.
- **Regular Expression Token Cleanup:** Iteratively applies `_clean_token_spacing` to collapse whitespace between individual characters (e.g., `'T h u r s d a y'` $\to$ `'Thursday'`).
- **Temporal Parsing:** Extracts bulletin issue date and 5-day validity windows using regular expressions.
- **Severity NLP:** Uses keyword pattern matching:
  - `SEVERE`: gale, cyclone, hurricane, sustained wind $\ge 65\text{ kmph}$ gusting $\ge 75\text{ kmph}$.
  - `WARNING`: squally, rough sea, caution, advised not to venture.
  - `NORMAL`: ONLY when text explicitly matches `"nil"`, `"nil."`, `"normal"`.

### Key Code Artifacts
- **Backend Provider:** `backend/app/services/ingestion/imd_marine_provider.py` (`IMDMarineProvider`)
- **Database Model:** `backend/app/models/marine_warning.py` (`MarineWarning`)
- **Unit Tests:** `backend/tests/test_imd_marine.py` (tested against `sample_imd_fisherman.pdf`)

---

## Feature 3: Independent Multi-Tier Safety Gate Decoupling

### Functionality
Enforces strict decoupling between machine learning predictions and sea safety. The ML model is prohibited from declaring a marine area safe. Sea safety is governed solely by authoritative meteorological warnings and physical oceanographic thresholds.

### Technical Implementation
The `SafetyGate` evaluates a multi-tier priority hierarchy:
1. **Tier 1 (Blocked Zone):** Reserved for military or maritime restricted zones.
2. **Tier 2 (UNSAFE):** Triggered if any active IMD warning has severity `SEVERE`.
3. **Tier 3 (CAUTION):** Triggered if active warning is `WARNING` or if physical thresholds are breached:
   - Wave Height $> 4.0\text{ m}$ (`SAFETY_WAVE_HEIGHT_THRESHOLD`)
   - Wind Speed $> 50.0\text{ km/h}$ (`SAFETY_WIND_SPEED_THRESHOLD`)
4. **Tier 4 (SAFE_CONFIRMED):** ONLY granted if an active authoritative bulletin explicitly confirms normal/calm conditions AND wave and wind data are present and within thresholds.
5. **Tier 5 (NO_WARNING_DATA):** Default state if warning feeds are missing, unconfirmed, or stale. **Never assumes calm/safe conditions.**

### Key Code Artifacts
- **Backend Service:** `backend/app/ml/safety_gate.py` (`SafetyGate`)
- **Configuration:** `backend/app/ml/config.py` (thresholds: 4.0 m wave, 50.0 km/h wind)
- **Frontend Presentation:**
  - `frontend/src/App.tsx`: High-contrast banner rendering `#ff5252` (Unsafe), `#ffb300` (Caution), `#00e676` (Safe Confirmed), or `#90a4ae` (No Warning Data).
  - `frontend/src/map/MarineMap.tsx`: Top floating banner (`marine-safety-banner`).

---

## Feature 4: Next-Calendar-Day Apparent Fishing Effort Forecasting (XGBoost)

### Functionality
Forecasts whether apparent commercial fishing effort will exceed $1.0$ hours on the next calendar day ($T+1$) across each of the 171 canonical 0.25° grid cells along Maharashtra's coast, using strictly causal data available at time $T$.

### Technical Implementation
- **Grid Architecture:** 171 marine cells covering Lat $15.50^\circ\text{N} - 20.00^\circ\text{N}$, Lon $72.00^\circ\text{E} - 74.00^\circ\text{E}$ generated via `global_land_mask`.
- **Feature Assembly:** Assembles exactly 29 canonical features:
  - 10 GFW historical fleet dynamics features (lag 1, lag 2, lag 3, 7-day mean/max/std/frequency, 14-day mean, regional fleet total).
  - 10 Environmental features (wave height, wave period, wave direction sin/cos, swell height, current velocity, wind speed, missingness indicators).
  - 4 Spatial features (latitude, longitude, distance to coast, coastal indicator).
  - 5 Temporal features (day of year, month, day of week, cyclical sin/cos day of year).
- **Frozen Pipeline Execution:**
  - Imputation: `phase3_imputer.joblib` (training median replacement).
  - Scaling: `phase3_scaler.joblib` (`StandardScaler`).
  - Model: `phase3_xgboost_model.joblib` (`predict_proba()[:, 1]`).
  - Decision Threshold: $0.47$ (`phase3_threshold.json`).
- **Benchmark Performance:** Test PR-AUC: $0.4898$ (+29.2% relative gain over best historical baseline), Test F1: $0.4959$, Test ROC-AUC: $0.9387$.

### Key Code Artifacts
- **Inference Pipeline:** `backend/app/ml/inference.py` (`Phase4InferencePipeline`)
- **Model Artifacts:** `backend/app/ml/artifacts/phase3_*`
- **Scientific Report:** `docs/phase3_scientific_evaluation_report.md`
- **CLI Batch Tool:** `backend/scripts/run_predictions.py`

---

## Feature 5: Real-Time Marine Weather Ingestion (Open-Meteo)

### Functionality
Polls the Open-Meteo Marine and Forecast APIs to acquire real-time physical oceanographic parameters for all 171 grid cells.

### Technical Implementation
- **Batch Processing:** Groups grid cell centroids into batches of 40 coordinate pairs to respect external API URL length limits.
- **Parameter Extraction:** Retrieves `wave_height`, `wave_period`, `wave_direction`, `swell_wave_height` (from Marine API) and `wind_speed_10m` (from Forecast API).
- **In-Memory Caching:** Caches environmental results for 15 minutes (`900` seconds) in `Phase4InferencePipeline._cached_env_df` to prevent rate-limiting.
- **Graceful Degradation:** If live Open-Meteo endpoints fail or time out, automatically falls back to representative real observations in `historical_full_year_2023.parquet` and flags the status as `DEMO_MODE`.

### Key Code Artifacts
- **Backend Implementation:** `backend/app/ml/inference.py` (`_fetch_current_env`, lines 153–232)
- **Base Provider:** `backend/app/services/ingestion/providers.py` (`OpenMeteoMarineProvider`)

---

## Feature 6: Source Freshness & Provenance Tracking (HUD)

### Functionality
Audits and surfaces the operational health, real observation timestamps, expiration dates, and latency (in minutes or days) across all authoritative feeds, displayed in an intuitive frontend Heads-Up Display (HUD).

### Technical Implementation
- **Observation-Based Auditing:** `SourceFreshnessTracker` inspects actual `data_timestamp` and `valid_until` columns in the database rather than trusting `retrieved_at`.
- **Status Classification:**
  - `LIVE`: Current time $\le$ validity date (or within latency threshold).
  - `STALE`: Advisory has passed its validity date.
  - `CACHED_HISTORICAL`: Applied to GFW AIS data due to inherent multi-day publication delay.
  - `UNAVAILABLE`: Zero records found in database or API error.
- **Provenance Assembly:** Embeds source freshness dictionaries into `/api/v1/sources/freshness` and `/api/v1/map/summary`.

### Key Code Artifacts
- **Backend Service:** `backend/app/services/freshness/source_tracker.py` (`SourceFreshnessTracker`)
- **API Endpoint:** `GET /api/v1/sources/freshness` (`backend/app/api/v1/sources.py`)
- **Frontend Component:** `frontend/src/components/FreshnessHUD.tsx` (`FreshnessHUD`)

---

## Feature 7: Bilingual Fisherman-First Interactive Marine Map (Leaflet)

### Functionality
Provides a responsive, high-contrast cartographic interface displaying the 0.25° prediction grid, INCOIS PFZ targets, coastal landing centres, and safety banners, fully translated into Marathi and English.

### Technical Implementation
- **Leaflet Integration:** Mounts an interactive map centered on coastal Maharashtra (`[17.85, 72.85]`, zoom: 7) using standard OpenStreetMap tiles.
- **Dynamic Prediction Grid Overlay:** Renders 171 rectangles (`L.rectangle`):
  - High Apparent Fishing Probability ($\ge 0.47$): Bright Cyan (`#00e5ff`, fill opacity 0.55).
  - Moderate Probability ($0.20 - 0.46$): Ocean Blue (`#1976d2`, fill opacity 0.35).
  - Low/No Activity: Dark Navy (`#0d2238`, fill opacity 0.15).
- **PFZ Markers:** Renders high-visibility green circle markers (`#00e676`) accompanied by 4 km dashed radius rings.
- **Landing Centre Anchors:** Renders amber harbor icons for major fishing ports (Sassoon Dock, Versova, Arnala, Mirkarwada, Malvan).
- **Interactive Inspection Modal:** Clicking any grid cell opens an inspection modal displaying cell ID, coordinates, distance to coast, coastal classification, wind/wave values, and probability.
- **Bilingual i18n:** Instant client-side language switching between English and Marathi via `isMarathi` toggle in `App.tsx`.

### Key Code Artifacts
- **Frontend Map Component:** `frontend/src/map/MarineMap.tsx`
- **Root Layout:** `frontend/src/App.tsx`
- **Translations:** `frontend/src/i18n/mr.ts` and `frontend/src/i18n/en.ts`

---

## Feature 8: Automated Ingestion Daemon & Batch Scheduling Engine

### Functionality
Runs as an independent long-running background daemon (`matsya_ingestion` container) executing scheduled ETL jobs across providers with complete fault isolation.

### Technical Implementation
- **Async Scheduling Loop:** `backend/scripts/run_ingestion.py` executes an async event loop tracking the `last_run` timestamp for each independent provider.
- **Configurable Intervals (`backend/app/core/config.py`):**
  - INCOIS PFZ: Every 24 hours (`1440` minutes).
  - IMD Marine Warnings: Every 4 hours (`240` minutes).
  - Open-Meteo Marine: Every 1 hour (`60` minutes).
  - GFW AIS Context: Every 7 days (`10080` minutes).
  - Predictions Batch: Every 6 hours (`360` minutes).
- **Fault Isolation:** If an individual provider throws an exception (e.g., INCOIS website redirect), `IngestionRunner` traps the error, logs structured diagnostics, and ensures the remaining jobs continue running without crashing the daemon process.

### Key Code Artifacts
- **CLI & Daemon Entry Point:** `backend/scripts/run_ingestion.py` (`daemon_loop`)
- **Orchestrator Service:** `backend/app/services/ingestion/ingestion_runner.py` (`IngestionRunner`)
- **Docker Service:** `ingestion` service in `docker-compose.yml`

---

# 9. Security Analysis

This document provides a comprehensive security review of the MatsyaAI Maharashtra codebase, evaluating authentication mechanisms, authorization boundaries, input sanitization, data protection, secret handling, and vulnerability mitigations.

---

## 9.1 Security Architecture Overview

```mermaid
flowchart TD
    subgraph ClientZone["Client Zone (Browser / Mobile)"]
        User["Artisanal / Commercial Fishermen"]
    end

    subgraph BoundaryZone["Network & Boundary Protection"]
        CORS["CORS Middleware<br/>(Allowed Origins Whitelist)"]
        Proxy["Vite Dev Proxy / Reverse Proxy"]
    end

    subgraph AppZone["FastAPI Application Boundary"]
        Validation["Pydantic Schema Validation<br/>(Type & Range Enforcement)"]
        DMS_Sanitizer["DMS Geodetic String Sanitizer<br/>(Regex Bounds Checking)"]
        PDF_Validator["PDF Header Magic Byte Verification<br/>(%PDF-1.x Checking)"]
    end

    subgraph ServiceZone["Backend Execution & Ingestion"]
        Daemon["Isolated Ingestion Daemon"]
        SafetyGate["SafetyGate Invariant Guard<br/>(Zero-Harm Sea Safety Enforcement)"]
    end

    subgraph PersistenceZone["Database & Persistence Boundary"]
        ORM["SQLAlchemy 2.0 ORM<br/>(Parameterized Queries - No Raw Concatenation)"]
        Postgres[(PostgreSQL 16 + PostGIS 3.4)]
    end

    User --> CORS
    CORS --> Proxy
    Proxy --> Validation
    Validation --> DMS_Sanitizer & PDF_Validator
    DMS_Sanitizer & PDF_Validator --> Daemon
    Daemon --> SafetyGate
    SafetyGate --> ORM
    ORM --> Postgres
```

---

## 9.2 Authentication & Authorization Analysis

### Public Access Architecture (Zero-Friction for Fishers)
- **Design Decision:** The fisherman-facing endpoints (`/api/v1/map/summary`, `/api/v1/health`, `/api/v1/pfz/latest`, `/api/v1/predictions/latest`, `/api/v1/sources/freshness`) require **no end-user authentication or login wall**.
- **Security & Domain Rationale:** Fishermen operating from remote jetties or coastal villages at 04:30 IST often have basic smartphones, spotty 2G/3G connectivity, and low digital literacy. Enforcing authentication (JWT, OAuth, passwords) would create a catastrophic operational barrier during maritime emergencies. The application serves public government advisories and open predictive analytics that carry zero personally identifiable information (PII).

### Upstream Service Authentication & Credentials
- **Global Fishing Watch (GFW):** Protected via HTTP Bearer token authentication (`Authorization: Bearer <GFW_API_TOKEN>`). If the token is missing or expired, the backend automatically flags the provider as `UNAVAILABLE` without crashing or blocking the platform.
- **INCOIS TextData System:** Utilizes stateful HTTP session management. The provider dynamically requests a `JSESSIONID` cookie from `TextDataHome` and attaches it to subsequent requests.
- **Copernicus Marine Service (CMEMS):** Evaluated using environment-injected credentials (`COPERNICUS_MARINE_SERVICE_USERNAME`, `COPERNICUS_MARINE_SERVICE_PASSWORD`).
- **India Meteorological Department (IMD):** Ingests public bulletin PDFs via HTTPS without requiring API keys.

---

## 9.3 Input Validation & Defensive Data Ingestion

### 1. Pydantic Runtime Validation
- All incoming and outgoing data payloads are strictly validated against Pydantic schemas (`BaseModel` subclasses in `backend/app/schemas/` and `backend/app/api/v1/`).
- Prevents mass-assignment vulnerabilities, validates types, and rejects malformed payloads before execution reaches business logic.

### 2. DMS Geodetic Sanitization
- In `backend/app/services/ingestion/incois_pfz_provider.py` (`parse_dms`):
  - Strips non-alphanumeric and unexpected punctuation using regular expressions (`re.sub(r'[^0-9NSEWnsew\. ]', ' ', clean_str)`).
  - Enforces strict numeric ranges: Latitude must lie within $[-90.0, 90.0]$, Longitude within $[-180.0, 180.0]$.
  - Enforces Maharashtra coastal regional bounding box filters: Latitude $[10.0, 25.0]$, Longitude $[65.0, 80.0]$ to reject anomalous scraping errors.

### 3. PDF Ingestion Magic Byte Validation
- In `backend/app/services/ingestion/imd_marine_provider.py` (`_fetch_pdf_with_retry`):
  - Before parsing downloaded bytes, checks for PDF magic bytes:
    ```python
    if not content.startswith(b"%PDF"):
        raise ValueError("Downloaded content is not a valid PDF document.")
    ```
  - Prevents MIME-type confusion or server error HTML pages from being fed into the PDF deserializer.

---

## 9.4 Data Protection & SQL Injection Immunity

### Complete ORM Parameterization
- Across the entire backend codebase, **zero raw SQL string concatenation or f-string queries exist**.
- All database interactions use SQLAlchemy 2.0 type-safe expressions (`select()`, `update()`, `func.count()`) executed via `AsyncSession`.
- All query parameters (e.g., cell IDs, timestamps, hash digests) are bound using PostgreSQL binary parameter placeholders (`$1`, `$2`), rendering SQL injection attacks virtually impossible.

### Cross-Origin Resource Sharing (CORS) Protection
- Configured in `backend/app/main.py` via `CORSMiddleware`:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.CORS_ORIGINS,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
- Defaults to strictly whitelisted frontend hosts (`http://localhost:5173`, `http://localhost:3000`), preventing unauthorized cross-origin browser requests from external domains.

---

## 9.5 Environment Variable & Secret Management

- **No Hardcoded Credentials:** The repository adheres strictly to 12-Factor App principles. Passwords, connection strings, and API keys are loaded exclusively from environment variables or a local `.env` file via `pydantic-settings`.
- **Git Protection:** `.gitignore` explicitly excludes `.env`, `*.joblib`, raw data dumps, and credentials:
  ```gitignore
  .env
  .env.*
  *.pem
  *.key
  ```
- **Template Safety:** `.env.example` provides empty placeholders and non-sensitive local defaults (`matsya:matsya_dev@db:5432/matsya_ai`).
- **Safe Degradation:** If external API tokens (`GFW_API_TOKEN`, `IMD_API_KEY`) are omitted, the application logs a clean warning and degrades gracefully to `UNAVAILABLE` or `DEMO_MODE` without exposing stack traces or crashing.

---

## 9.6 Vulnerability & Threat Assessment (OWASP Top 10 Evaluation)

| OWASP Threat Category | Risk Level in MatsyaAI | Technical Assessment & Mitigation |
| :--- | :--- | :--- |
| **A01: Broken Access Control** | Low | All endpoints are intentionally public read-only; database mutations are restricted to internal backend processes and daemons. |
| **A02: Cryptographic Failures** | Low | Internal services communicate over private Docker bridge networks; external integrations use HTTPS (TLS 1.2/1.3); deduplication uses cryptographically secure SHA-256. |
| **A03: Injection (SQL / Command)** | Very Low | Full SQLAlchemy 2.0 ORM parameterization; no shell command execution within request lifecycles. |
| **A04: Insecure Design (Safety)** | **Mitigated** | Traditional risk: ML predicting "safe to fish" in a cyclone. **Mitigated by Design:** `SafetyGate` completely decouples ML from safety decisions; absence of warning data defaults to `NO_WARNING_DATA`. |
| **A05: Security Misconfiguration** | Low | Docker Compose limits database exposure to standard ports; detailed debug stack traces are restricted to development mode. |
| **A06: Vulnerable Dependencies** | Low | Dependencies pinned to modern, active releases (FastAPI 0.115, Pydantic 2.9, SQLAlchemy 2.0, Vite 8, Leaflet 1.9). |
| **A07: Identification & Auth Failures** | N/A | Public application by design; no user credential storage or session hijacking vectors. |
| **A08: Software & Data Integrity Failures** | Low | Model artifacts (`.joblib`, `.json`) are stored locally within the application package and loaded using trusted local paths. |
| **A09: Security Logging & Monitoring** | Low | Implements structured key-value logging (`structlog`), tracking startup, shutdown, provider failures, and deduplication events. |
| **A10: Server-Side Request Forgery (SSRF)** | Low | All outbound HTTP requests target hardcoded, immutable authoritative URLs (`IMD_MUMBAI_FISHERMAN_PDF_URL`, `TEXT_DATA_MAHARASHTRA_URL`). User input never controls outbound URLs. |

---

## 9.7 Denial of Service (DoS) & Upstream Outage Protection

1. **Request Timeouts:** All external HTTP requests executed via `httpx` and `urllib` enforce explicit timeouts (`REQUEST_TIMEOUT_SECONDS = 30` or `10s`). No outbound request can hang worker threads indefinitely.
2. **In-Memory Caching:** Open-Meteo marine and weather queries are cached in memory for 15 minutes (`900` seconds). High volumes of client map requests do not cause external API quota exhaustion or IP bans.
3. **Database Connection Pooling:** PostgreSQL connection pool limits (`pool_size=5`, `max_overflow=10`) prevent connection exhaustion attacks on the database engine.
4. **Resilient Retry Backoff:** Failed external calls execute exponential backoff ($2, 4, 8$ seconds) up to a maximum of 3 retries, preventing self-inflicted denial-of-service on government portals.

---

# 10. Installation and Execution Guide

This guide provides exact, step-by-step instructions for installing, configuring, running, and verifying the MatsyaAI Maharashtra platform across both containerized (Docker Compose) and bare-metal local development environments.

---

## 10.1 Environment Prerequisites

### Option A: Containerized Environment (Recommended)
- **Docker Engine:** Version `24.0.0` or higher
- **Docker Compose:** Version `2.20.0` or higher
- **Hardware:** Minimum 4 GB RAM, 2 CPU cores, 5 GB free disk space.
- *No local Python, Node.js, or PostgreSQL installations are required.*

### Option B: Bare-Metal Local Development
- **Operating System:** Linux (Ubuntu 22.04+), macOS (13+), or Windows 10/11 (with PowerShell 7+ or WSL2).
- **Python:** Version `3.12.x` (Python 3.12.4 verified).
- **Node.js & npm:** Node `v20.x` or `v22.x` (v22.16.0 verified), npm `v10.x`.
- **Database:** PostgreSQL `16.x` with **PostGIS `3.4.x`** extension installed and running.
- **Git:** Version `2.40+`.

---

## 10.2 Configuration: Environment Setup

Clone the repository and initialize the environment configuration file:

```bash
# 1. Clone the repository
git clone <repository-url>
cd Matsya_AI

# 2. Copy the environment template
cp .env.example .env
```

### Environment Variables Breakdown (`.env`)

| Variable | Description | Default / Example Value |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |
| `APP_VERSION` | Semantic application version | `0.1.0` |
| `POSTGRES_USER` | PostgreSQL superuser username | `matsya` |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password | `matsya_dev` |
| `POSTGRES_DB` | PostgreSQL database name | `matsya_ai` |
| `POSTGRES_HOST` | Database host name (`db` in Docker, `localhost` locally) | `db` |
| `POSTGRES_PORT` | Database port | `5432` |
| `DATABASE_URL` | AsyncPG connection string used by SQLAlchemy & Alembic | `postgresql+asyncpg://matsya:matsya_dev@db:5432/matsya_ai` |
| `BACKEND_HOST` | FastAPI bind address | `0.0.0.0` |
| `BACKEND_PORT` | FastAPI listening port | `8000` |
| `CORS_ORIGINS` | JSON array of whitelisted browser client origins | `["http://localhost:5173","http://localhost:3000"]` |
| `GFW_API_TOKEN` | Bearer token for Global Fishing Watch API (Optional) | `""` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## 10.3 Quick Start: Containerized Execution (Docker Compose)

Docker Compose provisions and connects all four platform services automatically.

```bash
# Build images and start all containers in detached mode
docker compose up --build -d

# Follow consolidated logs
docker compose logs -f
```

### Provisioned Services & Ports

| Service Name | Container Name | Internal Port | Host Port | Accessible URL |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** | `matsya_frontend` | 5173 | 5173 | [http://localhost:5173](http://localhost:5173) |
| **Backend** | `matsya_backend` | 8000 | 8000 | [http://localhost:8000](http://localhost:8000) |
| **Database** | `matsya_db` | 5432 | 5432 | `localhost:5432` |
| **Ingestion** | `matsya_ingestion` | N/A (Daemon) | N/A | Runs `run_ingestion.py --daemon` |

---

## 10.4 Manual Bare-Metal Installation (Step-by-Step)

If developing without Docker, follow these steps to initialize each component locally.

### Step 1: Database Setup (PostgreSQL + PostGIS)
Ensure PostgreSQL 16 is running, then create the database and enable PostGIS:

```bash
# Using psql as postgres admin
psql -U postgres -c "CREATE USER matsya WITH PASSWORD 'matsya_dev';"
psql -U postgres -c "CREATE DATABASE matsya_ai OWNER matsya;"
psql -U postgres -d matsya_ai -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Update your local `.env` file to point to `localhost`:
```ini
DATABASE_URL=postgresql+asyncpg://matsya:matsya_dev@localhost:5432/matsya_ai
```

### Step 2: Backend Virtual Environment & Migrations

```bash
# 1. Create a Python 3.12 virtual environment in the project root
python -m venv .venv

# 2. Activate virtual environment
# On Linux / macOS:
source .venv/bin/activate
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install pinned backend dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt

# 4. Run Alembic database migrations to head revision
cd backend
alembic upgrade head
cd ..

# 5. Seed initial Maharashtra landing centres
python backend/scripts/seed_landing_centres.py
```

### Step 3: Seed Initial Ingestion Data (Optional but Recommended)

```bash
# Run one-shot ingestion for all live sources
python backend/scripts/run_ingestion.py --source all

# Run initial batch predictions
python backend/scripts/run_predictions.py
```

### Step 4: Run Backend Server

```bash
# From project root with virtual environment activated:
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend API is now accessible at [http://localhost:8000](http://localhost:8000), and interactive Swagger documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Step 5: Frontend Installation & Execution

```bash
# In a separate terminal, navigate to the frontend directory:
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
The frontend is now accessible at [http://localhost:5173](http://localhost:5173).

---

## 10.5 Verification & Health Inspection

Verify that the system is fully operational using standard CLI commands:

### 1. Backend Health Check
```bash
curl -X GET http://localhost:8000/api/v1/health
```
**Expected Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "database": "connected",
  "timestamp": "2026-11-13T14:30:00+00:00"
}
```

### 2. PostGIS Extension Verification
```bash
# If using Docker:
docker compose exec db psql -U matsya -d matsya_ai -c "SELECT PostGIS_Version();"

# Expected output:
# 3.4.x ...
```

### 3. Consolidated Map Summary Inspection
```bash
curl -X GET http://localhost:8000/api/v1/map/summary
```
Verify that the JSON response contains `metadata`, `marine_safety`, `predictions`, `pfz_advisory`, and `source_freshness` keys.

---

## 10.6 Troubleshooting & Common Issues

| Issue / Error Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'backend'` | Python execution without project root on `PYTHONPATH`. | Run commands from the project root directory (`D:\Matsya_AI`), or execute with `python -m backend.scripts.<script_name>`. |
| `asyncpg.exceptions.InvalidCatalogNameError: database "matsya_ai" does not exist` | Database not yet created in PostgreSQL. | Execute `CREATE DATABASE matsya_ai;` via `psql`. If using Docker, verify `POSTGRES_DB=matsya_ai` in `.env`. |
| `function postgis_version() does not exist` | PostGIS extension not initialized. | Run `CREATE EXTENSION IF NOT EXISTS postgis;` in the target database. Ensure you are using the `postgis/postgis` image, not plain `postgres`. |
| `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)` | PostgreSQL service is stopped or port 5432 is blocked. | Verify database status with `docker compose ps` or `Get-Service postgresql*`. Check for port conflicts on 5432. |
| Frontend displays `Failed to load map data` | Backend is unreachable or proxy misconfigured. | Verify backend is running on port 8000. In `frontend/vite.config.ts`, verify proxy target matches backend host. Click `Load Real Demo Cache` on UI for offline fallback. |
| `tsc is not recognized` during `npm run build` | `node_modules` not installed on host machine. | Run `npm install` inside the `frontend/` directory before executing `npm run build`. |

---

# 11. Testing, Performance, and Observability

This document details the testing architecture, unit and integration test suites, verified test execution outcomes, performance optimizations, error-handling mechanisms, and known operational limitations of the MatsyaAI Maharashtra platform.

---

## 11.1 Testing Frameworks & Architecture

The testing architecture spans two independent testing frameworks tailored to their respective technology stacks:

```mermaid
flowchart LR
    subgraph BackendTests["Backend Test Suite (Pytest)"]
        direction TB
        T_DB["test_database.py"]
        T_IMD["test_imd_marine.py"]
        T_PFZ["test_incois_pfz.py"]
        T_Gate["test_safety_gate_phase6.py"]
        T_Fresh["test_source_freshness.py"]
        T_Leak["test_phase3_baselines_and_leakage.py"]
        T_Prov["test_prediction_provenance.py"]
        T_Batch["test_prediction_batch.py"]
    end

    subgraph FrontendTests["Frontend Test Suite (Vitest)"]
        direction TB
        F_App["App.test.tsx"]
        F_HUD["FreshnessHUD rendering"]
    end

    subgraph ExecEnv["Execution Harness"]
        PytestHarness["Pytest 8.3.3 + Pytest-Asyncio 0.24.0<br/>(HTTPX Async TestClient)"]
        VitestHarness["Vitest 5.0.1 + Testing Library<br/>(JSDOM 29.1.1 Environment)"]
    end

    BackendTests --> PytestHarness
    FrontendTests --> VitestHarness
```

---

## 11.2 Backend Unit & Integration Test Suites

The backend includes **15 dedicated test modules** in `backend/tests/`:

| Test Module | Scope & Focus | Verification Invariants Tested |
| :--- | :--- | :--- |
| `test_database.py` | Database & PostGIS | Engine connectivity, session lifecycle, PostGIS geometry creation and distance calculations. |
| `test_health.py` | Health Check Router | `/api/v1/health` response formatting, database connectivity ping handling. |
| `test_imd_marine.py` | IMD Ingestion Provider | PyPDF2 spatial visitor line extraction, font kerning regex cleanup, date/validity parsing, and `NORMAL`/`WARNING`/`SEVERE` severity classification against genuine historical PDF fixture `fixtures/sample_imd_fisherman.pdf`. |
| `test_incois_pfz.py` | INCOIS PFZ Provider | Session cookie acquisition, HTML table scraping, robust DMS string parsing, geographic bounds filtering, SHA-256 deduplication, and stale marking. |
| `test_safety_gate_phase6.py` | Safety Gate Subsystem | Priority hierarchy: `UNSAFE` on severe warnings, `CAUTION` on high waves/winds, `SAFE_CONFIRMED` only with active bulletin confirmation, and `NO_WARNING_DATA` on stale/missing feeds. |
| `test_source_freshness.py` | Freshness Engine | True observation timestamp auditing (ensuring freshness is calculated from observation dates, never `retrieved_at` alone). |
| `test_phase3_baselines_and_leakage.py` | Causal ML & Baselines | Verifies that feature calculations at $T$ use only data $\le T$, split disjointness, chronological monotonicity, and baseline reproducibility. |
| `test_phase4_integration.py` | Inference Serving | End-to-end prediction generation across 171 canonical cells, feature alignment, and response schema adherence. |
| `test_prediction_provenance.py` | Provenance Auditing | Metadata contracts, ensuring model disclaimers and source status are embedded in prediction outputs. |
| `test_prediction_batch.py` | Batch Execution | Ingestion runner batch execution and PostgreSQL persistence. |
| `test_features.py` & `test_feature_builder.py` | Feature Engineering | Haversine distance calculations and nearest-neighbor canonical cell regridding. |
| `test_ingestion.py` & `test_ingestion_scheduler.py` | Ingestion Orchestration | Runner execution, provider fault isolation, and scheduling intervals. |
| `test_predictions_endpoint.py` | Predictions Router | HTTP GET contract validation for `/api/v1/predictions`. |

---

## 11.3 Verified Test Results & Regression Sign-Off

As documented in `FINAL_READINESS_REPORT.md`:

### 1. Backend Regression Suite
- **Command:** `docker compose exec backend pytest`
- **Total Tests:** **126 passed**, 0 failed, 0 skipped.
- **Result:** **100% PASS**. All database models, ingestion parsers, safety gate rules, and inference endpoints passed clean regression verification.

### 2. Frontend Test Suite
- **Command:** `npm run test` (executed via Vitest + JSDOM)
- **Result:** **0 passed, 0 failed, 9 skipped**.
- **Root Cause Analysis:** The 9 skipped tests in `frontend/src/App.test.tsx` are due to a documented limitation of the headless **JSDOM** environment: JSDOM does not implement native SVG/Canvas DOM rendering APIs required by the Leaflet mapping engine (`L.map`, `L.tileLayer`). In standard production CI, Leaflet component testing requires headless browser automation (Playwright or Puppeteer) or mocked Leaflet canvas modules.
- **Frontend Production Build:** `npm run build` executed via `tsc -b && vite build` completed successfully with **0 TypeScript errors** in **230 milliseconds**.

---

## 11.4 Performance Optimizations

### 1. In-Memory Environmental Caching
- **Implementation:** `Phase4InferencePipeline._cached_env_df` in `backend/app/ml/inference.py`.
- **Mechanism:** Live Open-Meteo marine and weather query results are cached in memory with a **15-minute (900-second) Time-to-Live (TTL)**.
- **Impact:** Eliminates redundant external HTTP requests for incoming client map requests, protects against external API rate-limiting, and reduces endpoint response latency from ~1,800 ms down to under **25 milliseconds**.

### 2. Vectorized Causal Data Processing & Columnar Scans
- **Implementation:** Historical GFW effort records (59,850 observations) are stored in Apache Parquet format (`historical_full_year_2023.parquet`).
- **Mechanism:** PyArrow columnar reader loads and scans 350 days of fleet records across 171 cells in under **120 milliseconds**, while NumPy array operations compute 7-day and 14-day rolling window statistics in sub-second time.

### 3. Spatial Batching & Bounding Box Filtering
- **Implementation:** `_fetch_current_env` batches coordinate pairs into chunks of 40 centroids.
- **Mechanism:** Reduces 171 individual HTTP round-trips down to 5 batched HTTP requests.

### 4. Asynchronous Database Connection Pooling
- **Implementation:** `create_async_engine` in `backend/app/core/database.py`.
- **Parameters:** `pool_size = 5`, `max_overflow = 10`, `pool_pre_ping = True`.
- **Impact:** Reuses existing PostgreSQL socket connections across concurrent ASGI requests, eliminating TCP connection overhead.

---

## 11.5 Error Handling & Fault Isolation

```mermaid
flowchart TD
    subgraph IngestionErrors["Ingestion Subsystem Fault Isolation"]
        E1["External Provider Exception<br/>(e.g., INCOIS Redirect / 503)"] --> Trap["IngestionRunner Traps Exception"]
        Trap --> Log["Log Structured Diagnostic Trace"]
        Trap --> Retain["Retain Last Known Valid Records in DB"]
        Retain --> StaleMark["Mark Expired Records is_stale=True"]
        StaleMark --> Continue["Daemon Continues Remaining Jobs"]
    end

    subgraph SafetyErrors["Safety Subsystem Fault Isolation"]
        E2["Warning Feed Unavailable or Stale"] --> SafeTrap["SafetyGate Traps Missing Feed"]
        SafeTrap --> Fallback["Default to NO_WARNING_DATA"]
        Fallback --> UI_Grey["UI Renders Neutral Slate-Grey Banner"]
        UI_Grey --> Advise["Fisher Prompted to Check Physical Port Signals"]
    end
```

---

## 11.6 Logging, Diagnostics & Observability

- **Structured Logging:** Utilizes `structlog` (`backend/app/core/logging.py`) with ISO-8601 UTC timestamps, contextual key-values (`app`, `version`, `environment`), and log levels (`INFO`, `WARNING`, `ERROR`).
- **Audit Trails:** Every ingestion run records `retrieved_at`, `source_publication_time`, and deterministic content hashes (`hash_id`), establishing complete forensic reproducibility.
- **Liveness Probes:** The `/api/v1/health` endpoint serves as a Docker and Kubernetes liveness/readiness probe, verifying database connectivity on every check.

---

## 11.7 Known System Limitations

1. **Host-Level Tooling Dependency:** Executing tests locally without Docker requires activating a virtual environment containing dependencies from `backend/requirements.txt` and running `npm install` inside `frontend/`.
2. **JSDOM Leaflet Testing Limitation:** Vitest component tests for `MarineMap.tsx` are skipped in JSDOM due to missing browser canvas primitives; requires Playwright for end-to-end UI automation.
3. **GFW Live Stream Latency:** Global Fishing Watch AIS data has an inherent multi-day archival publication latency; GFW context is strictly labeled `CACHED_HISTORICAL` or `UNAVAILABLE` when a live token is not provided.
4. **Organic Prediction Batch Generation:** Newly deployed instances require running `python backend/scripts/run_predictions.py` or waiting for the ingestion scheduler daemon to persist initial prediction batches before `/api/v1/predictions` returns populated rows.

---

# 12. Technical Strengths and Improvement Recommendations

This document provides a senior architectural evaluation of the MatsyaAI Maharashtra codebase, separating verified technical achievements from identified technical debt, and outlines a prioritized engineering roadmap.

---

## 12.1 Code & Architectural Strengths

### 1. Zero-Harm Safety-First Architectural Decoupling
- **Strength:** Unlike conventional commercial fisheries platforms that merge "fish hot spots" with "safe sailing" flags, MatsyaAI enforces an **independent, immutable Safety Gate**.
- **Impact:** Machine learning predictions **never** dictate sea safety. If an active severe warning is issued by IMD, even a zone with 99% predicted vessel effort is overridden to `UNSAFE`. If warning feeds are missing or stale, the system defaults to `NO_WARNING_DATA`, explicitly preventing the fatal mistake of assuming "no active warning equals calm sea".

### 2. Methodological Rigor in Machine Learning (Phase 3 Causal Formulation)
- **Strength:** Solves the pervasive data leakage problem in time-series fisheries informatics.
- **Impact:** Rather than evaluating same-day correlations ($T \to T$), the pipeline predicts next-calendar-day ($T+1$) effort using information available strictly $\le T$. Models were benchmarked against three distinct domain baselines (Persistence, Trailing 7-Day, Spatial Prior) on a strictly chronological split (Jan–Aug Train, Aug–Oct Val, Oct–Dec Test) on full-year 2023 data. XGBoost proved its predictive value decisively (+29.2% PR-AUC gain over the strongest baseline).

### 3. Production-Grade Ingestion Parsers & Resilient Web Scraping
- **Strength:** Elegant handling of notoriously difficult Indian government data feeds:
  - **PyPDF2 Spatial Visitor:** Extracts text using physical $(x, y)$ coordinates to solve font kerning separation artifacts in IMD bulletins.
  - **Stateful Session Handshake:** Manages `JSESSIONID` cookies to scrape INCOIS HTML tables while rejecting generic redirect fallbacks.
  - **Idempotent Ingestion:** Cryptographic SHA-256 batch hashes prevent duplicate record accumulation across periodic daemon cycles.

### 4. True Observation-Based Data Freshness Auditing
- **Strength:** The `SourceFreshnessTracker` calculates data freshness from actual meteorological bulletin publication and validity timestamps, **never** trusting the download timestamp (`retrieved_at`) alone.
- **Impact:** Completely eliminates "false freshness" illusions where stale data is downloaded today and erroneously displayed as live.

### 5. Local Language Inclusivity (Bilingual English & Marathi)
- **Strength:** First-class internationalization (`i18n`) for Marathi (`मराठी`), the primary language of Maharashtra's coastal fishing communities, covering navigation, warnings, metrics, and scientific disclaimers.

---

## 12.2 Verified Technical Debt & Areas for Improvement

| Area | Verified Codebase Finding | Technical Risk / Impact | Recommended Remediation |
| :--- | :--- | :--- | :--- |
| **Frontend Testing** | 9 tests in `App.test.tsx` are skipped in JSDOM due to Leaflet canvas/SVG API limitations. | UI regressions and component layout breaks are not caught in headless unit test runs. | Introduce Playwright or Puppeteer for headless browser end-to-end integration testing, or mock Leaflet canvas primitives. |
| **Prediction Batch Persistence** | When starting with an empty database, `/api/v1/predictions` returns an empty array until the ingestion daemon or `run_predictions.py` is executed. | Fresh deployments show zero prediction cells until the batch script runs. | Add an automatic database seed check on startup (`lifespan` in `main.py`) that executes an initial inference batch if `predictions` row count is zero. |
| **GFW Production Token** | `GFW_API_TOKEN` is currently unset in default configurations, causing GFW to report `UNAVAILABLE`. | Real-time trailing AIS fleet dynamics rely on cached 2023 Parquet files rather than live GFW streams. | Register an official Global Fishing Watch API partnership token and inject it into production CI/CD secrets. |
| **Single-Process Scheduling** | The ingestion daemon in `run_ingestion.py` runs an in-memory `asyncio.sleep` scheduling loop. | If the ingestion container crashes or restarts, state is maintained only via database query; no distributed job management. | Migrate long-term scheduling to Celery with Redis broker, or use cloud-native cron runners (e.g., Kubernetes CronJobs / Google Cloud Run Jobs). |
| **Offline PWA Capabilities** | The React frontend is a standard web application requiring network access for initial bundle load. | Fishermen at sea lose cellular connectivity 15–25 km offshore. | Implement a Progressive Web App (PWA) service worker with CacheStorage to enable full offline map caching for pre-departure vessel navigation. |

---

## 12.3 Prioritized Engineering Roadmap

```mermaid
flowchart TD
    subgraph NearTerm["Phase 1: Immediate Enhancements (1-2 Months)"]
        N1["Playwright End-to-End Test Suite for Leaflet UI"]
        N2["Automatic Database Seeding on FastAPI Startup"]
        N3["Leaflet Canvas Mocking for Vitest Unit Suite"]
    end

    subgraph MediumTerm["Phase 2: Platform Maturation (3-6 Months)"]
        M1["Progressive Web App (PWA) Offline Tile Caching"]
        M2["Production GFW API Live Token Integration"]
        M3["Celery + Redis Distributed Ingestion Worker"]
        M4["SMS / WhatsApp / IVR Alert Gateway for Non-Smartphones"]
    end

    subgraph LongTerm["Phase 3: Scale & Multi-State Expansion (6-12 Months)"]
        L1["Expand Grid to Gujarat, Goa, Karnataka, and Kerala Coasts"]
        L2["Copernicus CMEMS NetCDF Direct Ingestion Pipeline"]
        L3["Vessel GPS Tracker Integration (NavIC / AIS Receiver Feeds)"]
        L4["High-Resolution 0.1° XGBoost Retraining with Bathymetry Features"]
    end

    NearTerm --> MediumTerm --> LongTerm
```

---

## 12.4 Comprehensive Project Summary

### 1. Technology Stack Summary
- **Frontend:** React 19, TypeScript, Leaflet, Vite, Oxlint.
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, Structlog.
- **Database & Spatial:** PostgreSQL 16, PostGIS 3.4, SQLAlchemy (Asyncio), AsyncPG, GeoAlchemy2, Alembic.
- **Machine Learning & Data Science:** XGBoost 3.2.0, Scikit-Learn 1.6.1, Pandas, NumPy, PyArrow (Parquet), Global-Land-Mask.
- **Ingestion & Parsing:** BeautifulSoup4, PyPDF2 (spatial visitor extraction), HTTPX.
- **DevOps & Containerization:** Docker, Docker Compose multi-service architecture.

### 2. Major Algorithms & Techniques
- **Geodesic Math:** Haversine Great-Circle Distance, DMS-to-Decimal degree conversions.
- **Computational Geometry:** Point-in-polygon marine masking via `global_land_mask`.
- **Document Intelligence:** 2D Cartesian transformation matrix line sorting and regex kerning reconstruction.
- **Causal Machine Learning:** Strict chronological train/validation/test splits ($T \to T+1$), 29 canonical lag and cyclical features, probability threshold tuning ($0.47$).
- **Safety Logic:** Multi-tier deterministic rule hierarchy overriding ML models during severe meteorological events.

### 3. Key Architectural Decisions
- **Decoupled Safety Governance:** Independent Safety Gate ensures zero accidental harm from ML recommendations.
- **True Timestamp Auditing:** Data freshness grounded in real observation/validity timestamps.
- **Async Non-Blocking Core:** Asynchronous database and HTTP pipelines deliver sub-25 ms cached API response times.
- **Idempotent Ingestion:** Cryptographic SHA-256 deduplication guarantees zero data duplication.

### 4. Demonstrable Engineering Competencies
- **Senior Software Architecture:** Decoupled micro-services, fault-isolated background daemons, and clean separation of concerns.
- **Full-Stack Mastery:** Modern reactive TypeScript frontend integrated with high-throughput asynchronous Python backends.
- **Data Engineering Rigor:** Resilient PDF scraping, stateful session web scraping, and robust PostGIS spatial indexing.
- **Scientific Integrity:** Defeating data leakage through rigorous causal lookbacks, baseline benchmarking, and automated regression testing.