# 🐟 MatsyaAI Maharashtra

**Marine Decision-Support Platform for Maharashtra Fishermen**

MatsyaAI Maharashtra is a fisherman-first application that combines INCOIS oceanographic data, IMD weather warnings, and geospatial intelligence to answer three simple questions:

1. **Can I safely go fishing today?**
2. **Where are the best potential fishing zones today?**
3. **How do I navigate to the selected zone?**

> ⚠️ **Milestone 1 — Project Scaffolding**
> This is the foundation release. The frontend, backend, and database are wired together with health-check connectivity. Real data integration begins in Milestone 3.

---

## Architecture

```
Official Data Sources (INCOIS, IMD, Fisheries Dept)
        ↓
  Data Ingestion Workers
        ↓
  Validation + Normalization
        ↓
  PostgreSQL + PostGIS
        ↓
  Feature Engineering → Prediction Engine
        ↓
  Safety Engine + Recommendation Engine
        ↓
  FastAPI Backend
        ↓
  React Frontend → Fisherman
```

---

## Prerequisites

- [Docker](https://www.docker.com/) (v24+)
- [Docker Compose](https://docs.docker.com/compose/) (v2+)

That's it. Everything runs in containers.

---

## Quick Start

### 1. Clone & configure

```bash
git clone <repo-url>
cd matsya-ai

# Create environment file from template
cp .env.example .env
```

### 2. Start all services

```bash
docker compose up --build
```

This starts four services:

| Service | Port | URL |
|---------|------|-----|
| **Frontend** (React + Vite) | 5173 | http://localhost:5173 |
| **Backend** (FastAPI) | 8000 | http://localhost:8000 |
| **Database** (PostgreSQL + PostGIS) | 5432 | `postgresql://matsya:matsya_dev@localhost:5432/matsya_ai` |
| **Ingestion** (background data collector) | — | — |

### 3. Create the database tables (first run only)

A fresh database has no tables, so the ingestion worker will log
`relation "..." does not exist` errors until migrations are applied:

```bash
docker compose exec backend sh -c "cd /app/backend && PYTHONPATH=/app alembic upgrade head"
docker compose restart ingestion
```

`PYTHONPATH=/app` is required because `alembic/env.py` imports `backend.app...`.
The tables persist in the `pgdata` volume, so this is only needed again after
`docker compose down -v`.

### 4. Verify

```bash
# Backend health check
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status":"healthy","version":"0.1.0","environment":"development","database":"connected","timestamp":"..."}

# Backend API docs
open http://localhost:8000/docs

# Frontend
open http://localhost:5173

# PostGIS verification
docker compose exec db psql -U matsya -d matsya_ai -c "SELECT PostGIS_Version();"
```

---

## Project Structure

```
Matsya_AI/
│
├── frontend/                   # React 19 + Vite + TypeScript + Leaflet PWA
│   ├── src/
│   │   ├── components/         # Shared UI & chart components
│   │   ├── pages/              # Dashboard pages (Overview, Map, Safety, Weather, Districts, Navigation)
│   │   ├── expedition/         # Offline Expedition Mode feature module
│   │   │   ├── components/     # HUD, Plan, Download, Catch Log, Compass, Sync UI
│   │   │   ├── engine/         # Geodesy, navigation engine, safety evaluator, voyage recorder, simulation
│   │   │   ├── services/       # IndexedDB, sync, basemap/bathymetry/MPA layers, API
│   │   │   ├── hooks/          # GPS & device compass hooks
│   │   │   ├── types/          # Expedition TypeScript contracts
│   │   │   └── __tests__/      # Expedition unit & integration tests
│   │   ├── map/                # MarineMap Leaflet layers (activity, PFZ, oceanography, MPA, GEBCO)
│   │   ├── services/           # Backend API client
│   │   ├── lib/                # App state, districts, routing, formatting
│   │   ├── types/              # API TypeScript definitions
│   │   └── i18n/               # Bilingual dictionaries (EN + MR)
│   ├── public/
│   └── package.json
│
├── backend/                    # Python FastAPI & PostGIS API
│   ├── app/
│   │   ├── api/v1/             # REST routers (health, map, pfz, predictions, sources, marine, expedition)
│   │   ├── core/               # Config, database, logging, canonical landing centres
│   │   ├── models/             # SQLAlchemy/GeoAlchemy2 ORM models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Ingestion workers, freshness tracker, expedition services
│   │   └── ml/                 # Frozen Phase 3 XGBoost inference & SafetyGate
│   ├── alembic/                # Database migrations
│   ├── static/offline/         # Generated GEBCO contours, VIIRS Chl-a, MUR SST, currents, Malvan MPA
│   ├── scripts/                # Backend CLI tools (grid, ingestion, predictions, bathymetry)
│   ├── tests/                  # Pytest suite
│   └── requirements.txt
│
├── data_pipeline/              # Live oceanographic & safety data acquisition
│   ├── oceanography/           # Maharashtra coast oceanography pipeline (GEBCO, VIIRS, MUR SST, U/V, MPA, IMD)
│   ├── incois/                 # INCOIS PFZ documentation
│   ├── imd/                    # IMD warning documentation
│   └── fisheries/              # Fisheries department documentation
│
├── data/
│   └── snapshots/              # Baseline & sample API JSON snapshots for offline/local dev
│
├── ml/                         # ML training, causal features, baselines & leakage validation
│   ├── training/
│   ├── features/
│   ├── evaluation/
│   └── models/
│
├── database/
│   ├── migrations/
│   └── seeds/                  # Landing centre seed scripts
│
├── scripts/
│   ├── dev-server/             # Local Node dev API server (local_api_server.js)
│   └── dev-https/              # Local HTTPS dev cert generator
│
├── tools/
│   ├── diagnostics/            # Source probes, verification & debug scripts (+ captured_samples/)
│   └── docs-builder/           # Documentation HTML/PDF render helpers
│
├── docs/                       # Consolidated documentation
│   ├── architecture/           # System architecture, folder tree, DB design, Expedition audit
│   ├── api/                    # REST API specification
│   ├── guides/                 # Overview, installation, features, testing
│   ├── science/                # Algorithms, data sources, Phase 3 ML report
│   ├── security/               # Security analysis
│   └── reports/                # Readiness & consolidated technical reports
│
├── docker/                     # Dockerfiles (backend & frontend)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Development

### Running without Docker

**Local Dev Backend (Node, no Postgres setup needed):**
```bash
node scripts/dev-server/local_api_server.js
```

**Or Full FastAPI Backend:**
```bash
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

**Acquire Live Maharashtra Oceanographic Layers:**
```bash
node data_pipeline/oceanography/acquire_maharashtra_ocean_data.mjs
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Database:**
You'll need PostgreSQL 16+ with PostGIS 3.4+ running locally.

### Running Tests

```bash
# Backend tests
docker compose exec backend pytest

# Or locally
cd backend && pytest
```

---

## Offline Expedition Mode

Switch to **🧭 Expedition** in the header (or open `http://localhost:5173/#expedition`).

1. **Plan** (needs signal): pick a departure landing centre and a destination — an INCOIS PFZ
   point or any tapped map point. The server builds an *expedition package*
   (`POST /api/v1/expedition/packages`) with the route and waypoints, emergency return
   harbours, INCOIS PFZ zones, IMD warnings with issue/expiry times, a 72 h wave/wind forecast
   along the route, the latest AI prediction grid, and the safety thresholds.
2. **Download**: shows each component's expiry (package `valid_until` = earliest one) and
   downloads the offline basemap / depth contours into the browser cache if the files exist
   on the server (see `backend/static/offline/README.md` to build them).
3. **At Sea** (no connectivity needed): device GPS → position, heading, bearing/distance to
   target, cross-track error, ETA, nearest return harbour; track points are saved locally every
   30 s / 50 m. Safety is re-evaluated offline from the packaged warnings + forecast using the
   same rules as the backend SafetyGate — **expired data never shows as safe**.
4. **Catch Log**: species / weight / notes with GPS and time, stored offline.
5. **Sync**: on reconnection, records upload idempotently (`POST /api/v1/expedition/sync`)
   and fresh warnings/forecast/predictions are merged into the package.

The app is an installable PWA (service worker precaches the shell). Known limits: browser GPS
pauses when the screen is off (a screen wake-lock is requested while at sea; a Capacitor
Android wrapper is the planned fix), and geolocation/service workers require HTTPS on a real
phone (localhost is fine for development). The basemap and GEBCO contours are **not** nautical
charts.

### Testing on a phone (HTTPS)

Phones only allow GPS and offline mode (service workers) on a **trusted HTTPS** address.

1. Generate a local dev CA + certificate for your PC's Wi-Fi IP (re-run if the IP changes):
   ```bash
   bash scripts/dev-https/generate-dev-certs.sh          # auto-detects the IP
   docker compose up -d --force-recreate frontend
   ```
   The dev server switches to HTTPS automatically when `frontend/certs/` exists
   (`VITE_HTTPS=0` turns it off). The PC address becomes **https://localhost:5173**.
2. Connect the phone to the **same Wi-Fi** as the PC.
3. On the phone open `https://<PC-IP>:5173/dev-ca.crt` (accept the one-time warning) to download the CA.
   - **Android:** Settings → Security & privacy → More security settings → Encryption & credentials →
     Install a certificate → **CA certificate** → pick `matsya-dev-ca.crt`.
   - **iPhone:** open the downloaded profile in Settings → General → VPN & Device Management → Install,
     then Settings → General → About → Certificate Trust Settings → enable "MatsyaAI Local Dev CA".
4. Open `https://<PC-IP>:5173/#expedition` — no warning, GPS and offline mode work. Use "Add to Home
   screen" to install the PWA.
5. When done testing, remove the CA from the phone (same settings screen → User credentials).

`frontend/certs/ca.key` can sign certificates your phone trusts — it is git-ignored and excluded
from Docker images; don't share it.

## Environment Variables

See `.env.example` for all available configuration options.

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://matsya:matsya_dev@db:5432/matsya_ai` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["http://localhost:5173"]` |
| `ENVIRONMENT` | `development` / `production` | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `INCOIS_BASE_URL` | INCOIS data endpoint | _(empty — not yet verified)_ |
| `IMD_BASE_URL` | IMD weather endpoint | _(empty — not yet verified)_ |

---

## Data Integrity Policy

This project **never fabricates official data**. All data source endpoints, API keys, coordinates, and scientific values must be verified against official sources before use. Mock/development data is always clearly labelled as such.

---

## Milestone Roadmap

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Project scaffolding | ✅ Complete |
| 2 | Database + geographic foundation | 🔲 Planned |
| 3 | Official data integration | 🔲 Planned |
| 4 | Fisherman landing page | 🔲 Planned |
| 5 | Fishing map | 🔲 Planned |
| 6 | Safety engine | 🔲 Planned |
| 7 | Prediction engine | 🔲 Planned |
| 8 | Navigation | 🔲 Planned |
| 9 | Offline/PWA | 🔲 Planned |
| 10 | Testing & deployment | 🔲 Planned |

---

## Geographic Scope

Maharashtra coast (six coastal districts):

- Palghar
- Thane
- Mumbai
- Raigad
- Ratnagiri
- Sindhudurg

---

## License

TBD
