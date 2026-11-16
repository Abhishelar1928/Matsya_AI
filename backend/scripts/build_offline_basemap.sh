#!/usr/bin/env sh
# =============================================================================
# MatsyaAI — Build the offline vector basemap for Expedition Mode
# =============================================================================
# Extracts a Maharashtra-coast subset of the public Protomaps OpenStreetMap
# build into a single PMTiles file that the PWA caches and renders offline.
#
# Requires the `pmtiles` CLI (Go binary): https://github.com/protomaps/go-pmtiles/releases
#
# Usage:
#   sh backend/scripts/build_offline_basemap.sh            # latest daily build
#   sh backend/scripts/build_offline_basemap.sh 20260601   # pin a build date
#
# Output: backend/static/offline/maharashtra-coast.pmtiles (~40–80 MB at z0–13)
# License: OpenStreetMap contributors (ODbL). Not a nautical chart.
# =============================================================================
set -eu

BUILD="${1:-}"
OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/static/offline"
OUT="$OUT_DIR/maharashtra-coast.pmtiles"
# bbox = min_lon,min_lat,max_lon,max_lat (matches REGION_BBOX in package_builder.py)
BBOX="71.5,15.5,74.0,20.5"
MAXZOOM=13

if ! command -v pmtiles >/dev/null 2>&1; then
  echo "pmtiles CLI not found. Install from https://github.com/protomaps/go-pmtiles/releases" >&2
  exit 1
fi

if [ -z "$BUILD" ]; then
  # Resolve the newest build listed at https://build.protomaps.com/
  BUILD="$(curl -fsSL https://build.protomaps.com/ | grep -oE '[0-9]{8}\.pmtiles' | sort -u | tail -1 | sed 's/\.pmtiles//')"
  [ -n "$BUILD" ] || { echo "Could not resolve latest Protomaps build" >&2; exit 1; }
fi

mkdir -p "$OUT_DIR"
echo "Extracting Protomaps build $BUILD, bbox=$BBOX, maxzoom=$MAXZOOM → $OUT"
pmtiles extract "https://build.protomaps.com/$BUILD.pmtiles" "$OUT" --bbox="$BBOX" --maxzoom="$MAXZOOM"
ls -lh "$OUT"
echo "Done. The backend serves it at /api/v1/offline-assets/maharashtra-coast.pmtiles"
