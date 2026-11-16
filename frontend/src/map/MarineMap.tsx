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
import { Layers, Navigation, X } from 'lucide-react';
import type { CellPrediction, MapSummaryResponse, PFZLocation } from '../types/map';
import { districtLabel, districtOf } from '../lib/districts';
import { fmtCoord, fmtDate, fmtPct, parseKm } from '../lib/format';
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
  height?: number | string;
  showControls?: boolean;
  focus?: MapFocus | null;
  flush?: boolean;
  /** Start with the layer panel collapsed (compact embeds). */
  layersCollapsed?: boolean;
}

type Selection = { kind: 'cell'; cell: CellPrediction } | { kind: 'pfz'; pfz: PFZLocation; index: number } | null;

const GRID = 0.25;

/** Sequential single-hue scale (light → dark ocean blue). */
export function activityStyle(cell: CellPrediction): { fill: string; opacity: number; stroke: string } {
  const p = cell.predicted_apparent_fishing_probability;
  if (cell.predicted_apparent_fishing_binary === 1) return { fill: '#1d5fb4', opacity: 0.55, stroke: '#1d5fb4' };
  if (p >= 0.25) return { fill: '#5b9be0', opacity: 0.4, stroke: '#5b9be0' };
  if (p >= 0.1) return { fill: '#a9cdf2', opacity: 0.4, stroke: '#a9cdf2' };
  return { fill: '#ffffff', opacity: 0, stroke: '#c5d3e2' };
}

export function MarineMap({ data, mr, height = 560, showControls = true, focus = null, flush = false, layersCollapsed = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const gridRef = useRef<L.LayerGroup | null>(null);
  const pfzRef = useRef<L.LayerGroup | null>(null);
  const landingRef = useRef<L.LayerGroup | null>(null);
  const focusRef = useRef<L.CircleMarker | null>(null);

  const [showGrid, setShowGrid] = useState(true);
  const [showPfz, setShowPfz] = useState(true);
  const [showLanding, setShowLanding] = useState(true);
  const [layersOpen, setLayersOpen] = useState(() => !layersCollapsed && window.innerWidth > 720);
  const [sel, setSel] = useState<Selection>(null);

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
    gridRef.current = L.layerGroup().addTo(map);
    pfzRef.current = L.layerGroup().addTo(map);
    landingRef.current = L.layerGroup().addTo(map);
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
      rect.on('click', () => setSel({ kind: 'cell', cell }));
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
      m.on('click', () => setSel({ kind: 'pfz', pfz, index }));
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

  const counts = useMemo(() => ({
    high: data.predictions.filter((c) => c.predicted_apparent_fishing_binary === 1).length,
    pfz: data.pfz_advisory.count,
  }), [data]);

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
            </div>
          )}
        </div>
      )}

      {showControls && !sel && (
        <div className="map-panel map-legend" aria-label="Legend">
          <div className="text-xs fw-600 text-muted" style={{ marginBottom: 4 }}>{tr('Predicted fishing activity', 'अपेक्षित मासेमारी हालचाल')}</div>
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(29,95,180,0.55)' }} />{tr('High (above model threshold)', 'जास्त (मॉडेल मर्यादेपेक्षा अधिक)')}</div>
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(91,155,224,0.4)' }} />{tr('Moderate (25%+)', 'मध्यम (25%+)')}</div>
          <div className="legend-row"><span className="legend-swatch" style={{ background: 'rgba(169,205,242,0.4)' }} />{tr('Low (10–25%)', 'कमी (10–25%)')}</div>
          <hr className="divider" style={{ margin: '6px 0' }} />
          <div className="legend-row"><span className="legend-marker" style={{ background: '#0f8a66' }} />{tr('INCOIS PFZ advisory', 'INCOIS PFZ सल्ला')}</div>
          <div className="legend-row"><span className="landing-pin" style={{ marginLeft: 1 }} />{tr('Landing centre', 'लँडिंग केंद्र')}</div>
        </div>
      )}

      {sel && (
        <div className="map-panel map-inspector" role="dialog" aria-label={tr('Details', 'तपशील')}>
          <div className="map-inspector-header">
            <div className="fw-600">
              {sel.kind === 'cell' ? tr('Grid cell', 'ग्रिड क्षेत्र') : tr('INCOIS PFZ advisory', 'INCOIS PFZ सल्ला')}
            </div>
            <button className="btn btn-ghost btn-sm btn-icon" onClick={() => setSel(null)} aria-label={tr('Close', 'बंद करा')}><X size={16} /></button>
          </div>
          {sel.kind === 'cell' ? (
            <CellDetail cell={sel.cell} data={data} mr={mr} />
          ) : (
            <PfzDetail pfz={sel.pfz} index={sel.index} data={data} mr={mr} />
          )}
        </div>
      )}
    </div>
  );
}

