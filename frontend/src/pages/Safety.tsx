/** Safety — SafetyGate status, active IMD warnings, district risk indicators. */

import { useMemo } from 'react';
import { BellRing, Info } from 'lucide-react';
import { Badge, Card, Empty, Meter, PageHeader } from '../components/ui';
import { conditionsAt, peakAhead, useData } from '../lib/data';
import { DISTRICTS, districtLabel } from '../lib/districts';
import { fmtDateTime, fmtNum } from '../lib/format';
import { useLang } from '../lib/lang';
import { humanize, SAFETY, safetyMeta, severityTone } from '../lib/status';
import { Disclaimer, PageState, SafetyCallout } from './shared';

/** IMD descriptions arrive as "Region: X | Condition: Y | Source: Z" — keep region + condition only. */
function parseWarning(desc: string): { region: string; condition: string | null } {
  const parts = desc.split('|').map((s) => s.trim()).filter(Boolean);
  const region = (parts.find((p) => /^region:/i.test(p)) ?? parts[0] ?? '').replace(/^region:\s*/i, '');
  const raw = parts.find((p) => /^condition:/i.test(p))?.replace(/^condition:\s*/i, '') ?? null;
  const condition = raw
    ? raw.replace(/\s*·?\s*Source:.*$/i, '').replace(/\s+\./g, '.').replace(/[.\s-]+$/, '').trim() || null
    : null;
  return { region, condition: condition && /^nil$/i.test(condition) ? 'Nil' : condition };
}

export function Safety() {
  return <PageState><Content /></PageState>;
}

