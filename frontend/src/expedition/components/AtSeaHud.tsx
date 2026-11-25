/**
 * At-Sea Navigation HUD, Marine Chartplotter, Voyage Black Box, & Emergency Return.
 *
 * Uses centralized navigationEngine, adaptive voyageRecorder, 4-state marine safety
 * intelligence, IndexedDB state recovery across reloads, GPX/CSV export, voyage replay,
 * Night Mode, and isolated simulation testing.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { AlertTriangle, Download, LocateFixed, Moon, Navigation, Play, ShieldAlert, Sun } from 'lucide-react';
import {
  createOfflineBasemap,
  LAND_OSM_BG,
  loadBathymetry,
  loadMpaAndHazards,
  OCEAN_BG_BY_THEME,
  type MapTheme,
} from '../services/basemapLayers';
import { MarineCompass } from './CompassRose';
import {
  addTrackPoint,
  addVoyageEvent,
  getVoyageState,
  listCatches,
  listTrack,
  listVoyageEvents,
  newUuid,
  saveVoyageState,
} from '../services/expeditionDb';
import { EmergencyReturn } from './EmergencyReturn';
import {
  angularDiffDeg,
  estimateCurrentDrift,
  etaMinutes,
  formatDms,
  haversineKm,
  initialBearingDeg,
  isPointOnLand,
  kmToNm,
  minDistanceToShallowContoursKm,
  mpsToKnots,
  type ShallowContourLine,
} from '../engine/geodesy';
import {
  createNavigationState,
  processFix,
  type NavigationState,
  type TurnInstruction,
} from '../engine/navigationEngine';
import { evaluateMarineSafety, type ExpeditionSafetyState } from '../engine/offlineSafety';
import { SIMULATION_SCENARIOS, type SimulationScenario } from '../engine/simulation';
import type {
  AnchorWatchState,
  CatchRecord,
  ExpeditionPackage,
  MobMarker,
  PersistedVoyageState,
  TrackPoint,
  VoyageEvent,
} from '../types/expeditionTypes';
import { Badge, Button, colors } from './ExpeditionPrimitives';
import { gpsHelp, type GeoState } from '../hooks/useGeolocation';
import { exportVoyageCsv, exportVoyageGpx, shouldRecordTrackPoint, type SampledPointRef } from '../engine/voyageRecorder';
import { t } from '../../i18n';

interface Props {
  pkg: ExpeditionPackage;
  isMarathi: boolean;
  online: boolean;
  geo: GeoState;
  simulating: boolean;
  simulationScenario: SimulationScenario;
  onChangeScenario: (s: SimulationScenario) => void;
  onToggleSimulation: () => void;
  onLogCatch: () => void;
  onEnd: () => void;
}

function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const SAFETY_STYLE: Record<ExpeditionSafetyState, { bg: string; border: string; fg: string; labelEn: string; labelMr: string }> = {
  SAFE_DATA: { bg: 'rgba(6,118,71,0.22)', border: '#10b981', fg: '#6ee7b7', labelEn: 'SAFE DATA', labelMr: 'सुरक्षित डेटा' },
  CAUTION: { bg: 'rgba(181,71,8,0.26)', border: '#f59e0b', fg: '#fcd34d', labelEn: 'CAUTION', labelMr: 'सावधान' },
  UNSAFE: { bg: 'rgba(180,35,24,0.34)', border: '#ef4444', fg: '#fca5a5', labelEn: 'UNSAFE', labelMr: 'असुरक्षित' },
  UNKNOWN: { bg: 'rgba(71,84,103,0.3)', border: '#94a3b8', fg: '#cbd5e1', labelEn: 'UNKNOWN', labelMr: 'अपुष्ट डेटा' },
};

export function AtSea({
  pkg,
  isMarathi,
  online,
  geo,
  simulating,
  simulationScenario,
  onChangeScenario,
  onToggleSimulation,
  onLogCatch,
  onEnd,
}: Props) {
  const [now, setNow] = useState(Date.now());
  const [nightMode, setNightMode] = useState(false);
  const [showEmergency, setShowEmergency] = useState(false);
  const [showSafetySources, setShowSafetySources] = useState(false);
  const [basemapKind, setBasemapKind] = useState<'pmtiles' | 'osm' | 'fallback' | null>(null);
  const [hasShallowData, setHasShallowData] = useState(false);
  const [shallowLines, setShallowLines] = useState<ShallowContourLine[]>([]);
  const [mpaCount, setMpaCount] = useState(0);
  const [selectedMapPoint, setSelectedMapPoint] = useState<{ latitude: number; longitude: number; onLand: boolean } | null>(null);
  const [overrideTarget, setOverrideTarget] = useState<{ latitude: number; longitude: number; name: string } | null>(null);

  // Persisted black-box & emergency states
  const [trackCount, setTrackCount] = useState(0);
  const [savedTrack, setSavedTrack] = useState<TrackPoint[]>([]);
  const [events, setEvents] = useState<VoyageEvent[]>([]);
  const [catches, setCatches] = useState<CatchRecord[]>([]);
  const [mob, setMob] = useState<MobMarker | null>(null);
  const [anchorWatch, setAnchorWatch] = useState<AnchorWatchState | null>(null);
  const [restoredFromStorage, setRestoredFromStorage] = useState(false);
  const [replayIndex, setReplayIndex] = useState<number | null>(null);

  // Navigation state machine
  const [navState, setNavState] = useState<NavigationState>(() => createNavigationState(pkg.route.waypoints));
  const navStateRef = useRef<NavigationState>(navState);
  const lastRecordedRef = useRef<SampledPointRef | null>(null);
  const prevGpsHealthRef = useRef<string>('WAITING');
  const prevSafetyRef = useRef<string | null>(null);
  const voyageStartedAtRef = useRef<string>(new Date().toISOString());

  // Leaflet refs
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInst = useRef<L.Map | null>(null);
  const basemapGroupRef = useRef<L.LayerGroup | null>(null);
  const vesselRef = useRef<L.CircleMarker | null>(null);
  const accuracyCircleRef = useRef<L.Circle | null>(null);
  const bearingLineRef = useRef<L.Polyline | null>(null);
  const trailRef = useRef<L.Polyline | null>(null);
  const mobLayerRef = useRef<L.CircleMarker | null>(null);
  const anchorLayerRef = useRef<L.Circle | null>(null);
  const replayMarkerRef = useRef<L.CircleMarker | null>(null);
  const selectedMarkerRef = useRef<L.CircleMarker | null>(null);
  const overrideMarkerRef = useRef<L.CircleMarker | null>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(id);
  }, []);

  // Restore persisted track, events, catches, & voyage state after reload/crash
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [vs, trk, evs, cts] = await Promise.all([
        getVoyageState(pkg.manifest.package_id),
        listTrack(pkg.manifest.package_id),
        listVoyageEvents(pkg.manifest.package_id),
        listCatches(pkg.manifest.package_id),
      ]);
      if (cancelled) return;

      setSavedTrack(trk);
      setTrackCount(trk.length);
      setEvents(evs);
      setCatches(cts);

      if (trk.length > 0) {
        const last = trk[trk.length - 1];
        lastRecordedRef.current = {
          timestamp: Date.parse(last.recorded_at) || Date.now(),
          latitude: last.latitude,
          longitude: last.longitude,
          cogDeg: last.cog_deg ?? last.heading_deg,
        };
        trailRef.current?.setLatLngs(trk.map((p) => [p.latitude, p.longitude] as [number, number]));
      }

      if (vs) {
        voyageStartedAtRef.current = vs.started_at;
        setMob(vs.mob);
        setAnchorWatch(vs.anchor_watch);
        setNavState(createNavigationState(pkg.route.waypoints, vs.active_waypoint_index));
        navStateRef.current = createNavigationState(pkg.route.waypoints, vs.active_waypoint_index);
        if (trk.length > 0 || vs.mob || vs.anchor_watch) {
          setRestoredFromStorage(true);
        }
        const resumeEv: VoyageEvent = {
          client_uuid: newUuid(),
          expedition_id: pkg.manifest.package_id,
          recorded_at: new Date().toISOString(),
          event_type: 'VOYAGE_RESUME',
          latitude: trk[trk.length - 1]?.latitude ?? null,
          longitude: trk[trk.length - 1]?.longitude ?? null,
          detail: 'Resumed voyage state from IndexedDB',
          synced: 0,
        };
        await addVoyageEvent(resumeEv);
        setEvents((e) => [...e, resumeEv]);
      } else {
        const nowIso = new Date().toISOString();
        voyageStartedAtRef.current = nowIso;
        await saveVoyageState({
          expedition_id: pkg.manifest.package_id,
          active_waypoint_index: 1,
          arrived_destination: false,
          last_safety_state: null,
          mob: null,
          anchor_watch: null,
          started_at: nowIso,
          updated_at: nowIso,
        });
        const startEv: VoyageEvent = {
          client_uuid: newUuid(),
          expedition_id: pkg.manifest.package_id,
          recorded_at: nowIso,
          event_type: 'VOYAGE_START',
          latitude: null,
          longitude: null,
          detail: `Started expedition to ${pkg.destination.name}`,
          synced: 0,
        };
        await addVoyageEvent(startEv);
        setEvents([startEv]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pkg.manifest.package_id, pkg.destination.name, pkg.route.waypoints]);

  // Process incoming GPS + physical compass through centralized navigation engine
  const navResult = useMemo(() => {
    const res = processFix(navStateRef.current, geo.fix, geo.compassHeadingDeg, now);
    return res;
  }, [geo.fix, geo.compassHeadingDeg, now]);

  useEffect(() => {
    navStateRef.current = navResult.state;
    setNavState(navResult.state);

    const snap = navResult.snapshot;
    const fix = snap.fix;

    // Emit GPS health transitions
    if (prevGpsHealthRef.current !== snap.gpsHealth) {
      if (snap.gpsHealth === 'LOST' && prevGpsHealthRef.current !== 'WAITING') {
        const ev: VoyageEvent = {
          client_uuid: newUuid(),
          expedition_id: pkg.manifest.package_id,
          recorded_at: new Date().toISOString(),
          event_type: 'GPS_LOST',
          latitude: fix?.latitude ?? null,
          longitude: fix?.longitude ?? null,
          detail: 'GPS fix became stale (>30 s)',
          synced: 0,
        };
        void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
      } else if (snap.gpsHealth === 'LIVE' && prevGpsHealthRef.current === 'LOST') {
        const ev: VoyageEvent = {
          client_uuid: newUuid(),
          expedition_id: pkg.manifest.package_id,
          recorded_at: new Date().toISOString(),
          event_type: 'GPS_RESTORED',
          latitude: fix?.latitude ?? null,
          longitude: fix?.longitude ?? null,
          detail: 'Live GPS fix restored',
          synced: 0,
        };
        void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
      }
      prevGpsHealthRef.current = snap.gpsHealth;
    }

    // Persist emitted navigation events (never persist simulation events as real records)
    if (navResult.emittedEvents.length > 0 && !fix?.simulated) {
      for (const em of navResult.emittedEvents) {
        const ev: VoyageEvent = {
          client_uuid: newUuid(),
          expedition_id: pkg.manifest.package_id,
          recorded_at: new Date(em.timestamp).toISOString(),
          event_type: em.type,
          latitude: em.latitude,
          longitude: em.longitude,
          detail: em.detail,
          synced: 0,
        };
        void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
      }
    }
  }, [navResult, pkg.manifest.package_id]);

  // Log browser foreground/background interruptions into Black Box
  useEffect(() => {
    if (geo.lastInterruptedAt && !simulating) {
      const ev: VoyageEvent = {
        client_uuid: newUuid(),
        expedition_id: pkg.manifest.package_id,
        recorded_at: new Date(geo.lastInterruptedAt).toISOString(),
        event_type: 'VISIBILITY_INTERRUPTED',
        latitude: navResult.snapshot.fix?.latitude ?? null,
        longitude: navResult.snapshot.fix?.longitude ?? null,
        detail: 'App backgrounded or screen locked; browser paused GPS tracking',
        synced: 0,
      };
      void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.lastInterruptedAt]);

  // Evaluate 4-state Marine Safety Intelligence
  const safetyReport = useMemo(
    () =>
      evaluateMarineSafety(
        pkg,
        navResult.snapshot.fix
          ? { latitude: navResult.snapshot.fix.latitude, longitude: navResult.snapshot.fix.longitude }
          : null,
        now,
      ),
    [pkg, navResult.snapshot.fix, now],
  );

  // Persist safety transitions
  useEffect(() => {
    if (prevSafetyRef.current && prevSafetyRef.current !== safetyReport.state) {
      const ev: VoyageEvent = {
        client_uuid: newUuid(),
        expedition_id: pkg.manifest.package_id,
        recorded_at: new Date().toISOString(),
        event_type: 'SAFETY_CHANGE',
        latitude: navResult.snapshot.fix?.latitude ?? null,
        longitude: navResult.snapshot.fix?.longitude ?? null,
        detail: `${prevSafetyRef.current} -> ${safetyReport.state}: ${safetyReport.reason}`,
        synced: 0,
      };
      void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
    }
    prevSafetyRef.current = safetyReport.state;
  }, [safetyReport.state, safetyReport.reason, pkg.manifest.package_id, navResult.snapshot.fix]);

  // Persist voyage_state snapshot whenever waypoint, mob, or anchor changes
  useEffect(() => {
    const stateDoc: PersistedVoyageState = {
      expedition_id: pkg.manifest.package_id,
      active_waypoint_index: navState.activeWaypointIndex,
      arrived_destination: navState.arrivedDestination,
      last_safety_state: safetyReport.state,
      mob,
      anchor_watch: anchorWatch,
      started_at: voyageStartedAtRef.current,
      updated_at: new Date().toISOString(),
    };
    void saveVoyageState(stateDoc);
  }, [pkg.manifest.package_id, navState.activeWaypointIndex, navState.arrivedDestination, safetyReport.state, mob, anchorWatch]);

  // Anchor drift computation
  const anchorDriftKm = useMemo(() => {
    const f = navResult.snapshot.fix;
    if (!anchorWatch || !f) return null;
    return haversineKm(anchorWatch.latitude, anchorWatch.longitude, f.latitude, f.longitude);
  }, [anchorWatch, navResult.snapshot.fix]);
  const anchorDriftAlert = anchorWatch !== null && anchorDriftKm !== null && anchorDriftKm * 1000 > anchorWatch.radius_m;

  // --- Map initialization & theme-aware basemap ----------------------------
  const mapTheme: MapTheme = nightMode ? 'night' : 'dark';

  useEffect(() => {
    if (!mapRef.current || mapInst.current) return;
    const dest = pkg.destination;
    const map = L.map(mapRef.current, {
      center: [(pkg.landing_centre.latitude + dest.latitude) / 2, (pkg.landing_centre.longitude + dest.longitude) / 2],
      zoom: 9,
      minZoom: 6,
      maxZoom: 13,
      zoomControl: false,
    });
    mapRef.current.style.background = OCEAN_BG_BY_THEME[mapTheme];
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ metric: true, imperial: false, position: 'bottomleft' }).addTo(map);
    mapInst.current = map;

    basemapGroupRef.current = L.layerGroup().addTo(map);

    const overlay = L.layerGroup().addTo(map);

    // Offline map coverage boundary
    const bbox = pkg.offline_assets?.bbox;
    if (bbox) {
      L.rectangle(
        [
          [bbox.min_lat, bbox.min_lon],
          [bbox.max_lat, bbox.max_lon],
        ],
        { color: '#64748b', weight: 1, dashArray: '4 6', fill: false, interactive: false },
      ).addTo(overlay);
    }

    // Direct reference route & numbered waypoints
    L.polyline(
      pkg.route.waypoints.map((w) => [w.latitude, w.longitude] as [number, number]),
      { color: '#38bdf8', weight: 2, dashArray: '6 6' },
    ).addTo(overlay);

    pkg.route.waypoints.forEach((w) => {
      if (w.index === 0 || w.index === pkg.route.waypoints.length - 1) return;
      L.circleMarker([w.latitude, w.longitude], {
        radius: 5,
        color: '#0f172a',
        fillColor: '#38bdf8',
        fillOpacity: 0.95,
        weight: 1.5,
      })
        .bindTooltip(`WP ${w.index} (${w.km_from_start.toFixed(1)} km)`)
        .addTo(overlay);
    });

    pkg.route.land_crossings.forEach((c) => {
      L.circleMarker([c.latitude, c.longitude], {
        radius: 5,
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.9,
      })
        .bindTooltip('Land mask crossing warning')
        .addTo(overlay);
    });

    // Destination & departure
    L.circleMarker([dest.latitude, dest.longitude], {
      radius: 9,
      color: '#ffffff',
      fillColor: '#38bdf8',
      fillOpacity: 1,
      weight: 3,
    })
      .bindTooltip(dest.name)
      .addTo(overlay);

    L.circleMarker([pkg.landing_centre.latitude, pkg.landing_centre.longitude], {
      radius: 6,
      color: '#ffffff',
      fillColor: '#10b981',
      fillOpacity: 1,
      weight: 2,
    })
      .bindTooltip(`${pkg.landing_centre.name}${pkg.landing_centre.verified ? '' : ' (Unverified)'}`)
      .addTo(overlay);

    // PFZ locations
    pkg.pfz.locations.forEach((loc) => {
      L.circleMarker([loc.latitude, loc.longitude], {
        radius: 5,
        color: '#ffffff',
        fillColor: colors.pfz,
        fillOpacity: 1,
        weight: 1.5,
      })
        .bindTooltip(`PFZ ${loc.landing_centre} ${loc.direction} ${loc.distance_km} km`)
        .addTo(overlay);
    });

    // High-activity cells (subtle)
    pkg.predictions.cells
      .filter((c) => c.high === 1)
      .forEach((c) => {
        L.rectangle(
          [
            [c.lat - 0.125, c.lon - 0.125],
            [c.lat + 0.125, c.lon + 0.125],
          ],
          { color: '#3b82f6', weight: 0.6, fillColor: '#3b82f6', fillOpacity: 0.16, interactive: false },
        ).addTo(overlay);
      });

    // Emergency return harbours
    pkg.emergency_returns.forEach((r) => {
      L.circleMarker([r.latitude, r.longitude], {
        radius: 4,
        color: '#ffffff',
        fillColor: '#22c55e',
        fillOpacity: 0.85,
        weight: 1.5,
      })
        .bindTooltip(`${r.name} (${r.district})${r.verified ? '' : ' *'}`)
        .addTo(overlay);
    });

    trailRef.current = L.polyline([], { color: '#fbbf24', weight: 2.5, opacity: 0.85 }).addTo(map);
    bearingLineRef.current = L.polyline([], { color: '#38bdf8', weight: 1.5, dashArray: '3 5', opacity: 0.7 }).addTo(map);
    accuracyCircleRef.current = L.circle([pkg.landing_centre.latitude, pkg.landing_centre.longitude], {
      radius: 0,
      color: '#38bdf8',
      weight: 1,
      fillColor: '#38bdf8',
      fillOpacity: 0.12,
      interactive: false,
    }).addTo(map);
    vesselRef.current = L.circleMarker([pkg.landing_centre.latitude, pkg.landing_centre.longitude], {
      radius: 8,
      color: '#ffffff',
      fillColor: '#f59e0b',
      fillOpacity: 1,
      weight: 3,
    }).addTo(map);

    map.on('dragstart', () => setFollow(false));
    map.on('click', (e: L.LeafletMouseEvent) => {
      const lat = +e.latlng.lat.toFixed(5);
      const lon = +e.latlng.lng.toFixed(5);
      setSelectedMapPoint({ latitude: lat, longitude: lon, onLand: isPointOnLand(lat, lon) });
    });

    return () => {
      map.remove();
      mapInst.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pkg.manifest.package_id]);

  const activePointOnLand = useMemo(() => {
    if (selectedMapPoint) return selectedMapPoint.onLand;
    if (geo.fix) return isPointOnLand(geo.fix.latitude, geo.fix.longitude);
    return pkg.route.warnings.includes('DESTINATION_ON_LAND') || isPointOnLand(pkg.destination.latitude, pkg.destination.longitude);
  }, [selectedMapPoint, geo.fix, pkg.route.warnings, pkg.destination.latitude, pkg.destination.longitude]);

  // Show marker for manually tapped point on the At-Sea map
  useEffect(() => {
    const map = mapInst.current;
    if (!map) return;
    if (selectedMarkerRef.current) {
      selectedMarkerRef.current.remove();
      selectedMarkerRef.current = null;
    }
    if (selectedMapPoint) {
      selectedMarkerRef.current = L.circleMarker([selectedMapPoint.latitude, selectedMapPoint.longitude], {
        radius: 6,
        color: '#ffffff',
        fillColor: selectedMapPoint.onLand ? '#10b981' : '#38bdf8',
        fillOpacity: 1,
        weight: 2,
      })
        .bindTooltip(selectedMapPoint.onLand ? 'Selected (Land · OSM)' : 'Selected (Sea · Marine chart)')
        .addTo(map);
    }
  }, [selectedMapPoint]);

  useEffect(() => {
    const map = mapInst.current;
    if (!map) return;
    if (overrideMarkerRef.current) {
      overrideMarkerRef.current.remove();
      overrideMarkerRef.current = null;
    }
    if (overrideTarget) {
      overrideMarkerRef.current = L.circleMarker([overrideTarget.latitude, overrideTarget.longitude], {
        radius: 10,
        color: '#38bdf8',
        fillColor: '#0284c7',
        fillOpacity: 0.35,
        weight: 2.5,
        dashArray: '4 3',
      })
        .bindTooltip(`Active Target: ${overrideTarget.name}`)
        .addTo(map);
    }
  }, [overrideTarget]);

  // Keep cyan bearing line synced immediately whenever fix or active target changes
  useEffect(() => {
    const fix = navResult.snapshot.fix;
    if (!fix) return;
    const activeTarget = overrideTarget ?? pkg.destination;
    bearingLineRef.current?.setLatLngs([
      [fix.latitude, fix.longitude],
      [activeTarget.latitude, activeTarget.longitude],
    ]);
  }, [navResult.snapshot.fix, overrideTarget, pkg.destination]);

  // Swap basemap/bathymetry layer when theme or land/sea location changes
  useEffect(() => {
    const group = basemapGroupRef.current;
    if (!group || !mapRef.current) return;
    mapRef.current.style.background = activePointOnLand ? LAND_OSM_BG : OCEAN_BG_BY_THEME[mapTheme];
    let cancelled = false;
    void (async () => {
      const [{ layer, kind }, bathy, hazards] = await Promise.all([
        createOfflineBasemap(pkg, mapTheme, { onLand: activePointOnLand }),
        activePointOnLand ? Promise.resolve(null) : loadBathymetry(pkg, mapTheme),
        loadMpaAndHazards(pkg),
      ]);
      if (cancelled) return;
      group.clearLayers();
      layer.addTo(group);
      setBasemapKind(kind);
      if (bathy) {
        bathy.layer.addTo(group);
        setHasShallowData(bathy.hasShallowContours);
        setShallowLines(bathy.shallowLines);
      } else {
        setHasShallowData(false);
        setShallowLines([]);
      }
      hazards.layer.addTo(group);
      setMpaCount(hazards.mpaCount);
    })();
    return () => {
      cancelled = true;
    };
  }, [pkg, mapTheme, activePointOnLand]);

  // Sync MOB & Anchor Watch overlays on map
  useEffect(() => {
    const map = mapInst.current;
    if (!map) return;
    if (mobLayerRef.current) {
      mobLayerRef.current.remove();
      mobLayerRef.current = null;
    }
    if (mob) {
      mobLayerRef.current = L.circleMarker([mob.latitude, mob.longitude], {
        radius: 9,
        color: '#ffffff',
        fillColor: '#ef4444',
        fillOpacity: 1,
        weight: 2.5,
      })
        .bindTooltip('MOB (Man Overboard)')
        .addTo(map);
    }
  }, [mob]);

  useEffect(() => {
    const map = mapInst.current;
    if (!map) return;
    if (anchorLayerRef.current) {
      anchorLayerRef.current.remove();
      anchorLayerRef.current = null;
    }
    if (anchorWatch) {
      anchorLayerRef.current = L.circle([anchorWatch.latitude, anchorWatch.longitude], {
        radius: anchorWatch.radius_m,
        color: anchorDriftAlert ? '#ef4444' : '#f59e0b',
        weight: 2,
        dashArray: '4 4',
        fillOpacity: 0.1,
      })
        .bindTooltip(`Anchor Watch (${anchorWatch.radius_m} m)`)
        .addTo(map);
    }
  }, [anchorWatch, anchorDriftAlert]);

  // Update vessel marker, accuracy ring, & adaptive black-box track recording
  useEffect(() => {
    const snap = navResult.snapshot;
    const fix = snap.fix;
    if (!fix || !mapInst.current) return;

    const ll: [number, number] = [fix.latitude, fix.longitude];
    vesselRef.current?.setLatLng(ll);
    if (accuracyCircleRef.current) {
      accuracyCircleRef.current.setLatLng(ll);
      accuracyCircleRef.current.setRadius(fix.accuracy_m ?? 0);
    }
    if (follow) mapInst.current.panTo(ll, { animate: true });

    if (fix.simulated) {
      trailRef.current?.addLatLng(ll);
      return;
    }

    if (shouldRecordTrackPoint(lastRecordedRef.current, fix, snap, fix.timestamp)) {
      lastRecordedRef.current = {
        timestamp: fix.timestamp,
        latitude: fix.latitude,
        longitude: fix.longitude,
        cogDeg: snap.cogDeg,
      };
      trailRef.current?.addLatLng(ll);
      const tp: TrackPoint = {
        client_uuid: newUuid(),
        expedition_id: pkg.manifest.package_id,
        recorded_at: new Date(fix.timestamp).toISOString(),
        latitude: fix.latitude,
        longitude: fix.longitude,
        speed_mps: fix.speed_mps,
        heading_deg: fix.heading_deg,
        cog_deg: snap.cogDeg,
        compass_heading_deg: snap.compassHeadingDeg,
        xte_km: Number(snap.crossTrackKm.toFixed(3)),
        accuracy_m: fix.accuracy_m,
        synced: 0,
      };
      void addTrackPoint(tp).then(() => {
        setSavedTrack((prev) => [...prev, tp]);
        setTrackCount((n) => n + 1);
      });
    }
  }, [navResult, follow, pkg.destination.latitude, pkg.destination.longitude, pkg.manifest.package_id]);

  // Voyage replay marker
  useEffect(() => {
    const map = mapInst.current;
    if (!map) return;
    if (replayMarkerRef.current) {
      replayMarkerRef.current.remove();
      replayMarkerRef.current = null;
    }
    if (replayIndex !== null && savedTrack[replayIndex]) {
      const pt = savedTrack[replayIndex];
      replayMarkerRef.current = L.circleMarker([pt.latitude, pt.longitude], {
        radius: 7,
        color: '#ffffff',
        fillColor: '#a855f7',
        fillOpacity: 1,
        weight: 2,
      })
        .bindTooltip(`Replay: ${new Date(pt.recorded_at).toLocaleTimeString()}`)
        .addTo(map);
      map.panTo([pt.latitude, pt.longitude], { animate: true });
    }
  }, [replayIndex, savedTrack]);

  // Actions: MOB & Anchor Watch
  const handleMarkMob = () => {
    const f = navResult.snapshot.fix;
    if (!f) return;
    const m: MobMarker = { latitude: f.latitude, longitude: f.longitude, marked_at: new Date().toISOString() };
    setMob(m);
    const ev: VoyageEvent = {
      client_uuid: newUuid(),
      expedition_id: pkg.manifest.package_id,
      recorded_at: m.marked_at,
      event_type: 'MOB_MARKED',
      latitude: f.latitude,
      longitude: f.longitude,
      detail: 'Man Overboard marked',
      synced: 0,
    };
    void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
  };

  const handleClearMob = () => {
    setMob(null);
    const ev: VoyageEvent = {
      client_uuid: newUuid(),
      expedition_id: pkg.manifest.package_id,
      recorded_at: new Date().toISOString(),
      event_type: 'MOB_CLEARED',
      latitude: navResult.snapshot.fix?.latitude ?? null,
      longitude: navResult.snapshot.fix?.longitude ?? null,
      detail: 'MOB marker cleared',
      synced: 0,
    };
    void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
  };

  const handleSetAnchor = (radiusM: number) => {
    const f = navResult.snapshot.fix;
    if (!f) return;
    const aw: AnchorWatchState = {
      latitude: f.latitude,
      longitude: f.longitude,
      radius_m: radiusM,
      set_at: new Date().toISOString(),
    };
    setAnchorWatch(aw);
    const ev: VoyageEvent = {
      client_uuid: newUuid(),
      expedition_id: pkg.manifest.package_id,
      recorded_at: aw.set_at,
      event_type: 'ANCHOR_SET',
      latitude: f.latitude,
      longitude: f.longitude,
      detail: `Anchor watch set (${radiusM} m)`,
      synced: 0,
    };
    void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
  };

  const handleClearAnchor = () => {
    setAnchorWatch(null);
    const ev: VoyageEvent = {
      client_uuid: newUuid(),
      expedition_id: pkg.manifest.package_id,
      recorded_at: new Date().toISOString(),
      event_type: 'ANCHOR_CLEARED',
      latitude: navResult.snapshot.fix?.latitude ?? null,
      longitude: navResult.snapshot.fix?.longitude ?? null,
      detail: 'Anchor watch stopped',
      synced: 0,
    };
    void addVoyageEvent(ev).then(() => setEvents((e) => [...e, ev]));
  };

  const snap = navResult.snapshot;
  const fix = snap.fix;
  const safetyTheme = SAFETY_STYLE[safetyReport.state];
  const nearestHarbour = useMemo(() => {
    const lat = fix?.latitude ?? pkg.landing_centre.latitude;
    const lon = fix?.longitude ?? pkg.landing_centre.longitude;
    return pkg.emergency_returns
      .map((r) => ({ ...r, distKm: haversineKm(lat, lon, r.latitude, r.longitude) }))
      .sort((a, b) => a.distKm - b.distKm)[0];
  }, [fix, pkg.landing_centre, pkg.emergency_returns]);

  const shallowProximity = useMemo(() => {
    if (!fix || shallowLines.length === 0) return null;
    const hit = minDistanceToShallowContoursKm(fix.latitude, fix.longitude, shallowLines);
    return hit && hit.distanceKm <= 2.5 ? hit : null;
  }, [fix, shallowLines]);

  const currentDrift = useMemo(() => {
    const h = pkg.forecast?.points?.[0]?.hourly;
    if (!h?.time?.length || !h.ocean_current_u_mps || !h.ocean_current_v_mps) return null;
    let idx = -1;
    for (let i = h.time.length - 1; i >= 0; i--) {
      const ts = Date.parse(h.time[i]);
      if (!Number.isNaN(ts) && ts <= now) { idx = i; break; }
    }
    if (idx < 0) idx = 0;
    return estimateCurrentDrift(h.ocean_current_u_mps[idx], h.ocean_current_v_mps[idx], 1);
  }, [pkg.forecast, now]);

  const refPosLat = fix?.latitude ?? pkg.landing_centre.latitude;
  const refPosLon = fix?.longitude ?? pkg.landing_centre.longitude;
  const directOverrideKm = overrideTarget ? haversineKm(refPosLat, refPosLon, overrideTarget.latitude, overrideTarget.longitude) : null;
  const directOverrideBrg = overrideTarget ? initialBearingDeg(refPosLat, refPosLon, overrideTarget.latitude, overrideTarget.longitude) : null;
  const directOverrideEta = overrideTarget && directOverrideKm !== null ? etaMinutes(directOverrideKm, snap.smoothedSogMps) : null;
  const directTurnInstruction: TurnInstruction | undefined = (() => {
    if (!overrideTarget || directOverrideKm === null || directOverrideBrg === null) return undefined;
    if (directOverrideKm <= 0.15) return { action: 'ARRIVED', degrees: 0, referenceSource: 'NONE' };
    const refHdg = snap.cogDeg ?? snap.compassHeadingDeg;
    const refSrc: TurnInstruction['referenceSource'] = snap.cogDeg !== null ? 'COG' : snap.compassHeadingDeg !== null ? 'COMPASS' : 'NONE';
    if (refHdg === null) return { action: 'NO_HEADING', degrees: 0, referenceSource: 'NONE' };
    const diff = angularDiffDeg(refHdg, directOverrideBrg);
    if (Math.abs(diff) <= 10) return { action: 'ON_COURSE', degrees: 0, referenceSource: refSrc };
    return { action: diff > 0 ? 'TURN_RIGHT' : 'TURN_LEFT', degrees: Math.round(Math.abs(diff)), referenceSource: refSrc };
  })();

  return (
    <div className={`marine-hud${nightMode ? ' marine-night' : ''}`}>
      {/* Persistent Marine Top HUD Bar */}
      <div className="marine-topbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => setShowSafetySources((s) => !s)}
            style={{
              background: safetyTheme.bg,
              border: `1px solid ${safetyTheme.border}`,
              color: safetyTheme.fg,
              borderRadius: 6,
              padding: '5px 10px',
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {isMarathi ? safetyTheme.labelMr : safetyTheme.labelEn}
          </button>

          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              padding: '4px 8px',
              borderRadius: 6,
              background:
                snap.gpsHealth === 'LIVE'
                  ? 'rgba(16,185,129,0.2)'
                  : snap.gpsHealth === 'LOST'
                    ? 'rgba(239,68,68,0.25)'
                    : 'rgba(245,158,11,0.22)',
              color: snap.gpsHealth === 'LIVE' ? '#6ee7b7' : snap.gpsHealth === 'LOST' ? '#fca5a5' : '#fde68a',
            }}
          >
            GPS: {snap.gpsHealth}
            {fix?.accuracy_m ? ` ±${Math.round(fix.accuracy_m)}m` : ''}
          </span>

          <span style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, background: 'rgba(148,163,184,0.16)' }}>
            {online ? t('exp_online') : t('exp_offline')}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setNightMode((n) => !n)}>
            {nightMode ? <Sun size={14} /> : <Moon size={14} />}
            {nightMode ? (isMarathi ? 'डे मोड' : 'Day') : isMarathi ? 'नाइट मोड' : 'Night'}
          </button>
          <button type="button" className="btn btn-danger btn-sm" onClick={() => setShowEmergency((e) => !e)}>
            <ShieldAlert size={14} />
            {isMarathi ? 'आपत्कालीन / MOB' : 'Emergency / MOB'}
          </button>
        </div>
      </div>

      {/* Simulation Warning Banner (isolated) */}
      {simulating && (
        <div
          role="alert"
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            marginBottom: 12,
            background: 'rgba(245,158,11,0.2)',
            border: '1px solid #f59e0b',
            color: '#fde68a',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          SIMULATION MODE ACTIVE ({simulationScenario}) — Artificial vessel positions are NOT saved to the Black Box or synced.
        </div>
      )}

      {/* Anchor Drift / Crash Recovery / Expiry Banners */}
      {anchorDriftAlert && (
        <div role="alert" style={{ padding: '10px 14px', borderRadius: 8, marginBottom: 12, background: 'rgba(239,68,68,0.3)', border: '2px solid #ef4444', color: '#fecaca', fontWeight: 700 }}>
          ANCHOR DRIFT ALERT: Vessel drifted {anchorDriftKm !== null ? `${Math.round(anchorDriftKm * 1000)} m` : ''} beyond {anchorWatch?.radius_m} m limit!
        </div>
      )}

      {restoredFromStorage && (
        <div style={{ padding: '8px 12px', borderRadius: 8, marginBottom: 12, background: 'rgba(56,189,248,0.14)', border: '1px solid rgba(56,189,248,0.4)', fontSize: 12 }}>
          {isMarathi
            ? `मागील प्रवासाची स्थिती IndexedDB मधून पुनर्स्थापित केली (${savedTrack.length} ट्रॅक बिंदू).`
            : `Restored active voyage from device storage (${savedTrack.length} track point(s) recovered).`}
        </div>
      )}

      {/* Safety Summary & Source Provenance */}
      <div
        style={{
          padding: '12px 14px',
          borderRadius: 10,
          marginBottom: 14,
          background: safetyTheme.bg,
          border: `1px solid ${safetyTheme.border}`,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 700, color: safetyTheme.fg }}>
            {isMarathi ? safetyTheme.labelMr : safetyTheme.labelEn}: <span style={{ fontWeight: 500 }}>{safetyReport.reason}</span>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowSafetySources((s) => !s)}>
            {showSafetySources ? (isMarathi ? 'स्रोत लपवा' : 'Hide sources') : isMarathi ? 'स्रोत पहा' : 'Safety sources'}
          </button>
        </div>
        <div style={{ fontSize: 12, marginTop: 4, color: 'var(--hud-muted)' }}>
          {safetyReport.currentConditions.wave_height_m !== null && `Waves ${safetyReport.currentConditions.wave_height_m.toFixed(1)} m · `}
          {safetyReport.currentConditions.wind_speed_kmh !== null && `Wind ${safetyReport.currentConditions.wind_speed_kmh.toFixed(0)} km/h · `}
          {safetyReport.warningsExpired && <strong style={{ color: '#fcd34d' }}>Warnings expired · </strong>}
          {safetyReport.forecastExpired && <strong style={{ color: '#fcd34d' }}>Forecast expired · </strong>}
          {safetyReport.upcomingHazard.detected && <strong style={{ color: '#fcd34d' }}>{safetyReport.upcomingHazard.reason}</strong>}
        </div>

        {showSafetySources && (
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(148,163,184,0.25)', display: 'grid', gap: 6, fontSize: 12 }}>
            {safetyReport.sources.map((src) => (
              <div key={src.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                <div>
                  <strong>{src.name}</strong> ({src.dataType}) — <span style={{ color: 'var(--hud-muted)' }}>{src.note}</span>
                </div>
                <span style={{ fontWeight: 700, color: src.status === 'VALID' ? '#6ee7b7' : src.status === 'EXPIRED' ? '#fcd34d' : '#cbd5e1' }}>
                  {src.status}
                </span>
              </div>
            ))}
            <div style={{ fontSize: 11, color: 'var(--hud-muted)', marginTop: 4 }}>{safetyReport.disclaimer}</div>
          </div>
        )}
      </div>

      {/* Emergency Return Panel */}
      {showEmergency && (
        <EmergencyReturn
          pkg={pkg}
          fix={fix}
          smoothedSogMps={snap.smoothedSogMps}
          now={now}
          isMarathi={isMarathi}
          mob={mob}
          anchorWatch={anchorWatch}
          anchorDriftKm={anchorDriftKm}
          anchorDriftAlert={anchorDriftAlert}
          onMarkMob={handleMarkMob}
          onClearMob={handleClearMob}
          onSetAnchor={handleSetAnchor}
          onClearAnchor={handleClearAnchor}
          onClose={() => setShowEmergency(false)}
        />
      )}

      {/* Primary Marine Compass & Remaining Distance HUD */}
      <MarineCompass
        dark
        targetBearingDeg={directOverrideBrg ?? snap.nextWaypointBearingDeg}
        cogDeg={snap.cogDeg}
        compassHeadingDeg={snap.compassHeadingDeg}
        compassSupported={geo.compassSupported}
        headingCogDiffDeg={snap.headingCogDiffDeg}
        remainingKm={directOverrideKm ?? snap.remainingDistanceKm}
        totalKm={overrideTarget && directOverrideKm !== null ? Math.max(directOverrideKm, 0.1) : snap.totalRouteKm}
        etaMinutes={overrideTarget ? directOverrideEta : snap.etaMinutes}
        etaReliability={snap.etaReliability}
        gpsHealth={snap.gpsHealth}
        stationary={snap.stationary}
        simulated={!!fix?.simulated}
        turnInstruction={directTurnInstruction ?? snap.turnInstruction}
        destinationName={overrideTarget ? overrideTarget.name : pkg.destination.name}
        isMarathi={isMarathi}
      />

      {/* Secondary Telemetry Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 14 }}>
        <div className="marine-stat">
          <div className="marine-stat-label">{isMarathi ? 'वेग (SOG)' : 'Speed (SOG)'}</div>
          <div className="marine-stat-val num">
            {snap.smoothedSogMps !== null ? `${mpsToKnots(snap.smoothedSogMps).toFixed(1)} kn` : '—'}
          </div>
          <div className="marine-stat-sub num">
            {snap.smoothedSogMps !== null ? `${(snap.smoothedSogMps * 3.6).toFixed(1)} km/h` : 'Unavailable'}
          </div>
        </div>

        <div className="marine-stat">
          <div className="marine-stat-label">{t('exp_off_track')}</div>
          <div className="marine-stat-val num" style={{ color: snap.isOffTrack ? '#fca5a5' : undefined }}>
            {`${Math.abs(snap.crossTrackKm).toFixed(2)} km ${snap.crossTrackKm < 0 ? '←' : '→'}`}
          </div>
          <div className="marine-stat-sub num">
            {t('exp_waypoint')} {snap.nextWaypointIndex}/{Math.max(1, snap.totalWaypoints - 1)} · {snap.distanceToNextWaypointKm.toFixed(1)} km
          </div>
        </div>

        <div className="marine-stat">
          <div className="marine-stat-label">{t('exp_position')}</div>
          <div className="marine-stat-val num" style={{ fontSize: 15 }}>
            {fix ? `${fix.latitude.toFixed(4)}°N ${fix.longitude.toFixed(4)}°E` : '—'}
          </div>
          <div className="marine-stat-sub num">
            {fix ? formatDms(fix.latitude, fix.longitude) : t('exp_waiting_gps')}
          </div>
        </div>

        <div className="marine-stat">
          <div className="marine-stat-label">{t('exp_nearest_return')}</div>
          <div className="marine-stat-val" style={{ fontSize: 15 }}>
            {isMarathi ? nearestHarbour.name_mr : nearestHarbour.name}
          </div>
          <div className="marine-stat-sub num">
            {nearestHarbour.distKm.toFixed(1)} km ({kmToNm(nearestHarbour.distKm).toFixed(1)} nm)
          </div>
        </div>

        <div className="marine-stat">
          <div className="marine-stat-label">{isMarathi ? 'प्रवाह / बोट ड्रिफ्ट (1 तास)' : 'Current Drift (1 h est.)'}</div>
          <div className="marine-stat-val num" style={{ fontSize: 15 }}>
            {currentDrift ? `${currentDrift.speedKnots.toFixed(2)} kn ${currentDrift.compass}` : '—'}
          </div>
          <div className="marine-stat-sub num">
            {currentDrift
              ? `~${currentDrift.distanceKm.toFixed(1)} km (${Math.round(currentDrift.bearingDeg)}°) · coarse`
              : 'Unavailable'}
          </div>
        </div>
      </div>

      {shallowProximity && (
        <div role="alert" style={{ padding: '10px 14px', borderRadius: 8, marginBottom: 12, background: 'rgba(245,158,11,0.22)', border: '1px solid #f59e0b', color: '#fde68a', fontSize: 12, fontWeight: 600 }}>
          {isMarathi
            ? `उथळ पाण्याची सूचना: GEBCO ≤${shallowProximity.depthM} मी समोच्च रेषा ${shallowProximity.distanceKm.toFixed(1)} किमी जवळ (अधिकृत नेव्हिगेशन खोली नाही).`
            : `Shallow-water reference notice: GEBCO ≤${shallowProximity.depthM} m contour within ${shallowProximity.distanceKm.toFixed(1)} km (general-purpose bathymetry only — NOT verified safe depth).`}
        </div>
      )}

      {/* Advanced Marine Chartplotter */}
      <div style={{ position: 'relative' }}>
        <div className="map-frame" style={{ height: 420, borderColor: 'var(--hud-border)' }}>
          <div ref={mapRef} className="map-canvas" style={{ background: activePointOnLand ? LAND_OSM_BG : OCEAN_BG_BY_THEME[mapTheme] }} />
        </div>
        <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 800, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge color={basemapKind === 'pmtiles' ? colors.green : basemapKind === 'osm' ? colors.accent : colors.slate}>
            {basemapKind === 'pmtiles'
              ? 'Offline chart'
              : basemapKind === 'osm'
                ? 'Land · OpenStreetMap'
                : basemapKind === 'fallback'
                  ? 'Coordinate grid'
                  : '…'}
          </Badge>
          {selectedMapPoint && (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => {
                  setOverrideTarget({
                    latitude: selectedMapPoint.latitude,
                    longitude: selectedMapPoint.longitude,
                    name: `${selectedMapPoint.latitude.toFixed(4)}°N, ${selectedMapPoint.longitude.toFixed(4)}°E`,
                  });
                }}
                style={{ padding: '2px 8px', fontSize: 11 }}
              >
                <Navigation size={12} aria-hidden />
                {isMarathi ? 'येथे मार्गक्रमण करा' : 'Navigate here'}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setSelectedMapPoint(null)}
                style={{ padding: '2px 8px', fontSize: 11 }}
              >
                {isMarathi ? 'ऑटो नकाशा' : 'Auto map'}
              </button>
            </>
          )}
          {overrideTarget && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setOverrideTarget(null)}
              style={{ padding: '2px 8px', fontSize: 11, borderColor: '#38bdf8', color: '#7dd3fc' }}
            >
              {isMarathi ? 'मूळ मार्ग परत आणा' : 'Restore route'}
            </button>
          )}
          {geo.wakeLock && <Badge color={colors.accent}>Wake lock</Badge>}
          {!pkg.offline_assets.bathymetry.available && (
            <Badge color={colors.amber}>No offline bathymetry</Badge>
          )}
          {hasShallowData && <Badge color={colors.amber}>GEBCO 10/20m contours (not nav chart)</Badge>}
          {mpaCount > 0 && <Badge color={colors.slate}>{mpaCount} Protected area(s)</Badge>}
        </div>
        <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 800, display: 'flex', gap: 6 }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setFollow(true);
              if (fix && mapInst.current) {
                mapInst.current.setView([fix.latitude, fix.longitude], Math.max(mapInst.current.getZoom(), 11));
              }
            }}
          >
            <LocateFixed size={13} aria-hidden />
            {isMarathi ? 'माझे स्थान' : follow ? 'My Location' : 'Recenter'}
          </button>
        </div>
      </div>

      <div style={{ fontSize: 11, color: 'var(--hud-muted)', margin: '8px 0 14px', display: 'flex', gap: 6, alignItems: 'center' }}>
        <AlertTriangle size={13} />
        <span>
          Direct great-circle line is a distance reference only, NOT a safe navigable route.{' '}
          {pkg.offline_assets.nautical_charts.note}
        </span>
      </div>

      {/* GPS Help & Isolated Simulation Testing */}
      {(() => {
        const help = gpsHelp(geo, isMarathi);
        return (
          <div className="marine-panel" style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 13 }}>
                <strong>GPS Lifecycle:</strong>{' '}
                {simulating ? 'SIMULATED' : snap.gpsHealth} · {geo.visibilityState === 'visible' ? 'Foreground active' : 'Backgrounded'}
                {snap.rejectedJumpCount > 0 && ` · ${snap.rejectedJumpCount} jump(s) filtered`}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                  value={simulationScenario}
                  onChange={(e) => onChangeScenario(e.target.value as SimulationScenario)}
                  className="select"
                  style={{ width: 'auto', padding: '5px 8px', fontSize: 12 }}
                  aria-label="Simulation scenario"
                >
                  {SIMULATION_SCENARIOS.map((sc) => (
                    <option key={sc.id} value={sc.id}>
                      {isMarathi ? sc.labelMr : sc.labelEn}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn btn-secondary btn-sm" onClick={onToggleSimulation}>
                  {simulating ? (isMarathi ? 'सिम्युलेशन थांबवा' : 'Stop simulation') : isMarathi ? 'चाचणी सिम्युलेशन' : 'Test Simulation'}
                </button>
              </div>
            </div>
            {help && !simulating && (
              <div style={{ marginTop: 8, fontSize: 12, color: '#fde68a' }}>
                <strong>{help.title}:</strong> {help.steps.join(' ')}
              </div>
            )}
          </div>
        );
      })()}

      {/* Voyage Black Box, Replay & Export */}
      <div className="marine-panel" style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          <div>
            <strong>{isMarathi ? 'प्रवास ब्लॅक बॉक्स' : 'Voyage Black Box'}</strong>{' '}
            <span className="num" style={{ fontSize: 12, color: 'var(--hud-muted)' }}>
              ({trackCount} track pts · {events.length} events · {catches.length} catches)
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={savedTrack.length === 0 && events.length === 0}
              onClick={() =>
                downloadTextFile(
                  `matsya-voyage-${pkg.manifest.package_id.slice(0, 8)}.gpx`,
                  exportVoyageGpx(pkg, savedTrack, events, catches),
                  'application/gpx+xml',
                )
              }
            >
              <Download size={13} /> GPX
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={savedTrack.length === 0 && events.length === 0}
              onClick={() =>
                downloadTextFile(
                  `matsya-voyage-${pkg.manifest.package_id.slice(0, 8)}.csv`,
                  exportVoyageCsv(savedTrack, events, catches),
                  'text/csv',
                )
              }
            >
              <Download size={13} /> CSV
            </button>
          </div>
        </div>

        {savedTrack.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, marginBottom: 6 }}>
            <Play size={13} />
            <span>{isMarathi ? 'प्रवास रीप्ले' : 'Replay'}:</span>
            <input
              type="range"
              min={0}
              max={savedTrack.length - 1}
              value={replayIndex ?? savedTrack.length - 1}
              onChange={(e) => setReplayIndex(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            {replayIndex !== null && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReplayIndex(null)}>
                Clear
              </button>
            )}
          </div>
        )}

        <div style={{ fontSize: 11, color: 'var(--hud-muted)' }}>
          {isMarathi
            ? 'टीप: ब्राउझर PWA मध्ये स्क्रीन बंद केल्यास किंवा अ‍ॅप मागे गेल्यास सतत GPS नोंदणी हमी देता येत नाही; अ‍ॅप समोर (foreground) ठेवा.'
            : 'Browser PWA limitation: continuous background GPS tracking is NOT guaranteed when the device sleeps or app is backgrounded. Keep this screen active.'}
        </div>
      </div>

      {/* Bottom Action Bar */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Button onClick={onLogCatch} style={{ flex: 1 }}>
          {t('exp_log_catch')}
        </Button>
        <Button variant="danger" onClick={onEnd}>
          {t('exp_end')}
        </Button>
      </div>
    </div>
  );
}

export { AtSea as AtSeaHud };
