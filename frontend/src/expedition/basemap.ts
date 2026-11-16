/**
 * MatsyaAI Maharashtra — Offline basemap for Expedition Mode.
 *
 * Preferred: a PMTiles vector basemap (`/api/v1/offline-assets/maharashtra-coast.pmtiles`)
 * rendered by protomaps-leaflet. The service worker caches the file after the
 * first download so it works offline. If the asset is missing we fall back to a
 * plain ocean background with the route/zones drawn on top — still usable.
 */

import L from 'leaflet';
import { leafletLayer } from 'protomaps-leaflet';
import type { ExpeditionPackage } from './types';

export const OCEAN_BG = '#e9eef3';

export async function assetAvailable(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok;
  } catch {
    // Offline: check the service-worker cache
    if ('caches' in window) {
      const hit = await caches.match(url);
      return !!hit;
    }
    return false;
  }
}

export interface BasemapResult {
  layer: L.Layer;
  kind: 'pmtiles' | 'fallback';
}

export async function createOfflineBasemap(pkg: ExpeditionPackage): Promise<BasemapResult> {
  const asset = pkg.offline_assets.basemap;
  if (asset.available && asset.url && (await assetAvailable(asset.url))) {
    const layer = leafletLayer({
      url: asset.url,
      flavor: 'light',
      lang: 'en',
      attribution: '© OpenStreetMap contributors · Protomaps · Not a nautical chart',
      backgroundColor: OCEAN_BG,
      maxDataZoom: 13,
    }) as unknown as L.Layer;
    return { layer, kind: 'pmtiles' };
  }
  // Fallback: a graticule so the fisherman still has spatial reference.
  const group = L.layerGroup();
  for (let lat = 14; lat <= 21; lat += 0.5) {
    L.polyline([[lat, 70], [lat, 75]], { color: '#c5d3e2', weight: lat % 1 === 0 ? 1 : 0.5, interactive: false }).addTo(group);
  }
  for (let lon = 70; lon <= 75; lon += 0.5) {
    L.polyline([[14, lon], [21, lon]], { color: '#c5d3e2', weight: lon % 1 === 0 ? 1 : 0.5, interactive: false }).addTo(group);
  }
  return { layer: group, kind: 'fallback' };
}

export async function loadBathymetry(pkg: ExpeditionPackage): Promise<L.GeoJSON | null> {
  const asset = pkg.offline_assets.bathymetry;
  if (!asset.available || !asset.url) return null;
  try {
    const res = await fetch(asset.url);
    if (!res.ok) return null;
    const geo = await res.json();
    return L.geoJSON(geo, {
      style: (f) => {
        const depth = Math.abs(Number(f?.properties?.depth_m ?? f?.properties?.ELEV ?? 0));
        return { color: depth >= 100 ? '#4fc3f7' : depth >= 50 ? '#29b6f6' : '#81d4fa', weight: depth >= 100 ? 1.2 : 0.8, opacity: 0.6, interactive: false };
      },
    });
  } catch {
    return null;
  }
}
