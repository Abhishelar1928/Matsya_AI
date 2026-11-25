/**
 * Marine-grade Navigation Compass & Course Display.
 *
 * Distinctly renders:
 *  - Cyan Target Bearing arrow (great-circle bearing to next waypoint/destination)
 *  - Amber GPS Course Over Ground (COG) pointer (hidden when stationary/unreliable)
 *  - Green Physical Device Compass heading tick (only when DeviceOrientation supported)
 *  - Clear badges for GPS LOST, GPS WEAK, STATIONARY, SIMULATION
 */

import { angularDiffDeg, compassPoint, kmToNm } from '../engine/geodesy';
import type { GpsHealth, TurnInstruction } from '../engine/navigationEngine';

interface CompassProps {
  targetBearingDeg: number;
  /** GPS Course Over Ground (deg). Null when stationary or unavailable. */
  cogDeg?: number | null;
  /** Physical device compass heading (deg). Null when sensor unsupported. */
  compassHeadingDeg?: number | null;
  compassSupported?: boolean;
  headingCogDiffDeg?: number | null;
  remainingKm: number;
  totalKm?: number;
  etaMinutes?: number | null;
  etaReliability?: 'reliable' | 'low_confidence' | 'unavailable';
  gpsHealth?: GpsHealth;
  stationary?: boolean;
  simulated?: boolean;
  turnInstruction?: TurnInstruction;
  destinationName?: string;
  isMarathi?: boolean;
  dark?: boolean;
}

