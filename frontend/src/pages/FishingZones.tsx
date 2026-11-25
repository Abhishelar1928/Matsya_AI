/** Fishing zones — official INCOIS PFZ advisories and AI activity predictions. */

import { useMemo, useState } from 'react';
import { Fish, Gauge, Grid3x3, Map as MapIcon, Navigation, Radar, Search } from 'lucide-react';
import { Badge, Card, Meter, Metric, PageHeader, Segmented } from '../components/ui';
import { Histogram } from '../components/charts';
import { useData } from '../lib/data';
import { DISTRICTS, districtLabel, districtOf } from '../lib/districts';
import { fmtCoord, fmtDate, fmtDateTime, fmtPct, parseKm } from '../lib/format';
import { useLang } from '../lib/lang';
import { href, navigate, type Location } from '../lib/router';
import { freshnessMeta } from '../lib/status';
import { Disclaimer, PageState } from './shared';

type Tab = 'pfz' | 'predictions';

export function FishingZones({ loc }: { loc: Location }) {
  return <PageState><Content loc={loc} /></PageState>;
}

function Content({ loc }: { loc: Location }) {
  const { tr } = useLang();
  const tab: Tab = loc.params.get('tab') === 'predictions' ? 'predictions' : 'pfz';

  return (
    <div className="stack">
      <PageHeader
        title={tr('Fishing zones', 'मासेमारी क्षेत्रे')}
        description={tr(
          'Official INCOIS potential fishing zones and AI-predicted fishing activity for tomorrow',
          'अधिकृत INCOIS संभाव्य मासेमारी क्षेत्रे आणि उद्याची AI-अपेक्षित मासेमारी हालचाल',
        )}
        actions={
          <Segmented<Tab>
            label={tr('View', 'दृश्य')}
            value={tab}
            onChange={(v) => navigate('zones', { tab: v })}
            options={[
              { value: 'pfz', label: <><Radar size={14} aria-hidden />{tr('PFZ advisories', 'PFZ सल्ले')}</> },
              { value: 'predictions', label: <><Grid3x3 size={14} aria-hidden />{tr('Activity predictions', 'हालचाल अंदाज')}</> },
            ]}
          />
        }
      />
      {tab === 'pfz' ? <PfzTab /> : <PredictionsTab />}
      <Disclaimer />
    </div>
  );
}

