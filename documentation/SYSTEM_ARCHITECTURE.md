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
