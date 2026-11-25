/** Overview — the morning check: safety, zones, activity, conditions, sources. */

import { useMemo } from 'react';
import { ArrowRight, Database, Fish, Radar, ShieldCheck, Waves } from 'lucide-react';
import { Card, Dot, LinkButton, Metric, PageHeader, StatusBadge } from '../components/ui';
import { FreshnessHUD } from '../components/FreshnessHUD';
import { MarineMap } from '../map/MarineMap';
import { conditionsAt, useData } from '../lib/data';
import { DISTRICTS, districtLabel, districtOf } from '../lib/districts';
import { fmtCoord, fmtDate, fmtDateTime, fmtNum, parseKm } from '../lib/format';
import { useLang } from '../lib/lang';
import { href } from '../lib/router';
import { safetyMeta } from '../lib/status';
import { Disclaimer, PageState, SafetyCallout } from './shared';

export function Overview() {
  return (
    <PageState>
      <OverviewContent />
    </PageState>
  );
}

function OverviewContent() {
  const { summary, forecast, oceanLayers } = useData();
  const { mr, tr } = useLang();
  const data = summary!;

  const stats = useMemo(() => {
    const total = data.predictions.length;
    const high = data.predictions.filter((p) => p.predicted_apparent_fishing_binary === 1).length;
    const sources = data.source_freshness ? Object.values(data.source_freshness) : [];
    const live = sources.filter((s) => s.status === 'LIVE').length;
    const conditions = DISTRICTS.map((d) => ({ district: d, c: conditionsAt(forecast, d) }));
    const waves = conditions.map((x) => x.c?.wave).filter((v): v is number => v != null);
    const maxWave = waves.length ? Math.max(...waves) : null;
    const maxWaveDistrict = conditions.find((x) => x.c?.wave === maxWave)?.district ?? null;
    return { total, high, live, sourcesTotal: sources.length, conditions, maxWave, maxWaveDistrict };
  }, [data, forecast]);

  const safety = safetyMeta(data.marine_safety.overall_status);
  const pfz = data.pfz_advisory;
  const thresholds = forecast?.thresholds ?? { wave_height_m: 4, wind_speed_kmh: 50 };
  const today = new Date().toLocaleDateString(mr ? 'mr-IN' : undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="stack">
      <PageHeader
        title={tr('Overview', 'आढावा')}
        description={`${today} · ${tr('Marine conditions along the Maharashtra coast', 'महाराष्ट्र किनाऱ्यावरील सागरी परिस्थिती')}`}
        actions={<LinkButton href={href('navigation')} variant="primary" icon={ArrowRight}>{tr('Plan a trip', 'सफर नियोजित करा')}</LinkButton>}
      />

      <SafetyCallout />

      <div className="grid-kpi">
        <Metric label={tr('Marine safety', 'सागरी सुरक्षा')} icon={ShieldCheck} sub={tr('IMD / INCOIS official guidance', 'IMD / INCOIS अधिकृत मार्गदर्शन')}>
          <div style={{ padding: '4px 0 2px' }}><StatusBadge meta={safety} mr={mr} /></div>
        </Metric>
        <Metric
          label={tr('PFZ advisories', 'PFZ सल्ले')} icon={Radar} value={pfz.count}
          sub={pfz.validity_date ? `${tr('Valid until', 'वैध')} ${fmtDate(pfz.validity_date)}` : tr('No current advisory', 'सध्या सल्ला नाही')}
        />
        <Metric
          label={tr('High-activity cells', 'जास्त हालचाल क्षेत्रे')} icon={Fish}
          value={stats.high} unit={`/ ${stats.total}`}
          sub={tr('Predicted for tomorrow · 0.25° grid', 'उद्यासाठी अंदाज · 0.25° ग्रिड')}
        />
        <Metric
          label={tr('Highest wave now', 'सध्याची सर्वोच्च लाट')} icon={Waves}
          value={fmtNum(stats.maxWave)} unit="m"
          sub={stats.maxWaveDistrict ? `${districtLabel(stats.maxWaveDistrict, mr)} · ${tr('caution above', 'सावधानता')} ${thresholds.wave_height_m} m` : tr('Forecast unavailable', 'अंदाज उपलब्ध नाही')}
        />
      </div>

      <div className="grid-main-side stretch">
        <Card
          title={tr('Marine map', 'सागरी नकाशा')}
          subtitle={tr('Predicted activity, INCOIS zones and landing centres', 'अपेक्षित हालचाल, INCOIS क्षेत्रे व लँडिंग केंद्रे')}
          actions={<LinkButton href={href('map')} size="sm">{tr('Open map', 'नकाशा उघडा')}</LinkButton>}
          className="card-fill"
          flush
        >
          <MarineMap data={data} oceanLayers={oceanLayers} mr={mr} height="auto" flush layersCollapsed />
        </Card>

        <div className="stack">
          <Card
            title={tr('Conditions now', 'सध्याची परिस्थिती')}
            subtitle={forecast?.retrieved_at ? `${tr('Forecast retrieved', 'अंदाज मिळवला')} ${fmtDateTime(forecast.retrieved_at)}` : undefined}
            actions={<LinkButton href={href('weather')} size="sm">{tr('Forecast', 'अंदाज')}</LinkButton>}
            flush
          >
            <ul className="list">
              {stats.conditions.map(({ district, c }) => {
                const exceeds = c && ((c.wave ?? 0) > thresholds.wave_height_m || (c.wind ?? 0) > thresholds.wind_speed_kmh);
                return (
                  <li key={district} className="list-row">
                    <Dot tone={!c ? 'neutral' : exceeds ? 'warning' : 'success'} />
                    <div className="list-row-main">
                      <div className="list-row-title">{districtLabel(district, mr)}</div>
                    </div>
                    <span className="text-sm num text-secondary" style={{ whiteSpace: 'nowrap' }}>
                      {c ? <>{fmtNum(c.wave)} m · {fmtNum(c.wind, 0)} km/h</> : '—'}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Card>

          {data.source_freshness && (
            <Card
              title={tr('Data sources', 'डेटा स्रोत')}
              subtitle={`${stats.live} / ${stats.sourcesTotal} ${tr('sources current', 'स्रोत वर्तमान')}`}
              actions={<Database size={16} className="text-muted" aria-hidden />}
              flush
            >
              <FreshnessHUD freshness={data.source_freshness} isMarathi={mr} />
            </Card>
          )}
        </div>
      </div>

      <Card
        title={tr('Latest INCOIS PFZ advisories', 'नवीनतम INCOIS PFZ सल्ले')}
        subtitle={pfz.advisory_date ? `${tr('Issued', 'जारी')} ${fmtDate(pfz.advisory_date)} · ${pfz.source}` : pfz.source}
        actions={<LinkButton href={href('zones')} size="sm">{tr('View all', 'सर्व पहा')} ({pfz.count})</LinkButton>}
        flush
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{tr('Reference centre', 'संदर्भ केंद्र')}</th>
                <th>{tr('District', 'जिल्हा')}</th>
                <th>{tr('Bearing', 'दिशा')}</th>
                <th className="right">{tr('Distance', 'अंतर')}</th>
                <th>{tr('Location', 'स्थान')}</th>
                <th className="right"><span className="sr-only">{tr('Actions', 'कृती')}</span></th>
              </tr>
            </thead>
            <tbody>
              {pfz.locations.slice(0, 6).map((l, i) => {
                const d = districtOf(data.landing_centres, l.latitude, l.longitude);
                return (
                  <tr key={i}>
                    <td className="strong">{l.landing_centre}</td>
                    <td>{d ? districtLabel(d, mr) : '—'}</td>
                    <td className="num">{l.direction} · {l.bearing_degrees}°</td>
                    <td className="right num">{parseKm(l.distance_km)?.toFixed(0) ?? '—'} km</td>
                    <td className="kbd-coord">{fmtCoord(l.latitude, l.longitude)}</td>
                    <td className="right">
                      <a className="btn btn-ghost btn-sm" href={href('map', { lat: l.latitude, lon: l.longitude })}>{tr('Map', 'नकाशा')}</a>
                    </td>
                  </tr>
                );
              })}
              {pfz.count === 0 && (
                <tr><td colSpan={6} className="text-muted" style={{ textAlign: 'center', padding: 24 }}>{tr('No current PFZ advisory', 'सध्या PFZ सल्ला नाही')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Disclaimer />
    </div>
  );
}
