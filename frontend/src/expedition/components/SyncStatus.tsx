/**
 * Sync status: pending / uploaded / failed counts, last sync result,
 * manual retry button, and honest background-sync capability disclosure.
 */

import { useEffect, useState } from 'react';
import { getOutbox, recordCounts } from '../services/expeditionDb';
import { syncExpedition, type SyncResult } from '../services/expeditionSync';
import { Badge, Button, Card, colors, fmtTime } from './ExpeditionPrimitives';
import { t } from '../../i18n';

interface Props {
  expeditionId: string;
  isMarathi?: boolean;
  online: boolean;
  lastResult: SyncResult | null;
  lastSyncAt: string | null;
  onSynced: (r: SyncResult) => void;
}

export function SyncStatus({ expeditionId, isMarathi = false, online, lastResult, lastSyncAt, onSynced }: Props) {
  const [pendingDetail, setPendingDetail] = useState({ track_points: 0, catches: 0, observations: 0 });
  const [counts, setCounts] = useState({ pending: 0, uploaded: 0, failed: 0 });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const [o, c] = await Promise.all([getOutbox(expeditionId), recordCounts(expeditionId)]);
    setPendingDetail({
      track_points: o.track_points.length,
      catches: o.catches.length,
      observations: o.observations.length,
    });
    setCounts(c);
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expeditionId, lastResult]);

  const run = async () => {
    setBusy(true);
    const r = await syncExpedition(expeditionId);
    onSynced(r);
    await refresh();
    setBusy(false);
  };

  const bgSyncSupported =
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof ServiceWorkerRegistration !== 'undefined' &&
    'sync' in ServiceWorkerRegistration.prototype;

  return (
    <Card title={t('exp_sync')}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <Badge color={online ? colors.green : colors.slate}>{online ? t('exp_online') : t('exp_offline')}</Badge>
        <Badge color={counts.pending > 0 ? colors.amber : colors.green}>
          {isMarathi ? 'प्रलंबित' : 'Pending'}: {counts.pending}
        </Badge>
        <Badge color={colors.accent}>
          {isMarathi ? 'अपलोड झाले' : 'Uploaded'}: {counts.uploaded}
        </Badge>
        {counts.failed > 0 && (
          <Badge color={colors.red}>
            {isMarathi ? 'अयशस्वी' : 'Failed'}: {counts.failed}
          </Badge>
        )}
      </div>

      <div style={{ fontSize: 13, marginBottom: 8 }}>
        {t('exp_pending')}: <strong>{counts.pending}</strong>{' '}
        <span style={{ color: colors.muted }}>
          ({pendingDetail.track_points} track · {pendingDetail.catches} catch · {pendingDetail.observations} obs)
        </span>
      </div>

      <div style={{ fontSize: 13, color: colors.muted, marginBottom: 12 }}>
        {t('exp_last_sync')}: {lastSyncAt ? fmtTime(lastSyncAt) : t('exp_never')}
        {lastResult &&
          (lastResult.ok ? (
            <span style={{ color: colors.green }}>
              {' '}
              · {lastResult.uploaded} uploaded
              {lastResult.duplicates > 0 ? `, ${lastResult.duplicates} deduped` : ''}
              {lastResult.deltaApplied ? ', forecasts refreshed' : ''}
            </span>
          ) : (
            <span style={{ color: colors.red }}> · {lastResult.error}</span>
          ))}
      </div>

      <Button variant="secondary" onClick={run} disabled={!online || busy} style={{ width: '100%' }}>
        {busy
          ? t('loading')
          : counts.failed > 0
            ? isMarathi
              ? 'पुन्हा प्रयत्न करा (Retry)'
              : 'Retry failed upload'
            : t('exp_sync_now')}
      </Button>

      <div style={{ fontSize: 11, color: colors.muted, marginTop: 10, lineHeight: 1.5 }}>
        {isMarathi
          ? 'सर्व्हरकडून पुष्टी मिळेपर्यंत स्थानिक नोंदी सुरक्षित राहतात (डिलीट केल्या जात नाहीत).'
          : 'Locally queued records are never deleted before confirmed server acknowledgement.'}{' '}
        {bgSyncSupported
          ? isMarathi
            ? 'सिग्नल परत आल्यावर अ‍ॅप उघडल्यास किंवा पार्श्वभूमीत सिंक होईल.'
            : 'Best-effort background sync is available when online; keep app open if upload is urgent.'
          : isMarathi
            ? 'या ब्राउझरमध्ये पार्श्वभूमी सिंक समर्थित नाही; पोर्टवर आल्यावर अ‍ॅप उघडा.'
            : 'Background Sync API is not supported by this browser; open the app when back in signal to sync.'}
      </div>
    </Card>
  );
}
