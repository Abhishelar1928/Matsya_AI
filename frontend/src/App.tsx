/**
 * MatsyaAI Maharashtra — Root Application Component
 *
 * Phase 4: Full Fisherman-Facing Interactive Map & Decision Support Dashboard
 * Features:
 * - Interactive Leaflet Marine Map with 0.25° Canonical Grid
 * - Predicted Apparent Fishing Activity Layer (Validated Phase 3 Model)
 * - Official INCOIS Potential Fishing Zones (PFZ)
 * - Decoupled Independent Marine Safety Alerts
 * - Marathi / English Bilingual Support
 * - Model Provenance & Live/Demo Freshness Status
 */

import { useEffect, useState } from 'react';
import './App.css';
import { fetchHealth, fetchMapSummary } from './services/api';
import { MarineMap } from './map/MarineMap';
import { FreshnessHUD } from './components/FreshnessHUD';
import type { MapSummaryResponse } from './types/map';
import type { HealthResponse } from './types/health';

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [mapData, setMapData] = useState<MapSummaryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isMarathi, setIsMarathi] = useState<boolean>(false);
  const [isDemo, setIsDemo] = useState<boolean>(false);

  // Fetch application health and map data
  const loadDashboardData = async (demo: boolean) => {
    setLoading(true);
    try {
      const [healthRes, mapRes] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchMapSummary(demo),
      ]);
      if (healthRes) setHealth(healthRes);
      setMapData(mapRes);
      setError(null);
    } catch (err: any) {
      console.error('Failed to load map data:', err);
      setError(err.message || 'Failed to connect to backend service.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData(isDemo);
    // Refresh every 60 seconds
    const timer = setInterval(() => loadDashboardData(isDemo), 60000);
    return () => clearInterval(timer);
  }, [isDemo]);

  const toggleDemo = () => {
    const nextState = !isDemo;
    setIsDemo(nextState);
    loadDashboardData(nextState);
  };

  const highActivityCount = mapData?.predictions
    ? mapData.predictions.filter((p) => p.predicted_apparent_fishing_binary === 1).length
    : 0;

  // Safety status display helpers — NO_WARNING_DATA is NEVER green
  const safetyStatus = mapData?.marine_safety.overall_status;
  const safetyColor =
    safetyStatus === 'UNSAFE' ? '#ff5252' :
      safetyStatus === 'CAUTION' ? '#ffb300' :
        safetyStatus === 'SAFE_CONFIRMED' ? '#00e676' :
          '#90a4ae'; // neutral grey-blue for NO_WARNING_DATA

  const safetyLabel =
    safetyStatus === 'UNSAFE' ? (isMarathi ? '🚨 असुरक्षित' : '🚨 UNSAFE') :
      safetyStatus === 'CAUTION' ? (isMarathi ? '⚠️ सावधान' : '⚠️ CAUTION') :
        safetyStatus === 'SAFE_CONFIRMED' ? (isMarathi ? '🛡️ सुरक्षित पुष्टी' : '🛡️ SAFE CONFIRMED') :
          (isMarathi ? 'ℹ️ सुरक्षा माहिती अनुपलब्ध' : 'ℹ️ SAFETY DATA UNAVAILABLE');

  const safetySubtext =
    safetyStatus === 'NO_WARNING_DATA' || !safetyStatus
      ? (isMarathi
        ? 'सध्या सुरक्षित परिस्थितीची पुष्टी करण्यासाठी अधिकृत सागरी सुरक्षा माहिती अपुरी आहे.'
        : 'Current authoritative marine safety data is insufficient to confirm safe conditions.')
      : null;

  return (
    <div className="app-layout" style={{ minHeight: '100vh', background: '#071220', color: '#e0e6ed', fontFamily: "'Inter', sans-serif" }}>
      {/* --- Top Navigation Bar --- */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px 28px',
          background: 'rgba(10, 22, 40, 0.95)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 1100,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <span style={{ fontSize: '28px' }}>🐟</span>
          <div>
            <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 900, letterSpacing: '-0.5px', color: '#00e5ff' }}>
              {isMarathi ? 'मत्स्य AI महाराष्ट्र' : 'MatsyaAI Maharashtra'}
            </h1>
            <p style={{ margin: 0, fontSize: '11px', color: '#90caf9', fontWeight: 500 }}>
              {isMarathi ? 'सागरी निर्णय-समर्थन आणि मासेमारी हालचाल अंदाज' : 'Marine Decision-Support & Fishing Activity Forecast'}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Status Badges */}
          {mapData && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '4px 10px',
                borderRadius: '20px',
                background: isDemo ? 'rgba(255, 179, 0, 0.2)' : 'rgba(0, 230, 118, 0.2)',
                color: isDemo ? '#ffb300' : '#00e676',
                border: isDemo ? '1px solid #ffb300' : '1px solid #00e676',
              }}
            >
              ● {mapData.metadata.data_freshness_status}
            </span>
          )}

          {/* Language Toggle */}
          <button
            onClick={() => setIsMarathi(!isMarathi)}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#fff',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '8px',
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {isMarathi ? 'English' : 'मराठी'}
          </button>
        </div>
      </header>

      {/* --- Main Dashboard Body --- */}
      <main style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px' }}>
        {/* --- Primary Dashboard Hero --- */}
        <div style={{ background: 'rgba(15, 34, 61, 0.8)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', padding: '32px 24px', marginBottom: '24px', textAlign: 'center', boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
          <h2 style={{ fontSize: '14px', color: '#90caf9', textTransform: 'uppercase', letterSpacing: '1.5px', margin: '0 0 12px 0', fontWeight: 800 }}>
            {isMarathi ? "आजचा सल्ला" : "TODAY'S ADVISORY"}
          </h2>

          <div style={{ fontSize: '32px', fontWeight: 900, color: safetyColor, marginBottom: safetySubtext ? '8px' : '16px', letterSpacing: '-0.5px' }}>
            {safetyLabel}
          </div>
          {safetySubtext && (
            <div style={{ fontSize: '13px', color: '#90a4ae', background: 'rgba(144,164,174,0.08)', border: '1px solid rgba(144,164,174,0.2)', borderRadius: '8px', padding: '10px 16px', marginBottom: '16px', maxWidth: '540px', margin: '0 auto 16px auto', lineHeight: 1.5 }}>
              {safetySubtext}
            </div>
          )}

          <div style={{ fontSize: '18px', fontWeight: 700, color: '#e0e6ed', marginBottom: '20px' }}>
            {isMarathi ? "अपेक्षित मासेमारीची शक्यता" : "Fishing Potential"}: <span style={{ color: '#00e5ff', fontSize: '20px' }}>{highActivityCount > 0 ? 'HIGH' : 'LOW'}</span> <span style={{ fontSize: '14px', color: '#888', fontWeight: 500 }}>({highActivityCount} cells)</span>
          </div>

          <div style={{ display: 'inline-block', fontSize: '14px', color: '#ffb300', marginBottom: '32px', background: 'rgba(255, 179, 0, 0.1)', padding: '16px 24px', borderRadius: '12px', border: '1px solid rgba(255, 179, 0, 0.2)', maxWidth: '600px', lineHeight: '1.5' }}>
            <div style={{ fontWeight: 800, marginBottom: '6px', textTransform: 'uppercase', fontSize: '12px', letterSpacing: '1px' }}>{isMarathi ? "सागरी चेतावणी" : "Marine Warning"}</div>
            {mapData?.marine_safety.message && mapData.marine_safety.message !== 'No active warnings' && mapData.marine_safety.message !== 'No official marine warnings data available'
              ? mapData.marine_safety.message
              : (isMarathi ? 'अधिकृत सागरी हवामान डेटा अद्याप उपलब्ध नाही.' : 'No authoritative marine warning data currently available.')}
          </div>

          <div>
            <button onClick={() => {
              document.getElementById('fishing-map')?.scrollIntoView({ behavior: 'smooth' });
            }} style={{ background: '#00e5ff', color: '#000', border: 'none', padding: '16px 36px', borderRadius: '30px', fontSize: '16px', fontWeight: 800, cursor: 'pointer', boxShadow: '0 4px 20px rgba(0,229,255,0.4)', transition: 'transform 0.2s' }}>
              {isMarathi ? "मासेमारीची ठिकाणे पहा" : "VIEW FISHING SPOTS"}
            </button>
          </div>
        </div>

        {/* --- Secondary Metrics Strip --- */}
        {((mapData?.pfz_advisory?.count || 0) > 0) && (
          <details style={{ marginBottom: '24px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', padding: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <summary style={{ cursor: 'pointer', fontWeight: 700, color: '#90caf9', outline: 'none', display: 'flex', alignItems: 'center' }}>
              <span style={{ flexGrow: 1 }}>{isMarathi ? 'तांत्रिक तपशील आणि PFZ माहिती' : 'Technical Details & PFZ Information'}</span>
            </summary>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginTop: '16px' }}>
              <div style={{ background: 'rgba(15, 34, 61, 0.7)', borderRadius: '8px', padding: '12px' }}>
                <span style={{ fontSize: '11px', color: '#90caf9', textTransform: 'uppercase', fontWeight: 600 }}>{isMarathi ? 'अधिकृत INCOIS PFZ क्षेत्रे' : 'Official INCOIS PFZ Zones'}</span>
                <div style={{ fontSize: '20px', fontWeight: 900, color: '#00e676', marginTop: '4px' }}>
                  {mapData?.pfz_advisory?.count ?? 0} <span style={{ fontSize: '12px', color: '#888', fontWeight: 500 }}>Locations</span>
                </div>
              </div>
              <div style={{ background: 'rgba(15, 34, 61, 0.7)', borderRadius: '8px', padding: '12px' }}>
                <span style={{ fontSize: '11px', color: '#90caf9', textTransform: 'uppercase', fontWeight: 600 }}>{isMarathi ? 'प्रमाणित ML मॉडेल आवृत्ती' : 'Validated Model Version'}</span>
                <div style={{ fontSize: '16px', fontWeight: 800, color: '#fff', marginTop: '4px' }}>
                  {mapData?.metadata.model_version ?? 'Phase3_XGBoost_v1'}
                </div>
              </div>
            </div>
          </details>
        )}

        {/* Error / Loading State */}
        {loading && !mapData && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#00e5ff' }}>
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>🌊</div>
            <div>{isMarathi ? 'सागरी डेटा आणि अंदाज लोड करत आहे...' : 'Loading marine data and predictions...'}</div>
          </div>
        )}

        {error && (
          <div style={{ background: 'rgba(255, 82, 82, 0.15)', border: '1px solid #ff5252', padding: '14px', borderRadius: '10px', color: '#ff8a80', marginBottom: '16px' }}>
            <strong>Error:</strong> {error}
            <button onClick={() => loadDashboardData(true)} style={{ marginLeft: '12px', background: '#ff5252', color: '#fff', border: 'none', padding: '4px 10px', borderRadius: '4px', cursor: 'pointer' }}>
              Load Real Demo Cache
            </button>
          </div>
        )}

        {/* --- Data Freshness HUD --- */}
        {mapData?.source_freshness && (
          <FreshnessHUD freshness={mapData.source_freshness} isMarathi={isMarathi} />
        )}

        {/* --- Interactive Leaflet Marine Map --- */}
        {mapData && (
          <section style={{ marginBottom: '24px' }}>
            <MarineMap
              data={mapData}
              isMarathi={isMarathi}
              onToggleDemo={toggleDemo}
              isDemo={isDemo}
            />
          </section>
        )}

        {/* --- Coastal Landing Centres Directory --- */}
        {mapData && mapData.landing_centres && (
          <section style={{ background: 'rgba(15, 34, 61, 0.7)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '14px', padding: '20px', marginBottom: '24px' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 800, color: '#00e5ff' }}>
              ⚓ {isMarathi ? 'महाराष्ट्रातील प्रमुख लँडिंग केंद्रे आणि बंदरे' : 'Major Maharashtra Landing Centres & Harbours'}
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
              {mapData.landing_centres.map((lc, idx) => (
                <div key={idx} style={{ background: 'rgba(255,255,255,0.03)', padding: '10px 14px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontWeight: 700, fontSize: '13px', color: '#fff' }}>{lc.name}</div>
                  <div style={{ fontSize: '11px', color: '#aaa', marginTop: '2px' }}>
                    {lc.district} District &nbsp;·&nbsp; {lc.latitude.toFixed(2)}°N, {lc.longitude.toFixed(2)}°E
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* --- Scientific Disclaimers & Governance Notice --- */}
        <footer
          style={{
            background: 'rgba(5, 14, 26, 0.9)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '18px 24px',
            fontSize: '11px',
            lineHeight: 1.6,
            color: '#8898aa',
          }}
        >
          <div style={{ fontWeight: 700, color: '#ffb300', marginBottom: '4px' }}>
            ⚠️ {isMarathi ? 'महत्त्वाच्या वैज्ञानिक व कायदेशीर सूचना' : 'Scientific & Operational Disclaimers'}
          </div>
          <div>
            1. <strong>{isMarathi ? 'मासेमारी हालचाल अंदाज' : 'Predicted Apparent Fishing Activity'}:</strong> {isMarathi
              ? 'हे मॉडेल केवळ Global Fishing Watch (GFW) च्या ऐतिहासिक AIS नौका हालचालींवर आधारित संभाव्यता दर्शवते. हे माशांचे जैविक प्रमाण (Biomass), माशांची उपस्थिती किंवा हमखास पकड दर्शवत नाही.'
              : 'Matsya AI predicts apparent vessel fishing effort based on GFW AIS tracking patterns. It does NOT predict fish presence, fish biomass, fish species abundance, or guaranteed catch.'}
          </div>
          <div style={{ marginTop: '4px' }}>
            2. <strong>{isMarathi ? 'सागरी सुरक्षा स्वातंत्र्य' : 'Independent Marine Safety'}:</strong> {isMarathi
              ? 'सागरी सुरक्षा ML मॉडेलद्वारे ठरवली जात नाही. सुरक्षिततेसाठी केवळ IMD आणि INCOIS च्या अधिकृत सागरी हवामान चेतावण्या ग्राह्य धरल्या जातात.'
              : 'ML predictions NEVER dictate sea safety or generate "GO / DO NOT GO" commands. Sea safety is determined solely by official IMD and INCOIS marine warnings.'}
          </div>
          <div style={{ marginTop: '4px' }}>
            3. <strong>{isMarathi ? 'डेटा स्रोत' : 'Data Sources'}:</strong> GFW AIS Fishing Activity, Open-Meteo Marine/Weather Archive, INCOIS PFZ Official Advisories.
            {health && <span style={{ marginLeft: '12px', color: '#4caf50' }}>● API: {health.status} (v{health.version})</span>}
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
