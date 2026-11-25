/**
 * MatsyaAI Maharashtra — Emergency Return & Offshore Survival System.
 *
 * Provides:
 *  - Man Overboard (MOB) 1-tap marker with live bearing, distance, & elapsed timer
 *  - Anchor Watch with selectable swing radius & drift alert
 *  - Last Known Position (decimal + DMS) with clipboard copy
 *  - Nearest + alternative Maharashtra return harbours with verification status
 *    and explicit disclosure that nearest distance != safest harbour
 *  - Offline Coast Guard / MRCC Mumbai / VHF Ch 16 emergency instructions (EN + MR)
 */

import { useState } from 'react';
import { Anchor, Copy, LifeBuoy, Navigation2, PhoneCall, ShieldAlert } from 'lucide-react';
import { compassPoint, etaMinutes, formatDms, haversineKm, initialBearingDeg, kmToNm } from '../engine/geodesy';
import type { NavFix } from '../engine/navigationEngine';
import type { AnchorWatchState, ExpeditionPackage, MobMarker } from '../types/expeditionTypes';

interface Props {
  pkg: ExpeditionPackage;
  fix: NavFix | null;
  smoothedSogMps: number | null;
  now?: number;
  isMarathi: boolean;
  mob: MobMarker | null;
  anchorWatch: AnchorWatchState | null;
  anchorDriftKm: number | null;
  anchorDriftAlert: boolean;
  onMarkMob: () => void;
  onClearMob: () => void;
  onSetAnchor: (radiusM: number) => void;
  onClearAnchor: () => void;
  onClose: () => void;
}

