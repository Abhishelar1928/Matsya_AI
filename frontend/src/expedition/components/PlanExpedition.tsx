/**
 * Plan screen: choose landing centre + destination (INCOIS PFZ or tapped map point),
 * preview the direct route, then request the package from the server.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { LocateFixed } from 'lucide-react';
import { fetchLandingCentres, requestPackage } from '../services/expeditionApi';
import { getDeviceId, savePackage } from '../services/expeditionDb';
import { compassPoint, haversineKm, initialBearingDeg } from '../engine/geodesy';
import { Badge, Button, Card, colors } from './ExpeditionPrimitives';
import { MarineCompass } from './CompassRose';
import type { ExpeditionPackage, LandingCentreInfo } from '../types/expeditionTypes';
import type { PFZAdvisory } from '../../types/map';
import { t } from '../../i18n';

interface Props {
  isMarathi: boolean;
  pfz: PFZAdvisory | null;
  onPackageReady: (pkg: ExpeditionPackage) => void;
  initialPfzIndex?: number | null;
  initialDestination?: { latitude: number; longitude: number } | null;
  initialOrigin?: { latitude: number; longitude: number } | null;
}

type Dest = { latitude: number; longitude: number; name: string; pfz_index?: number };
type SelfLoc = { latitude: number; longitude: number; accuracy_m?: number | null };

export function PlanExpedition({
  isMarathi,
  pfz,
  onPackageReady,
  initialPfzIndex = null,
  initialDestination = null,
  initialOrigin = null,
}: Props) {
  const [centres, setCentres] = useState<LandingCentreInfo[]>([]);
  const [centreId, setCentreId] = useState<string>('');
  const [myLoc, setMyLoc] = useState<SelfLoc | null>(initialOrigin);
  const [useCurrentLocation, setUseCurrentLocation] = useState<boolean>(!!initialOrigin);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
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
      // Default emergency landing centre: nearest the origin or destination.
      const refPt = initialOrigin ?? dest;
      const nearest = refPt
        ? [...lcs].sort((a, b) => haversineKm(refPt.latitude, refPt.longitude, a.latitude, a.longitude) - haversineKm(refPt.latitude, refPt.longitude, b.latitude, b.longitude))[0]
        : lcs[0];
      setCentreId(nearest.id);
    }).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const centre = useMemo(() => centres.find((c) => c.id === centreId) ?? null, [centres, centreId]);
  const originPoint = useMemo(() => {
    if (useCurrentLocation && myLoc) {
      return {
        latitude: myLoc.latitude,
        longitude: myLoc.longitude,
        name: isMarathi ? 'माझे सध्याचे स्थान' : 'Current GPS Location',
      };
    }
    return centre ? { latitude: centre.latitude, longitude: centre.longitude, name: centre.name } : null;
  }, [useCurrentLocation, myLoc, centre, isMarathi]);

  const locateMe = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocError(isMarathi ? 'या डिव्हाइसवर GPS उपलब्ध नाही.' : 'GPS is not available in this browser.');
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const next: SelfLoc = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy_m: Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null,
        };
        setMyLoc(next);
        setUseCurrentLocation(true);
        setLocating(false);
        if (centres.length > 0) {
          const nearest = [...centres].sort(
            (a, b) => haversineKm(next.latitude, next.longitude, a.latitude, a.longitude) - haversineKm(next.latitude, next.longitude, b.latitude, b.longitude),
          )[0];
          setCentreId(nearest.id);
        }
        const map = mapInst.current;
        if (map) {
          if (dest) {
            map.fitBounds([[next.latitude, next.longitude], [dest.latitude, dest.longitude]], { padding: [36, 36], maxZoom: 11 });
          } else {
            map.setView([next.latitude, next.longitude], 10);
          }
        }
      },
      (err) => {
        setLocating(false);
        setLocError(err.message || (isMarathi ? 'स्थान मिळवता आले नाही.' : 'Could not fetch current location.'));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    );
  };

  // Map for picking a destination
  useEffect(() => {
    if (!mapRef.current || mapInst.current) return;
    const map = L.map(mapRef.current, { center: [17.85, 72.85], zoom: 7, minZoom: 6, maxZoom: 12 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors' }).addTo(map);
    if (initialOrigin && dest) {
      map.fitBounds([[initialOrigin.latitude, initialOrigin.longitude], [dest.latitude, dest.longitude]], { padding: [36, 36], maxZoom: 11 });
    } else if (dest) {
      map.setView([dest.latitude, dest.longitude], 8);
    } else if (initialOrigin) {
      map.setView([initialOrigin.latitude, initialOrigin.longitude], 10);
    }
    layerRef.current = L.layerGroup().addTo(map);
    map.on('click', (e: L.LeafletMouseEvent) => {
      setDest({ latitude: +e.latlng.lat.toFixed(5), longitude: +e.latlng.lng.toFixed(5), name: isMarathi ? 'निवडलेला बिंदू' : 'Selected point' });
    });
    mapInst.current = map;
    return () => { map.remove(); mapInst.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Draw PFZ points, centre, self-location and route preview
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
      L.marker([centre.latitude, centre.longitude], { icon }).bindTooltip(centre.name, { permanent: !useCurrentLocation, direction: 'right', offset: [8, 0] }).addTo(layer);
    }
    if (myLoc) {
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
        fillColor: '#2563eb',
        fillOpacity: 1,
        weight: 2.5,
      })
        .bindTooltip(isMarathi ? 'माझे सध्याचे स्थान' : 'My current location', { permanent: useCurrentLocation, direction: 'right', offset: [8, 0] })
        .addTo(layer);
    }
    if (dest) {
      L.circleMarker([dest.latitude, dest.longitude], { radius: 8, color: '#ffffff', fillColor: colors.accent, fillOpacity: 1, weight: 3 }).addTo(layer);
      if (originPoint) {
        L.polyline([[originPoint.latitude, originPoint.longitude], [dest.latitude, dest.longitude]], { color: colors.accent, weight: 2, dashArray: '6 6' }).addTo(layer);
      }
    }
  }, [pfz, centre, myLoc, useCurrentLocation, originPoint, dest, isMarathi]);

  const preview = useMemo(() => {
    if (!originPoint || !dest) return null;
    const km = haversineKm(originPoint.latitude, originPoint.longitude, dest.latitude, dest.longitude);
    const brg = initialBearingDeg(originPoint.latitude, originPoint.longitude, dest.latitude, dest.longitude);
    return { km, brg, compass: compassPoint(brg) };
  }, [originPoint, dest]);

  const build = async () => {
    if (!centre || !dest) return;
    setBuilding(true);
    setError(null);
    try {
      const device_id = await getDeviceId();
      const pkg = await requestPackage({
        device_id,
        landing_centre_id: centre.id,
        ...(useCurrentLocation && myLoc ? { origin: { latitude: myLoc.latitude, longitude: myLoc.longitude, name: 'Current GPS Location' } } : {}),
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
          <Button variant={useCurrentLocation && myLoc ? 'primary' : 'secondary'} onClick={locateMe} disabled={locating}>
            <LocateFixed size={15} aria-hidden />
            {locating
              ? (isMarathi ? 'GPS स्थान शोधत आहे…' : 'Getting GPS location…')
              : (isMarathi ? 'माझे सध्याचे स्थान वापरा (GPS)' : 'Use my current location (GPS)')}
          </Button>
          {myLoc && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setUseCurrentLocation((u) => !u)}
            >
              {useCurrentLocation
                ? (isMarathi ? 'लँडिंग केंद्रावरून सुरू करा' : 'Depart from landing centre instead')
                : (isMarathi ? 'GPS स्थानावरून सुरू करा' : 'Depart from GPS location')}
            </button>
          )}
        </div>
        {myLoc && (
          <div style={{ fontSize: 12, color: useCurrentLocation ? colors.accent : colors.muted, marginBottom: 8 }}>
            {useCurrentLocation
              ? (isMarathi ? 'सुरुवात (GPS): ' : 'Departing from GPS: ')
              : (isMarathi ? 'जतन केलेले GPS स्थान: ' : 'Saved GPS location: ')}
            <strong>{myLoc.latitude.toFixed(5)}°N, {myLoc.longitude.toFixed(5)}°E</strong>
            {myLoc.accuracy_m ? ` (±${Math.round(myLoc.accuracy_m)} m)` : ''}
          </div>
        )}
        {locError && (
          <div style={{ fontSize: 12, color: colors.amber, marginBottom: 8 }}>{locError}</div>
        )}
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
          <MarineCompass
            targetBearingDeg={preview.brg}
            remainingKm={preview.km}
            totalKm={preview.km}
            destinationName={dest?.name}
            isMarathi={isMarathi}
          />
          <div style={{ fontSize: 11, color: colors.amber, marginTop: 4 }}>{t('exp_not_chart')}</div>
        </Card>
      )}

      {error && <div className="callout callout-danger" style={{ marginBottom: 16 }}><div className="callout-text">{error}</div></div>}

      <Button onClick={build} disabled={!centre || !dest || building} style={{ width: '100%' }}>
        {building ? t('exp_building') : t('exp_build_package')}
      </Button>
    </div>
  );
}
