/** Navigation — route planning and the Offline Expedition workflow. */

import { PageHeader } from '../components/ui';
import { ExpeditionMode } from '../expedition/ExpeditionMode';
import { useData } from '../lib/data';
import { useLang } from '../lib/lang';
import type { Location } from '../lib/router';

export function Navigation({ loc }: { loc: Location }) {
  const { summary } = useData();
  const { mr, tr } = useLang();
  const pfzParam = loc.params.get('pfz');
  const lat = Number(loc.params.get('lat'));
  const lon = Number(loc.params.get('lon'));
  const pfzIndex = pfzParam !== null && Number.isInteger(Number(pfzParam)) ? Number(pfzParam) : null;
  const destination = lat && lon && Number.isFinite(lat) && Number.isFinite(lon) ? { latitude: lat, longitude: lon } : null;

  return (
    <div>
      <PageHeader
        title={tr('Navigation', 'मार्गदर्शन')}
        description={tr(
          'Plan a route while you have signal, download it, then navigate offline with device GPS.',
          'सिग्नल असताना मार्ग ठरवा, डाउनलोड करा, आणि नंतर उपकरणाच्या GPS ने ऑफलाइन मार्गक्रमण करा.',
        )}
      />
      <ExpeditionMode
        key={`${pfzIndex}-${destination?.latitude}-${destination?.longitude}`}
        isMarathi={mr}
        pfz={summary?.pfz_advisory ?? null}
        initialPfzIndex={pfzIndex}
        initialDestination={destination}
      />
    </div>
  );
}