export function MarineCompass({
  targetBearingDeg,
  cogDeg = null,
  compassHeadingDeg = null,
  compassSupported = false,
  headingCogDiffDeg = null,
  remainingKm,
  totalKm,
  etaMinutes = null,
  etaReliability = 'unavailable',
  gpsHealth,
  stationary = false,
  simulated = false,
  turnInstruction,
  destinationName,
  isMarathi = false,
  dark = false,
}: CompassProps) {
  const cardinal = compassPoint(targetBearingDeg);
  const progressPct =
    totalKm && totalKm > 0
      ? Math.max(0, Math.min(100, ((totalKm - remainingKm) / totalKm) * 100))
      : null;

  // Fallback turn hint if caller didn't pass structured turnInstruction
  let turnText: string | null = null;
  let turnColor = dark ? '#94a3b8' : 'var(--text-muted)';
  if (turnInstruction) {
    if (turnInstruction.action === 'ARRIVED') {
      turnText = isMarathi ? 'लक्ष्यावर पोहोचलात ✓' : 'Arrived at target ✓';
      turnColor = '#10b981';
    } else if (turnInstruction.action === 'ON_COURSE') {
      turnText = isMarathi ? 'योग्य दिशेवर ✓' : 'On course ✓';
      turnColor = '#10b981';
    } else if (turnInstruction.action === 'TURN_RIGHT') {
      turnText = isMarathi
        ? `उजवीकडे ${turnInstruction.degrees}° वळा ↻`
        : `Turn right ${turnInstruction.degrees}° ↻`;
      turnColor = '#f59e0b';
    } else if (turnInstruction.action === 'TURN_LEFT') {
      turnText = isMarathi
        ? `डावीकडे ${turnInstruction.degrees}° वळा ↺`
        : `Turn left ${turnInstruction.degrees}° ↺`;
      turnColor = '#f59e0b';
    } else if (stationary) {
      turnText = isMarathi ? 'बोट स्थिर (दिशा निष्क्रिय)' : 'Vessel stationary (COG inactive)';
    } else {
      turnText = isMarathi ? 'दिशा सेन्सर उपलब्ध नाही' : 'Move >1 kn for GPS COG';
    }
  } else if (cogDeg !== null) {
    const err = angularDiffDeg(cogDeg, targetBearingDeg);
    if (Math.abs(err) < 5) {
      turnText = isMarathi ? 'योग्य दिशेवर ✓' : 'On course ✓';
      turnColor = '#10b981';
    } else if (err > 0) {
      turnText = isMarathi ? `उजवीकडे ${Math.abs(err).toFixed(0)}° वळा ↻` : `Turn right ${Math.abs(err).toFixed(0)}° ↻`;
      turnColor = '#f59e0b';
    } else {
      turnText = isMarathi ? `डावीकडे ${Math.abs(err).toFixed(0)}° वळा ↺` : `Turn left ${Math.abs(err).toFixed(0)}° ↺`;
      turnColor = '#f59e0b';
    }
  }

  const etaStr =
    etaMinutes !== null && Number.isFinite(etaMinutes)
      ? etaMinutes > 90
        ? `${(etaMinutes / 60).toFixed(1)} h`
        : `${Math.round(etaMinutes)} min`
      : null;

  const surfaceBg = dark ? 'var(--hud-card, #0f1e33)' : 'var(--surface)';
  const borderCol = dark ? 'var(--hud-border, #1e3554)' : 'var(--border)';
  const textCol = dark ? 'var(--hud-text, #f1f5f9)' : 'var(--text)';
  const mutedCol = dark ? 'var(--hud-muted, #94a3b8)' : 'var(--text-muted)';
  const cyanCol = dark ? 'var(--hud-cyan, #38bdf8)' : '#0ea5e9';
  const amberCol = dark ? 'var(--hud-amber, #fbbf24)' : '#f59e0b';
  const greenCol = dark ? 'var(--hud-green, #34d399)' : '#10b981';

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 20,
        padding: '16px 18px',
        borderRadius: 12,
        border: `1px solid ${borderCol}`,
        background: surfaceBg,
        color: textCol,
        marginBottom: 16,
      }}
    >
      {/* SVG Marine Compass Rose */}
      <div style={{ flex: '0 0 auto', display: 'flex', justifyContent: 'center' }}>
        <svg
          width={176}
          height={176}
          viewBox="0 0 180 180"
          role="img"
          aria-label={`Compass bearing ${targetBearingDeg.toFixed(0)} degrees ${cardinal}`}
        >
          <circle cx="90" cy="90" r="82" fill={dark ? 'rgba(6,13,24,0.65)' : 'none'} stroke={borderCol} strokeWidth="2" />
          <circle cx="90" cy="90" r="64" fill="none" stroke={borderCol} strokeWidth="1" strokeDasharray="3 4" />

          {Array.from({ length: 24 }, (_, i) => {
            const deg = i * 15;
            const isMajor = deg % 90 === 0;
            const isMid = deg % 45 === 0 && !isMajor;
            const r1 = isMajor ? 70 : isMid ? 74 : 77;
            const r2 = 82;
            const rad = ((deg - 90) * Math.PI) / 180;
            return (
              <line
                key={deg}
                x1={90 + r1 * Math.cos(rad)}
                y1={90 + r1 * Math.sin(rad)}
                x2={90 + r2 * Math.cos(rad)}
                y2={90 + r2 * Math.sin(rad)}
                stroke={isMajor ? textCol : mutedCol}
                strokeWidth={isMajor ? 2 : 1}
              />
            );
          })}

          <text x="90" y="23" textAnchor="middle" fontSize="13" fontWeight="700" fill="#ef4444">N</text>
          <text x="160" y="95" textAnchor="middle" fontSize="12" fontWeight="700" fill={textCol}>E</text>
          <text x="90" y="166" textAnchor="middle" fontSize="12" fontWeight="700" fill={textCol}>S</text>
          <text x="20" y="95" textAnchor="middle" fontSize="12" fontWeight="700" fill={textCol}>W</text>

          {/* Physical device compass heading (only if sensor supported) */}
          {compassSupported && compassHeadingDeg !== null && (
            <g transform={`rotate(${compassHeadingDeg} 90 90)`}>
              <line x1="90" y1="90" x2="90" y2="38" stroke={greenCol} strokeWidth="2" strokeLinecap="round" />
              <polygon points="90,30 86,40 94,40" fill={greenCol} />
            </g>
          )}

          {/* Amber GPS Course Over Ground (COG) */}
          {cogDeg !== null && (
            <g transform={`rotate(${cogDeg} 90 90)`}>
              <line x1="90" y1="90" x2="90" y2="34" stroke={amberCol} strokeWidth="2.8" strokeLinecap="round" strokeDasharray="5 3" />
              <circle cx="90" cy="34" r="4" fill={amberCol} />
            </g>
          )}

          {/* Cyan Target Bearing */}
          <g transform={`rotate(${targetBearingDeg} 90 90)`}>
            <line x1="90" y1="90" x2="90" y2="27" stroke={cyanCol} strokeWidth="3.5" strokeLinecap="round" />
            <polygon points="90,17 83,33 97,33" fill={cyanCol} />
            <line x1="90" y1="90" x2="90" y2="110" stroke={mutedCol} strokeWidth="2" strokeLinecap="round" opacity="0.4" />
          </g>

          <circle cx="90" cy="90" r="6" fill={surfaceBg} stroke={cyanCol} strokeWidth="3" />
        </svg>
      </div>

      {/* Telemetry Readouts */}
      <div style={{ flex: 1, minWidth: 220 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
          {destinationName && (
            <div style={{ fontSize: 12, color: mutedCol }}>
              {isMarathi ? 'लक्ष्य' : 'Target'}: <strong style={{ color: textCol }}>{destinationName}</strong>
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {simulated && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: '#78350f', color: '#fde68a' }}>
                SIMULATION
              </span>
            )}
            {gpsHealth === 'LOST' && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: '#7f1d1d', color: '#fecaca' }}>
                GPS LOST
              </span>
            )}
            {gpsHealth === 'WEAK' && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: '#78350f', color: '#fde68a' }}>
                GPS WEAK
              </span>
            )}
            {stationary && gpsHealth && gpsHealth !== 'WAITING' && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: dark ? '#1e293b' : '#f1f5f9', color: mutedCol }}>
                STATIONARY
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 22, marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em', color: mutedCol }}>
              {isMarathi ? 'लक्ष्य दिशा (Bearing)' : 'Target Bearing'}
            </div>
            <div className="num" style={{ fontSize: 28, fontWeight: 700, color: cyanCol, lineHeight: 1.15 }}>
              {targetBearingDeg.toFixed(0)}° {cardinal}
            </div>
            {turnText && (
              <div style={{ fontSize: 13, fontWeight: 600, color: turnColor, marginTop: 3 }}>{turnText}</div>
            )}
          </div>

          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em', color: mutedCol }}>
              {isMarathi ? 'शिल्लक अंतर (Remaining)' : 'Remaining Distance'}
            </div>
            <div className="num" style={{ fontSize: 28, fontWeight: 700, color: textCol, lineHeight: 1.15 }}>
              {remainingKm.toFixed(1)} km
            </div>
            <div className="num" style={{ fontSize: 13, color: mutedCol, marginTop: 3 }}>
              {kmToNm(remainingKm).toFixed(1)} nm
              {etaStr ? ` · ETA ${etaStr}${etaReliability === 'low_confidence' ? ' (~)' : ''}` : ''}
            </div>
          </div>
        </div>

        {progressPct !== null && totalKm && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: mutedCol, marginBottom: 4 }}>
              <span>{isMarathi ? 'प्रवास प्रगती' : 'Route progress'}: {progressPct.toFixed(0)}%</span>
              <span className="num">{Math.max(0, totalKm - remainingKm).toFixed(1)} / {totalKm.toFixed(1)} km</span>
            </div>
            <div style={{ height: 8, borderRadius: 999, background: borderCol, overflow: 'hidden' }}>
              <div style={{ width: `${progressPct}%`, height: '100%', background: cyanCol, borderRadius: 999, transition: 'width 0.3s ease' }} />
            </div>
          </div>
        )}

        {/* Separated Direction Legend */}
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 10, fontSize: 11, color: mutedCol }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 3, background: cyanCol, display: 'inline-block', borderRadius: 2 }} />
            {isMarathi ? 'लक्ष्य दिशा' : `Target (${targetBearingDeg.toFixed(0)}°)`}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 3, background: amberCol, display: 'inline-block', borderRadius: 2 }} />
            {cogDeg !== null
              ? `GPS COG: ${cogDeg.toFixed(0)}° ${compassPoint(cogDeg)}`
              : isMarathi
                ? 'GPS COG: अनुपलब्ध/स्थिर'
                : 'GPS COG: unavailable'}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 3, background: greenCol, display: 'inline-block', borderRadius: 2 }} />
            {compassSupported && compassHeadingDeg !== null
              ? `Compass: ${compassHeadingDeg.toFixed(0)}°${headingCogDiffDeg !== null ? ` (Δ ${headingCogDiffDeg > 0 ? '+' : ''}${headingCogDiffDeg.toFixed(0)}°)` : ''}`
              : isMarathi
                ? 'होकायंत्र सेन्सर: समर्थित नाही'
                : 'Device compass: unavailable'}
          </span>
        </div>
      </div>
    </div>
  );
}
