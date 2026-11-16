# Offline assets for Expedition Mode

Files in this folder are served by the backend at `/api/v1/offline-assets/<file>` and
cached on the device by the PWA service worker. They are **not committed** (large,
regenerable). The app degrades gracefully when they are missing (grid background).

| File | What | How to build |
|---|---|---|
| `maharashtra-coast.pmtiles` | Vector basemap, bbox 71.5–74.0°E / 15.5–20.5°N, z0–13, OpenStreetMap (ODbL) | `sh backend/scripts/build_offline_basemap.sh` (needs the `pmtiles` CLI) |
| `bathymetry-contours.geojson` | GEBCO depth contours 10/20/30/50/100/200 m | Download a GEBCO subset as Esri ASCII from https://download.gebco.net/ then `python backend/scripts/build_bathymetry_contours.py subset.asc` |

Neither file is a navigational chart. Official NHO/ENC charts are licensed and not included.
