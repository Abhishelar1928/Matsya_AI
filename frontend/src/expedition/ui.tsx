/**
 * Expedition Mode UI adapter — maps the expedition screens onto the shared
 * MatsyaAI design system (light, minimal). Keeps the original exported API.
 * Colours are hex (not CSS vars) because Leaflet writes them as SVG attributes.
 */

import type { CSSProperties, ReactNode } from 'react';
import type { SafetyStatus } from '../types/map';
import { safetyMeta, type Tone } from '../lib/status';
import { fmtDateTime } from '../lib/format';

export const colors = {
  bg: '#f6f7f9',
  card: '#ffffff',
  border: '#e4e7ec',
  text: '#0b1f33',
  muted: '#667085',
  accent: '#0b6bcb',
  green: '#067647',
  amber: '#b54708',
  red: '#b42318',
  slate: '#475467',
  pfz: '#0f8a66',
  landing: '#0b1f33',
};

const toneByColor: Record<string, Tone> = {
  [colors.green]: 'success', [colors.amber]: 'warning', [colors.red]: 'danger',
  [colors.accent]: 'info', [colors.slate]: 'neutral',
};

export function safetyColor(status: SafetyStatus | string | undefined): string {
  const tone = safetyMeta(status).tone;
  return tone === 'danger' ? colors.red : tone === 'warning' ? colors.amber : tone === 'success' ? colors.green : colors.slate;
}

export function safetyLabel(status: SafetyStatus | string | undefined, mr: boolean): string {
  return safetyMeta(status).label[mr ? 1 : 0];
}

export function safetyTone(status: SafetyStatus | string | undefined): Tone {
  return safetyMeta(status).tone;
}

export function Card({ children, style, title }: { children: ReactNode; style?: CSSProperties; title?: ReactNode }) {
  return (
    <section className="card" style={{ marginBottom: 16, ...style }}>
      {title && <header className="card-header"><h2 className="card-title">{title}</h2></header>}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Button({
  children, onClick, disabled, variant = 'primary', style, type = 'button',
}: {
  children: ReactNode; onClick?: () => void; disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger'; style?: CSSProperties; type?: 'button' | 'submit';
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`btn btn-${variant} btn-lg`} style={style}>
      {children}
    </button>
  );
}

export function Badge({ children, color }: { children: ReactNode; color: string }) {
  const tone = toneByColor[color] ?? 'neutral';
  return <span className={`badge${tone !== 'neutral' ? ` badge-${tone}` : ''}`}>{children}</span>;
}

export function Stat({ label, value, sub, big }: { label: string; value: ReactNode; sub?: ReactNode; big?: boolean }) {
  return (
    <div className="card metric" style={{ padding: '12px 14px' }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ fontSize: big ? 26 : 20 }}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export const inputStyle: CSSProperties = {};
export const inputClass = 'select';

export function fmtTime(iso: string | null | undefined): string {
  return fmtDateTime(iso);
}
