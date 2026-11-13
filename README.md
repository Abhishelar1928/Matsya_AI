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

This starts three services:

| Service | Port | URL |
|---------|------|-----|
| **Frontend** (React + Vite) | 5173 | http://localhost:5173 |
| **Backend** (FastAPI) | 8000 | http://localhost:8000 |
| **Database** (PostgreSQL + PostGIS) | 5432 | `postgresql://matsya:matsya_dev@localhost:5432/matsya_ai` |

### 3. Verify

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
matsya-ai/
│
├── frontend/                   # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── pages/              # Route pages
│   │   ├── layouts/            # Page layouts
│   │   ├── map/                # MapLibre GL JS integration
│   │   ├── services/           # API client layer
│   │   ├── hooks/              # Custom React hooks
│   │   ├── types/              # TypeScript type definitions
│   │   ├── utils/              # Utility functions
│   │   └── i18n/               # Internationalization (EN + MR)
│   ├── public/
│   └── package.json
│
├── backend/                    # Python FastAPI
│   ├── app/
│   │   ├── api/v1/             # API endpoints
│   │   ├── core/               # Config, database, logging
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Business logic
│   │   └── repositories/       # Data access layer
│   ├── tests/
│   └── requirements.txt
│
├── data_pipeline/              # Data ingestion workers
│   ├── incois/                 # INCOIS ocean + PFZ data
│   ├── imd/                    # IMD weather + warnings
│   ├── fisheries/              # Maharashtra Fisheries Dept
│   ├── processing/             # Data transformation
│   ├── validation/             # Data validation rules
│   └── scheduler/              # Ingestion scheduling
│
├── ml/                         # Machine Learning
│   ├── training/               # Model training scripts
│   ├── inference/              # Prediction serving
│   ├── features/               # Feature engineering
│   ├── evaluation/             # Model evaluation
│   └── models/                 # Serialized models
│
├── database/
│   ├── migrations/             # Alembic migrations
│   └── seeds/                  # Seed data
│
├── docs/                       # Documentation
│   ├── architecture/
│   ├── data-sources/
│   └── api/
│
├── docker/
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Development

### Running without Docker

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
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

Maharashtra coast only (initial release):

- Palghar
- Mumbai
- Raigad
- Ratnagiri
- Sindhudurg

---

## License

TBD
