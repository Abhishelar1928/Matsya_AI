/**
 * At-sea screen: offline map + live GPS navigation.
 * Shows position, heading, bearing/distance to target, cross-track error,
 * ETA, nearest emergency return harbour and the offline-evaluated safety status.
 * Records track points to IndexedDB every 30 s or 50 m.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { createOfflineBasemap, loadBathymetry, OCEAN_BG } from './basemap';
import { addTrackPoint, newUuid } from './db';
import { compassPoint, etaMinutes, haversineKm, headingError, initialBearingDeg, kmToNm, mpsToKnots, routeProgress } from './geo';
import { evaluatePackageSafety, currentConditions } from './offlineSafety';
import { gpsHelp, type GeoState } from './useGeolocation';
import { Badge, Button, Card, colors, safetyLabel, safetyTone, Stat } from './ui';
import type { ExpeditionPackage } from './types';
import { t } from '../i18n';

interface Props {
  pkg: ExpeditionPackage;
  isMarathi: boolean;
  online: boolean;
  geo: GeoState;
  simulating: boolean;
  onToggleSimulation: () => void;
  onLogCatch: () => void;
  onEnd: () => void;
}

const TRACK_INTERVAL_MS = 30_000;
const TRACK_MIN_KM = 0.05;

export function AtSea({ pkg, isMarathi, online, geo, simulating, onToggleSimulation, onLogCatch, onEnd }: Props) {
  const [now, setNow] = useState(Date.now());
  const [basemapKind, setBasemapKind] = useState<'pmtiles' | 'fallback' | null>(null);
  const [trackCount, setTrackCount] = useState(0);

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInst = useRef<L.Map | null>(null);
  const vesselRef = useRef<L.CircleMarker | null>(null);
  const bearingLineRef = useRef<L.Polyline | null>(null);
  const trailRef = useRef<L.Polyline | null>(null);
  const lastSaved = useRef<{ t: number; lat: number; lon: number } | null>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const dest = pkg.destination;
  const fix = geo.fix;

  const nav = useMemo(() => {
    if (!fix) return null;
    const distKm = haversineKm(fix.latitude, fix.longitude, dest.latitude, dest.longitude);
    const brg = initialBearingDeg(fix.latitude, fix.longitude, dest.latitude, dest.longitude);
    const prog = routeProgress(pkg.route.waypoints, fix.latitude, fix.longitude);
    const nearest = pkg.emergency_returns
      .map((r) => ({ ...r, dist: haversineKm(fix.latitude, fix.longitude, r.latitude, r.longitude), brg: initialBearingDeg(fix.latitude, fix.longitude, r.latitude, r.longitude) }))
      .sort((a, b) => a.dist - b.dist)[0];
    return {
      distKm, brg, prog, nearest,
      eta: etaMinutes(distKm, fix.speed_mps),
      hdgErr: fix.heading_deg !== null ? headingError(fix.heading_deg, brg) : null,
    };
  }, [fix, dest, pkg]);

  const safety = useMemo(() => evaluatePackageSafety(pkg, fix?.latitude ?? null, fix?.longitude ?? null, now), [pkg, fix, now]);
  const cond = useMemo(() => currentConditions(pkg, fix?.latitude ?? null, fix?.longitude ?? null, now), [pkg, fix, now]);

  // --- Map init -------------------------------------------------------------
  useEffect(() => {
    if (!mapRef.current || mapInst.current) return;
    const map = L.map(mapRef.current, {
      center: [(pkg.landing_centre.latitude + dest.latitude) / 2, (pkg.landing_centre.longitude + dest.longitude) / 2],
      zoom: 9, minZoom: 6, maxZoom: 13, zoomControl: false,
    });
    mapRef.current.style.background = OCEAN_BG;
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ metric: true, imperial: false, position: 'bottomleft' }).addTo(map);
    mapInst.current = map;

    let cancelled = false;
    (async () => {
      const { layer, kind } = await createOfflineBasemap(pkg);
      if (cancelled) return;
      layer.addTo(map);
      setBasemapKind(kind);
      const bathy = await loadBathymetry(pkg);
      if (bathy && !cancelled) bathy.addTo(map);
    })();

    const overlay = L.layerGroup().addTo(map);
    // Route
    L.polyline(pkg.route.waypoints.map((w) => [w.latitude, w.longitude] as [number, number]), { color: colors.accent, weight: 2, dashArray: '6 6' }).addTo(overlay);
    pkg.route.waypoints.forEach((w) => {
      if (w.index === 0 || w.index === pkg.route.waypoints.length - 1) return;
      L.circleMarker([w.latitude, w.longitude], { radius: 3, color: '#ffffff', fillColor: colors.accent, fillOpacity: 1, weight: 1.5 }).addTo(overlay);
    });
    pkg.route.land_crossings.forEach((c) => {
      L.circleMarker([c.latitude, c.longitude], { radius: 5, color: colors.red, fillColor: colors.red, fillOpacity: 0.9 }).bindTooltip('Land crossing').addTo(overlay);
    });
    // Destination & start
    L.circleMarker([dest.latitude, dest.longitude], { radius: 9, color: '#ffffff', fillColor: colors.accent, fillOpacity: 1, weight: 3 }).bindTooltip(dest.name).addTo(overlay);
    L.circleMarker([pkg.landing_centre.latitude, pkg.landing_centre.longitude], { radius: 6, color: '#ffffff', fillColor: colors.landing, fillOpacity: 1, weight: 2 }).bindTooltip(pkg.landing_centre.name).addTo(overlay);
    // PFZ
    pkg.pfz.locations.forEach((loc) => {
      L.circleMarker([loc.latitude, loc.longitude], { radius: 5, color: '#ffffff', fillColor: colors.pfz, fillOpacity: 1, weight: 1.5 })
        .bindTooltip(`PFZ ${loc.landing_centre} ${loc.direction} ${loc.distance_km} km`).addTo(overlay);
    });
    // Predictions (high cells only, subtle)
    pkg.predictions.cells.filter((c) => c.high === 1).forEach((c) => {
      L.rectangle([[c.lat - 0.125, c.lon - 0.125], [c.lat + 0.125, c.lon + 0.125]], { color: '#1d5fb4', weight: 0.6, fillColor: '#1d5fb4', fillOpacity: 0.18, interactive: false }).addTo(overlay);
    });
    // Emergency returns
    pkg.emergency_returns.forEach((r) => {
      L.circleMarker([r.latitude, r.longitude], { radius: 4, color: '#ffffff', fillColor: colors.landing, fillOpacity: 0.85, weight: 1.5 }).bindTooltip(`${r.name}`).addTo(overlay);
    });

    trailRef.current = L.polyline([], { color: colors.landing, weight: 2, opacity: 0.6 }).addTo(map);
    bearingLineRef.current = L.polyline([], { color: colors.landing, weight: 1, dashArray: '2 5', opacity: 0.6 }).addTo(map);
    vesselRef.current = L.circleMarker([pkg.landing_centre.latitude, pkg.landing_centre.longitude], { radius: 8, color: '#ffffff', fillColor: '#f79009', fillOpacity: 1, weight: 3 }).addTo(map);

    map.on('dragstart', () => setFollow(false));

    return () => { cancelled = true; map.remove(); mapInst.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pkg.manifest.package_id]);

  // --- Vessel marker, trail, track recording ---------------------------------
  useEffect(() => {
    if (!fix || !mapInst.current) return;
    const ll: [number, number] = [fix.latitude, fix.longitude];
    vesselRef.current?.setLatLng(ll);
    bearingLineRef.current?.setLatLngs([ll, [dest.latitude, dest.longitude]]);
    if (follow) mapInst.current.panTo(ll, { animate: true });

    // Simulated positions are for testing only — never stored or synced as real track.
    if (fix.simulated) {
      trailRef.current?.addLatLng(ll);
      return;
    }

    const last = lastSaved.current;
    const moved = last ? haversineKm(last.lat, last.lon, fix.latitude, fix.longitude) : Infinity;
    const elapsed = last ? fix.timestamp - last.t : Infinity;
    if (moved >= TRACK_MIN_KM || elapsed >= TRACK_INTERVAL_MS) {
      lastSaved.current = { t: fix.timestamp, lat: fix.latitude, lon: fix.longitude };
      trailRef.current?.addLatLng(ll);
      void addTrackPoint({
        client_uuid: newUuid(),
        expedition_id: pkg.manifest.package_id,
        recorded_at: new Date(fix.timestamp).toISOString(),
        latitude: fix.latitude,
        longitude: fix.longitude,
        speed_mps: fix.speed_mps,
        heading_deg: fix.heading_deg,
        accuracy_m: fix.accuracy_m,
        synced: 0,
      }).then(() => setTrackCount((n) => n + 1));
    }
  }, [fix, dest, follow, pkg.manifest.package_id]);

  const fmtKm = (km: number) => `${km.toFixed(1)} km`;
  const fmtNm = (km: number) => `${kmToNm(km).toFixed(1)} nm`;

  return (
    <div>
      {/* Safety — evaluated offline from packaged data; never green on expired data */}
      <div className={`callout callout-${safetyTone(safety.status)}`} style={{ marginBottom: 16 }} role="status">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="callout-title">{safetyLabel(safety.status, isMarathi)}</div>
          <div className="callout-text">{safety.reason}</div>
          {(safety.warnings_expired || safety.forecast_expired) && (
            <div className="callout-text fw-600" style={{ color: 'var(--warning)' }}>{t('exp_safety_expired')}</div>
          )}
          <div className="callout-meta">
            {cond.forecast_time && <span>{isMarathi ? 'अंदाज' : 'Forecast'} {new Date(cond.forecast_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
            {cond.wave_height_m !== null && <span>{isMarathi ? 'लाटा' : 'Waves'} {cond.wave_height_m.toFixed(1)} m</span>}
            {cond.wind_speed_kmh !== null && <span>{isMarathi ? 'वारा' : 'Wind'} {cond.wind_speed_kmh.toFixed(0)} km/h</span>}
            <Badge color={online ? colors.green : colors.slate}>{online ? t('exp_online') : t('exp_offline')}</Badge>
          </div>
        </div>
      </div>

      <div style={{ position: 'relative' }}>
        <div className="map-frame" style={{ height: 440 }}><div ref={mapRef} className="map-canvas" style={{ background: OCEAN_BG }} /></div>
        <div style={{ position: 'absolute', top: 12, left: 12, zIndex: 800, display: 'flex', gap: 6 }}>
          <Badge color={basemapKind === 'pmtiles' ? colors.green : colors.slate}>{basemapKind === 'pmtiles' ? 'Offline map' : basemapKind === 'fallback' ? 'Grid only' : '…'}</Badge>
          {geo.wakeLock && <Badge color={colors.accent}>Screen on</Badge>}
        </div>
        {!follow && (
          <button className="btn btn-secondary btn-sm" onClick={() => setFollow(true)} style={{ position: 'absolute', top: 12, right: 12, zIndex: 800 }}>{isMarathi ? 'बोटीवर केंद्रित करा' : 'Recenter'}</button>
        )}
      </div>
      <div className="text-xs text-muted" style={{ margin: '8px 0 16px' }}>{t('exp_not_chart')}</div>

      {(() => {
        const help = gpsHelp(geo, isMarathi);
        return (
          <Card style={{ borderColor: help || simulating ? 'var(--warning-border)' : undefined }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 14 }}>
                <strong>GPS:</strong>{' '}
                {simulating ? <Badge color={colors.amber}>{isMarathi ? 'सिम्युलेशन' : 'Simulated'}</Badge>
                  : fix ? <Badge color={colors.green}>{isMarathi ? 'चालू' : 'Fix'} ±{fix.accuracy_m?.toFixed(0) ?? '?'} m</Badge>
                  : <Badge color={colors.slate}>{t('exp_waiting_gps')}</Badge>}
                {!simulating && !geo.highAccuracy && <span style={{ fontSize: 11, color: colors.muted }}> · {isMarathi ? 'कमी अचूकता (Wi-Fi)' : 'low-accuracy mode (Wi-Fi)'}</span>}
                {!simulating && geo.permission !== 'unknown' && <span style={{ fontSize: 11, color: colors.muted }}> · permission: {geo.permission}</span>}
              </div>
              <button className="btn btn-secondary btn-sm" onClick={onToggleSimulation}>
                {simulating ? (isMarathi ? 'सिम्युलेशन थांबवा' : 'Stop simulation') : (isMarathi ? 'GPS सिम्युलेशन' : 'Simulate GPS')}
              </button>
            </div>
            {help && !simulating && (
              <div style={{ marginTop: 10 }}>
                <div className="fw-600" style={{ color: 'var(--warning)' }}>{help.title}</div>
                <ol className="text-secondary" style={{ margin: '6px 0 0 18px', padding: 0, fontSize: 13, lineHeight: 1.6 }}>
                  {help.steps.map((s) => <li key={s}>{s}</li>)}
                </ol>
                {geo.error && <div style={{ fontSize: 11, color: colors.muted, marginTop: 4 }}>Browser: {geo.error}</div>}
              </div>
            )}
            {simulating && (
              <div className="text-sm" style={{ color: 'var(--warning)', marginTop: 8 }}>
                {isMarathi ? 'चाचणी मोड: बनावट बोट मार्गावरून फिरते. ही स्थाने जतन किंवा सिंक केली जात नाहीत.' : 'Test mode: a fake vessel moves along the route at 60 kn. These positions are not saved or synced.'}
              </div>
            )}
          </Card>
        );
      })()}

      {fix && nav && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 16 }}>
            <Stat big label={t('exp_to_target')} value={fmtKm(nav.distKm)} sub={`${fmtNm(nav.distKm)} · ${nav.brg.toFixed(0)}° ${compassPoint(nav.brg)}`} />
            <Stat big label={t('exp_heading')} value={fix.heading_deg !== null ? `${fix.heading_deg.toFixed(0)}° ${compassPoint(fix.heading_deg)}` : '—'}
              sub={nav.hdgErr !== null ? (Math.abs(nav.hdgErr) < 5 ? 'On course' : `${nav.hdgErr > 0 ? 'Turn right' : 'Turn left'} ${Math.abs(nav.hdgErr).toFixed(0)}°`) : undefined} />
            <Stat label={t('exp_speed')} value={fix.speed_mps !== null ? `${mpsToKnots(fix.speed_mps).toFixed(1)} kn` : '—'} sub={fix.speed_mps !== null ? `${(fix.speed_mps * 3.6).toFixed(1)} km/h` : undefined} />
            <Stat label={t('exp_eta')} value={nav.eta !== null ? (nav.eta > 90 ? `${(nav.eta / 60).toFixed(1)} h` : `${Math.round(nav.eta)} min`) : '—'} />
            <Stat label={t('exp_off_track')} value={nav.prog ? `${Math.abs(nav.prog.crossTrackKm).toFixed(2)} km ${nav.prog.crossTrackKm < 0 ? '←' : '→'}` : '—'}
              sub={nav.prog ? `${t('exp_waypoint')} ${nav.prog.nextWaypointIndex}/${pkg.route.waypoints.length - 1} · ${fmtKm(nav.prog.distanceToNextKm)}` : undefined} />
            <Stat label={t('exp_position')} value={<span style={{ fontSize: 15 }}>{fix.latitude.toFixed(4)}°N<br />{fix.longitude.toFixed(4)}°E</span>} sub={fix.accuracy_m ? `±${fix.accuracy_m.toFixed(0)} m` : undefined} />
          </div>

          <Card title={t('exp_nearest_return')}>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{isMarathi ? nav.nearest.name_mr : nav.nearest.name} <span style={{ fontSize: 13, color: colors.muted }}>({nav.nearest.district})</span></div>
            <div style={{ fontSize: 15, marginTop: 4 }}>{fmtKm(nav.nearest.dist)} · {nav.nearest.brg.toFixed(0)}° {compassPoint(nav.nearest.brg)}</div>
          </Card>
        </>
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Button onClick={onLogCatch} style={{ flex: 1 }}>{t('exp_log_catch')}</Button>
        <Button variant="danger" onClick={onEnd}>{t('exp_end')}</Button>
      </div>
      <div style={{ fontSize: 11, color: colors.muted, marginTop: 8 }}>{t('exp_track_points')}: {trackCount}</div>
    </div>
  );
}
