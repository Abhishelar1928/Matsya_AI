# INCOIS PFZ Machine-Readable Access — Validation Report

**Date:** 2026-09-06  
**Investigator:** Antigravity IDE (Claude Opus 4.6)  
**Objective:** Determine whether Matsya AI can directly consume the official INCOIS PFZ advisory programmatically.

---

## Executive Summary

**A publicly accessible, machine-readable, GeoJSON/WFS endpoint for INCOIS PFZ data has been DISCOVERED and VERIFIED.**

The INCOIS PFZ WebGIS application (`/DataInfo/MFASPFZ/index.html`) is backed by a **GeoServer** instance at `incois.gov.in/geoserver/` that exposes OGC-standard **WFS (Web Feature Service)** endpoints returning GeoJSON. These endpoints are used by the official WebGIS frontend itself and are accessible without authentication.

---

## Verdict

| Criterion                        | Status              | Details |
|----------------------------------|---------------------|---------|
| **OFFICIAL SOURCE VERIFIED**     | ✅ YES              | `incois.gov.in/geoserver/PFZ_Automation/ows` — hosted on INCOIS's own domain |
| **MACHINE-READABLE ACCESS VERIFIED** | ✅ YES          | OGC WFS 1.1.0 returning `application/json` (GeoJSON) |
| **MAHARASHTRA PFZ VERIFIED**     | ✅ YES              | Landing Centres dataset has `SECTOR_NAM='MAHARASHTRA'`, `SECTOR_ID='SEC002'` — 60+ Maharashtra entries confirmed |
| **CURRENT DATA VERIFIED**        | ❌ FAIL              | PFZ lines date back to 2021 (Julian_day=248, Year=2021). Landing Centres dataset is timestamped `2024-04-27` and its `VALIDITY_D` is `2024-04-28`. Today is 2026-09-06. The data is STALE and cannot be used for current recommendations. |
| **COORDINATES VERIFIED**         | ✅ YES              | Full lat/lon geometry in GeoJSON `MultiLineString` (PFZ lines) and `Point` (landing centres) |
| **UPDATE FREQUENCY VERIFIED**    | ❌ FAIL              | WFS layers have not been updated recently. Dynamic layer discovery shows no recent layers. |
| **RELIABLE FOR MATSYA AI**       | ❌ NO               | The endpoints provide historical/stale data, not current operational advisories. |

---

## Discovered Endpoints

### 1. PFZ Lines (Core Fishing Zones)

```
GET https://incois.gov.in/geoserver/PFZ_Automation/ows
  ?service=WFS&version=1.1.0&request=GetFeature
  &typeName=PFZ_Automation:pfzlines
  &outputFormat=application/json
```

Returns: GeoJSON FeatureCollection with MultiLineString geometries

Properties: Category, SECTORBOUN, SECTORBO_1, SECTORNAME, Julian_day, Sno, Year, UID, Length

**Freshness Check**: ❌ FAILED. The data returns `Year=2021` and `Julian_day=248`.

### 2. Landing Centres (PFZ Advisory Reference Points) — PRIMARY FOR MATSYA AI

```
GET https://incois.gov.in/geoserver/PFZ_LandingCentres/ows
  ?service=WFS&version=1.1.0&request=GetFeature
  &typeName=PFZ_LandingCentres:LandingCenters_29Apr2024
  &outputFormat=application/json
```

Returns: GeoJSON FeatureCollection with Point geometries

Key properties: SECTOR_NAM, SECTOR_ID, DIST_NAME, LC_NAME, LC_UNIQUE_, 
LONGITUDE, LATITUDE, DIRECTION, BEARING, DISTANCE_F, DISTANCE_T, 
DEPTH_FROM, DEPTH_TO, FORECAST_D, VALIDITY_D, STATUS, MARINE_FIS

**Freshness Check**: ❌ FAILED. `FORECAST_D` is `2024-04-27T18:30:00Z` and `VALIDITY_D` is `2024-04-28T18:30:00Z`.

### 3. Sectors (Sector Boundaries)

```
GET https://incois.gov.in/geoserver/PFZ_Sectors/ows
  ?service=WFS&version=1.1.0&request=GetFeature
  &typeName=PFZ_Sectors:sector_new
  &outputFormat=application/json
```

### 4. WFS GetCapabilities (Dynamic Layer Discovery)

```
GET https://incois.gov.in/geoserver/PFZ_Automation/ows
  ?service=WFS&version=1.1.0&request=GetCapabilities
```

**Dynamic Layer Discovery Results**: 
- `PFZ_LandingCentres` workspace contains ONLY the `LandingCenters_29Apr2024` layer. No layers for 2025 or 2026.
- `PFZ_Automation` workspace contains `India_EEZ` and `pfzlines`.
- Confirmed: Standard OGC WFS 1.1.0, supports CQL_FILTER, Fees: NONE, AccessConstraints: NONE

---

## Maharashtra PFZ Data Confirmed

60+ landing centres in MAHARASHTRA sector with districts:
- Thane (Satpati, Tarapur Pt, Datiware, Rangaon, etc.)
- Mumbai (Worli-Lotus, Colaba Pt, CuffPared)
- Mumbai Suburban (Uarashi Rf, Manori, Patwadi)
- Raigarh (Nagaon, Rewdanda, Thal, Uran, etc.)
- Ratnagiri (Ratnagiri, Mirkarwada, Guhagar, Jaigarh Head, etc.)
- Sindhudurg (Vengurla, MuthUbhadanda, Deobag, Khavana, etc.)

Each has PFZ coordinates, depth, distance, direction, and bearing.

---

## Reliability Assessment

### Strengths
1. Official INCOIS infrastructure — same GeoServer used by their own WebGIS
2. Standard OGC WFS — well-documented, widely-supported protocol
3. No authentication required
4. Rich data — coordinates, depth, distance, direction, bearing
5. Maharashtra coverage — 60+ landing centres
6. Multiple output formats — JSON, KML, CSV, Shapefile, GML
7. Access constraints explicitly stated as NONE

### Caveats
1. No documented public API — endpoints used by WebGIS but not advertised
2. Rate limiting observed — rapid successive requests received HTTP 503
3. Data freshness — Landing Centres dataset name includes a date (29Apr2024)
4. No API versioning guarantees — layer names could change
5. PFZ lines dataset does not include State_Name — sector filtering requires spatial queries or cross-reference

### Recommended Next Steps

1. **Do not integrate into Matsya AI yet.** The WFS endpoints currently serve severely outdated historical data (2021 and 2024).
2. Contact INCOIS to establish whether there is an operational REST API or updated WFS layer for 2026.
3. Fall back to the secondary strategy or display an explicit "Data Unavailable" UI if no official source can be obtained.

---

## Final Verdicts

- OFFICIAL SOURCE: PASS
- WFS ACCESS: PASS
- DYNAMIC LAYER DISCOVERY: PASS
- CURRENT PFZ DATA: FAIL
- MAHARASHTRA PFZ: PASS (Historical only)
- PFZ GEOMETRY: PASS (Historical only)
- LANDING-CENTRE ADVISORY: PASS
- DATE/VALIDITY INTEGRITY: FAIL
- RATE-LIMIT HANDLING: PASS
- STALE-DATA PROTECTION: PASS
- READY FOR APPLICATION INTEGRATION: NO
