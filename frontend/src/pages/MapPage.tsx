/** Full marine map. Supports #/map?lat=..&lon=.. focus links from other pages. */

import { Segmented, PageHeader } from '../components/ui';
import { MarineMap } from '../map/MarineMap';
import { useData } from '../lib/data';
import { useLang } from '../lib/lang';
import type { Location } from '../lib/router';
import { PageState, SafetyCallout } from './shared';

export function MapPage({ loc }: { loc: Location }) {
  return <PageState><Content loc={loc} /></PageState>;
}

function Content({ loc }: { loc: Location }) {
  const { summary, demo, setDemo } = useData();
  const { mr, tr } = useLang();
  const lat = Number(loc.params.get('lat'));
  const lon = Number(loc.params.get('lon'));
  const focus = Number.isFinite(lat) && Number.isFinite(lon) && lat && lon ? { lat, lon, zoom: 9 } : null;

  return (
    <div className="stack">
      <PageHeader
        title={tr('Marine map', 'सागरी नकाशा')}
        description={tr('Select a grid cell or PFZ point for details', 'तपशीलासाठी ग्रिड क्षेत्र किंवा PFZ बिंदू निवडा')}
        actions={
          <Segmented<'live' | 'demo'>
            label={tr('Data mode', 'डेटा मोड')}
            value={demo ? 'demo' : 'live'}
            onChange={(v) => setDemo(v === 'demo')}
            options={[{ value: 'live', label: tr('Live', 'थेट') }, { value: 'demo', label: tr('Demo', 'डेमो') }]}
          />
        }
      />
      <SafetyCallout />
      <MarineMap data={summary!} mr={mr} height="max(440px, calc(100vh - 300px))" focus={focus} />
    </div>
  );
}
