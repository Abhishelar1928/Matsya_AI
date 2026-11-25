/**
 * Download screen: manifest inspection, SHA-256 integrity verification,
 * storage quota checks, download cancellation/retry, package replacement,
 * and offline readiness verification before starting the voyage.
 */

import { useEffect, useRef, useState } from 'react';
import { downloadAsset } from '../services/expeditionApi';
import {
  deletePackage,
  getStorageEstimate,
  verifyPackageIntegrity,
  type PackageIntegrityResult,
  type StorageEstimateInfo,
} from '../services/expeditionDb';
import { packageFreshness, formatRemaining, type FreshnessLevel } from '../services/freshness';
import { Badge, Button, Card, colors, fmtTime } from './ExpeditionPrimitives';
import type { ExpeditionPackage } from '../types/expeditionTypes';
import { t } from '../../i18n';

interface Props {
  pkg: ExpeditionPackage;
  isMarathi: boolean;
  onStart: () => void;
  onReplace: () => void;
}

const levelColor: Record<FreshnessLevel, string> = {
  VALID: colors.green,
  EXPIRING: colors.amber,
  EXPIRED: colors.red,
  UNAVAILABLE: colors.slate,
};

function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n > 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

export function DownloadPackage({ pkg, isMarathi, onStart, onReplace }: Props) {
  const [progress, setProgress] = useState<
    Record<string, { loaded: number; total: number | null; done: boolean; cancelled?: boolean; error?: string }>
  >({});
  const [storage, setStorage] = useState<StorageEstimateInfo | null>(null);
  const [persisted, setPersisted] = useState<boolean | null>(null);
  const [integrity, setIntegrity] = useState<PackageIntegrityResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    void (async () => {
      if (navigator.storage?.persist) {
        try {
          setPersisted(await navigator.storage.persist());
        } catch {
          setPersisted(false);
        }
      }
      setStorage(await getStorageEstimate());
      setIntegrity(await verifyPackageIntegrity(pkg));
    })();
  }, [pkg]);

  const assets = [
    { key: 'basemap', label: t('exp_basemap'), a: pkg.offline_assets.basemap },
    { key: 'bathymetry', label: t('exp_bathymetry'), a: pkg.offline_assets.bathymetry },
  ];

  const downloadAll = async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    setDownloading(true);
    try {
      for (const { key, a } of assets) {
        if (!a.available || !a.url) continue;
        setProgress((p) => ({ ...p, [key]: { loaded: 0, total: a.size_bytes ?? null, done: false } }));
        try {
          await downloadAsset(
            a.url,
            (loaded, total) => setProgress((p) => ({ ...p, [key]: { loaded, total, done: false } })),
            controller.signal,
          );
          setProgress((p) => ({ ...p, [key]: { ...p[key], done: true } }));
        } catch (e) {
          const isAbort = e instanceof DOMException && e.name === 'AbortError';
          setProgress((p) => ({
            ...p,
            [key]: {
              ...p[key],
              done: false,
              cancelled: isAbort,
              error: isAbort ? (isMarathi ? 'रद्द केले' : 'Cancelled') : e instanceof Error ? e.message : String(e),
            },
          }));
          if (isAbort) break;
        }
      }
    } finally {
      abortRef.current = null;
      setDownloading(false);
      setStorage(await getStorageEstimate());
    }
  };

  const cancelDownload = () => {
    abortRef.current?.abort();
  };

  const handleDeleteReplace = async () => {
    const msg = isMarathi
      ? 'सध्याचे पॅकेज हटवून नवीन मोहीम नियोजित करायची? (नोंदवलेला डेटा सुरक्षित राहील.)'
      : 'Delete this offline package and plan a replacement? (Queued catches/tracks remain preserved.)';
    if (!window.confirm(msg)) return;
    await deletePackage(pkg.manifest.package_id);
    onReplace();
  };

  const fresh = packageFreshness(pkg);
  const anyDownloadable = assets.some(({ a }) => a.available);
  const hasAnyError = Object.values(progress).some((p) => p.error);

  const compLabel: Record<string, string> = {
    warnings: isMarathi ? 'IMD चेतावण्या' : 'IMD warnings',
    forecast: isMarathi ? 'लाटा / वारा अंदाज' : 'Wave & wind forecast',
    predictions: isMarathi ? 'AI अंदाज ग्रिड' : 'AI prediction grid',
    pfz: isMarathi ? 'INCOIS PFZ क्षेत्रे' : 'INCOIS PFZ zones',
  };

  const checklist = [
    {
      ok: true,
      label: isMarathi ? 'मोहीम पॅकेज IndexedDB मध्ये जतन' : 'Expedition package persisted in IndexedDB',
    },
    {
      ok: integrity?.status !== 'MISMATCH',
      label:
        integrity?.status === 'VERIFIED'
          ? isMarathi
            ? `अखंडता तपासणी पूर्ण (${integrity.checked.length} घटक)`
            : `SHA-256 integrity verified (${integrity.checked.length} sections)`
          : integrity?.status === 'MISMATCH'
            ? isMarathi
              ? 'चेकसम जुळत नाही — पॅकेज पुन्हा डाउनलोड करा'
              : 'Checksum mismatch — re-download recommended'
            : isMarathi
              ? 'चेकसम उपलब्ध नाही (आवृत्ती १ पॅकेज)'
              : 'No checksums in manifest (v1 fallback)',
    },
    {
      ok: fresh.some((f) => f.key === 'warnings' && f.level !== 'EXPIRED' && f.level !== 'UNAVAILABLE'),
      label: isMarathi ? 'सक्रिय IMD चेतावणी डेटा उपलब्ध' : 'Active IMD marine warning context present',
    },
    {
      ok: persisted === true,
      label:
        persisted === true
          ? isMarathi
            ? 'कायमस्वरूपी साठवण मंजूर'
            : 'Browser persistent storage granted'
          : isMarathi
            ? 'कायमस्वरूपी साठवण नाकारली (बॅकअप निर्यात करा)'
            : 'Persistent storage unconfirmed (export GPX/CSV backup after trip)',
    },
  ];

  return (
    <div>
      <Card title={t('exp_package_ready')}>
        <div style={{ fontSize: 14, marginBottom: 6 }}>
          <strong>{isMarathi ? pkg.landing_centre.name_mr : pkg.landing_centre.name}</strong> →{' '}
          <strong style={{ color: colors.accent }}>{pkg.destination.name}</strong>
        </div>
        <div style={{ fontSize: 13, color: colors.muted }}>
          {pkg.route.distance_km.toFixed(1)} km · {pkg.route.initial_bearing_deg}° {pkg.route.initial_bearing_compass} ·{' '}
          {pkg.route.waypoints.length} {t('exp_waypoint').toLowerCase()}s
        </div>
        {pkg.route.warnings.includes('ROUTE_CROSSES_LAND') && (
          <div style={{ marginTop: 8, color: colors.amber, fontWeight: 700, fontSize: 13 }}>{t('exp_route_crosses_land')}</div>
        )}
        <div style={{ marginTop: 10, fontSize: 12, color: colors.muted, display: 'grid', gap: 3 }}>
          <div>
            Schema v{pkg.manifest.schema_version} · {isMarathi ? 'निर्मिती' : 'Generated'}:{' '}
            <strong>{fmtTime(pkg.manifest.generated_at ?? pkg.manifest.created_at)}</strong>
          </div>
          <div>
            {t('exp_valid_until')}: <strong>{fmtTime(pkg.manifest.valid_until)}</strong>
          </div>
          {pkg.manifest.coverage && (
            <div>
              {isMarathi ? 'क्षेत्र' : 'Coverage'}: {pkg.manifest.coverage.min_lat}–{pkg.manifest.coverage.max_lat}°N,{' '}
              {pkg.manifest.coverage.min_lon}–{pkg.manifest.coverage.max_lon}°E
            </div>
          )}
        </div>
      </Card>

      <Card title={`${t('exp_component')} / ${t('exp_expires')}`}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <tbody>
            {fresh.map((f) => (
              <tr key={f.key} style={{ borderTop: `1px solid ${colors.border}` }}>
                <td style={{ padding: '8px 0' }}>{compLabel[f.key]}</td>
                <td style={{ padding: '8px 0', color: colors.muted }}>{fmtTime(f.valid_until)}</td>
                <td style={{ padding: '8px 0', textAlign: 'right' }}>
                  <Badge color={levelColor[f.level]}>
                    {f.level === 'UNAVAILABLE' ? t('exp_not_available') : formatRemaining(f.minutes_left)}
                  </Badge>
                </td>
              </tr>
            ))}
            <tr style={{ borderTop: `1px solid ${colors.border}` }}>
              <td style={{ padding: '8px 0' }}>{t('exp_charts')}</td>
              <td style={{ padding: '8px 0', color: colors.muted }} colSpan={2}>
                {pkg.offline_assets.nautical_charts.note}
              </td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title={t('exp_download_assets')}>
        {assets.map(({ key, label, a }) => {
          const p = progress[key];
          const pct = p?.total ? Math.min(100, Math.round((p.loaded / p.total) * 100)) : null;
          return (
            <div key={key} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span>
                  {label} <span style={{ color: colors.muted }}>({fmtBytes(a.size_bytes)})</span>
                </span>
                <span>
                  {!a.available ? (
                    <Badge color={colors.slate}>{t('exp_not_available')}</Badge>
                  ) : p?.done ? (
                    <Badge color={colors.green}>{isMarathi ? 'पूर्ण' : 'Downloaded'}</Badge>
                  ) : p?.error ? (
                    <Badge color={colors.red}>{p.error}</Badge>
                  ) : pct !== null ? (
                    `${pct}%`
                  ) : (
                    ''
                  )}
                </span>
              </div>
              {p && !p.done && !p.error && (
                <div style={{ height: 6, background: 'var(--surface-sunken)', borderRadius: 3, marginTop: 4 }}>
                  <div style={{ height: 6, width: `${pct ?? 30}%`, background: colors.accent, borderRadius: 3 }} />
                </div>
              )}
              <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>{a.note}</div>
            </div>
          );
        })}

        {anyDownloadable ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="secondary" onClick={downloadAll} disabled={downloading} style={{ flex: 1 }}>
              {hasAnyError ? (isMarathi ? 'पुन्हा प्रयत्न करा' : 'Retry download') : t('exp_download_assets')}
            </Button>
            {downloading && (
              <Button variant="danger" onClick={cancelDownload}>
                {isMarathi ? 'रद्द करा' : 'Cancel'}
              </Button>
            )}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: colors.muted }}>
            {isMarathi
              ? 'सर्व्हरवर ऑफलाइन नकाशा फाइल नाही. मार्ग व क्षेत्रे ग्रिड पार्श्वभूमीवर दिसतील.'
              : 'No offline map file on the server yet. Route and zones will be drawn on a calibrated coordinate grid.'}
          </div>
        )}

        {storage && storage.supported && (
          <div style={{ fontSize: 12, color: colors.muted, marginTop: 10 }}>
            {isMarathi ? 'डिव्हाइस साठवण' : 'Device storage'}: <strong>{fmtBytes(storage.usageBytes)}</strong> /{' '}
            {fmtBytes(storage.quotaBytes)}
            {storage.percentUsed !== null ? ` (${storage.percentUsed}%)` : ''}
          </div>
        )}
        {persisted === false && (
          <div style={{ fontSize: 11, color: colors.amber, marginTop: 6 }}>
            {isMarathi
              ? 'ब्राउझरने कायमस्वरूपी साठवण नाकारली; जागा कमी असल्यास ऑफलाइन डेटा हटवला जाऊ शकतो.'
              : 'Browser declined persistent storage; cached data is not permanent and may be evicted under low disk space.'}
          </div>
        )}
      </Card>

      <Card title={isMarathi ? 'ऑफलाइन तयारी तपासणी' : 'Offline Readiness Check'}>
        <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
          {checklist.map((item) => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Badge color={item.ok ? colors.green : colors.amber}>{item.ok ? 'OK' : 'NOTE'}</Badge>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Button onClick={onStart} disabled={integrity?.status === 'MISMATCH'} style={{ flex: 2 }}>
          {t('exp_start')}
        </Button>
        <Button variant="secondary" onClick={handleDeleteReplace} style={{ flex: 1 }}>
          {isMarathi ? 'पॅकेज बदला' : 'Delete / Replace'}
        </Button>
      </div>
    </div>
  );
}
