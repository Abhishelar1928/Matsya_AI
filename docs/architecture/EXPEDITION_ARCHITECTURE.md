# MatsyaAI Expedition Mode — Repository Audit & Architecture Assessment

**Audit Date:** 2026-11-24  
**Scope:** Frontend Expedition PWA (`frontend/src/expedition/*`, `frontend/vite.config.ts`), Backend Expedition API & Services (`backend/app/api/v1/expedition.py`, `backend/app/services/expedition/*`, `backend/app/models/expedition.py`, `backend/alembic/versions/e7a1c0ffee01_add_offline_expedition_tables.py`), Canonical Data (`backend/app/core/landing_centres.py`, `backend/static/offline/`), and Dev Mock Server (`scratch/dev_mock_backend.js`).

---

## 1. Current Architecture Inventory

### Frontend (`frontend/src/expedition/`)
- **`ExpeditionMode.tsx`**: 5-tab state container (`plan` → `download` → `sea` → `catch` → `sync`), owns `useGeolocation` and `startAutoSync`, restores active package from IndexedDB.
- **`PlanExpedition.tsx`**: Landing centre selector, Leaflet map for selecting INCOIS PFZ or tapping custom coordinates, calls `POST /api/v1/expedition/packages`.
- **`DownloadPackage.tsx`**: Displays package component expiry, requests `navigator.storage.persist()`, streams offline assets (`/api/v1/offline-assets/*`) into Service Worker cache via `vite-plugin-pwa` Workbox rules.
- **`AtSea.tsx`**: Leaflet map (`basemap.ts` supporting `protomaps-leaflet` PMTiles or graticule fallback + optional GEBCO GeoJSON contours), displays `MarineCompass` (`Compass.tsx`), live GPS stats, nearest emergency return harbour, and records track points every 30 s or 50 m.
- **`geo.ts`**: Spherical geodesy utilities (`haversineKm`, `initialBearingDeg`, `crossTrackKm`, `alongTrackKm`, `compassPoint`, `headingError`, `etaMinutes`, `routeProgress`).
- **`useGeolocation.ts`**: `navigator.geolocation.watchPosition` with high-to-low accuracy fallback, `navigator.permissions.query`, Screen Wake Lock, and inline route simulation.
- **`offlineSafety.ts`**: Client-side port of `backend/app/ml/safety_gate.py` evaluating packaged IMD warnings and Open-Meteo hourly forecast at the nearest forecast point.
- **`db.ts`**: `idb` wrapper (`matsya-expedition`, `DB_VERSION = 1`) with object stores: `packages`, `track_points`, `catches`, `observations`, `settings`.
- **`sync.ts` / `SyncStatus.tsx`**: Outbox uploader (`BATCH_TRACK_POINTS = 2000`), applies server delta updates back into IndexedDB.
- **`CatchLog.tsx`**: Offline catch form with 10 hardcoded EN/MR species, weight, notes, and auto-filled GPS fix.

### Backend (`backend/app/`)
- **`api/v1/expedition.py`**: `GET /expedition/landing-centres`, `POST /expedition/packages`, `POST /expedition/sync`.
- **`services/expedition/package_builder.py`**: Assembles JSON package (`SCHEMA_VERSION = 1`), computes `earliest()` manifest expiry across warnings, forecast, predictions, and PFZ.
- **`services/expedition/routing.py`**: Great-circle route with 10 km waypoints and `global_land_mask` (~1 km resolution) crossing checks (`HARBOUR_EXCLUSION_KM = 3.0`).
- **`services/expedition/forecast.py`**: Fetches 72 h Open-Meteo marine & wind forecasts for up to 6 waypoints.
- **`services/expedition/sync.py`**: PostgreSQL `INSERT ... ON CONFLICT (client_uuid) DO NOTHING` idempotent sync.
- **`models/expedition.py` & `alembic/versions/e7a1c0ffee01`**: Tables `expeditions`, `expedition_track_points`, `catch_records`, `field_observations`.

---

## 2. Identified Bugs, Calculation Flaws, & Architectural Gaps

1. **Signed Along-Track & `asin` Domain Bug (`geo.ts:35-52`):**
   - `alongTrackKm` uses `Math.acos(Math.cos(d13) / Math.cos(xt))`, which is always $\ge 0$ and loses sign when a vessel is *behind* waypoint $A$. As a result, `routeProgress` misclassifies points behind a leg start as lying inside the leg.
   - `crossTrackKm` does not clamp `Math.sin(d13) * Math.sin(b13 - b12)` to `[-1, 1]`, risking `NaN` from floating-point overshoot on antipodal or extreme values.

