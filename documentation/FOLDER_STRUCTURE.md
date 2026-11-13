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