function Content() {
  const { summary, warnings, forecast } = useData();
  const { mr, tr } = useLang();
  const data = summary!;
  const status = data.marine_safety.overall_status;
  const thresholds = forecast?.thresholds ?? { wave_height_m: 4, wind_speed_kmh: 50 };

  const rules = [
    { key: 'UNSAFE', title: tr('Severe warning in force', 'तीव्र चेतावणी लागू'), text: tr('Any active IMD warning of severe, very severe or extremely severe level.', 'तीव्र, अतितीव्र किंवा अत्यंत तीव्र स्तराची कोणतीही सक्रिय IMD चेतावणी.') },
    { key: 'CAUTION', title: tr('Caution warning or threshold exceeded', 'सावधानता चेतावणी किंवा मर्यादा ओलांडली'), text: tr(`Active rough-sea / caution warning, or waves above ${thresholds.wave_height_m} m, or wind above ${thresholds.wind_speed_kmh} km/h.`, `सक्रिय खवळलेला समुद्र / सावधानता चेतावणी, किंवा ${thresholds.wave_height_m} मी पेक्षा उंच लाटा, किंवा ${thresholds.wind_speed_kmh} किमी/तास पेक्षा जास्त वारा.`) },
    { key: 'SAFE_CONFIRMED', title: tr('Normal conditions confirmed', 'सामान्य परिस्थितीची पुष्टी'), text: tr('Only when an active official bulletin explicitly reports normal conditions and wave/wind data are present and within limits.', 'केवळ सक्रिय अधिकृत बुलेटिन सामान्य परिस्थिती स्पष्टपणे सांगते आणि लाटा/वारा डेटा मर्यादेत असतो तेव्हाच.') },
    { key: 'NO_WARNING_DATA', title: tr('Safety not confirmed', 'सुरक्षिततेची पुष्टी नाही'), text: tr('No current bulletin, expired data or missing measurements. Absence of a warning is never treated as safe.', 'वर्तमान बुलेटिन नाही, कालबाह्य डेटा किंवा मोजमाप उपलब्ध नाही. चेतावणी नसणे कधीही सुरक्षित मानले जात नाही.') },
  ];

  const breakdown = useMemo(() => {
    const total = data.predictions.length || 1;
    return Object.keys(SAFETY).map((k) => ({ key: k, n: data.predictions.filter((p) => p.safety_status === k).length, total }));
  }, [data.predictions]);

  const districtRisk = DISTRICTS.map((d) => {
    const c = conditionsAt(forecast, d);
    const series = forecast?.districts.find((x) => x.district === d)?.hourly;
    const peakWave = series ? peakAhead(series.wave_height_m, series.time, 24) : null;
    const peakWind = series ? peakAhead(series.wind_speed_kmh, series.time, 24) : null;
    const exceeds = (peakWave ?? 0) > thresholds.wave_height_m || (peakWind ?? 0) > thresholds.wind_speed_kmh;
    return { d, c, peakWave, peakWind, exceeds };
  });

  // Show the latest bulletin only; earlier bulletins that are still within validity are superseded.
  const latestIssued = warnings?.items.reduce<string | null>((m, w) => (!m || w.issued_at > m ? w.issued_at : m), null) ?? null;
  const current = (warnings?.items ?? []).filter((w) => w.issued_at === latestIssued);
  const superseded = (warnings?.items.length ?? 0) - current.length;

  const toneColor: Record<string, string> ={ success: 'var(--success)', warning: '#f79009', danger: 'var(--danger)', neutral: 'var(--text-faint)', info: 'var(--primary)' };

  return (
    <div className="stack">
      <PageHeader
        title={tr('Marine safety', 'सागरी सुरक्षा')}
        description={tr('Official warnings and forecast thresholds. The AI model never decides safety.', 'अधिकृत चेतावण्या व अंदाज मर्यादा. AI मॉडेल कधीही सुरक्षा ठरवत नाही.')}
      />
      <SafetyCallout withLink={false} />

      <div className="grid-main-side">
        <Card
          title={tr('Active IMD warnings', 'सक्रिय IMD चेतावण्या')}
          subtitle={latestIssued ? `${warnings!.source} · ${tr('issued', 'जारी')} ${fmtDateTime(latestIssued)}` : warnings?.source}
          actions={<BellRing size={16} className="text-muted" aria-hidden />}
          footer={superseded > 0 ? tr(`${superseded} entries from an earlier bulletin are superseded and hidden.`, `आधीच्या बुलेटिनमधील ${superseded} नोंदी बदलल्या असल्याने लपवल्या आहेत.`) : undefined}
          flush
        >
          {!warnings || current.length === 0 ? (
            <Empty title={tr('No active warning bulletin', 'सक्रिय चेतावणी बुलेटिन नाही')}>
              {tr('Safety cannot be confirmed without a current bulletin.', 'वर्तमान बुलेटिनशिवाय सुरक्षिततेची पुष्टी करता येत नाही.')}
            </Empty>
          ) : (
            <ul className="list">
              {current.map((w, i) => {
                const { region, condition } = parseWarning(w.description);
                return (
                  <li key={i} className="list-row" style={{ alignItems: 'flex-start' }}>
                    <div className="list-row-main">
                      <div className="fw-500" style={{ color: 'var(--text)' }}>{region}</div>
                      <div className="text-sm text-secondary" style={{ marginTop: 2 }}>
                        {humanize(w.warning_type)}{condition && <> · {condition}</>}
                      </div>
                      <div className="list-row-sub num" style={{ marginTop: 4 }}>
                        {tr('Valid', 'वैध')} {fmtDateTime(w.valid_from)} – {fmtDateTime(w.valid_until)}
                      </div>
                    </div>
                    <Badge tone={severityTone(w.severity)}>{humanize(w.severity)}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title={tr('How safety is determined', 'सुरक्षा कशी ठरवली जाते')} subtitle={tr('Rules are checked in this order', 'नियम या क्रमाने तपासले जातात')}>
          <ol className="rule-list">
            {rules.map((r, i) => {
              const meta = safetyMeta(r.key);
              return (
                <li key={r.key} className={`rule${status === r.key ? ' active' : ''}`}>
                  <span className="rule-index">{i + 1}</span>
                  <div>
                    <div className="rule-title">
                      <meta.icon size={15} aria-hidden style={{ color: toneColor[meta.tone], flexShrink: 0, marginTop: 2 }} />
                      <span style={{ flex: 1 }}>{r.title}</span>
                      {status === r.key && <Badge tone="info">{tr('Current', 'सध्या')}</Badge>}
                    </div>
                    <div style={{ marginTop: 2 }}>{r.text}</div>
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>
      </div>

      <Card
        title={tr('District risk indicators', 'जिल्हानिहाय धोका निर्देशक')}
        subtitle={tr('Offshore forecast now and peak over the next 24 hours, against safety thresholds', 'सध्याचा व पुढील 24 तासांतील कमाल अंदाज, सुरक्षा मर्यादांशी तुलना')}
        flush
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tr('District', 'जिल्हा')}</th>
                <th style={{ minWidth: 200 }}>{tr('Wave height (now / 24 h peak)', 'लाटांची उंची (सध्या / 24 तास कमाल)')}</th>
                <th style={{ minWidth: 200 }}>{tr('Wind (now / 24 h peak)', 'वारा (सध्या / 24 तास कमाल)')}</th>
                <th>{tr('Indicator', 'निर्देशक')}</th>
              </tr>
            </thead>
            <tbody>
              {districtRisk.map(({ d, c, peakWave, peakWind, exceeds }) => (
                <tr key={d}>
                  <td className="strong">{districtLabel(d, mr)}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1 }}><Meter value={peakWave} max={thresholds.wave_height_m} label={tr('Wave height vs threshold', 'लाटांची उंची')} /></div>
                      <span className="num" style={{ width: 92, textAlign: 'right' }}>{fmtNum(c?.wave)} / {fmtNum(peakWave)} m</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1 }}><Meter value={peakWind} max={thresholds.wind_speed_kmh} label={tr('Wind vs threshold', 'वारा')} /></div>
                      <span className="num" style={{ width: 110, textAlign: 'right' }}>{fmtNum(c?.wind, 0)} / {fmtNum(peakWind, 0)} km/h</span>
                    </div>
                  </td>
                  <td>
                    {peakWave == null && peakWind == null
                      ? <Badge>{tr('No forecast', 'अंदाज नाही')}</Badge>
                      : exceeds ? <Badge tone="warning">{tr('Exceeds limit', 'मर्यादा ओलांडली')}</Badge>
                      : <Badge tone="success">{tr('Within limits', 'मर्यादेत')}</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card-footer" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Info size={14} style={{ marginTop: 2, flexShrink: 0 }} aria-hidden />
          {tr(
            `Bars fill toward the caution limits (${thresholds.wave_height_m} m waves, ${thresholds.wind_speed_kmh} km/h wind). Within limits does not mean safe — official warnings take precedence.`,
            `पट्ट्या सावधानता मर्यादेकडे भरतात (${thresholds.wave_height_m} मी लाटा, ${thresholds.wind_speed_kmh} किमी/तास वारा). मर्यादेत असणे म्हणजे सुरक्षित नव्हे — अधिकृत चेतावण्या प्राधान्य घेतात.`,
          )}
        </div>
      </Card>

      <Card title={tr('Safety status across the grid', 'ग्रिडवरील सुरक्षा स्थिती')} subtitle={`${data.predictions.length} ${tr('grid cells', 'ग्रिड क्षेत्रे')}`}>
        <div className="share-bar" role="img" aria-label={breakdown.map((b) => `${b.key}: ${b.n}`).join(', ')}>
          {breakdown.filter((b) => b.n > 0).map((b) => (
            <span key={b.key} style={{ width: `${(b.n / b.total) * 100}%`, background: toneColor[safetyMeta(b.key).tone] }} />
          ))}
        </div>
        <div className="chart-legend" style={{ marginTop: 12 }}>
          {breakdown.map((b) => {
            const meta = safetyMeta(b.key);
            return (
              <span key={b.key}>
                <meta.icon size={14} aria-hidden style={{ color: toneColor[meta.tone] }} />
                {meta.short[mr ? 1 : 0]} <strong className="num" style={{ color: 'var(--text)' }}>{b.n}</strong>
              </span>
            );
          })}
        </div>
      </Card>

      <Disclaimer />
    </div>
  );
}