2. **Heading vs. Course Over Ground Conflation & Signal Hygiene (`useGeolocation.ts:170-189`):**
   - `coords.heading` (GPS Course Over Ground) is treated identically to vessel heading, with no separation from magnetic/device compass orientation (`DeviceOrientationEvent`).
   - Unreliable or noisy COG is accepted when stationary or moving slowly (`< 0.5 m/s`), causing erratic needle spinning.
   - Missing GPS stale/loss detection (`fixAgeMs > 30s`), no single-sample outlier/teleport jump rejection, and linear lat/lon interpolation in simulation instead of spherical great-circle interpolation.
   - No visibility/suspension lifecycle tracking to disclose browser background GPS pauses.

3. **Misleading Direct-Line Navigability Flag (`routing.py:127`):**
   - `is_navigable_direct: not warnings` relies only on a ~1 km land mask (`global_land_mask`) with a 3 km harbour exclusion radius. This misses narrow reefs, shoals, sandbars, buoys, wrecks, and shallow water, and must explicitly disclose that the great-circle line is a **direct-distance reference only**, not a safe navigable route.

4. **Safety Engine Scope & State Granularity (`offlineSafety.ts`):**
   - Evaluates only the current hour at a single nearest forecast point, ignoring deteriorating conditions ahead on the route or return corridor within the trip window.
   - Lacks per-source provenance reporting (source name, observation vs. forecast type, issue/valid-from/expiry timestamps, geographic coverage).
   - INCOIS Ocean State Forecasts (OSF) and high-wave/swell alerts have no ingestion provider in the backend; must be surfaced explicitly as `UNAVAILABLE` rather than omitted or assumed safe.

5. **Package Manifest, Integrity, & Offline Readiness (`package_builder.py`, `DownloadPackage.tsx`, `db.ts`):**
   - Manifest lacks `generated_at`, `valid_from`, `source`, `version`, `coverage`, `component_versions`, SHA-256 `checksums`, and an embedded approved `species_catalogue`.
   - `db.ts` (`DB_VERSION = 1`) writes package and `active_package_id` in two separate operations (non-atomic) and has no `voyage_events` or `voyage_state` stores for crash recovery or voyage replay.
   - `DownloadPackage.tsx` lacks download cancellation (`AbortController`), retry controls, storage quota estimation (`navigator.storage.estimate()`), integrity verification, explicit delete/replace, and an offline-readiness check before launching.

6. **Voyage Black Box, Replay, & Emergency Return (`AtSea.tsx`):**
   - Reloading the app during an active voyage does not restore the recorded track trail, active waypoint, MOB marker, or anchor watch state.
   - No GPX/CSV export, no voyage replay, no Man Overboard (MOB) marker, no Anchor Watch drift alert, no multi-harbour emergency comparison, and no dark/night wheelhouse HUD mode.
   - Map lacks a GPS accuracy circle, numbered waypoints, coverage boundary rectangle, and shallow-water contour highlighting.

7. **Synchronization Races & Loop Guard (`sync.ts`, `scratch/dev_mock_backend.js`):**
   - `syncExpedition` has no per-expedition mutex; simultaneous `online` events, periodic timers, and manual sync clicks can issue duplicate concurrent requests.
   - Batch loop breaks only when `pending === 0` or `last` is true; if a server acknowledges 0 items on a multi-batch queue, it loops infinitely.
   - Lacks per-batch `X-Idempotency-Key`, failed-record count tracking, and best-effort `BackgroundSync` registration.
   - `scratch/dev_mock_backend.js` `/api/v1/expedition/sync` stub previously omitted `acknowledged_uuids`, `inserted`, and `duplicates`.

---

## 3. Data-Source, Browser, & Security Limitations (Verified)
- **Landing Centre Coordinates (`backend/app/core/landing_centres.py`):** All 10 centres carry `verified=False` (`database/seeds/landing_centres_mock.py (unverified)`).
- **Offline Assets (`backend/static/offline/README.md`):** `maharashtra-coast.pmtiles`, `bathymetry-contours.geojson`, and NHO/ENC charts are not shipped in the repo; offline charts degrade to a graticule fallback unless assets are generated locally.
- **INCOIS OSF:** No ingestion module exists for INCOIS Ocean State Forecasts; must report `UNAVAILABLE`.
- **INCOIS PFZ TLS (`backend/app/services/ingestion/incois_pfz_provider.py:290`):** Uses `verify=False` due to upstream certificate chain issues; noted as a transport security limitation.
- **Auth:** Sync endpoints authorize solely via `(expedition_id, device_id)` without user authentication or signed tokens.
- **PWA Lifecycle:** Browsers suspend JS timers and `watchPosition` when backgrounded or when the device sleeps, and may evict storage if `navigator.storage.persist()` is denied.
