/**
 * MatsyaAI Maharashtra — Marine map (Leaflet).
 *
 * Layers: predicted apparent fishing activity (0.25° grid, single-hue sequential
 * scale), official INCOIS PFZ advisories, landing centres. A muted basemap keeps
 * the data layers in front. Selecting a cell or PFZ point opens an inspector.
 * Safety status is shown per cell but is never derived from the ML prediction.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Layers, LocateFixed, Navigation, X } from 'lucide-react';
import type { CellPrediction, MapSummaryResponse, OceanLayersManifest, PFZLocation } from '../types/map';
import { estimateCurrentDrift, compassPoint, haversineKm, initialBearingDeg, isPointOnLand, kmToNm } from '../expedition/engine/geodesy';
import { districtLabel, districtOf, nearestCentre } from '../lib/districts';
import { fmtCoord, fmtDate, fmtDateTime, fmtPct, parseKm } from '../lib/format';
import { href } from '../lib/router';
import { safetyMeta } from '../lib/status';
import { StatusBadge, Switch } from '../components/ui';

export interface MapFocus {
  lat: number;
  lon: number;
  zoom?: number;
}

interface Props {
  data: MapSummaryResponse;
  mr: boolean;
  oceanLayers?: OceanLayersManifest | null;
  height?: number | string;
  showControls?: boolean;
  focus?: MapFocus | null;
  flush?: boolean;
  /** Start with the layer panel collapsed (compact embeds). */
  layersCollapsed?: boolean;
}

type Selection =
  | { kind: 'cell'; cell: CellPrediction }
  | { kind: 'pfz'; pfz: PFZLocation; index: number }
  | { kind: 'point'; latitude: number; longitude: number }
  | null;

interface SelfLocation {
  latitude: number;
  longitude: number;
  accuracy_m: number | null;
}

const GRID = 0.25;

/** Sequential single-hue scale (light → dark ocean blue). */
export function activityStyle(cell: CellPrediction): { fill: string; opacity: number; stroke: string } {
  const p = cell.predicted_apparent_fishing_probability;
  const thr = cell.decision_threshold || 0.25;
  if (cell.predicted_apparent_fishing_binary === 1) return { fill: '#1d5fb4', opacity: 0.55, stroke: '#1d5fb4' };
  if (p >= thr * 0.55) return { fill: '#5b9be0', opacity: 0.4, stroke: '#5b9be0' };
  if (p >= Math.min(0.05, thr * 0.25)) return { fill: '#a9cdf2', opacity: 0.4, stroke: '#a9cdf2' };
  return { fill: '#ffffff', opacity: 0, stroke: '#c5d3e2' };
}

