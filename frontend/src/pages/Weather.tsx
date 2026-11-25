/** Weather — 72 h offshore wave & wind forecast per district, plus source freshness. */

import { useMemo, useState } from 'react';
import { ArrowUp, CloudOff, Compass, Gauge, Table2, Thermometer, Timer, Waves, Wind } from 'lucide-react';
import { Button, Card, Empty, Metric, PageHeader, Segmented } from '../components/ui';
import { ChartLegend, TimeSeriesChart } from '../components/charts';
import { FreshnessHUD } from '../components/FreshnessHUD';
import { compassPoint, estimateCurrentDrift } from '../expedition/engine/geodesy';
import { conditionsAt, peakAhead, useData } from '../lib/data';
import { DISTRICTS, districtLabel, type District } from '../lib/districts';
import { fmtDateTime, fmtNum } from '../lib/format';
import { useLang } from '../lib/lang';
import { navigate, type Location } from '../lib/router';
import { Disclaimer, PageState } from './shared';

export function Weather({ loc }: { loc: Location }) {
  return <PageState><Content loc={loc} /></PageState>;
}

function Content({ loc }: { loc: Location }) {
  const { summary, forecast } = useData();
  const { mr, tr } = useLang();
  const param = loc.params.get('district');
  const district: District = (DISTRICTS as readonly string[]).includes(param ?? '') ? (param as District) : 'Mumbai';
  const [showTable, setShowTable] = useState(false);

  const d = forecast?.districts.find((x) => x.district === district);
  const h = d?.hourly ?? null;
  const now = conditionsAt(forecast, district);
  const thresholds = forecast?.thresholds ?? { wave_height_m: 4, wind_speed_kmh: 50 };

  const peaks = useMemo(() => h ? {
    wave: peakAhead(h.wave_height_m, h.time, 24),
    wind: peakAhead(h.wind_speed_kmh, h.time, 24),
    gust: peakAhead(h.wind_gusts_kmh, h.time, 24),
  } : null, [h]);

  const tableRows = useMemo(() => {
    if (!h) return [];
    const start = Date.now() - 3600_000;
    return h.time.map((t, i) => ({ t, i })).filter(({ t }) => Date.parse(t) >= start).filter((_, k) => k % 3 === 0).slice(0, 16);
  }, [h]);

  return (
    <div className="stack">
      <PageHeader
        title={tr('Weather & sea state', 'हवामान व समुद्र स्थिती')}
        description={forecast
          ? `${forecast.provider} · ${tr('retrieved', 'मिळवले')} ${fmtDateTime(forecast.retrieved_at)} · ${tr('valid to', 'वैध')} ${fmtDateTime(forecast.valid_until)}`
          : tr('Offshore forecast for each coastal district', 'प्रत्येक किनारी जिल्ह्याचा अंदाज')}
        actions={
          <Segmented<District>
            label={tr('District', 'जिल्हा')}
            value={district}
            onChange={(v) => navigate('weather', { district: v })}
            options={DISTRICTS.map((x) => ({ value: x, label: districtLabel(x, mr) }))}
          />
        }
      />

      {!h ? (
        <Card><Empty icon={CloudOff} title={tr('Forecast unavailable', 'अंदाज उपलब्ध नाही')}>{forecast?.error ?? tr('The forecast service could not be reached.', 'अंदाज सेवेशी संपर्क झाला नाही.')}</Empty></Card>
      ) : (
        <>
          <div className="grid-kpi">
            <Metric label={tr('Wave height', 'लाटांची उंची')} icon={Waves} value={fmtNum(now?.wave)} unit="m"
              sub={`${tr('24 h peak', '24 तास कमाल')} ${fmtNum(peaks?.wave)} m · ${tr('limit', 'मर्यादा')} ${thresholds.wave_height_m} m`} />
            <Metric label={tr('Wave period', 'लाट कालावधी')} icon={Timer} value={fmtNum(now?.period)} unit="s"
              sub={`${tr('Swell', 'स्वेल')} ${fmtNum(now?.swell)} m${now?.swellPeriod != null ? ` (${fmtNum(now.swellPeriod)} s)` : ''}`} />
            <Metric label={tr('Wind speed', 'वाऱ्याचा वेग')} icon={Wind} value={fmtNum(now?.wind, 0)} unit="km/h"
              sub={`${tr('24 h peak', '24 तास कमाल')} ${fmtNum(peaks?.wind, 0)} km/h · ${tr('limit', 'मर्यादा')} ${thresholds.wind_speed_kmh}`} />
            <Metric label={tr('Gusts & direction', 'झोत व दिशा')} icon={Gauge} value={fmtNum(now?.gust, 0)} unit="km/h"
              sub={now?.windDir != null ? (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <ArrowUp size={12} style={{ transform: `rotate(${(now.windDir + 180) % 360}deg)` }} aria-hidden />
                  {tr('From', 'कडून')} {compassPoint(now.windDir)} ({Math.round(now.windDir)}°)
                </span>
              ) : '—'} />
            <Metric label={tr('Sea surface temp', 'समुद्र तापमान')} icon={Thermometer} value={fmtNum(now?.sst)} unit="°C"
              sub={tr('Offshore model grid (~8 km)', 'ऑफशोर मॉडेल ग्रिड (~8 किमी)')} />
            {(() => {
              const drift = estimateCurrentDrift(now?.currentU, now?.currentV, 1);
              return (
                <Metric label={tr('Surface current / drift', 'समुद्री प्रवाह / ड्रिफ्ट')} icon={Compass}
                  value={drift ? fmtNum(drift.speedKnots, 2) : '—'} unit={drift ? 'kn' : ''}
                  sub={drift ? `${drift.compass} (${Math.round(drift.bearingDeg)}°) · ~${drift.distanceKm.toFixed(1)} km/h drift` : tr('Unavailable', 'उपलब्ध नाही')} />
              );
            })()}
          </div>

          <div className="grid-2">
            <Card title={tr('Wave height', 'लाटांची उंची')} subtitle={`${districtLabel(district, mr)} · ${tr('next 72 hours', 'पुढील 72 तास')}`}>
              <TimeSeriesChart
                times={h.time}
                series={[{ id: 'wave', label: tr('Wave height', 'लाटांची उंची'), color: 'var(--series-1)', values: h.wave_height_m }]}
                unit="m"
                threshold={{ value: thresholds.wave_height_m, label: `${tr('Caution', 'सावधानता')} ${thresholds.wave_height_m} m` }}
                ariaLabel={tr('Wave height forecast', 'लाटांचा अंदाज')}
              />
            </Card>
            <Card
              title={tr('Wind', 'वारा')}
              subtitle={`${districtLabel(district, mr)} · ${tr('next 72 hours', 'पुढील 72 तास')}`}
              actions={<ChartLegend items={[
                { label: tr('Sustained', 'सतत'), color: 'var(--series-1)' },
                { label: tr('Gusts', 'झोत'), color: 'var(--series-2)' },
              ]} />}
            >
              <TimeSeriesChart
                times={h.time}
                series={[
                  { id: 'wind', label: tr('Sustained', 'सतत'), color: 'var(--series-1)', values: h.wind_speed_kmh },
                  { id: 'gust', label: tr('Gusts', 'झोत'), color: 'var(--series-2)', values: h.wind_gusts_kmh },
                ]}
                unit="km/h"
                digits={0}
                threshold={{ value: thresholds.wind_speed_kmh, label: `${tr('Caution', 'सावधानता')} ${thresholds.wind_speed_kmh} km/h` }}
                ariaLabel={tr('Wind speed and gust forecast', 'वारा व झोत अंदाज')}
              />
            </Card>
          </div>

          <Card
            title={tr('Hourly forecast', 'तासिक अंदाज')}
            subtitle={tr('Every 3 hours, next 48 hours', 'दर 3 तासांनी, पुढील 48 तास')}
            actions={<Button size="sm" icon={Table2} onClick={() => setShowTable((s) => !s)}>{showTable ? tr('Hide table', 'तक्ता लपवा') : tr('Show table', 'तक्ता दाखवा')}</Button>}
            flush={showTable}
          >
            {showTable ? (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{tr('Time', 'वेळ')}</th>
                      <th className="right">{tr('Wave', 'लाट')} (m)</th>
                      <th className="right">{tr('Period', 'कालावधी')} (s)</th>
                      <th className="right">{tr('Swell', 'स्वेल')} (m)</th>
                      <th className="right">{tr('Wind', 'वारा')} (km/h)</th>
                      <th className="right">{tr('Gusts', 'झोत')} (km/h)</th>
                      <th>{tr('From', 'कडून')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableRows.map(({ t, i }) => (
                      <tr key={t}>
                        <td className="num">{fmtDateTime(t)}</td>
                        <td className="right num strong">{fmtNum(h.wave_height_m[i])}</td>
                        <td className="right num">{fmtNum(h.wave_period_s[i])}</td>
                        <td className="right num">{fmtNum(h.swell_wave_height_m[i])}</td>
                        <td className="right num strong">{fmtNum(h.wind_speed_kmh[i], 0)}</td>
                        <td className="right num">{fmtNum(h.wind_gusts_kmh[i], 0)}</td>
                        <td>{h.wind_direction_deg[i] != null ? compassPoint(h.wind_direction_deg[i] as number) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted">
                {tr(
                  `Forecast point ${d!.latitude.toFixed(2)}° N, ${d!.longitude.toFixed(2)}° E — offshore of ${district}. Model forecast, not an observation.`,
                  `अंदाज बिंदू ${d!.latitude.toFixed(2)}° N, ${d!.longitude.toFixed(2)}° E — ${districtLabel(district, true)} किनाऱ्यापासून दूर. मॉडेल अंदाज, प्रत्यक्ष निरीक्षण नाही.`,
                )}
              </p>
            )}
          </Card>
        </>
      )}

      {summary?.source_freshness && (
        <Card title={tr('Data freshness', 'डेटा ताजेपणा')} subtitle={tr('When each upstream source last delivered data', 'प्रत्येक स्रोताने शेवटचा डेटा कधी दिला')} flush>
          <FreshnessHUD freshness={summary.source_freshness} isMarathi={mr} />
        </Card>
      )}

      <Disclaimer />
    </div>
  );
}
