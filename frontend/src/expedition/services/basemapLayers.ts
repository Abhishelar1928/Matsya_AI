/**
 * MatsyaAI Maharashtra — Offline basemap & bathymetry for Expedition Mode.
 *
 * Supports 'light' | 'dark' | 'night' chart themes, PMTiles vector basemap
 * when available (with graticule fallback), and shallow-water bathymetry highlighting.
 */

import L from 'leaflet';
import { leafletLayer } from 'protomaps-leaflet';
import type { ShallowContourLine } from '../engine/geodesy';
import type { ExpeditionPackage, OfflineAsset } from '../types/expeditionTypes';

export type MapTheme = 'light' | 'dark' | 'night';

export const OCEAN_BG = '#0b1829';

export const OCEAN_BG_BY_THEME: Record<MapTheme, string> = {
  light: '#e9eef3',
  dark: '#091524',
  night: '#090304',
};

export async function assetAvailable(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok;
  } catch {
    if ('caches' in window) {
      const hit = await caches.match(url);
      return !!hit;
    }
    return false;
  }
}

export interface BasemapResult {
  layer: L.Layer;
  kind: 'pmtiles' | 'osm' | 'fallback';
}

export const LAND_OSM_BG = '#e9eef3';

export function createOsmLandBasemap(): BasemapResult {
  const layer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
  });
  return { layer, kind: 'osm' };
}

export async function createOfflineBasemap(
  pkg: ExpeditionPackage,
  theme: MapTheme = 'dark',
  options?: { onLand?: boolean },
): Promise<BasemapResult> {
  if (options?.onLand) {
    return createOsmLandBasemap();
  }
  const bg = OCEAN_BG_BY_THEME[theme];
  const asset = pkg.offline_assets.basemap;
  if (asset.available && asset.url && (await assetAvailable(asset.url))) {
    const layer = leafletLayer({
      url: asset.url,
      flavor: theme === 'light' ? 'light' : 'dark',
      lang: 'en',
      attribution: '© OpenStreetMap contributors · Protomaps · Not a nautical chart',
      backgroundColor: bg,
      maxDataZoom: 13,
    }) as unknown as L.Layer;
    return { layer, kind: 'pmtiles' };
  }

  // Fallback: calibrated graticule grid with theme-aware contrast
  const group = L.layerGroup();
  const majorColor = theme === 'light' ? '#9cb3cb' : theme === 'night' ? '#4f161b' : '#244162';
  const minorColor = theme === 'light' ? '#c5d3e2' : theme === 'night' ? '#330d10' : '#172c44';
  const bbox = pkg.offline_assets?.bbox ?? { min_lat: 14.5, max_lat: 21.0, min_lon: 70.0, max_lon: 75.0 };
  const minLat = Math.floor(Math.min(14, bbox.min_lat));
  const maxLat = Math.ceil(Math.max(21, bbox.max_lat));
  const minLon = Math.floor(Math.min(70, bbox.min_lon));
  const maxLon = Math.ceil(Math.max(75, bbox.max_lon));

  for (let lat = minLat; lat <= maxLat; lat += 0.5) {
    const isMajor = Math.abs(lat % 1) < 1e-6;
    L.polyline(
      [
        [lat, minLon],
        [lat, maxLon],
      ],
      { color: isMajor ? majorColor : minorColor, weight: isMajor ? 1 : 0.5, interactive: false },
    ).addTo(group);
  }
  for (let lon = minLon; lon <= maxLon; lon += 0.5) {
    const isMajor = Math.abs(lon % 1) < 1e-6;
    L.polyline(
      [
        [minLat, lon],
        [maxLat, lon],
      ],
      { color: isMajor ? majorColor : minorColor, weight: isMajor ? 1 : 0.5, interactive: false },
    ).addTo(group);
  }
  return { layer: group, kind: 'fallback' };
}