export function MarineMap({ data, mr, oceanLayers = null, height = 560, showControls = true, focus = null, flush = false, layersCollapsed = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const gridRef = useRef<L.LayerGroup | null>(null);
  const pfzRef = useRef<L.LayerGroup | null>(null);
  const landingRef = useRef<L.LayerGroup | null>(null);
  const oceanRasterRef = useRef<L.LayerGroup | null>(null);
  const currentsRef = useRef<L.LayerGroup | null>(null);
  const bathyRef = useRef<L.LayerGroup | null>(null);
  const mpaRef = useRef<L.LayerGroup | null>(null);
  const myLocLayerRef = useRef<L.LayerGroup | null>(null);
  const pickedLayerRef = useRef<L.LayerGroup | null>(null);
  const focusRef = useRef<L.CircleMarker | null>(null);

  const [showGrid, setShowGrid] = useState(true);
  const [showPfz, setShowPfz] = useState(true);
  const [showLanding, setShowLanding] = useState(true);
  const [showChla, setShowChla] = useState(false);
  const [showSst, setShowSst] = useState(false);
  const [showCurrents, setShowCurrents] = useState(false);
  const [showBathy, setShowBathy] = useState(true);
  const [showMpa, setShowMpa] = useState(true);
  const [layersOpen, setLayersOpen] = useState(() => !layersCollapsed && window.innerWidth > 720);
  const [sel, setSel] = useState<Selection>(null);
  const [myLoc, setMyLoc] = useState<SelfLocation | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  const tr = (en: string, m: string) => (mr ? m : en);

  // --- init ------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [17.9, 72.75],
      zoom: 7,
      minZoom: 6,
      maxZoom: 12,
      zoomControl: false,
      attributionControl: true,
    });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomright', imperial: false }).addTo(map);
    oceanRasterRef.current = L.layerGroup().addTo(map);
    bathyRef.current = L.layerGroup().addTo(map);
    mpaRef.current = L.layerGroup().addTo(map);
    gridRef.current = L.layerGroup().addTo(map);
    currentsRef.current = L.layerGroup().addTo(map);
    pfzRef.current = L.layerGroup().addTo(map);
    landingRef.current = L.layerGroup().addTo(map);
    pickedLayerRef.current = L.layerGroup().addTo(map);
    myLocLayerRef.current = L.layerGroup().addTo(map);
    map.on('click', (e: L.LeafletMouseEvent) => {
      setSel({ kind: 'point', latitude: +e.latlng.lat.toFixed(5), longitude: +e.latlng.lng.toFixed(5) });
    });
    mapRef.current = map;
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(containerRef.current);
    return () => { ro.disconnect(); map.remove(); mapRef.current = null; };
  }, []);

  // --- focus -----------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    focusRef.current?.remove();
    if (focus) {
      map.setView([focus.lat, focus.lon], focus.zoom ?? 9);
      focusRef.current = L.circleMarker([focus.lat, focus.lon], {
        radius: 14, color: '#0b6bcb', weight: 2, fill: false, dashArray: '3 3', interactive: false,
      }).addTo(map);
    }
  }, [focus?.lat, focus?.lon, focus?.zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- prediction grid -------------------------------------------------------
  useEffect(() => {
    const layer = gridRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showGrid) return;
    data.predictions.forEach((cell) => {
      const s = activityStyle(cell);
      const h = GRID / 2;
      const rect = L.rectangle(
        [[cell.latitude - h, cell.longitude - h], [cell.latitude + h, cell.longitude + h]],
        { color: s.stroke, weight: 0.6, opacity: 0.7, fillColor: s.fill, fillOpacity: s.opacity },
      );
      rect.bindTooltip(`${fmtPct(cell.predicted_apparent_fishing_probability)} ${tr('predicted activity', 'अपेक्षित हालचाल')}`, { sticky: true, direction: 'top' });
      rect.on('click', (e) => { L.DomEvent.stopPropagation(e); setSel({ kind: 'cell', cell }); });
      rect.addTo(layer);
    });
  }, [data.predictions, showGrid, mr]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- PFZ -------------------------------------------------------------------
  useEffect(() => {
    const layer = pfzRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showPfz) return;
    data.pfz_advisory.locations.forEach((pfz, index) => {
      const m = L.circleMarker([pfz.latitude, pfz.longitude], {
        radius: 6, color: '#ffffff', weight: 2, fillColor: '#0f8a66', fillOpacity: 1,
      });
      m.bindTooltip(`PFZ · ${pfz.landing_centre} ${pfz.direction}`, { direction: 'top' });
      m.on('click', (e) => { L.DomEvent.stopPropagation(e); setSel({ kind: 'pfz', pfz, index }); });
      m.addTo(layer);
    });
  }, [data.pfz_advisory, showPfz]);

  // --- landing centres -------------------------------------------------------
  useEffect(() => {
    const layer = landingRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showLanding) return;
    const icon = L.divIcon({ className: '', html: '<div class="landing-pin"></div>', iconSize: [12, 12], iconAnchor: [6, 6] });
    data.landing_centres.forEach((lc) => {
      L.marker([lc.latitude, lc.longitude], { icon, keyboard: false })
        .bindTooltip(`${mr && lc.name_mr ? lc.name_mr : lc.name}`, { direction: 'right', offset: [8, 0] })
        .addTo(layer);
    });
  }, [data.landing_centres, showLanding, mr]);

  // --- Chlorophyll-a & SST raster overlays ---------------------------------
  useEffect(() => {
    const layer = oceanRasterRef.current;
    if (!layer) return;
    layer.clearLayers();
    const chl = oceanLayers?.layers?.chlorophyll;
    if (showChla && chl?.status === 'LIVE' && chl.png_url && chl.bbox) {
      L.imageOverlay(
        chl.png_url,
        [[chl.bbox.min_lat, chl.bbox.min_lon], [chl.bbox.max_lat, chl.bbox.max_lon]],
        { opacity: 0.72, interactive: false },
      ).addTo(layer);
    }
    const sst = oceanLayers?.layers?.sst;
    if (showSst && sst?.status === 'LIVE' && sst.png_url && sst.bbox) {
      L.imageOverlay(
        sst.png_url,
        [[sst.bbox.min_lat, sst.bbox.min_lon], [sst.bbox.max_lat, sst.bbox.max_lon]],
        { opacity: 0.72, interactive: false },
      ).addTo(layer);
    }
  }, [oceanLayers, showChla, showSst]);

  // --- GEBCO Bathymetry contours (10 / 20 / 50 / 100 / 200 m) ---------------
  useEffect(() => {
    const layer = bathyRef.current;
    if (!layer) return;
    layer.clearLayers();
    const b = oceanLayers?.layers?.bathymetry;
    if (!showBathy || b?.status !== 'LIVE' || !b.url) return;
    let cancelled = false;
    void fetch(b.url)
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (cancelled || !geo) return;
        L.geoJSON(geo, {
          style: (f) => {
            const depth = Math.abs(Number(f?.properties?.depth_m ?? 0));
            if (depth <= 10) return { color: '#dc2626', weight: 1.6, dashArray: '4 3', opacity: 0.85 };
            if (depth <= 20) return { color: '#d97706', weight: 1.4, dashArray: '4 3', opacity: 0.85 };
            if (depth <= 50) return { color: '#0284c7', weight: 1.1, opacity: 0.7 };
            if (depth <= 100) return { color: '#1d4ed8', weight: 1.1, opacity: 0.65 };
            return { color: '#4338ca', weight: 0.9, opacity: 0.5 };
          },
          onEachFeature: (f, l) => {
            const depth = Math.abs(Number(f?.properties?.depth_m ?? 0));
            if (depth > 0) l.bindTooltip(`GEBCO ${depth} m contour (NOT verified nav depth)`);
          },
        }).addTo(layer);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [oceanLayers, showBathy]);

  // --- Marine Protected Areas (Malvan Marine Sanctuary) ---------------------
  useEffect(() => {
    const layer = mpaRef.current;
    if (!layer) return;
    layer.clearLayers();
    const mpa = oceanLayers?.layers?.marine_protected_areas;
    if (!showMpa || mpa?.status !== 'LIVE' || !mpa.url) return;
    let cancelled = false;
    void fetch(mpa.url)
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (cancelled || !geo) return;
        L.geoJSON(geo, {
          style: { color: '#9333ea', weight: 2, dashArray: '4 4', fillColor: '#a855f7', fillOpacity: 0.2 },
          onEachFeature: (f, l) => {
            l.bindTooltip(`${f?.properties?.name ?? 'Protected Area'} — ${f?.properties?.restriction ?? ''}`);
          },
        }).addTo(layer);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [oceanLayers, showMpa]);

  // --- Ocean Surface Current Vectors (U/V) ----------------------------------
  useEffect(() => {
    const layer = currentsRef.current;
    if (!layer) return;
    layer.clearLayers();
    const curr = oceanLayers?.layers?.ocean_currents;
    if (!showCurrents || curr?.status !== 'LIVE' || !curr.url) return;
    let cancelled = false;
    void fetch(curr.url)
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (cancelled || !geo?.features) return;
        for (const f of geo.features) {
          const [lon, lat] = f.geometry.coordinates;
          const p = f.properties || {};
          const deg = Number(p.direction_deg ?? 0);
          const icon = L.divIcon({
            className: '',
            html: `<div style="transform:rotate(${deg}deg);color:#0f766e;font-weight:700;font-size:15px;line-height:1;text-shadow:0 0 2px #fff;">↑</div>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8],
          });
          L.marker([lat, lon], { icon, keyboard: false })
            .bindTooltip(
              `Current: ${p.speed_knots ?? '?'} kn (${p.speed_mps ?? '?'} m/s) → ${deg}° · U=${p.u_mps}, V=${p.v_mps} m/s · 1h drift ~${p.drift_1h_km ?? '?'} km`,
            )
            .addTo(layer);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [oceanLayers, showCurrents]);

  // --- Self-location marker & accuracy ring ---------------------------------
  useEffect(() => {
    const layer = myLocLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!myLoc) return;
    if (myLoc.accuracy_m && myLoc.accuracy_m > 0) {
      L.circle([myLoc.latitude, myLoc.longitude], {
        radius: myLoc.accuracy_m,
        color: '#2563eb',
        weight: 1,
        fillColor: '#3b82f6',
        fillOpacity: 0.14,
        interactive: false,
      }).addTo(layer);
    }
    L.circleMarker([myLoc.latitude, myLoc.longitude], {
      radius: 7,
      color: '#ffffff',
      weight: 2.5,
      fillColor: '#2563eb',
      fillOpacity: 1,
    })
      .bindTooltip(
        `${tr('My location', 'माझे सध्याचे स्थान')}${myLoc.accuracy_m ? ` (±${Math.round(myLoc.accuracy_m)} m)` : ''}`,
        { direction: 'top' },
      )
      .addTo(layer);
  }, [myLoc, mr]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Picked point pin & direct bearing line from self-location ------------
  useEffect(() => {
    const layer = pickedLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (sel?.kind !== 'point') return;
    L.circleMarker([sel.latitude, sel.longitude], {
      radius: 7,
      color: '#ffffff',
      weight: 2.5,
      fillColor: '#0284c7',
      fillOpacity: 1,
    })
      .bindTooltip(tr('Selected point', 'निवडलेला बिंदू'), { direction: 'top' })
      .addTo(layer);
    if (myLoc) {
      L.polyline(
        [[myLoc.latitude, myLoc.longitude], [sel.latitude, sel.longitude]],
        { color: '#0284c7', weight: 2, dashArray: '5 5', interactive: false },
      ).addTo(layer);
    }
  }, [sel, myLoc, mr]); // eslint-disable-line react-hooks/exhaustive-deps

  const locateMe = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocError(tr('GPS is not supported by this browser.', 'या ब्राउझरमध्ये GPS उपलब्ध नाही.'));
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next: SelfLocation = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy_m: Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null,
        };
        setMyLoc(next);
        setLocating(false);
        const map = mapRef.current;
        if (map) map.setView([next.latitude, next.longitude], Math.max(map.getZoom(), 10));
      },
      (err) => {
        setLocating(false);
        setLocError(err.message || tr('Could not get your location.', 'सध्याचे स्थान मिळू शकले नाही.'));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    );
  };

  // Suppress unused import lint if drift estimate helper isn't needed elsewhere in this file
  void estimateCurrentDrift;

  const counts = useMemo(() => ({
    high: data.predictions.filter((c) => c.predicted_apparent_fishing_binary === 1).length,
    pfz: data.pfz_advisory.count,
  }), [data]);
  const isSeasonal =
    data.metadata.prediction_mode === 'seasonal_climatology' ||
    data.predictions[0]?.prediction_mode === 'seasonal_climatology';
  const seasonalAnchor =
    data.metadata.seasonal_anchor_date ?? data.predictions[0]?.seasonal_anchor_date ?? null;

  return (
    <div className={`map-frame${flush ? ' flush' : ''}`} style={{ height, minHeight: 420 }}>
      <div ref={containerRef} className="map-canvas" />

      {showControls && (
        <div className="map-panel map-layers">
          <button className="map-layers-title" onClick={() => setLayersOpen((o) => !o)} aria-expanded={layersOpen}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><Layers size={14} aria-hidden />{tr('Layers', 'स्तर')}</span>
            <span aria-hidden style={{ fontWeight: 400 }}>{layersOpen ? '−' : '+'}</span>
          </button>
          {layersOpen && (
            <div style={{ paddingTop: 4 }}>
              <Switch checked={showGrid} onChange={setShowGrid}>
                {tr('Predicted activity', 'अपेक्षित हालचाल')} <span className="text-xs text-muted num">{counts.high} {tr('high', 'जास्त')}</span>
              </Switch>
              <Switch checked={showPfz} onChange={setShowPfz}>
                {tr('INCOIS PFZ', 'INCOIS PFZ')} <span className="text-xs text-muted num">{counts.pfz}</span>
              </Switch>
              <Switch checked={showLanding} onChange={setShowLanding}>{tr('Landing centres', 'लँडिंग केंद्रे')}</Switch>
              {oceanLayers?.layers?.bathymetry?.status === 'LIVE' && (
                <Switch checked={showBathy} onChange={setShowBathy}>
                  {tr('GEBCO depth (10–200 m)', 'GEBCO खोली (10–200 मी)')}
                </Switch>
              )}
              {oceanLayers?.layers?.marine_protected_areas?.status === 'LIVE' && (
                <Switch checked={showMpa} onChange={setShowMpa}>
                  {tr('Marine protected areas', 'सागरी अभयारण्ये')}
                </Switch>
              )}
              {oceanLayers?.layers?.ocean_currents?.status === 'LIVE' && (
                <Switch checked={showCurrents} onChange={setShowCurrents}>
                  {tr('Ocean currents (U/V)', 'समुद्री प्रवाह (U/V)')}
                </Switch>
              )}
              {oceanLayers?.layers?.chlorophyll?.status === 'LIVE' && (
                <Switch checked={showChla} onChange={(v) => { setShowChla(v); if (v) setShowSst(false); }}>
                  {tr('Chlorophyll-a (VIIRS)', 'क्लोरोफिल-a (VIIRS)')}
                </Switch>
              )}
              {oceanLayers?.layers?.sst?.status === 'LIVE' && (
                <Switch checked={showSst} onChange={(v) => { setShowSst(v); if (v) setShowChla(false); }}>
                  {tr('Sea surface temp (MUR)', 'समुद्र पृष्ठभाग तापमान')}
                </Switch>
              )}
            </div>
          )}
        </div>
      )}

      {showControls && !sel && (
        <div className="map-panel map-legend" aria-label="Legend">
          <div className="text-xs fw-600 text-muted" style={{ marginBottom: 4 }}>
            {isSeasonal
              ? tr('GFW seasonal pattern (2020–2024 ref)', 'GFW हंगामी पॅटर्न (२०२०–२०२४ संदर्भ)')
              : tr('Predicted fishing activity', 'अपेक्षित मासेमारी हालचाल')}
          </div>
          {isSeasonal && seasonalAnchor && (
            <div className="text-xs text-muted" style={{ marginBottom: 4 }}>
              {tr(`Seasonal anchor: ${seasonalAnchor}`, `हंगामी संदर्भ: ${seasonalAnchor}`)}
            </div>
          )}
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(29,95,180,0.55)' }} />{tr('High (above calibrated threshold)', 'जास्त (प्रमाणित मर्यादेपेक्षा अधिक)')}</div>
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(91,155,224,0.4)' }} />{tr('Moderate (near threshold)', 'मध्यम (मर्यादेजवळ)')}</div>
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(169,205,242,0.4)' }} />{tr('Low baseline gradient', 'कमी आधारभूत हालचाल')}</div>
          <hr className="divider" style={{ margin: '6px 0' }} />
          <div className="legend-row"><span className="legend-marker" style={{ background: '#0f8a66' }} />{tr('INCOIS PFZ advisory', 'INCOIS PFZ सल्ला')}</div>
          <div className="legend-row"><span className="landing-pin" style={{ marginLeft: 1 }} />{tr('Landing centre', 'लँडिंग केंद्र')}</div>
          {showBathy && oceanLayers?.layers?.bathymetry?.status === 'LIVE' && (
            <div className="legend-row"><span className="legend-swatch" style={{ background: '#d97706' }} />{tr('GEBCO 10/20m shallow (not nav chart)', 'GEBCO 10/20 मी उथळ (नेव्हिगेशन तक्ता नाही)')}</div>
          )}
          {showMpa && oceanLayers?.layers?.marine_protected_areas?.status === 'LIVE' && (
            <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(168,85,247,0.5)' }} />{tr('Protected area (Malvan MPA)', 'सागरी अभयारण्य (मालवण)')}</div>
          )}
          {showChla && oceanLayers?.layers?.chlorophyll?.observation_timestamp && (
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              Chl-a (mg/m³) · {fmtDateTime(oceanLayers.layers.chlorophyll.observation_timestamp)}
            </div>
          )}
          {showSst && oceanLayers?.layers?.sst?.acquisition_date && (
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              SST (°C) · {fmtDateTime(oceanLayers.layers.sst.acquisition_date)}
            </div>
          )}
        </div>
      )}

      {showControls && (
        <div style={{ position: 'absolute', bottom: 26, right: 54, zIndex: 500, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          {locError && (
            <div style={{ background: 'rgba(15,23,42,0.9)', color: '#fca5a5', padding: '4px 8px', borderRadius: 6, fontSize: 11, maxWidth: 220 }}>
              {locError}
            </div>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={locateMe}
            disabled={locating}
            style={{ boxShadow: '0 2px 8px rgba(15,23,42,0.18)', background: myLoc ? '#eff6ff' : undefined, color: myLoc ? '#1d4ed8' : undefined }}
          >
            <LocateFixed size={14} aria-hidden />
            {locating ? tr('Locating…', 'शोधत आहे…') : myLoc ? tr('My location', 'माझे स्थान') : tr('Locate me', 'सध्याचे स्थान')}
          </button>
        </div>
      )}

      {sel && (
        <div className="map-panel map-inspector" role="dialog" aria-label={tr('Details', 'तपशील')}>
          <div className="map-inspector-header">
            <div className="fw-600">
              {sel.kind === 'cell'
                ? tr('Grid cell', 'ग्रिड क्षेत्र')
                : sel.kind === 'pfz'
                  ? tr('INCOIS PFZ advisory', 'INCOIS PFZ सल्ला')
                  : tr('Selected location', 'निवडलेले स्थान')}
            </div>
            <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setSel(null)} aria-label={tr('Close', 'बंद करा')}><X size={16} /></button>
          </div>
          {sel.kind === 'cell' ? (
            <CellDetail cell={sel.cell} data={data} mr={mr} myLoc={myLoc} />
          ) : sel.kind === 'pfz' ? (
            <PfzDetail pfz={sel.pfz} index={sel.index} data={data} mr={mr} myLoc={myLoc} />
          ) : (
            <PointDetail latitude={sel.latitude} longitude={sel.longitude} data={data} mr={mr} myLoc={myLoc} onLocateMe={locateMe} locating={locating} />
          )}
        </div>
      )}
    </div>
  );
}

function CellDetail({ cell, data, mr, myLoc }: { cell: CellPrediction; data: MapSummaryResponse; mr: boolean; myLoc: SelfLocation | null }) {
  const tr = (en: string, m: string) => (mr ? m : en);
  const district = districtOf(data.landing_centres, cell.latitude, cell.longitude);
  const calLabel = cell.calibration_method
    ? `${cell.calibration_method[0].toUpperCase()}${cell.calibration_method.slice(1)} ${tr('calibrated', 'कॅलिब्रेटेड')}`
    : null;
  const navParams: Record<string, string | number> = { lat: cell.latitude.toFixed(4), lon: cell.longitude.toFixed(4) };
  if (myLoc) {
    navParams.olat = myLoc.latitude.toFixed(5);
    navParams.olon = myLoc.longitude.toFixed(5);
  }
  return (
    <div className="map-inspector-body">
      <div>
        <div className="text-xs text-muted">{tr('Marine safety (independent of AI)', 'सागरी सुरक्षा (AI पासून स्वतंत्र)')}</div>
        <div style={{ marginTop: 4 }}><StatusBadge meta={safetyMeta(cell.safety_status)} mr={mr} long /></div>
      </div>
      <dl className="kv">
        <dt>{tr('Predicted activity', 'अपेक्षित हालचाल')}</dt>
        <dd className="fw-600">{fmtPct(cell.predicted_apparent_fishing_probability)}</dd>
        {cell.habitat_suitability_score != null && (
          <>
            <dt>{tr('Habitat suitability', 'अधिवास योग्यता')}</dt>
            <dd className="fw-600">{fmtPct(cell.habitat_suitability_score)}</dd>
          </>
        )}
        <dt>{tr('Classification', 'वर्गीकरण')}</dt>
        <dd>{cell.predicted_apparent_fishing_binary === 1 ? tr('High', 'जास्त') : tr('Low', 'कमी')}</dd>
        <dt>{tr('District', 'जिल्हा')}</dt>
        <dd>{district ? districtLabel(district, mr) : '—'}</dd>
        <dt>{tr('From nearest centre', 'जवळच्या केंद्रापासून')}</dt>
        <dd>{cell.distance_to_coast_km.toFixed(1)} km</dd>
        <dt>{tr('Location', 'स्थान')}</dt>
        <dd className="kbd-coord">{fmtCoord(cell.latitude, cell.longitude, 2)}</dd>
        <dt>{tr('Model', 'मॉडेल')}</dt>
        <dd className="text-xs">{cell.model_version}{calLabel ? ` · ${calLabel}` : ''}</dd>
        {cell.prediction_mode === 'seasonal_climatology' && (
          <>
            <dt>{tr('Reference basis', 'संदर्भ आधार')}</dt>
            <dd className="text-xs">
              {tr('2020–2024 seasonal climatology', '२०२०–२०२४ हंगामी संदर्भ')}
              {cell.seasonal_anchor_date ? ` (${cell.seasonal_anchor_date})` : ''}
            </dd>
          </>
        )}
      </dl>
      <p className="text-xs text-muted">
        {cell.prediction_mode === 'seasonal_climatology'
          ? tr(
              'Combines 2020–2024 seasonal GFW vessel patterns with ocean habitat suitability (SST, Chl-a, GEBCO depth). Use alongside live INCOIS PFZ; does not guarantee catch or safety.',
              '२०२०–२०२४ हंगामी नौका पॅटर्न आणि सागरी अधिवास योग्यता (SST, Chl-a, GEBCO खोली) एकत्र करतो. थेट INCOIS PFZ सोबत वापरा; पकड किंवा सुरक्षिततेची हमी देत नाही.',
            )
          : tr(
              'Phase 4 spatio-oceanographic forecast combining SST/Chl-a/depth habitat cues with neighboring fleet activity. Not a prediction of fish presence or catch.',
              'समुद्री तापमान, क्लोरोफिल, खोली आणि शेजारील नौका हालचालींवर आधारित फेज ४ अंदाज. माशांची उपस्थिती किंवा पकड यांचा अंदाज नाही.',
            )}
      </p>
      <a className="btn btn-secondary btn-sm" href={href('navigation', navParams)}>
        <Navigation size={14} aria-hidden />{myLoc ? tr('Navigate from my location', 'माझ्या स्थानावरून मार्गक्रमण करा') : tr('Plan a trip here', 'येथे सफर नियोजित करा')}
      </a>
    </div>
  );
}

function PfzDetail({ pfz, index, data, mr, myLoc }: { pfz: PFZLocation; index: number; data: MapSummaryResponse; mr: boolean; myLoc: SelfLocation | null }) {
  const tr = (en: string, m: string) => (mr ? m : en);
  const district = districtOf(data.landing_centres, pfz.latitude, pfz.longitude);
  const depth = pfz.depth_min_m != null || pfz.depth_max_m != null ? `${pfz.depth_min_m ?? '?'}–${pfz.depth_max_m ?? '?'} m` : '—';
  const navParams: Record<string, string | number> = { pfz: index };
  if (myLoc) {
    navParams.olat = myLoc.latitude.toFixed(5);
    navParams.olon = myLoc.longitude.toFixed(5);
  }
  return (
    <div className="map-inspector-body">
      <dl className="kv">
        <dt>{tr('Reference centre', 'संदर्भ केंद्र')}</dt><dd className="fw-600">{pfz.landing_centre}</dd>
        <dt>{tr('District', 'जिल्हा')}</dt><dd>{district ? districtLabel(district, mr) : '—'}</dd>
        <dt>{tr('Direction', 'दिशा')}</dt><dd>{pfz.direction} · {pfz.bearing_degrees}°</dd>
        <dt>{tr('Distance', 'अंतर')}</dt><dd>{parseKm(pfz.distance_km)?.toFixed(0) ?? pfz.distance_km} km</dd>
        <dt>{tr('Depth', 'खोली')}</dt><dd>{depth}</dd>
        <dt>{tr('Location', 'स्थान')}</dt><dd className="kbd-coord">{fmtCoord(pfz.latitude, pfz.longitude, 3)}</dd>
        <dt>{tr('Valid until', 'वैध')}</dt><dd>{fmtDate(data.pfz_advisory.validity_date)}</dd>
      </dl>
      <p className="text-xs text-muted">{tr('Official Government of India advisory (INCOIS). Independent of the AI model.', 'भारत सरकारचा अधिकृत सल्ला (INCOIS). AI मॉडेलपासून स्वतंत्र.')}</p>
      <a className="btn btn-primary btn-sm" href={href('navigation', navParams)}>
        <Navigation size={14} aria-hidden />{myLoc ? tr('Navigate from my location', 'माझ्या स्थानावरून येथे जा') : tr('Plan trip to this zone', 'या क्षेत्राकडे सफर नियोजित करा')}
      </a>
    </div>
  );
}

function PointDetail({
  latitude,
  longitude,
  data,
  mr,
  myLoc,
  onLocateMe,
  locating,
}: {
  latitude: number;
  longitude: number;
  data: MapSummaryResponse;
  mr: boolean;
  myLoc: SelfLocation | null;
  onLocateMe: () => void;
  locating: boolean;
}) {
  const tr = (en: string, m: string) => (mr ? m : en);
  const onLand = isPointOnLand(latitude, longitude);
  const nearest = nearestCentre(data.landing_centres, latitude, longitude);
  const fromMeKm = myLoc ? haversineKm(myLoc.latitude, myLoc.longitude, latitude, longitude) : null;
  const fromMeBrg = myLoc ? initialBearingDeg(myLoc.latitude, myLoc.longitude, latitude, longitude) : null;
  const navParams: Record<string, string | number> = { lat: latitude.toFixed(5), lon: longitude.toFixed(5) };
  if (myLoc) {
    navParams.olat = myLoc.latitude.toFixed(5);
    navParams.olon = myLoc.longitude.toFixed(5);
  }
  return (
    <div className="map-inspector-body">
      <dl className="kv">
        <dt>{tr('Location', 'स्थान')}</dt>
        <dd className="kbd-coord">{fmtCoord(latitude, longitude, 4)}</dd>
        <dt>{tr('Surface', 'क्षेत्र')}</dt>
        <dd>{onLand ? tr('Land / Coast', 'जमीन / किनारा') : tr('Arabian Sea', 'अरबी समुद्र')}</dd>
        {nearest && (
          <>
            <dt>{tr('Nearest centre', 'जवळचे केंद्र')}</dt>
            <dd>{mr && nearest.centre.name_mr ? nearest.centre.name_mr : nearest.centre.name} ({nearest.km.toFixed(1)} km)</dd>
          </>
        )}
        {fromMeKm !== null && fromMeBrg !== null && (
          <>
            <dt>{tr('From my location', 'माझ्या स्थानापासून')}</dt>
            <dd className="fw-600">{fromMeKm.toFixed(1)} km ({kmToNm(fromMeKm).toFixed(1)} nm) · {compassPoint(fromMeBrg)} ({Math.round(fromMeBrg)}°)</dd>
          </>
        )}
      </dl>
      {!myLoc && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onLocateMe} disabled={locating}>
          <LocateFixed size={14} aria-hidden />
          {locating ? tr('Getting GPS…', 'GPS मिळवत आहे…') : tr('Use my GPS location first', 'माझे सध्याचे GPS स्थान वापरा')}
        </button>
      )}
      <a className="btn btn-primary btn-sm" href={href('navigation', navParams)}>
        <Navigation size={14} aria-hidden />
        {myLoc ? tr('Navigate to this point', 'या बिंदूकडे मार्गक्रमण करा') : tr('Navigate to point', 'या बिंदूकडे जा')}
      </a>
    </div>
  );
}
