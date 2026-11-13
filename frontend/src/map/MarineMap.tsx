/**
 * MatsyaAI Maharashtra — Interactive Fisherman-Facing Marine Map
 *
 * Visualizes:
 * 1. Canonical 0.25° grid with Predicted Apparent Fishing Activity (Phase 3 model)
 * 2. Official INCOIS Potential Fishing Zones (PFZ)
 * 3. Independent Marine Safety and Weather Warnings
 * 4. Coastal Landing Centres and Harbours
 */

import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { MapSummaryResponse, CellPrediction } from '../types/map';

interface MarineMapProps {
  data: MapSummaryResponse;
  isMarathi: boolean;
  onToggleDemo: () => void;
  isDemo: boolean;
}

export const MarineMap: React.FC<MarineMapProps> = ({
  data,
  isMarathi,
  onToggleDemo,
  isDemo,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const gridLayerRef = useRef<L.LayerGroup | null>(null);
  const pfzLayerRef = useRef<L.LayerGroup | null>(null);
  const landingLayerRef = useRef<L.LayerGroup | null>(null);

  const [showPredictions, setShowPredictions] = useState<boolean>(true);
  const [showPFZ, setShowPFZ] = useState<boolean>(true);
  const [showLandingCentres, setShowLandingCentres] = useState<boolean>(true);
  const [selectedCell, setSelectedCell] = useState<CellPrediction | null>(null);

  const [isMobile, setIsMobile] = useState<boolean>(window.innerWidth <= 768);
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Initialize Leaflet Map once
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Centered on Maharashtra marine coast (15.5N - 20.0N, 72.0E - 74.0E)
    const map = L.map(mapContainerRef.current, {
      center: [17.85, 72.85],
      zoom: 7,
      minZoom: 6,
      maxZoom: 11,
      zoomControl: false,
    });

    // Standard OpenStreetMap basemap
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Initialize layer groups
    gridLayerRef.current = L.layerGroup().addTo(map);
    pfzLayerRef.current = L.layerGroup().addTo(map);
    landingLayerRef.current = L.layerGroup().addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Prediction Grid Layer
  useEffect(() => {
    if (!gridLayerRef.current) return;
    gridLayerRef.current.clearLayers();

    if (!showPredictions || !data.predictions) return;

    const resolution = 0.25;
    const halfRes = resolution / 2;

    data.predictions.forEach((cell) => {
      const bounds: L.LatLngBoundsExpression = [
        [cell.latitude - halfRes, cell.longitude - halfRes],
        [cell.latitude + halfRes, cell.longitude + halfRes],
      ];

      const prob = cell.predicted_apparent_fishing_probability;
      const isHigh = cell.predicted_apparent_fishing_binary === 1;

      // Color coding based on apparent fishing probability
      let fillColor = '#0d2238';
      let fillOpacity = 0.15;
      let strokeColor = '#1e3a5f';
      let weight = 0.5;

      if (isHigh) {
        fillColor = '#00e5ff'; // Bright cyan for high predicted effort
        fillOpacity = 0.55;
        strokeColor = '#00ffff';
        weight = 1.5;
      } else if (prob >= 0.20) {
        fillColor = '#1976d2'; // Medium blue for moderate
        fillOpacity = 0.35;
        strokeColor = '#42a5f5';
        weight = 0.8;
      }

      const rect = L.rectangle(bounds, {
        color: strokeColor,
        weight: weight,
        fillColor: fillColor,
        fillOpacity: fillOpacity,
      });

      rect.on('click', () => {
        setSelectedCell(cell);
      });



      rect.addTo(gridLayerRef.current!);
    });
  }, [data.predictions, showPredictions, isMarathi]);

  // Update Official INCOIS PFZ Layer
  useEffect(() => {
    if (!pfzLayerRef.current) return;
    pfzLayerRef.current.clearLayers();

    if (!showPFZ || !data.pfz_advisory || !data.pfz_advisory.locations) return;

    data.pfz_advisory.locations.forEach((pfz) => {
      const marker = L.circleMarker([pfz.latitude, pfz.longitude], {
        radius: 8,
        color: '#00e676',
        fillColor: '#00e676',
        fillOpacity: 0.85,
        weight: 2,
      });

      const ring = L.circle([pfz.latitude, pfz.longitude], {
        radius: 4000,
        color: '#00e676',
        fillColor: '#00e676',
        fillOpacity: 0.15,
        weight: 1.5,
        dashArray: '4, 6',
      });

      const popupHtml = `
        <div style="font-family: 'Inter', sans-serif; font-size: 12px; line-height: 1.4; color: #111;">
          <h4 style="margin: 0 0 6px 0; color: #00796b;">📍 ${isMarathi ? 'अधिकृत INCOIS PFZ सल्ला' : 'Official INCOIS PFZ Advisory'}</h4>
          <strong>${isMarathi ? 'लँडिंग केंद्र' : 'Landing Centre'}:</strong> ${pfz.landing_centre}<br/>
          <strong>${isMarathi ? 'दिशा' : 'Direction'}:</strong> ${pfz.direction} (${pfz.bearing_degrees}°)<br/>
          <strong>${isMarathi ? 'अंतर' : 'Distance'}:</strong> ${typeof pfz.distance_km === 'number' ? pfz.distance_km.toFixed(1) : pfz.distance_km} km<br/>
          <strong>${isMarathi ? 'वैधता' : 'Validity'}:</strong> ${data.pfz_advisory.validity_date ? new Date(data.pfz_advisory.validity_date).toLocaleDateString() : 'N/A'}<br/>
          <p style="margin: 6px 0 0 0; font-size: 10px; color: #666;">
            ${isMarathi ? '*हा अधिकृत सरकारी सल्ला आहे, ML अंदाज नाही.' : '*Official Indian Govt advisory, independent of ML.'}
          </p>
        </div>
      `;
      marker.bindPopup(popupHtml);

      marker.addTo(pfzLayerRef.current!);
      ring.addTo(pfzLayerRef.current!);
    });
  }, [data.pfz_advisory, showPFZ, isMarathi]);

  // Update Coastal Landing Centres Layer
  useEffect(() => {
    if (!landingLayerRef.current) return;
    landingLayerRef.current.clearLayers();

    if (!showLandingCentres || !data.landing_centres) return;

    data.landing_centres.forEach((centre) => {
      const icon = L.divIcon({
        className: 'landing-centre-icon',
        html: `<div style="background: #ffb300; border: 2px solid #fff; border-radius: 50%; width: 10px; height: 10px; box-shadow: 0 0 6px rgba(0,0,0,0.5);"></div>`,
        iconSize: [10, 10],
      });

      const marker = L.marker([centre.latitude, centre.longitude], { icon });
      marker.bindPopup(`
        <div style="font-family: 'Inter', sans-serif; font-size: 12px; color: #111;">
          <strong>⚓ ${centre.name}</strong><br/>
          <span>${centre.district} District, Maharashtra</span>
        </div>
      `);
      marker.addTo(landingLayerRef.current!);
    });
  }, [data.landing_centres, showLandingCentres]);

  const safety = data.marine_safety;
  const isSafetyCaution = safety.overall_status === 'CAUTION';
  const isSafetyUnsafe = safety.overall_status === 'UNSAFE';
  const isSafetyConfirmed = safety.overall_status === 'SAFE_CONFIRMED';

  const safetyBg = isSafetyUnsafe
    ? '#b71c1c'
    : isSafetyCaution
    ? '#e65100'
    : isSafetyConfirmed
    ? '#1b5e20'
    : '#37474f'; // neutral dark slate for NO_WARNING_DATA — never green

  const safetyIcon = isSafetyUnsafe ? '🚨' : isSafetyCaution ? '⚠️' : isSafetyConfirmed ? '🛡️' : 'ℹ️';

  // Human-readable label — raw NO_WARNING_DATA never shown to user
  const safetyStatusLabel =
    safety.overall_status === 'UNSAFE'
      ? (isMarathi ? 'असुरक्षित' : 'UNSAFE')
      : safety.overall_status === 'CAUTION'
      ? (isMarathi ? 'सावधान' : 'CAUTION')
      : safety.overall_status === 'SAFE_CONFIRMED'
      ? (isMarathi ? 'सुरक्षित पुष्टी' : 'SAFE CONFIRMED')
      : (isMarathi ? 'सुरक्षा माहिती अनुपलब्ध' : 'SAFETY DATA UNAVAILABLE');

  const naText = isMarathi ? 'उपलब्ध नाही' : 'N/A';

  return (
    <div
      id="fishing-map"
      className="marine-map-wrapper"
      style={{
        position: 'relative',
        width: '100%',
        height: isMobile ? '500px' : '700px',
        borderRadius: '16px',
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      {/* 1. Independent Marine Safety Banner */}
      <div
        className="marine-safety-banner"
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          right: 12,
          zIndex: 1000,
          background: safetyBg,
          color: '#fff',
          padding: isMobile ? '8px 12px' : '10px 16px',
          borderRadius: '10px',
          boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(255,255,255,0.2)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: isMobile ? '16px' : '20px' }}>{safetyIcon}</span>
          <div>
            <div style={{ fontSize: isMobile ? '11px' : '13px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              {isMarathi ? 'सागरी सुरक्षा स्थिती' : 'Official Marine Safety'}: {safetyStatusLabel}
            </div>
            {!isMobile && (
              <div style={{ fontSize: '11px', opacity: 0.9 }}>{safety.message}</div>
            )}
          </div>
        </div>
        <div style={{ textAlign: 'right', fontSize: '10px', opacity: 0.8 }}>
          <span>{isMarathi ? 'ML पासून स्वतंत्र' : 'Decoupled from ML'}</span>
        </div>
      </div>

      {/* 2. Map Container */}
      <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />

      {/* 3. Layer Controls Floating HUD */}
      <div
        className="map-layer-controls"
        style={{
          position: 'absolute',
          bottom: isMobile ? 12 : 24,
          left: isMobile ? 12 : 20,
          zIndex: 999,
          background: 'rgba(10, 22, 40, 0.85)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: '12px',
          padding: '12px 16px',
          color: '#fff',
          fontSize: '12px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          minWidth: isMobile ? '160px' : '220px',
        }}
      >
        <details open={!isMobile}>
          <summary style={{ cursor: 'pointer', fontWeight: 700, marginBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '4px', outline: 'none' }}>
            <span>🗺️ {isMarathi ? 'नकाशा स्तर' : 'Map Layers'}</span>
          </summary>
          <div style={{ padding: '4px 0' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '6px', padding: '2px 0' }}>
              <input
                type="checkbox"
                checked={showPredictions}
                onChange={(e) => setShowPredictions(e.target.checked)}
              />
              <span style={{ color: '#00e5ff', fontWeight: 600 }}>■</span>
              <span>{isMarathi ? 'अपेक्षित मासेमारी (ML)' : 'Fishing Activity (ML)'}</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '6px', padding: '2px 0' }}>
              <input
                type="checkbox"
                checked={showPFZ}
                onChange={(e) => setShowPFZ(e.target.checked)}
              />
              <span style={{ color: '#00e676', fontWeight: 600 }}>●</span>
              <span>{isMarathi ? 'INCOIS PFZ (सरकारी)' : 'INCOIS PFZ (Govt)'}</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '6px', padding: '2px 0' }}>
              <input
                type="checkbox"
                checked={showLandingCentres}
                onChange={(e) => setShowLandingCentres(e.target.checked)}
              />
              <span style={{ color: '#ffb300', fontWeight: 600 }}>⚓</span>
              <span>{isMarathi ? 'लँडिंग केंद्रे' : 'Landing Centres'}</span>
            </label>

            {/* Demo Mode Switch */}
            <div style={{ marginTop: '8px', paddingTop: '6px', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', color: isDemo ? '#ffb300' : '#4caf50' }}>
                {isDemo ? (isMarathi ? 'डेमो मोड' : 'DEMO MODE') : (isMarathi ? 'थेट डेटा' : 'LIVE API')}
              </span>
              <button
                onClick={onToggleDemo}
                style={{
                  background: isDemo ? '#ffb300' : 'rgba(255,255,255,0.15)',
                  color: isDemo ? '#000' : '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '10px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  minHeight: '28px',
                }}
              >
                {isDemo ? 'Use Live' : 'Use Demo'}
              </button>
            </div>
          </div>
        </details>
      </div>

      {/* 4. Cell Detail Panel (bottom sheet on mobile, sidebar on desktop) */}
      {selectedCell && (
        <div
          className="cell-inspector-card"
          style={{
            position: 'absolute',
            top: isMobile ? 'auto' : 75,
            bottom: isMobile ? 0 : 'auto',
            right: isMobile ? 0 : 20,
            left: isMobile ? 0 : 'auto',
            zIndex: 1001,
            width: isMobile ? '100%' : '284px',
            maxHeight: isMobile ? '55vh' : 'calc(100% - 95px)',
            overflowY: 'auto',
            background: 'rgba(7, 18, 32, 0.97)',
            backdropFilter: 'blur(20px)',
            border: isMobile ? 'none' : '1px solid rgba(0, 229, 255, 0.3)',
            borderTop: isMobile ? '2px solid rgba(0, 229, 255, 0.4)' : undefined,
            borderRadius: isMobile ? '16px 16px 0 0' : '14px',
            padding: '16px',
            color: '#fff',
            fontSize: '12px',
            boxShadow: '0 -8px 40px rgba(0,0,0,0.7)',
          }}
        >
          {/* Header row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 800, color: '#00e5ff' }}>
              📍 {isMarathi ? 'निवडलेले मासेमारी क्षेत्र' : 'Selected Fishing Area'}
            </span>
            <button
              onClick={() => setSelectedCell(null)}
              style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', cursor: 'pointer', fontSize: '14px', borderRadius: '6px', padding: '4px 8px', minWidth: '32px', minHeight: '32px' }}
            >
              ✕
            </button>
          </div>

          {/* ⚠️ SAFETY STATUS — always shown prominently, NEVER hidden */}
          <div style={{
            background: selectedCell.safety_status === 'UNSAFE'
              ? 'rgba(183, 28, 28, 0.3)'
              : selectedCell.safety_status === 'CAUTION'
              ? 'rgba(230, 81, 0, 0.3)'
              : selectedCell.safety_status === 'SAFE_CONFIRMED'
              ? 'rgba(27, 94, 32, 0.3)'
              : 'rgba(55, 71, 79, 0.3)',
            border: `1px solid ${
              selectedCell.safety_status === 'UNSAFE' ? '#ff5252'
              : selectedCell.safety_status === 'CAUTION' ? '#ffa000'
              : selectedCell.safety_status === 'SAFE_CONFIRMED' ? '#00e676'
              : '#546e7a'
            }`,
            padding: '10px 12px',
            borderRadius: '8px',
            marginBottom: '10px',
          }}>
            <div style={{ fontSize: '10px', color: '#aaa', textTransform: 'uppercase', marginBottom: '4px' }}>
              {isMarathi ? 'सागरी सुरक्षा (IMD/INCOIS)' : 'Sea Safety (IMD/INCOIS)'}
            </div>
            <div style={{
              fontSize: '18px',
              fontWeight: 900,
              color: selectedCell.safety_status === 'UNSAFE' ? '#ff5252'
                : selectedCell.safety_status === 'CAUTION' ? '#ffca28'
                : selectedCell.safety_status === 'SAFE_CONFIRMED' ? '#00e676'
                : '#90a4ae',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <span>{selectedCell.safety_status === 'UNSAFE' ? '🚨' : selectedCell.safety_status === 'CAUTION' ? '⚠️' : selectedCell.safety_status === 'SAFE_CONFIRMED' ? '🛡️' : 'ℹ️'}</span>
              <span>{
                selectedCell.safety_status === 'UNSAFE' ? (isMarathi ? 'असुरक्षित' : 'UNSAFE')
                : selectedCell.safety_status === 'CAUTION' ? (isMarathi ? 'सावधान' : 'CAUTION')
                : selectedCell.safety_status === 'SAFE_CONFIRMED' ? (isMarathi ? 'सुरक्षित पुष्टी' : 'SAFE CONFIRMED')
                : (isMarathi ? 'सुरक्षा माहिती अनुपलब्ध' : 'SAFETY DATA UNAVAILABLE')
              }</span>
            </div>
            <div style={{ fontSize: '9px', color: '#aaa', marginTop: '4px', fontStyle: 'italic' }}>
              {isMarathi ? 'ML मॉडेलपासून पूर्णपणे स्वतंत्र' : 'Strictly independent of ML predictions'}
            </div>
          </div>

          {/* Fishing Potential */}
          <div style={{ marginBottom: '10px' }}>
            <div style={{ fontSize: '10px', color: '#888', textTransform: 'uppercase', marginBottom: '4px' }}>
              {isMarathi ? 'अपेक्षित संभाव्यता (T+1)' : 'Fishing Potential (Next Day T+1)'}
            </div>
            <div style={{ fontSize: '28px', fontWeight: 900, color: selectedCell.predicted_apparent_fishing_binary === 1 ? '#00e5ff' : '#90caf9' }}>
              {(selectedCell.predicted_apparent_fishing_probability * 100).toFixed(1)}%
            </div>
            <div style={{
              display: 'inline-block',
              background: selectedCell.predicted_apparent_fishing_binary === 1 ? 'rgba(0,229,255,0.15)' : 'rgba(255,255,255,0.07)',
              color: selectedCell.predicted_apparent_fishing_binary === 1 ? '#00e5ff' : '#ccc',
              padding: '3px 10px',
              borderRadius: '4px',
              fontWeight: 700,
              fontSize: '12px',
              marginTop: '2px',
            }}>
              {selectedCell.prediction_label}
            </div>
          </div>

          {/* Environmental data */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', background: 'rgba(255,255,255,0.04)', padding: '8px', borderRadius: '8px', marginBottom: '10px' }}>
            <div>
              <span style={{ fontSize: '10px', color: '#aaa' }}>{isMarathi ? 'लाटांची उंची' : 'Wave Height'}:</span><br/>
              <strong>{selectedCell.current_wave_height_m !== null ? `${selectedCell.current_wave_height_m.toFixed(1)} m` : naText}</strong>
            </div>
            <div>
              <span style={{ fontSize: '10px', color: '#aaa' }}>{isMarathi ? 'वाऱ्याचा वेग' : 'Wind Speed'}:</span><br/>
              <strong>{selectedCell.current_wind_speed_kmh !== null ? `${selectedCell.current_wind_speed_kmh.toFixed(1)} km/h` : naText}</strong>
            </div>
            <div>
              <span style={{ fontSize: '10px', color: '#aaa' }}>{isMarathi ? 'किनाऱ्यापासून अंतर' : 'Coast Distance'}:</span><br/>
              <strong>{selectedCell.distance_to_coast_km.toFixed(1)} km</strong>
            </div>
          </div>

          <div style={{ fontSize: '9px', color: '#888', fontStyle: 'italic', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '6px', marginBottom: '8px' }}>
            {selectedCell.disclaimer}
          </div>

          {/* Provenance — collapsed by default */}
          {data.prediction_provenance && (
            <details style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '6px', padding: '6px 10px', fontSize: '10px' }}>
              <summary style={{ cursor: 'pointer', fontWeight: 700, color: '#90caf9', outline: 'none' }}>
                {isMarathi ? 'डेटा संदर्भ (Provenance)' : 'Prediction Data Provenance'}
              </summary>
              <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px', color: '#ccc' }}>
                <div>
                  <span style={{ color: '#aaa' }}>{isMarathi ? 'पर्यावरणीय परिस्थिती:' : 'Environmental:'} </span>
                  <strong style={{ color: '#fff' }}>
                    {data.prediction_provenance.sources.environmental.status === 'LIVE'
                      ? (isMarathi ? 'वर्तमान' : 'Current')
                      : data.prediction_provenance.sources.environmental.status === 'STALE'
                      ? (isMarathi ? 'जुना डेटा' : 'Outdated')
                      : data.prediction_provenance.sources.environmental.status}
                  </strong>
                </div>
                <div>
                  <span style={{ color: '#aaa' }}>{isMarathi ? 'मासेमारी संदर्भ:' : 'Fishing context:'} </span>
                  <strong style={{ color: '#fff' }}>
                    {data.prediction_provenance.sources.gfw_context.status === 'CACHED_HISTORICAL'
                      ? (isMarathi ? 'ऐतिहासिक' : 'Historical')
                      : data.prediction_provenance.sources.gfw_context.status}
                  </strong>
                </div>
                <div>
                  <span style={{ color: '#aaa' }}>{isMarathi ? 'PFZ सल्ला:' : 'PFZ advisory:'} </span>
                  <strong style={{ color: '#fff' }}>
                    {data.prediction_provenance.sources.incois_pfz.status === 'LIVE'
                      ? (isMarathi ? 'वर्तमान' : 'Current')
                      : data.prediction_provenance.sources.incois_pfz.status === 'STALE'
                      ? (isMarathi ? 'जुना डेटा' : 'Outdated')
                      : data.prediction_provenance.sources.incois_pfz.status}
                  </strong>
                </div>
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: '4px', paddingTop: '4px' }}>
                  <span style={{ color: '#aaa' }}>{isMarathi ? 'एकूण:' : 'Overall:'} </span>
                  <strong style={{ color: data.prediction_provenance.overall_data_status === 'LIVE' ? '#00e676' : '#ffb300' }}>
                    {data.prediction_provenance.overall_data_status === 'HISTORICAL_CONTEXT_USED'
                      ? (isMarathi ? 'ऐतिहासिक संदर्भाचा वापर' : 'Historical context used')
                      : data.prediction_provenance.overall_data_status}
                  </strong>
                </div>
              </div>
            </details>
          )}
        </div>
      )}

      {/* 5. Demo Mode Watermark */}
      {isDemo && (
        <div
          style={{
            position: 'absolute',
            bottom: 24,
            right: 60,
            zIndex: 998,
            background: 'rgba(255, 179, 0, 0.9)',
            color: '#000',
            fontWeight: 800,
            fontSize: '11px',
            padding: '4px 12px',
            borderRadius: '20px',
            boxShadow: '0 2px 10px rgba(0,0,0,0.3)',
            letterSpacing: '0.5px',
          }}
        >
          ⚠️ {isMarathi ? 'डेमो मोड: ऐतिहासिक वास्तविक डेटा संदर्भ' : 'DEMO MODE: REAL HISTORICAL REFERENCE'}
        </div>
      )}
    </div>
  );
};
