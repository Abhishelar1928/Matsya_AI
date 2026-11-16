/**
 * Download screen: shows what is in the package and each component's expiry,
 * downloads the offline basemap/bathymetry into the service-worker cache, and
 * lets the fisherman start the expedition.
 */

import { useEffect, useState } from 'react';
import { downloadAsset } from './api';
import { packageFreshness, formatRemaining, type FreshnessLevel } from './freshness';
import { Badge, Button, Card, colors, fmtTime } from './ui';
import type { ExpeditionPackage } from './types';
import { t } from '../i18n';

interface Props {
  pkg: ExpeditionPackage;
  isMarathi: boolean;
  onStart: () => void;
}

const levelColor: Record<FreshnessLevel, string> = {
  VALID: colors.green, EXPIRING: colors.amber, EXPIRED: colors.red, UNAVAILABLE: colors.slate,
};

function fmtBytes(n: number | null | undefined): string {
  if (!n) return '—';
  return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`;
}

export function DownloadPackage({ pkg, isMarathi, onStart }: Props) {
  const [progress, setProgress] = useState<Record<string, { loaded: number; total: number | null; done: boolean; error?: string }>>({});
  const [persisted, setPersisted] = useState<boolean | null>(null);

  useEffect(() => {
    if (navigator.storage?.persist) {
      navigator.storage.persist().then(setPersisted).catch(() => setPersisted(false));
    }
  }, []);

  const assets = [
    { key: 'basemap', label: t('exp_basemap'), a: pkg.offline_assets.basemap },
    { key: 'bathymetry', label: t('exp_bathymetry'), a: pkg.offline_assets.bathymetry },
  ];

  const downloadAll = async () => {
    for (const { key, a } of assets) {
      if (!a.available || !a.url) continue;
      setProgress((p) => ({ ...p, [key]: { loaded: 0, total: a.size_bytes ?? null, done: false } }));
      try {
        await downloadAsset(a.url, (loaded, total) => setProgress((p) => ({ ...p, [key]: { loaded, total, done: false } })));
        setProgress((p) => ({ ...p, [key]: { ...p[key], done: true } }));
      } catch (e) {
        setProgress((p) => ({ ...p, [key]: { ...p[key], done: false, error: e instanceof Error ? e.message : String(e) } }));
      }
    }
  };

  const fresh = packageFreshness(pkg);
  const anyDownloadable = assets.some(({ a }) => a.available);
  const compLabel: Record<string, string> = {
    warnings: isMarathi ? 'IMD चेतावण्या' : 'IMD warnings',
    forecast: isMarathi ? 'लाटा / वारा अंदाज' : 'Wave & wind forecast',
    predictions: isMarathi ? 'AI अंदाज ग्रिड' : 'AI prediction grid',
    pfz: isMarathi ? 'INCOIS PFZ क्षेत्रे' : 'INCOIS PFZ zones',
  };

  return (
    <div>
      <Card title={`${t('exp_package_ready')}`}>
        <div style={{ fontSize: 14, marginBottom: 6 }}>
          <strong>{isMarathi ? pkg.landing_centre.name_mr : pkg.landing_centre.name}</strong> → <strong style={{ color: colors.accent }}>{pkg.destination.name}</strong>
        </div>
        <div style={{ fontSize: 13, color: colors.muted }}>
          {pkg.route.distance_km.toFixed(1)} km · {pkg.route.initial_bearing_deg}° {pkg.route.initial_bearing_compass} · {pkg.route.waypoints.length} {t('exp_waypoint').toLowerCase()}s
        </div>
        {pkg.route.warnings.includes('ROUTE_CROSSES_LAND') && (
          <div style={{ marginTop: 8, color: colors.amber, fontWeight: 700, fontSize: 13 }}>{t('exp_route_crosses_land')}</div>
        )}
        <div style={{ marginTop: 10, fontSize: 13 }}>
          {t('exp_valid_until')}: <strong>{fmtTime(pkg.manifest.valid_until)}</strong>
        </div>
      </Card>

      <Card title={`${t('exp_component')} / ${t('exp_expires')}`}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <tbody>
            {fresh.map((f) => (
              <tr key={f.key} style={{ borderTop: `1px solid ${colors.border}` }}>
                <td style={{ padding: '8px 0' }}>{compLabel[f.key]}</td>
                <td style={{ padding: '8px 0', color: colors.muted }}>{fmtTime(f.valid_until)}</td>
                <td style={{ padding: '8px 0', textAlign: 'right' }}><Badge color={levelColor[f.level]}>{f.level === 'UNAVAILABLE' ? t('exp_not_available') : formatRemaining(f.minutes_left)}</Badge></td>
              </tr>
            ))}
            <tr style={{ borderTop: `1px solid ${colors.border}` }}>
              <td style={{ padding: '8px 0' }}>{t('exp_charts')}</td>
              <td style={{ padding: '8px 0', color: colors.muted }} colSpan={2}>{pkg.offline_assets.nautical_charts.note}</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title={`${t('exp_download_assets')}`}>
        {assets.map(({ key, label, a }) => {
          const p = progress[key];
          const pct = p?.total ? Math.min(100, Math.round((p.loaded / p.total) * 100)) : null;
          return (
            <div key={key} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span>{label} <span style={{ color: colors.muted }}>({fmtBytes(a.size_bytes)})</span></span>
                <span>{!a.available ? <Badge color={colors.slate}>{t('exp_not_available')}</Badge> : p?.done ? <Badge color={colors.green}>{isMarathi ? 'पूर्ण' : 'Downloaded'}</Badge> : p?.error ? <Badge color={colors.red}>{p.error}</Badge> : pct !== null ? `${pct}%` : ''}</span>
              </div>
              {p && !p.done && (
                <div style={{ height: 6, background: 'var(--surface-sunken)', borderRadius: 3, marginTop: 4 }}>
                  <div style={{ height: 6, width: `${pct ?? 30}%`, background: colors.accent, borderRadius: 3 }} />
                </div>
              )}
              <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>{a.note}</div>
            </div>
          );
        })}
        {anyDownloadable ? (
          <Button variant="secondary" onClick={downloadAll} style={{ width: '100%' }}>{t('exp_download_assets')}</Button>
        ) : (
          <div style={{ fontSize: 12, color: colors.muted }}>
            {isMarathi ? 'सर्व्हरवर ऑफलाइन नकाशा फाइल नाही. मार्ग व क्षेत्रे ग्रिड पार्श्वभूमीवर दिसतील.' : 'No offline map file on the server yet. Route and zones will be drawn on a grid background.'}
          </div>
        )}
        {persisted === false && (
          <div style={{ fontSize: 11, color: colors.amber, marginTop: 8 }}>
            {isMarathi ? 'ब्राउझर कायमस्वरूपी साठवण नाकारली; जागा कमी असल्यास डेटा हटवला जाऊ शकतो.' : 'Browser declined persistent storage; data may be evicted under low disk space.'}
          </div>
        )}
      </Card>

      <Button onClick={onStart} style={{ width: '100%' }}>{t('exp_start')}</Button>
    </div>
  );
}