// -----------------------------------------------------------------------------
function PfzTab() {
  const { summary } = useData();
  const { mr, tr } = useLang();
  const data = summary!;
  const pfz = data.pfz_advisory;
  const [district, setDistrict] = useState<string>('all');
  const [q, setQ] = useState('');

  const rows = useMemo(() => pfz.locations.map((l, index) => ({
    ...l, index,
    district: districtOf(data.landing_centres, l.latitude, l.longitude) ?? '—',
    km: parseKm(l.distance_km),
  })), [pfz, data.landing_centres]);

  const filtered = rows.filter((r) =>
    (district === 'all' || r.district === district) &&
    (!q || r.landing_centre.toLowerCase().includes(q.toLowerCase())));

  const byDistrict = DISTRICTS.map((d) => ({ d, n: rows.filter((r) => r.district === d).length }));
  const status = freshnessMeta(pfz.status);

  return (
    <>
      <div className="grid-kpi">
        <Metric label={tr('Advisory points', 'सल्ला बिंदू')} icon={Radar} value={pfz.count}
          sub={<Badge tone={status.tone} icon={status.icon}>{status.label[mr ? 1 : 0]}</Badge>} />
        <Metric label={tr('Issued', 'जारी')} value={<span style={{ fontSize: 20 }}>{fmtDate(pfz.advisory_date)}</span>} sub={pfz.source} />
        <Metric label={tr('Valid until', 'वैध')} value={<span style={{ fontSize: 20 }}>{fmtDateTime(pfz.validity_date)}</span>}
          sub={tr('Re-check after expiry', 'मुदतीनंतर पुन्हा तपासा')} />
        <Metric label={tr('By district', 'जिल्हानिहाय')}>
          <div className="chip-list" style={{ marginTop: 2 }}>
            {byDistrict.map(({ d, n }) => <span key={d} className="chip">{districtLabel(d, mr)} <span className="num fw-600">{n}</span></span>)}
          </div>
        </Metric>
      </div>

      <Card flush>
        <div className="toolbar" style={{ padding: '0 20px 12px' }}>
          <div className="grow input-with-icon">
            <Search aria-hidden />
            <input className="input" placeholder={tr('Search reference centre…', 'संदर्भ केंद्र शोधा…')} value={q} onChange={(e) => setQ(e.target.value)} aria-label={tr('Search', 'शोधा')} />
          </div>
          <div style={{ width: 200 }}>
            <select className="select" value={district} onChange={(e) => setDistrict(e.target.value)} aria-label={tr('District', 'जिल्हा')}>
              <option value="all">{tr('All districts', 'सर्व जिल्हे')}</option>
              {DISTRICTS.map((d) => <option key={d} value={d}>{districtLabel(d, mr)}</option>)}
            </select>
          </div>
          <span className="text-sm text-muted num">{filtered.length} / {rows.length}</span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>{tr('Reference centre', 'संदर्भ केंद्र')}</th>
                <th>{tr('District', 'जिल्हा')}</th>
                <th>{tr('Bearing', 'दिशा')}</th>
                <th className="right">{tr('Distance', 'अंतर')}</th>
                <th className="right">{tr('Depth', 'खोली')}</th>
                <th>{tr('Location', 'स्थान')}</th>
                <th className="right"><span className="sr-only">{tr('Actions', 'कृती')}</span></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.index}>
                  <td className="num text-muted">{r.index + 1}</td>
                  <td className="strong">{r.landing_centre}</td>
                  <td>{districtLabel(r.district, mr)}</td>
                  <td className="num">{r.direction} · {r.bearing_degrees}°</td>
                  <td className="right num">{r.km != null ? `${r.km.toFixed(0)} km` : '—'}</td>
                  <td className="right num">{r.depth_min_m != null || r.depth_max_m != null ? `${r.depth_min_m ?? '?'}–${r.depth_max_m ?? '?'} m` : '—'}</td>
                  <td className="kbd-coord">{fmtCoord(r.latitude, r.longitude)}</td>
                  <td className="right" style={{ whiteSpace: 'nowrap' }}>
                    <a className="btn btn-ghost btn-sm" href={href('map', { lat: r.latitude, lon: r.longitude })} aria-label={tr('Show on map', 'नकाशावर दाखवा')}><MapIcon size={14} /></a>
                    <a className="btn btn-secondary btn-sm" href={href('navigation', { pfz: r.index })}><Navigation size={14} aria-hidden />{tr('Plan trip', 'सफर')}</a>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="text-muted" style={{ textAlign: 'center', padding: 32 }}>{tr('No advisories match the filters', 'फिल्टरशी जुळणारे सल्ले नाहीत')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

// -----------------------------------------------------------------------------
function PredictionsTab() {
  const { summary } = useData();
  const { mr, tr } = useLang();
  const data = summary!;
  const [district, setDistrict] = useState<string>('all');
  const preds = data.predictions;
  const threshold = preds[0]?.decision_threshold ?? data.metadata.decision_threshold ?? null;
  const calMethod = preds[0]?.calibration_method ?? data.metadata.calibration_method ?? null;
  const calLabel = calMethod ? `${calMethod[0].toUpperCase()}${calMethod.slice(1).replace('_', ' ')}` : null;
  const pMode = preds[0]?.prediction_mode ?? data.metadata.prediction_mode ?? 'daily_operational';
  const isSeasonal = pMode === 'seasonal_climatology';
  const anchorDate = preds[0]?.seasonal_anchor_date ?? data.metadata.seasonal_anchor_date ?? null;
  const hasHabitat = preds.some((r) => r.habitat_suitability_score != null);

  const rows = useMemo(() => preds.map((p) => ({
    ...p, district: districtOf(data.landing_centres, p.latitude, p.longitude) ?? '—',
  })).sort((a, b) => b.predicted_apparent_fishing_probability - a.predicted_apparent_fishing_probability), [preds, data.landing_centres]);

  const filtered = rows.filter((r) => district === 'all' || r.district === district);
  const high = rows.filter((r) => r.predicted_apparent_fishing_binary === 1).length;

  const bins = useMemo(() => {
    const out = Array.from({ length: 10 }, (_, i) => ({ from: i / 10, to: (i + 1) / 10, count: 0 }));
    filtered.forEach((r) => { out[Math.min(9, Math.floor(r.predicted_apparent_fishing_probability * 10))].count++; });
    return out;
  }, [filtered]);

  return (
    <>
      <div className="grid-kpi">
        <Metric label={tr('Grid cells', 'ग्रिड क्षेत्रे')} icon={Grid3x3} value={rows.length} sub={tr('0.25° marine grid', '0.25° सागरी ग्रिड')} />
        <Metric label={tr('High activity', 'जास्त हालचाल')} icon={Fish} value={high} unit={`/ ${rows.length}`} sub={tr('Above the decision threshold', 'निर्णय मर्यादेपेक्षा अधिक')} />
        <Metric
          label={tr('Decision threshold', 'निर्णय मर्यादा')}
          icon={Gauge}
          value={threshold != null ? fmtPct(threshold) : '—'}
          sub={calLabel
            ? tr(`Validated · ${calLabel} calibrated`, `प्रमाणित · ${calLabel} कॅलिब्रेटेड`)
            : tr('Validated on 2023 hold-out data', '2023 चाचणी डेटावर प्रमाणित')}
        />
        <Metric
          label={isSeasonal ? tr('Seasonal basis', 'हंगामी आधार') : tr('Prediction for', 'अंदाज')}
          value={<span style={{ fontSize: 20 }}>{isSeasonal && anchorDate ? anchorDate : fmtDateTime(data.metadata.prediction_timestamp)}</span>}
          sub={isSeasonal ? tr(`${data.metadata.model_version} · 2020–2024 climatology`, `${data.metadata.model_version} · २०२०–२०२४ संदर्भ`) : data.metadata.model_version}
        />
      </div>

      <div className="grid-2">
        <Card title={tr('Distribution of predicted activity', 'अपेक्षित हालचालीचे वितरण')} subtitle={tr('Number of grid cells by predicted probability', 'अपेक्षित संभाव्यतेनुसार ग्रिड क्षेत्रांची संख्या')}>
          <Histogram
            bins={bins}
            xLabel={tr('Predicted probability', 'अपेक्षित संभाव्यता')}
            yLabel={tr('Cells', 'क्षेत्रे')}
            marker={threshold != null ? { value: threshold, label: tr('Threshold', 'मर्यादा') } : undefined}
            ariaLabel={tr('Histogram of predicted activity probabilities', 'अपेक्षित हालचालींचा आलेख')}
            tooltip={(b) => (
              <>
                <div className="chart-tooltip-title">{fmtPct(b.from)}–{fmtPct(b.to)}</div>
                <div className="chart-tooltip-row"><span>{tr('Grid cells', 'ग्रिड क्षेत्रे')}</span><span>{b.count}</span></div>
              </>
            )}
          />
        </Card>
        <Card title={tr('How to read this', 'हे कसे वाचावे')}>
          <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
            <li>{tr('GFW pattern (blue grid): shows where AIS-equipped commercial vessels historically operated in this seasonal window (2020–2024 climatology when live AIS is absent).', 'GFW पॅटर्न (निळा ग्रिड): या हंगामात AIS-सज्ज नौका ऐतिहासिकदृष्ट्या कुठे कार्यरत होत्या ते दाखवतो.')}</li>
            <li>{tr('Ocean habitat score (Stage 1): scores environmental favourability from SST fronts, ESA CCI Chlorophyll-a, and 30 arc-sec bathymetry with zero vessel history.', 'सागरी अधिवास गुण (टप्पा १): नौका इतिहासाशिवाय SST, क्लोरोफिल-अ आणि खोलीवरून पर्यावरणीय अनुकूलता मोजतो.')}</li>
            <li>{tr('INCOIS PFZ advisories (green pins): live satellite-derived coastal potential fishing zones that also cover small nearshore artisanal boats missed by AIS.', 'INCOIS PFZ सल्ला (हिरवे पिन): AIS मध्ये न दिसणाऱ्या लहान किनारी नौकांसाठी उपयुक्त अधिकृत थेट उपग्रह सल्ला.')}</li>
            <li>{tr('Marine SafetyGate (badges): always evaluated independently from IMD warnings and wave/wind thresholds — never inferred from fishing scores.', 'सागरी सुरक्षा (SafetyGate): हवामान आणि लाटांच्या मर्यादेवर आधारित स्वतंत्र तपासणी — मासेमारी गुणांपासून पूर्णपणे वेगळी.')}</li>
          </ul>
        </Card>
      </div>

      <Card
        title={tr('Cells ranked by predicted activity', 'अपेक्षित हालचालीनुसार क्रमवारी')}
        actions={
          <div style={{ width: 200 }}>
            <select className="select" value={district} onChange={(e) => setDistrict(e.target.value)} aria-label={tr('District', 'जिल्हा')}>
              <option value="all">{tr('All districts', 'सर्व जिल्हे')}</option>
              {DISTRICTS.map((d) => <option key={d} value={d}>{districtLabel(d, mr)}</option>)}
            </select>
          </div>
        }
        flush
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tr('Location', 'स्थान')}</th>
                <th>{tr('District', 'जिल्हा')}</th>
                <th style={{ width: '28%' }}>{tr('Predicted activity', 'अपेक्षित हालचाल')}</th>
                {hasHabitat && <th className="right">{tr('Habitat', 'अधिवास')}</th>}
                <th>{tr('Class', 'वर्ग')}</th>
                <th className="right">{tr('From nearest centre', 'जवळच्या केंद्रापासून')}</th>
                <th className="right"><span className="sr-only">{tr('Actions', 'कृती')}</span></th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 25).map((r) => (
                <tr key={r.grid_cell_id}>
                  <td className="kbd-coord">{fmtCoord(r.latitude, r.longitude, 2)}</td>
                  <td>{districtLabel(r.district, mr)}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1 }}><Meter value={r.predicted_apparent_fishing_probability} max={1} warnAt={2} label={tr('Predicted activity', 'अपेक्षित हालचाल')} /></div>
                      <span className="num fw-500" style={{ color: 'var(--text)', width: 40, textAlign: 'right' }}>{fmtPct(r.predicted_apparent_fishing_probability)}</span>
                    </div>
                  </td>
                  {hasHabitat && (
                    <td className="right num">
                      {r.habitat_suitability_score != null ? fmtPct(r.habitat_suitability_score) : '—'}
                    </td>
                  )}
                  <td>{r.predicted_apparent_fishing_binary === 1 ? <Badge tone="info">{tr('High', 'जास्त')}</Badge> : <span className="text-muted">{tr('Low', 'कमी')}</span>}</td>
                  <td className="right num">{r.distance_to_coast_km.toFixed(0)} km</td>
                  <td className="right"><a className="btn btn-ghost btn-sm" href={href('map', { lat: r.latitude, lon: r.longitude })}>{tr('Map', 'नकाशा')}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
