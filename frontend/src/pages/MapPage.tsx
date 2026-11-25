/** Full marine map. Supports #/map?lat=..&lon=.. focus links from other pages. */

import { PageHeader } from '../components/ui';
import { MarineMap } from '../map/MarineMap';
import { useData } from '../lib/data';
import { useLang } from '../lib/lang';
import type { Location } from '../lib/router';
import { PageState, SafetyCallout } from './shared';

export function MapPage({ loc }: { loc: Location }) {
  return <PageState><Content loc={loc} /></PageState>;
}

function Content({ loc }: { loc: Location }) {
  const { summary, oceanLayers } = useData();
  const { mr, tr } = useLang();
  const lat = Number(loc.params.get('lat'));
  const lon = Number(loc.params.get('lon'));
  const focus = Number.isFinite(lat) && Number.isFinite(lon) && lat && lon ? { lat, lon, zoom: 9 } : null;

  return (
    <div className="stack">
      <PageHeader
        title={tr('Marine map', 'सागरी नकाशा')}
        description={tr('Select a grid cell or PFZ point for details, or toggle oceanographic layers', 'तपशीलासाठी ग्रिड क्षेत्र किंवा PFZ बिंदू निवडा, किंवा समुद्री स्तर पहा')}
      />
      <SafetyCallout />
      <MarineMap data={summary!} oceanLayers={oceanLayers} mr={mr} height="max(440px, calc(100vh - 300px))" focus={focus} />
    </div>
  );
}
