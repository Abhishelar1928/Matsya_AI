/**
 * Plan screen: choose landing centre + destination (INCOIS PFZ or tapped map point),
 * preview the direct route, then request the package from the server.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { fetchLandingCentres, requestPackage } from './api';
import { getDeviceId, savePackage } from './db';
import { compassPoint, haversineKm, initialBearingDeg } from './geo';
import { Badge, Button, Card, colors } from './ui';
import type { ExpeditionPackage, LandingCentreInfo } from './types';
import type { PFZAdvisory } from '../types/map';
import { t } from '../i18n';

interface Props {
  isMarathi: boolean;
  pfz: PFZAdvisory | null;
  onPackageReady: (pkg: ExpeditionPackage) => void;
  initialPfzIndex?: number | null;
  initialDestination?: { latitude: number; longitude: number } | null;
}

type Dest = { latitude: number; longitude: number; name: string; pfz_index?: number };

export function PlanExpedition({ isMarathi, pfz, onPackageReady, initialPfzIndex = null, initialDestination = null }: Props) {
  const [centres, setCentres] = useState<LandingCentreInfo[]>([]);
  const [centreId, setCentreId] = useState<string>('');
  const [dest, setDest] = useState<Dest | null>(() => {
    const loc = initialPfzIndex !== null ? pfz?.locations[initialPfzIndex] : undefined;
    if (loc && initialPfzIndex !== null) {
      return { latitude: loc.latitude, longitude: loc.longitude, name: `INCOIS PFZ (${loc.landing_centre} ${loc.direction})`, pfz_index: initialPfzIndex };
    }
    if (initialDestination) return { ...initialDestination, name: isMarathi ? "निवडलेला बिंदू" : "Selected point" };
    return null;
  });
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInst = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    fetchLandingCentres().then((lcs) => {
      setCentres(lcs);
      if (!lcs.length || centreId) return;
      // Default departure: the landing centre nearest the chosen destination.
      const nearest = dest
        ? [...lcs].sort((a, b) => haversineKm(dest.latitude, dest.longitude, a.latitude, a.longitude) - haversineKm(dest.latitude, dest.longitude, b.latitude, b.longitude))[0]
        : lcs[0];
      setCentreId(nearest.id);
    }).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const centre = useMemo(() => centres.find((c) => c.id === centreId) ?? null, [centres, centreId]);

  // Map for picking a destination
  useEffect(() => {
    if (!mapRef.current || mapInst.current) return;
    const map = L.map(mapRef.current, { center: [17.85, 72.85], zoom: 7, minZoom: 6, maxZoom: 12 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors' }).addTo(map);
    if (dest) map.setView([dest.latitude, dest.longitude], 8);
    layerRef.current = L.layerGroup().addTo(map);
    map.on('click', (e: L.LeafletMouseEvent) => {
      setDest({ latitude: +e.latlng.lat.toFixed(5), longitude: +e.latlng.lng.toFixed(5), name: isMarathi ? 'निवडलेला बिंदू' : 'Selected point' });
    });
    mapInst.current = map;
    return () => { map.remove(); mapInst.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Draw PFZ points, centre and route preview
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    pfz?.locations.forEach((loc, i) => {
      const m = L.circleMarker([loc.latitude, loc.longitude], { radius: 6, color: '#ffffff', fillColor: colors.pfz, fillOpacity: 1, weight: 2 });
      m.on('click', () => setDest({ latitude: loc.latitude, longitude: loc.longitude, name: `INCOIS PFZ (${loc.landing_centre} ${loc.direction})`, pfz_index: i }));
      m.bindTooltip(`PFZ #${i + 1}: ${loc.landing_centre} ${loc.direction}`);
      m.addTo(layer);
    });
    if (centre) {
      const icon = L.divIcon({ className: '', html: '<div class="landing-pin"></div>', iconSize: [12, 12], iconAnchor: [6, 6] });
      L.marker([centre.latitude, centre.longitude], { icon }).bindTooltip(centre.name, { permanent: true, direction: 'right', offset: [8, 0] }).addTo(layer);
    }
    if (dest) {
      L.circleMarker([dest.latitude, dest.longitude], { radius: 8, color: '#ffffff', fillColor: colors.accent, fillOpacity: 1, weight: 3 }).addTo(layer);
      if (centre) {
        L.polyline([[centre.latitude, centre.longitude], [dest.latitude, dest.longitude]], { color: colors.accent, weight: 2, dashArray: '6 6' }).addTo(layer);
      }
    }
  }, [pfz, centre, dest]);

  const preview = useMemo(() => {
    if (!centre || !dest) return null;
    const km = haversineKm(centre.latitude, centre.longitude, dest.latitude, dest.longitude);
    const brg = initialBearingDeg(centre.latitude, centre.longitude, dest.latitude, dest.longitude);
    return { km, brg, compass: compassPoint(brg) };
  }, [centre, dest]);

  const build = async () => {
    if (!centre || !dest) return;
    setBuilding(true);
    setError(null);
    try {
      const device_id = await getDeviceId();
      const pkg = await requestPackage({
        device_id,
        landing_centre_id: centre.id,
        ...(dest.pfz_index !== undefined ? { pfz_index: dest.pfz_index } : { destination: { latitude: dest.latitude, longitude: dest.longitude, name: dest.name } }),
      });
      await savePackage(pkg);
      onPackageReady(pkg);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div>
      <Card title={`${t('exp_landing_centre')}`}>
        <select value={centreId} onChange={(e) => setCentreId(e.target.value)} className="select">
          {centres.map((c) => (
            <option key={c.id} value={c.id}>{c.district} — {isMarathi ? c.name_mr : c.name}{c.verified ? '' : ' *'}</option>
          ))}
        </select>
        {centre && !centre.verified && (
          <div style={{ fontSize: 11, color: colors.muted, marginTop: 6 }}>
            * {isMarathi ? 'स्थान अद्याप अधिकृतरीत्या सत्यापित नाही' : 'Coordinates not yet officially verified'}
          </div>
        )}
      </Card>

      <Card title={`${t('exp_destination')}`}>
        <div style={{ fontSize: 13, color: colors.muted, marginBottom: 8 }}>
          {t('exp_pick_pfz')} {pfz?.count ? <Badge color={colors.green}>{pfz.count} PFZ</Badge> : <Badge color={colors.slate}>{t('exp_not_available')}</Badge>} {t('exp_or_tap_map')}
        </div>
        <div className="map-frame" style={{ height: 380 }}><div ref={mapRef} className="map-canvas" /></div>
        {dest && (
          <div style={{ marginTop: 10, fontSize: 14 }}>
            <strong style={{ color: colors.accent }}>{dest.name}</strong> · {dest.latitude.toFixed(4)}°N, {dest.longitude.toFixed(4)}°E
          </div>
        )}
      </Card>

      {preview && (
        <Card title={`${t('exp_route_preview')}`}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            <div><div style={{ fontSize: 11, color: colors.muted }}>{t('exp_distance')}</div><div style={{ fontSize: 22, fontWeight: 600 }}>{preview.km.toFixed(1)} km <span style={{ fontSize: 13, color: colors.muted }}>({(preview.km / 1.852).toFixed(1)} nm)</span></div></div>
            <div><div style={{ fontSize: 11, color: colors.muted }}>{t('exp_bearing')}</div><div style={{ fontSize: 22, fontWeight: 600 }}>{preview.brg.toFixed(0)}° {preview.compass}</div></div>
          </div>
          <div style={{ fontSize: 11, color: colors.amber, marginTop: 10 }}>{t('exp_not_chart')}</div>
        </Card>
      )}

      {error && <div className="callout callout-danger" style={{ marginBottom: 16 }}><div className="callout-text">{error}</div></div>}

      <Button onClick={build} disabled={!centre || !dest || building} style={{ width: '100%' }}>
        {building ? t('exp_building') : t('exp_build_package')}
      </Button>
    </div>
  );
}
