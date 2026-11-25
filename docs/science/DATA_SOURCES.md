11# MatsyaAI Maharashtra — Data Source Registry

This registry tracks the official data sources, endpoints, programmatic access statuses, terms of use, and data freshness for the MatsyaAI Maharashtra marine decision-support platform.

## INCOIS ERDDAP (Archival & Observational Data)
**Endpoint**: `https://erddap.incois.gov.in/erddap/`
**Access**: Public (No authentication required).
**Note**: SSL certificates fail validation. All ERDDAP data discovered is extremely stale and unusable for daily operational forecasts.

| Parameter | Dataset ID | Time Coverage Start | Time Coverage End | Status |
| :--- | :--- | :--- | :--- | :--- |
| **SST** | `NOAA_AVHRR_AMSR_datasets` | 2002-06-01 | 2011-10-04 | ⏳ HISTORICAL-ONLY |
| **SST** | `incois_argo_sst_weekly` | 2009-01-07 | 2010-12-29 | ⏳ HISTORICAL-ONLY |
| **Chlorophyll-a** | `incois_oceansat2_datasets` | 2011-02-02 | 2020-05-01 | ⏳ HISTORICAL-ONLY |
| **Chlorophyll-a** | `IRS_chlorophyll_datasets` | 2003-01-05 | 2006-03-21 | ⏳ HISTORICAL-ONLY |
| **Wind** | `ascat_daily_datasets` | 2007-03-21 | 2023-05-21 |1⏳ HISTORICAL-ONLY |

## INCOIS GeoServer / WebGIS (PFZ & OSF)
**Endpoint**: `https://incois.gov.in/geoserver/wms` and `wfs`
**Access**: WMS (Images) is public. WFS (Machine-Readable GeoJSON) is blocked (HTTP 403 Forbidden).

| Parameter | Layer Name | Format | Status | Technical Details |
| :--- | :--- | :--- | :--- | :--- |
| **PFZ Polygons** | `PFZ_Automation:pfzlines` | WMS (PNG) | ❌ UNSUITABLE | Public map viewing only. Machine-readable WFS endpoint returns HTTP 403. |
| **Maharashtra OSF** | `OSF_CoastalForecast:SECTORNAME_MAHARASHTRA` | WMS (PNG) | ❌ UNSUITABLE | Machine-readable WFS endpoint returns HTTP 403. Cannot be processed. |

## INCOIS THREDDS (Waves & Currents)
**Endpoint**: `https://las.incois.gov.in/thredds/catalog.xml`
**Access**: THREDDS XML catalogs, OPeNDAP.

| Parameter | Service | Access Method | Status |
| :--- | :--- | :--- | :--- |
| **Wave/Current** | INCOIS OSF | THREDDS OPeNDAP | ⚠️ UNVERIFIED / ❌ UNSUITABLE | Highly nested/dynamic catalog structures with hashed names. No straightforward LIVE paths for programmatic retrieval without API keys or guidance. |

## India Meteorological Department (IMD) Marine Warnings
**Endpoint**: `https://api.imd.gov.in` / `https://mausam.imd.gov.in`
**Access**: API Gateway (Registration required) / Web HTML/PDFs (Public).

| Parameter | Service | Access Method | Status |
| :--- | :--- | :--- | :--- |
| **Marine Warnings** | IMD API Gateway | REST API | ❌ UNSUITABLE (Requires API registration, credentials, and IP whitelisting) |
| **Marine Warnings** | Public Web HTML/PDF | Scraping | ⚠️ UNVERIFIED (Highly brittle, prone to breaking changes. Not standard practice for mission-critical alerts) |

## MOSDAC (ISRO Meteorological Data)
**Endpoint**: `https://mosdac.gov.in/catalog/catalog.xml`
**Access**: Public Catalog, Private Data Download (Registration Required).

| Parameter | Service | Access Method | Status |
| :--- | :--- | :--- | :--- |
| **Meteorological** | MOSDAC THREDDS | OPeNDAP / HTTPServer | ❌ UNSUITABLE (Data downloading strictly requires user registration and institutional approval per terms of use). |