export function EmergencyReturn({
  pkg,
  fix,
  smoothedSogMps,
  now = 0,
  isMarathi,
  mob,
  anchorWatch,
  anchorDriftKm,
  anchorDriftAlert,
  onMarkMob,
  onClearMob,
  onSetAnchor,
  onClearAnchor,
  onClose,
}: Props) {
  const [anchorRadiusM, setAnchorRadiusM] = useState(100);
  const [copied, setCopied] = useState(false);

  const refLat = fix?.latitude ?? pkg.landing_centre.latitude;
  const refLon = fix?.longitude ?? pkg.landing_centre.longitude;

  const harbours = pkg.emergency_returns
    .map((h) => {
      const distKm = haversineKm(refLat, refLon, h.latitude, h.longitude);
      const brg = initialBearingDeg(refLat, refLon, h.latitude, h.longitude);
      const eta = fix ? etaMinutes(distKm, smoothedSogMps) : null;
      return { ...h, distKm, brg, compass: compassPoint(brg), eta };
    })
    .sort((a, b) => a.distKm - b.distKm)
    .slice(0, 5);

  const mobNav =
    mob && fix
      ? {
          distM: haversineKm(fix.latitude, fix.longitude, mob.latitude, mob.longitude) * 1000,
          brg: initialBearingDeg(fix.latitude, fix.longitude, mob.latitude, mob.longitude),
          elapsedMin: now > 0 ? Math.max(0, Math.round((now - Date.parse(mob.marked_at)) / 60_000)) : 0,
        }
      : null;

  const copyPos = async () => {
    if (!fix) return;
    const text = `${fix.latitude.toFixed(5)}N, ${fix.longitude.toFixed(5)}E (${formatDms(fix.latitude, fix.longitude)})`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      style={{
        border: '2px solid #ef4444',
        borderRadius: 12,
        padding: 16,
        marginBottom: 16,
        background: 'var(--hud-card, #140b10)',
        color: 'var(--hud-text, #f8fafc)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 16, color: '#fca5a5' }}>
          <ShieldAlert size={20} />
          {isMarathi ? 'आपत्कालीन परतीची प्रणाली (Emergency)' : 'Emergency Return & Safety System'}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          {isMarathi ? 'बंद करा' : 'Close'}
        </button>
      </div>

      {/* Man Overboard (MOB) & Anchor Watch */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginBottom: 14 }}>
        <div style={{ padding: 12, borderRadius: 8, border: '1px solid rgba(239,68,68,0.45)', background: 'rgba(127,29,29,0.22)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, marginBottom: 6, color: '#fecaca' }}>
            <LifeBuoy size={16} />
            {isMarathi ? 'मनुष्य पाण्यात (MOB)' : 'Man Overboard (MOB)'}
          </div>
          {mob ? (
            <div>
              <div className="num" style={{ fontSize: 13 }}>
                {mob.latitude.toFixed(5)}°N, {mob.longitude.toFixed(5)}°E
              </div>
              {mobNav && (
                <div className="num" style={{ fontSize: 16, fontWeight: 700, color: '#fde68a', margin: '4px 0' }}>
                  {mobNav.distM < 1000 ? `${Math.round(mobNav.distM)} m` : `${(mobNav.distM / 1000).toFixed(2)} km`} ·{' '}
                  {mobNav.brg.toFixed(0)}° {compassPoint(mobNav.brg)} ({mobNav.elapsedMin}m ago)
                </div>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={onClearMob} style={{ marginTop: 6 }}>
                {isMarathi ? 'MOB चिन्ह काढा' : 'Clear MOB'}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={!fix}
              onClick={onMarkMob}
              style={{ width: '100%' }}
            >
              {fix
                ? isMarathi
                  ? 'आत्ताची जागा MOB म्हणून नोंदवा'
                  : 'Mark MOB at Current GPS'
                : isMarathi
                  ? 'GPS सिग्नल आवश्यक'
                  : 'Needs GPS Fix'}
            </button>
          )}
        </div>

        <div
          style={{
            padding: 12,
            borderRadius: 8,
            border: `1px solid ${anchorDriftAlert ? '#ef4444' : 'rgba(148,163,184,0.3)'}`,
            background: anchorDriftAlert ? 'rgba(185,28,28,0.35)' : 'rgba(15,23,42,0.45)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, marginBottom: 6 }}>
            <Anchor size={16} />
            {isMarathi ? 'नांगर पहारा (Anchor Watch)' : 'Anchor Watch & Drift Alert'}
          </div>
          {anchorWatch ? (
            <div>
              <div className="num" style={{ fontSize: 13 }}>
                Radius: {anchorWatch.radius_m} m · Drift:{' '}
                <strong>{anchorDriftKm !== null ? `${Math.round(anchorDriftKm * 1000)} m` : '—'}</strong>
              </div>
              {anchorDriftAlert && (
                <div style={{ color: '#fecaca', fontWeight: 700, fontSize: 13, marginTop: 4 }}>
                  {isMarathi ? 'सावधान! बोट नांगर मर्यादेबाहेर सरकली आहे!' : 'DRIFT ALERT: Vessel moved outside anchor radius!'}
                </div>
              )}
              <button type="button" className="btn btn-secondary btn-sm" onClick={onClearAnchor} style={{ marginTop: 6 }}>
                {isMarathi ? 'नांगर पहारा बंद करा' : 'Stop Anchor Watch'}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select
                value={anchorRadiusM}
                onChange={(e) => setAnchorRadiusM(Number(e.target.value))}
                className="select"
                style={{ width: 100, padding: '6px 8px', fontSize: 12 }}
              >
                <option value={30}>30 m</option>
                <option value={50}>50 m</option>
                <option value={100}>100 m</option>
                <option value={250}>250 m</option>
              </select>
              <button type="button" className="btn btn-secondary btn-sm" disabled={!fix} onClick={() => onSetAnchor(anchorRadiusM)} style={{ flex: 1 }}>
                {isMarathi ? 'नांगर सेट करा' : 'Set Anchor'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Last Known Position */}
      <div style={{ padding: 10, borderRadius: 8, border: '1px solid rgba(148,163,184,0.25)', marginBottom: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--hud-muted, #94a3b8)' }}>
            {isMarathi ? 'शेवटचे ज्ञात स्थान (LKP)' : 'Last Known Position (For Coast Guard / VHF Distress)'}
          </div>
          {fix ? (
            <div className="num" style={{ fontSize: 14, fontWeight: 600 }}>
              {fix.latitude.toFixed(5)}°N, {fix.longitude.toFixed(5)}°E · {formatDms(fix.latitude, fix.longitude)}
              {fix.accuracy_m !== null ? ` (±${Math.round(fix.accuracy_m)} m)` : ''}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#fde68a' }}>{isMarathi ? 'अद्याप GPS स्थान नाही' : 'No GPS fix recorded yet'}</div>
          )}
        </div>
        {fix && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={copyPos}>
            <Copy size={14} /> {copied ? (isMarathi ? 'कॉपी झाले' : 'Copied') : isMarathi ? 'कॉपी करा' : 'Copy'}
          </button>
        )}
      </div>

      {/* Return Harbours */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Navigation2 size={15} />
          {isMarathi ? 'जवळची परतीची बंदरे (थेट अंतर)' : 'Return Harbours (Direct Great-Circle Reference)'}
        </div>
        <div style={{ display: 'grid', gap: 6 }}>
          {harbours.map((h, i) => (
            <div
              key={h.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 8,
                padding: '8px 10px',
                borderRadius: 6,
                background: i === 0 ? 'rgba(56,189,248,0.12)' : 'rgba(15,23,42,0.4)',
                border: '1px solid rgba(148,163,184,0.2)',
                fontSize: 13,
              }}
            >
              <div>
                <strong>{isMarathi ? h.name_mr : h.name}</strong>{' '}
                <span style={{ color: 'var(--hud-muted, #94a3b8)' }}>({h.district})</span>
                {!h.verified && (
                  <span style={{ marginLeft: 6, fontSize: 10, padding: '1px 5px', borderRadius: 4, background: '#78350f', color: '#fde68a' }}>
                    {isMarathi ? 'असत्यापित' : 'Unverified coords'}
                  </span>
                )}
              </div>
              <div className="num">
                <strong>{h.distKm.toFixed(1)} km</strong> ({kmToNm(h.distKm).toFixed(1)} nm) · {h.brg.toFixed(0)}° {h.compass}
                {h.eta !== null ? ` · ETA ${h.eta > 90 ? `${(h.eta / 60).toFixed(1)}h` : `${Math.round(h.eta)}m`}` : ''}
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: '#fde68a', marginTop: 6 }}>
          {isMarathi
            ? 'टीप: भौगोलिकदृष्ट्या सर्वात जवळचे बंदर नेहमीच सर्वात सुरक्षित किंवा प्रवेशयोग्य असते असे नाही. खोली, भरती व बंदर प्रवेश मार्ग तपासा.'
            : 'Warning: Nearest geographical harbour is NOT necessarily the safest or navigable in rough seas. Direct bearings do not avoid reefs, shoals, or breakwaters.'}
        </div>
      </div>

      {/* Offline Emergency Contacts & Checklist */}
      <div style={{ padding: 10, borderRadius: 8, background: 'rgba(15,23,42,0.6)', fontSize: 12, lineHeight: 1.6 }}>
        <div style={{ fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
          <PhoneCall size={14} />
          {isMarathi ? 'ऑफलाइन आपत्कालीन सूचना (महाराष्ट्र)' : 'Offline Emergency Instructions (Maharashtra Coast)'}
        </div>
        <ul style={{ margin: '0 0 0 18px', padding: 0 }}>
          <li><strong>Indian Coast Guard SAR:</strong> Dial <strong>1554</strong> (toll-free when in mobile range) · <strong>MRCC Mumbai:</strong> +91-22-24388065</li>
          <li><strong>VHF Distress:</strong> Channel <strong>16 (156.8 MHz)</strong> — transmit MAYDAY with vessel name & LKP coordinates above.</li>
          <li>{isMarathi ? 'लाइफ जॅकेट घाला, पंप व सिग्नल फ्लेअर्स तयार ठेवा.' : 'Put on life jackets immediately, check bilge pumps, keep distress flares/torch ready.'}</li>
        </ul>
      </div>
    </div>
  );
}
