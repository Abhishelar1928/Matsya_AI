/**
 * Sync status: pending counts, last sync result, manual sync button.
 */

import { useEffect, useState } from 'react';
import { getOutbox } from './db';
import { syncExpedition, type SyncResult } from './sync';
import { Badge, Button, Card, colors, fmtTime } from './ui';
import { t } from '../i18n';

interface Props {
  expeditionId: string;
  online: boolean;
  lastResult: SyncResult | null;
  lastSyncAt: string | null;
  onSynced: (r: SyncResult) => void;
}

export function SyncStatus({ expeditionId, online, lastResult, lastSyncAt, onSynced }: Props) {
  const [pending, setPending] = useState({ track_points: 0, catches: 0, observations: 0 });
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const o = await getOutbox(expeditionId);
    setPending({ track_points: o.track_points.length, catches: o.catches.length, observations: o.observations.length });
  };
  useEffect(() => { void refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [expeditionId, lastResult]);

  const run = async () => {
    setBusy(true);
    const r = await syncExpedition(expeditionId);
    onSynced(r);
    await refresh();
    setBusy(false);
  };

  const total = pending.track_points + pending.catches + pending.observations;

  return (
    <Card title={t('exp_sync')}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <Badge color={online ? colors.green : colors.slate}>{online ? t('exp_online') : t('exp_offline')}</Badge>
        <span style={{ fontSize: 13 }}>{t('exp_pending')}: <strong>{total}</strong> <span style={{ color: colors.muted }}>({pending.track_points} track · {pending.catches} catch · {pending.observations} obs)</span></span>
      </div>
      <div style={{ fontSize: 13, color: colors.muted, marginBottom: 10 }}>
        {t('exp_last_sync')}: {lastSyncAt ? fmtTime(lastSyncAt) : t('exp_never')}
        {lastResult && (lastResult.ok
          ? <span style={{ color: colors.green }}> · {lastResult.uploaded} uploaded{lastResult.deltaApplied ? ', forecasts refreshed' : ''}</span>
          : <span style={{ color: colors.red }}> · {lastResult.error}</span>)}
      </div>
      <Button variant="secondary" onClick={run} disabled={!online || busy} style={{ width: '100%' }}>{busy ? t('loading') : t('exp_sync_now')}</Button>
    </Card>
  );
}
