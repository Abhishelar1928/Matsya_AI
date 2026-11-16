/** Districts — Palghar, Mumbai, Raigad, Ratnagiri, Sindhudurg at a glance. */

import { useMemo } from 'react';
import { Anchor, CloudSun, Map as MapIcon } from 'lucide-react';
import { Badge, Card, LinkButton, PageHeader } from '../components/ui';
import { conditionsAt, useData } from '../lib/data';
import { DISTRICTS, districtLabel, districtOf } from '../lib/districts';
import { fmtNum } from '../lib/format';
import { useLang } from '../lib/lang';
import { href } from '../lib/router';
import { Disclaimer, PageState } from './shared';

export function Districts() {
  return <PageState><Content /></PageState>;
}

function Content() {
  const { summary, forecast } = useData();
  const { mr, tr } = useLang();
  const data = summary!;
  const thresholds = forecast?.thresholds ?? { wave_height_m: 4, wind_speed_kmh: 50 };

  const rows = useMemo(() => DISTRICTS.map((d) => {
    const centres = data.landing_centres.filter((c) => c.district === d);
    const pfz = data.pfz_advisory.locations.filter((l) => districtOf(data.landing_centres, l.latitude, l.longitude) === d).length;
    const cells = data.predictions.filter((p) => districtOf(data.landing_centres, p.latitude, p.longitude) === d);
    const high = cells.filter((p) => p.predicted_apparent_fishing_binary === 1).length;
    const c = conditionsAt(forecast, d);
    const lat = centres.length ? centres.reduce((s, x) => s + x.latitude, 0) / centres.length : null;
    const lon = centres.length ? Math.min(...centres.map((x) => x.longitude)) - 0.2 : null;
    return { d, centres, pfz, cells: cells.length, high, c, lat, lon };
  }), [data, forecast]);

  return (
    <div className="stack">
      <PageHeader
        title={tr('Coastal districts', 'किनारी जिल्हे')}
        description={tr('Five districts, north to south. Zones and grid cells are attributed to the nearest landing centre.', 'उत्तरेकडून दक्षिणेकडे पाच जिल्हे. क्षेत्रे व ग्रिड जवळच्या लँडिंग केंद्राच्या जिल्ह्याला जोडली आहेत.')}
      />
      <div className="grid-3">
        {rows.map((r) => {
          const exceeds = r.c && ((r.c.wave ?? 0) > thresholds.wave_height_m || (r.c.wind ?? 0) > thresholds.wind_speed_kmh);
          return (
            <Card
              key={r.d}
              className="district-card"
              title={districtLabel(r.d, mr)}
              subtitle={mr ? r.d : undefined}
              actions={!r.c ? <Badge>{tr('No forecast', 'अंदाज नाही')}</Badge> : exceeds ? <Badge tone="warning">{tr('Rough', 'खवळलेला')}</Badge> : <Badge tone="success">{tr('Within limits', 'मर्यादेत')}</Badge>}
            >
              <div className="district-stats">
                <div>
                  <div className="district-stat-label">{tr('PFZ advisories', 'PFZ सल्ले')}</div>
                  <div className="district-stat-value">{r.pfz}</div>
                </div>
                <div>
                  <div className="district-stat-label">{tr('High-activity cells', 'जास्त हालचाल क्षेत्रे')}</div>
                  <div className="district-stat-value">{r.high} <span className="text-sm text-muted" style={{ fontWeight: 400 }}>/ {r.cells}</span></div>
                </div>
                <div>
                  <div className="district-stat-label">{tr('Waves now', 'सध्याच्या लाटा')}</div>
                  <div className="district-stat-value">{fmtNum(r.c?.wave)} <span className="text-sm text-muted" style={{ fontWeight: 400 }}>m</span></div>
                </div>
                <div>
                  <div className="district-stat-label">{tr('Wind now', 'सध्याचा वारा')}</div>
                  <div className="district-stat-value">{fmtNum(r.c?.wind, 0)} <span className="text-sm text-muted" style={{ fontWeight: 400 }}>km/h</span></div>
                </div>
              </div>
              <hr className="divider" />
              <div>
                <div className="district-stat-label" style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Anchor size={13} aria-hidden />{tr('Landing centres', 'लँडिंग केंद्रे')}
                </div>
                <div className="chip-list">
                  {r.centres.map((c) => <span key={c.name} className="chip">{mr && c.name_mr ? c.name_mr : c.name.replace(`${r.d} - `, '')}</span>)}
                </div>
              </div>
              <div className="page-actions">
                {r.lat != null && r.lon != null && (
                  <LinkButton size="sm" icon={MapIcon} href={href('map', { lat: r.lat.toFixed(3), lon: r.lon.toFixed(3) })}>{tr('Map', 'नकाशा')}</LinkButton>
                )}
                <LinkButton size="sm" icon={CloudSun} href={href('weather', { district: r.d })}>{tr('Forecast', 'अंदाज')}</LinkButton>
              </div>
            </Card>
          );
        })}
      </div>
      <Disclaimer />
    </div>
  );
}
