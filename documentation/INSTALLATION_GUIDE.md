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
