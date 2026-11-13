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
