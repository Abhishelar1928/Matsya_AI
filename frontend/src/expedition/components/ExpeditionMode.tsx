/**
 * MatsyaAI Maharashtra — Offline Expedition Mode container.
 *
 * Tabs: Plan → Download → At Sea → Catch Log → Sync.
 * Loads the active package from IndexedDB on start (works fully offline),
 * owns the GPS/compass watch while at sea or logging, and runs background sync.
 */

import { useEffect, useMemo, useState } from 'react';
import { deletePackage, getActivePackage, getActivePackageId, getPackage } from '../services/expeditionDb';
import { startAutoSync, type SyncResult } from '../services/expeditionSync';
import { useGeolocation, type SimulationRoute } from '../hooks/useGeolocation';
import type { SimulationScenario } from '../engine/simulation';
import { PlanExpedition } from './PlanExpedition';
import { DownloadPackage } from './DownloadPackage';
import { AtSea } from './AtSeaHud';
import { CatchLog } from './CatchLog';
import { SyncStatus } from './SyncStatus';
import { Button, Card, colors } from './ExpeditionPrimitives';
import { Segmented } from '../../components/ui';
import type { ExpeditionPackage } from '../types/expeditionTypes';
import type { PFZAdvisory } from '../../types/map';
import { t } from '../../i18n';

type Screen = 'plan' | 'download' | 'sea' | 'catch' | 'sync';

interface Props {
  isMarathi: boolean;
  pfz: PFZAdvisory | null;
  /** Pre-selected destination from another page (map cell / PFZ link). */
  initialPfzIndex?: number | null;
  initialDestination?: { latitude: number; longitude: number } | null;
  initialOrigin?: { latitude: number; longitude: number } | null;
}

export function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}

export function ExpeditionMode({ isMarathi, pfz, initialPfzIndex = null, initialDestination = null, initialOrigin = null }: Props) {
  const [pkg, setPkg] = useState<ExpeditionPackage | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [screen, setScreen] = useState<Screen>('plan');
  const [lastSync, setLastSync] = useState<SyncResult | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const online = useOnline();
  const [simulate, setSimulate] = useState(false);
  const [scenario, setScenario] = useState<SimulationScenario>('normal');

  const simRoute = useMemo<SimulationRoute | null>(
    () => (simulate && pkg ? { points: pkg.route.waypoints, speedKnots: 40, scenario } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [simulate, scenario, pkg?.manifest.package_id],
  );
  const geo = useGeolocation(screen === 'sea' || screen === 'catch', simRoute);

  // Restore active package (offline-safe)
  useEffect(() => {
    getActivePackage().then((p) => {
      setPkg(p);
      const preselected = initialPfzIndex !== null || initialDestination !== null;
      setScreen(p && !preselected ? 'sea' : 'plan');
      setLoaded(true);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Background sync
  useEffect(() => {
    if (!pkg) return;
    return startAutoSync(getActivePackageId, async (r) => {
      if (r.skippedConcurrent) return;
      setLastSync(r);
      setLastSyncAt(new Date().toISOString());
      if (r.deltaApplied) {
        const fresh = await getPackage(pkg.manifest.package_id);
        if (fresh) setPkg(fresh);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pkg?.manifest.package_id]);

  const endExpedition = async () => {
    if (!pkg) return;
    const msg = isMarathi
      ? 'मोहीम संपवायची? न पाठवलेला डेटा सिंक होईपर्यंत जतन राहील.'
      : 'End this expedition? Unsynced records stay saved until uploaded.';
    if (!window.confirm(msg)) return;
    await deletePackage(pkg.manifest.package_id);
    setPkg(null);
    setScreen('plan');
  };

  const tabs: { id: Screen; label: string; disabled?: boolean }[] = [
    { id: 'plan', label: t('exp_plan') },
    { id: 'download', label: t('exp_download'), disabled: !pkg },
    { id: 'sea', label: t('exp_at_sea'), disabled: !pkg },
    { id: 'catch', label: t('exp_catch'), disabled: !pkg },
    { id: 'sync', label: t('exp_sync'), disabled: !pkg },
  ];

  if (!loaded) return <div className="empty">{t('loading')}</div>;

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Segmented<Screen>
          label={t('exp_title')}
          value={screen}
          onChange={setScreen}
          options={tabs.map((tab) => ({ value: tab.id, label: tab.label, disabled: tab.disabled }))}
        />
      </div>

      {screen === 'plan' &&
        (online ? (
          <PlanExpedition
            isMarathi={isMarathi}
            pfz={pfz}
            initialPfzIndex={initialPfzIndex}
            initialDestination={initialDestination}
            initialOrigin={initialOrigin}
            onPackageReady={(p) => {
              setPkg(p);
              setScreen('download');
            }}
          />
        ) : (
          <Card>
            <div style={{ color: colors.amber, marginBottom: 4 }}>
              {t('exp_offline')} — {t('exp_no_package')}
            </div>
            {pkg && (
              <Button variant="secondary" onClick={() => setScreen('sea')} style={{ marginTop: 10 }}>
                {t('exp_at_sea')} →
              </Button>
            )}
          </Card>
        ))}
      {screen === 'download' && pkg && (
        <DownloadPackage
          pkg={pkg}
          isMarathi={isMarathi}
          onStart={() => setScreen('sea')}
          onReplace={() => {
            setPkg(null);
            setScreen('plan');
          }}
        />
      )}
      {screen === 'sea' && pkg && (
        <AtSea
          pkg={pkg}
          isMarathi={isMarathi}
          online={online}
          geo={geo}
          simulating={simulate}
          simulationScenario={scenario}
          onChangeScenario={setScenario}
          onToggleSimulation={() => setSimulate((s) => !s)}
          onLogCatch={() => setScreen('catch')}
          onEnd={endExpedition}
        />
      )}
      {screen === 'catch' && pkg && (
        <CatchLog
          expeditionId={pkg.manifest.package_id}
          isMarathi={isMarathi}
          fix={geo.fix?.simulated ? null : geo.fix}
          catalogue={pkg.species_catalogue}
          onBack={() => setScreen('sea')}
        />
      )}
      {screen === 'sync' && pkg && (
        <SyncStatus
          expeditionId={pkg.manifest.package_id}
          isMarathi={isMarathi}
          online={online}
          lastResult={lastSync}
          lastSyncAt={lastSyncAt}
          onSynced={async (r) => {
            setLastSync(r);
            setLastSyncAt(new Date().toISOString());
            if (r.deltaApplied) {
              const f = await getPackage(pkg.manifest.package_id);
              if (f) setPkg(f);
            }
          }}
        />
      )}
    </div>
  );
}