export async function loadBathymetry(
  pkg: ExpeditionPackage,
  theme: MapTheme = 'dark',
): Promise<{ layer: L.GeoJSON; hasShallowContours: boolean; shallowLines: ShallowContourLine[] } | null> {
  const asset = pkg.offline_assets.bathymetry;
  if (!asset.available || !asset.url) return null;
  try {
    const res = await fetch(asset.url);
    if (!res.ok) return null;
    const geo = await res.json();
    let hasShallowContours = false;
    const shallowLines: ShallowContourLine[] = [];

    const layer = L.geoJSON(geo, {
      style: (f) => {
        const depth = Math.abs(Number(f?.properties?.depth_m ?? f?.properties?.ELEV ?? 0));
        if (depth > 0 && depth <= 10) {
          hasShallowContours = true;
          return { color: '#ef4444', weight: 1.8, dashArray: '4 3', opacity: 0.9 };
        }
        if (depth > 10 && depth <= 20) {
          hasShallowContours = true;
          return {
            color: theme === 'night' ? '#ff6b6b' : '#f59e0b',
            weight: 1.5,
            dashArray: '5 3',
            opacity: 0.85,
          };
        }
        if (depth <= 50) {
          return { color: theme === 'night' ? '#b91c1c' : '#38bdf8', weight: 1.1, opacity: 0.72 };
        }
        if (depth <= 100) {
          return { color: theme === 'night' ? '#991b1b' : '#0284c7', weight: 1.1, opacity: 0.65 };
        }
        return { color: theme === 'night' ? '#7f1d1d' : '#6366f1', weight: 0.9, opacity: 0.55 };
      },
      onEachFeature: (f, l) => {
        const depth = Math.abs(Number(f?.properties?.depth_m ?? f?.properties?.ELEV ?? 0));
        if (depth > 0 && depth <= 20 && f?.geometry?.type === 'LineString' && Array.isArray(f.geometry.coordinates)) {
          shallowLines.push({ depth_m: depth, coordinates: f.geometry.coordinates as [number, number][] });
        }
        if (depth > 0) {
          l.bindTooltip(
            depth <= 20
              ? `Shallow contour: ${depth} m (GEBCO — NOT verified navigation depth)`
              : `Depth contour: ${depth} m (GEBCO — general-purpose only)`,
          );
        }
      },
    });
    return { layer, hasShallowContours, shallowLines };
  } catch {
    return null;
  }
}

export async function loadOptionalGeoJson(asset?: OfflineAsset): Promise<GeoJSON.FeatureCollection | null> {
  if (!asset?.available || !asset.url) return null;
  try {
    const res = await fetch(asset.url);
    if (!res.ok) return null;
    const geo = await res.json();
    return geo && Array.isArray(geo.features) ? (geo as GeoJSON.FeatureCollection) : null;
  } catch {
    return null;
  }
}

export async function loadMpaAndHazards(
  pkg: ExpeditionPackage,
): Promise<{ layer: L.LayerGroup; mpaCount: number; offshoreCount: number; shippingCount: number }> {
  const group = L.layerGroup();
  const [mpaGeo, offGeo, shipGeo] = await Promise.all([
    loadOptionalGeoJson(pkg.offline_assets.marine_protected_areas),
    loadOptionalGeoJson(pkg.offline_assets.offshore_installations),
    loadOptionalGeoJson(pkg.offline_assets.shipping_lanes),
  ]);

  let mpaCount = 0;
  let offshoreCount = 0;
  let shippingCount = 0;

  if (mpaGeo && mpaGeo.features.length > 0) {
    mpaCount = mpaGeo.features.length;
    L.geoJSON(mpaGeo, {
      style: { color: '#c084fc', weight: 2, dashArray: '4 4', fillColor: '#9333ea', fillOpacity: 0.18 },
      onEachFeature: (f, l) => {
        const name = String(f?.properties?.name ?? 'Marine Protected Area');
        const note = String(f?.properties?.restriction ?? 'Restricted marine area');
        l.bindTooltip(`${name} — ${note}`);
      },
    }).addTo(group);
  }

  if (offGeo && offGeo.features.length > 0) {
    offshoreCount = offGeo.features.length;
    L.geoJSON(offGeo, {
      pointToLayer: (_f, ll) =>
        L.circleMarker(ll, { radius: 5, color: '#ffffff', fillColor: '#f97316', fillOpacity: 0.95, weight: 1.5 }),
      onEachFeature: (f, l) => {
        l.bindTooltip(`${f?.properties?.name ?? 'Offshore platform'} (${f?.properties?.source ?? 'OSM'})`);
      },
    }).addTo(group);
  }

  if (shipGeo && shipGeo.features.length > 0) {
    shippingCount = shipGeo.features.length;
    L.geoJSON(shipGeo, {
      style: { color: '#eab308', weight: 1.6, dashArray: '6 4', opacity: 0.85 },
      onEachFeature: (f, l) => {
        l.bindTooltip(`${f?.properties?.name ?? 'Shipping lane'} (OpenSeaMap — not official ENC)`);
      },
    }).addTo(group);
  }

  return { layer: group, mpaCount, offshoreCount, shippingCount };
}
