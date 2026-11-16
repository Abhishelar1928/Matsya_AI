/**
 * MatsyaAI design system — reusable primitives.
 * Styling lives in index.css (tokens + component classes); these components
 * only compose class names so every page looks the same.
 */

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';
import type { StatusMeta, Tone } from '../lib/status';

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

// --- Card --------------------------------------------------------------------
export function Card({
  title, subtitle, actions, children, footer, flush, className,
}: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode;
  footer?: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={cx('card', className)}>
      {(title || actions) && (
        <header className="card-header">
          <div style={{ minWidth: 0 }}>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="page-actions">{actions}</div>}
        </header>
      )}
      {children !== undefined && <div className={cx('card-body', flush && 'flush')}>{children}</div>}
      {footer && <footer className="card-footer">{footer}</footer>}
    </section>
  );
}

// --- Page header -------------------------------------------------------------
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

// --- Button ------------------------------------------------------------------
type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export function Button({
  variant = 'secondary', size, icon: Icon, block, children, className, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant; size?: 'sm' | 'lg'; icon?: LucideIcon; block?: boolean;
}) {
  return (
    <button
      type="button"
      className={cx('btn', `btn-${variant}`, size && `btn-${size}`, block && 'btn-block', !children && Icon && 'btn-icon', className)}
      {...rest}
    >
      {Icon && <Icon size={16} strokeWidth={2} aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({
  href, variant = 'secondary', size, icon: Icon, children,
}: { href: string; variant?: BtnVariant; size?: 'sm' | 'lg'; icon?: LucideIcon; children: ReactNode }) {
  return (
    <a href={href} className={cx('btn', `btn-${variant}`, size && `btn-${size}`)} style={{ textDecoration: 'none' }}>
      {Icon && <Icon size={16} strokeWidth={2} aria-hidden />}
      {children}
    </a>
  );
}

// --- Badge / status ----------------------------------------------------------
export function Badge({ tone = 'neutral', icon: Icon, children }: { tone?: Tone; icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className={cx('badge', tone !== 'neutral' && `badge-${tone}`)}>
      {Icon && <Icon aria-hidden />}
      {children}
    </span>
  );
}

export function StatusBadge({ meta, mr, long }: { meta: StatusMeta; mr: boolean; long?: boolean }) {
  const text = (long ? meta.label : meta.short)[mr ? 1 : 0];
  return <Badge tone={meta.tone} icon={meta.icon}>{text}</Badge>;
}

export function Dot({ tone = 'neutral' }: { tone?: Tone }) {
  return <span className={cx('dot', tone !== 'neutral' && `dot-${tone}`)} aria-hidden />;
}

// --- Callout -----------------------------------------------------------------
export function Callout({
  tone = 'neutral', icon: Icon, title, children, meta, action,
}: { tone?: Tone; icon: LucideIcon; title: ReactNode; children?: ReactNode; meta?: ReactNode; action?: ReactNode }) {
  return (
    <div className={cx('callout', tone !== 'neutral' && `callout-${tone}`)} role="status">
      <div className="callout-icon"><Icon size={20} strokeWidth={2} aria-hidden /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="callout-title">{title}</div>
        {children && <div className="callout-text">{children}</div>}
        {meta && <div className="callout-meta">{meta}</div>}
      </div>
      {action && <div className="callout-action" style={{ flexShrink: 0, alignSelf: 'center' }}>{action}</div>}
    </div>
  );
}

// --- Metric ------------------------------------------------------------------
export function Metric({
  label, value, unit, sub, icon: Icon, children,
}: { label: string; value?: ReactNode; unit?: string; sub?: ReactNode; icon?: LucideIcon; children?: ReactNode }) {
  return (
    <div className="card metric">
      <div className="metric-label">{Icon && <Icon aria-hidden />}{label}</div>
      {value !== undefined && <div className="metric-value">{value}{unit && <small>{unit}</small>}</div>}
      {children}
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

// --- Segmented control -------------------------------------------------------
export function Segmented<T extends string>({
  value, options, onChange, label,
}: { value: T; options: { value: T; label: ReactNode; disabled?: boolean }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} disabled={o.disabled} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- Switch ------------------------------------------------------------------
export function Switch({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track" aria-hidden />
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>{children}</span>
    </label>
  );
}

// --- Meter -------------------------------------------------------------------
export function Meter({ value, max, warnAt = 0.75, label }: { value: number | null; max: number; warnAt?: number; label: string }) {
  if (value === null) return <div className="meter" aria-label={`${label}: no data`} />;
  const ratio = Math.max(0, Math.min(1, value / max));
  const tone = value > max ? 'danger' : ratio >= warnAt ? 'warning' : '';
  return (
    <div className="meter" role="meter" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
      <div className={cx('meter-fill', tone)} style={{ width: `${Math.max(ratio * 100, 2)}%` }} />
    </div>
  );
}

// --- Empty / skeleton --------------------------------------------------------
export function Empty({ icon: Icon = Inbox, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon aria-hidden />
      <div className="empty-title">{title}</div>
      {children && <div>{children}</div>}
    </div>
  );
}

export function Skeleton({ height = 16, width = '100%', style }: { height?: number | string; width?: number | string; style?: CSSProperties }) {
  return <div className="skeleton" style={{ height, width, ...style }} aria-hidden />;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}
