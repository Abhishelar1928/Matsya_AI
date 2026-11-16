/** Formatting helpers — one place so every page reads the same. */

export function fmtDateTime(iso: string | null | undefined, opts?: { withYear?: boolean }): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', ...(opts?.withYear ? { year: 'numeric' } : {}),
    hour: '2-digit', minute: '2-digit',
  });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function fmtTime(iso: string | number | null | undefined): string {
  if (iso === null || iso === undefined) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** "12 min ago", "3 h ago", "in 5 h" */
export function fmtRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '—';
  const diffMin = Math.round((t - now) / 60000);
  const abs = Math.abs(diffMin);
  const unit = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} d`;
  if (abs < 1) return 'just now';
  return diffMin < 0 ? `${unit} ago` : `in ${unit}`;
}

export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

export function fmtCoord(lat: number, lon: number, digits = 3): string {
  return `${lat.toFixed(digits)}° N, ${lon.toFixed(digits)}° E`;
}

export function fmtPct(n: number, digits = 0): string {
  return `${(n * 100).toFixed(digits)}%`;
}

export function parseKm(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === 'number') return v;
  const m = v.match(/[\d.]+/);
  return m ? Number(m[0]) : null;
}
