/**
 * Lightweight SVG charts (no chart library).
 *
 * Follows the data-viz rules: one y-axis, 2px lines, recessive grid, a dashed
 * reference line for thresholds, crosshair + tooltip on hover, legend for ≥2
 * series, bars ≤24px with 4px rounded data-ends, text in text tokens.
 */

import { useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode, type RefObject } from 'react';

function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Axis ticks on a 1/2/2.5/5 × 10ⁿ step, ~4 intervals, top tick ≥ max. */
function niceTicks(max: number, target = 4): { max: number; ticks: number[] } {
  const raw = Math.max(max, 1e-6) / target;
  const exp = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / exp;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * exp;
  const top = Math.ceil(max / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(+v.toFixed(6));
  return { max: top, ticks };
}

function fmtTick(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(v < 1 ? 2 : 1).replace(/0$/, '');
}


// =============================================================================
// Time series
// =============================================================================
export interface Series {
  id: string;
  label: string;
  color: string; // CSS colour (var(--series-n))
  values: (number | null)[];
}

export function TimeSeriesChart({
  times, series, unit, height = 220, threshold, nowMarker = true, digits = 1, ariaLabel,
}: {
  times: string[];
  series: Series[];
  unit: string;
  height?: number;
  threshold?: { value: number; label: string };
  nowMarker?: boolean;
  digits?: number;
  ariaLabel: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const m = { top: 22, right: 16, bottom: 28, left: 40 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;

  const ts = useMemo(() => times.map((t) => Date.parse(t)), [times]);
  const t0 = ts[0] ?? 0;
  const t1 = ts[ts.length - 1] ?? 1;
  const allVals = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const axis = niceTicks(Math.max(...allVals, threshold ? threshold.value * 1.05 : 0, 0.1));
  const yMax = axis.max;
  const x = (t: number) => m.left + ((t - t0) / Math.max(1, t1 - t0)) * iw;
  const y = (v: number) => m.top + ih - (v / yMax) * ih;

  const yTicks = axis.ticks;
  const dayTicks = useMemo(() => {
    const out: number[] = [];
    ts.forEach((t) => { const d = new Date(t); if (d.getHours() === 0) out.push(t); });
    return out;
  }, [ts]);
  // Choose a label interval that leaves ≥56px between time labels.
  const hoursSpan = Math.max(1, (t1 - t0) / 3600_000);
  const pxPerHour = iw / hoursSpan;
  const labelEvery = [3, 6, 12, 24].find((h) => h * pxPerHour >= 56) ?? 24;
  const sixHourTicks = useMemo(() => ts.filter((t) => new Date(t).getHours() % labelEvery === 0), [ts, labelEvery]);

  const path = (vals: (number | null)[]) => {
    let d = '';
    let pen = false;
    vals.forEach((v, i) => {
      if (v === null || v === undefined) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${x(ts[i]).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const px = e.clientX - rect.left;
    const t = t0 + (px / iw) * (t1 - t0);
    let best = 0;
    ts.forEach((tt, i) => { if (Math.abs(tt - t) < Math.abs(ts[best] - t)) best = i; });
    setHover(best);
  };

  const now = Date.now();
  const showNow = nowMarker && now >= t0 && now <= t1;
  const tooltipLeft = hover !== null ? Math.min(Math.max(x(ts[hover]) + 12, 0), width - 170) : 0;

  if (times.length === 0) return null;

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <g className="chart-grid">
          {yTicks.slice(1).map((v) => <line key={v} x1={m.left} x2={m.left + iw} y1={y(v)} y2={y(v)} />)}
          {dayTicks.map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={m.top} y2={m.top + ih} />)}
        </g>
        <line className="chart-baseline" x1={m.left} x2={m.left + iw} y1={y(0)} y2={y(0)} />
        <g className="chart-axis">
          {yTicks.map((v) => (
            <text key={v} x={m.left - 8} y={y(v) + 4} textAnchor="end">{fmtTick(v)}</text>
          ))}
          <text x={m.left - 8} y={8} textAnchor="end" style={{ fontSize: 10 }}>{unit}</text>
          {sixHourTicks.map((t) => {
            const d = new Date(t);
            const isDay = d.getHours() === 0;
            return (
              <text key={t} x={x(t)} y={height - 8} textAnchor="middle" style={isDay ? { fontWeight: 600, fill: 'var(--text-secondary)' } : undefined}>
                {isDay ? d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }) : `${String(d.getHours()).padStart(2, '0')}:00`}
              </text>
            );
          })}
        </g>
        {threshold && threshold.value <= yMax && (
          <g>
            <line className="chart-threshold" x1={m.left} x2={m.left + iw} y1={y(threshold.value)} y2={y(threshold.value)} />
            <text className="chart-threshold-label" x={m.left + iw} y={y(threshold.value) - 6} textAnchor="end">{threshold.label}</text>
          </g>
        )}
        {showNow && (
          <g>
            <line x1={x(now)} x2={x(now)} y1={m.top} y2={m.top + ih} stroke="var(--primary)" strokeWidth={1} strokeOpacity={0.35} />
            <text x={x(now) + 4} y={m.top + 10} style={{ fontSize: 10, fill: 'var(--primary)' }}>Now</text>
          </g>
        )}
        {series.map((s) => (
          <path key={s.id} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {hover !== null && (
          <g>
            <line className="chart-crosshair" x1={x(ts[hover])} x2={x(ts[hover])} y1={m.top} y2={m.top + ih} />
            {series.map((s) => {
              const v = s.values[hover];
              return v === null || v === undefined ? null : (
                <circle key={s.id} cx={x(ts[hover])} cy={y(v)} r={4.5} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
              );
            })}
          </g>
        )}
        <rect
          x={m.left} y={m.top} width={iw} height={ih} fill="transparent"
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} onPointerDown={onMove}
          style={{ touchAction: 'pan-y' }}
        />
      </svg>
      {hover !== null && (
        <div className="chart-tooltip" style={{ left: tooltipLeft, top: 8 }}>
          <div className="chart-tooltip-title">
            {new Date(ts[hover]).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </div>
          {series.map((s) => (
            <div key={s.id} className="chart-tooltip-row">
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <i style={{ width: 10, height: 2, background: s.color, display: 'inline-block' }} />{s.label}
              </span>
              <span>{s.values[hover] === null || s.values[hover] === undefined ? '—' : `${(s.values[hover] as number).toFixed(digits)} ${unit}`}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ChartLegend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="chart-legend">
      {items.map((it) => (
        <span key={it.label}>
          <i style={it.dashed ? { background: 'none', borderTop: `1px dashed ${it.color}`, height: 0 } : { background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

// =============================================================================
// Histogram (single series)
// =============================================================================
export function Histogram({
  bins, height = 200, color = 'var(--series-1)', xLabel, yLabel, marker, ariaLabel, tooltip,
}: {
  bins: { from: number; to: number; count: number }[];
  height?: number;
  color?: string;
  xLabel: string;
  yLabel: string;
  marker?: { value: number; label: string };
  ariaLabel: string;
  tooltip?: (b: { from: number; to: number; count: number }) => ReactNode;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const m = { top: 16, right: 12, bottom: 40, left: 36 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;
  const axis = niceTicks(Math.max(...bins.map((b) => b.count), 1), 3);
  const max = axis.max;
  const band = iw / bins.length;
  const barW = Math.min(24, band * 0.7);
  const y = (v: number) => m.top + ih - (v / max) * ih;
  const lo = bins[0]?.from ?? 0;
  const hi = bins[bins.length - 1]?.to ?? 1;
  const xv = (v: number) => m.left + ((v - lo) / (hi - lo)) * iw;
  const r = 4;

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}>
        <g className="chart-grid">
          {axis.ticks.slice(1).map((v) => <line key={v} x1={m.left} x2={m.left + iw} y1={y(v)} y2={y(v)} />)}
        </g>
        <g className="chart-axis">
          {axis.ticks.map((v) => <text key={v} x={m.left - 8} y={y(v) + 4} textAnchor="end">{fmtTick(v)}</text>)}
          {bins.filter((_, i) => i % 2 === 0).concat(bins.length ? [bins[bins.length - 1]] : []).map((b, i, arr) => (
            <text key={`${b.from}-${i}`} x={xv(i === arr.length - 1 ? b.to : b.from)} y={m.top + ih + 16} textAnchor="middle">
              {(i === arr.length - 1 ? b.to : b.from).toFixed(1)}
            </text>
          ))}
          <text x={m.left + iw / 2} y={height - 4} textAnchor="middle" style={{ fill: 'var(--text-secondary)' }}>{xLabel}</text>
          <text x={m.left - 8} y={m.top - 4} textAnchor="end" style={{ fontSize: 10 }}>{yLabel}</text>
        </g>
        {bins.map((b, i) => {
          const cx = m.left + band * i + band / 2;
          const h = Math.max(0, m.top + ih - y(b.count));
          const x0 = cx - barW / 2;
          const top = m.top + ih - h;
          const rr = Math.min(r, h);
          const d = h <= 0 ? '' : `M${x0},${m.top + ih} V${top + rr} Q${x0},${top} ${x0 + rr},${top} H${x0 + barW - rr} Q${x0 + barW},${top} ${x0 + barW},${top + rr} V${m.top + ih} Z`;
          return (
            <g key={i}>
              {d && <path d={d} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />}
              <rect x={m.left + band * i} y={m.top} width={band} height={ih} fill="transparent"
                onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onPointerDown={() => setHover(i)} />
            </g>
          );
        })}
        <line className="chart-baseline" x1={m.left} x2={m.left + iw} y1={m.top + ih} y2={m.top + ih} />
        {marker && (
          <g>
            <line className="chart-threshold" x1={xv(marker.value)} x2={xv(marker.value)} y1={m.top} y2={m.top + ih} />
            <text className="chart-threshold-label" x={xv(marker.value) + 4} y={m.top + 8}>{marker.label}</text>
          </g>
        )}
      </svg>
      {hover !== null && bins[hover] && (
        <div className="chart-tooltip" style={{ left: Math.min(m.left + band * hover + band, width - 170), top: 8 }}>
          {tooltip ? tooltip(bins[hover]) : (
            <>
              <div className="chart-tooltip-title">{bins[hover].from.toFixed(1)}–{bins[hover].to.toFixed(1)}</div>
              <div className="chart-tooltip-row"><span>{yLabel}</span><span>{bins[hover].count}</span></div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