function CellDetail({ cell, data, mr }: { cell: CellPrediction; data: MapSummaryResponse; mr: boolean }) {
  const tr = (en: string, m: string) => (mr ? m : en);
  const district = districtOf(data.landing_centres, cell.latitude, cell.longitude);
  return (
    <div className="map-inspector-body">
      <div>
        <div className="text-xs text-muted">{tr('Marine safety (independent of AI)', 'सागरी सुरक्षा (AI पासून स्वतंत्र)')}</div>
        <div style={{ marginTop: 4 }}><StatusBadge meta={safetyMeta(cell.safety_status)} mr={mr} long /></div>
      </div>
      <dl className="kv">
        <dt>{tr('Predicted activity', 'अपेक्षित हालचाल')}</dt>
        <dd className="fw-600">{fmtPct(cell.predicted_apparent_fishing_probability)}</dd>
        <dt>{tr('Classification', 'वर्गीकरण')}</dt>
        <dd>{cell.predicted_apparent_fishing_binary === 1 ? tr('High', 'जास्त') : tr('Low', 'कमी')}</dd>
        <dt>{tr('District', 'जिल्हा')}</dt>
        <dd>{district ? districtLabel(district, mr) : '—'}</dd>
        <dt>{tr('From nearest centre', 'जवळच्या केंद्रापासून')}</dt>
        <dd>{cell.distance_to_coast_km.toFixed(1)} km</dd>
        <dt>{tr('Location', 'स्थान')}</dt>
        <dd className="kbd-coord">{fmtCoord(cell.latitude, cell.longitude, 2)}</dd>
        <dt>{tr('Model', 'मॉडेल')}</dt>
        <dd className="text-xs">{cell.model_version}</dd>
      </dl>
      <p className="text-xs text-muted">
        {tr(
          'Next-day apparent fishing activity from historical vessel tracking. Not a prediction of fish presence or catch.',
          'ऐतिहासिक नौका हालचालींवर आधारित उद्याची अपेक्षित मासेमारी हालचाल. माशांची उपस्थिती किंवा पकड यांचा अंदाज नाही.',
        )}
      </p>
      <a className="btn btn-secondary btn-sm" href={href('navigation', { lat: cell.latitude.toFixed(4), lon: cell.longitude.toFixed(4) })}>
        <Navigation size={14} aria-hidden />{tr('Plan a trip here', 'येथे सफर नियोजित करा')}
      </a>
    </div>
  );
}

function PfzDetail({ pfz, index, data, mr }: { pfz: PFZLocation; index: number; data: MapSummaryResponse; mr: boolean }) {
  const tr = (en: string, m: string) => (mr ? m : en);
  const district = districtOf(data.landing_centres, pfz.latitude, pfz.longitude);
  const depth = pfz.depth_min_m != null || pfz.depth_max_m != null ? `${pfz.depth_min_m ?? '?'}–${pfz.depth_max_m ?? '?'} m` : '—';
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
      <a className="btn btn-primary btn-sm" href={href('navigation', { pfz: index })}>
        <Navigation size={14} aria-hidden />{tr('Plan trip to this zone', 'या क्षेत्राकडे सफर नियोजित करा')}
      </a>
    </div>
  );
}
