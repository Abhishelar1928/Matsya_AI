/**
 * Data source freshness list — one row per upstream source with status,
 * data timestamp and age. (Name kept for backwards compatibility.)
 */

import type { SourceFreshness, SourceFreshnessState } from '../types/map';
import { freshnessMeta } from '../lib/status';
import { fmtDateTime } from '../lib/format';
import { StatusBadge } from './ui';

const SOURCES: { key: keyof SourceFreshness; name: [string, string]; detail: [string, string] }[] = [
  { key: 'imd_marine_warnings', name: ['IMD marine warnings', 'IMD सागरी चेतावणी'], detail: ['Mumbai fishermen bulletin', 'मुंबई मच्छीमार बुलेटिन'] },
  { key: 'incois_pfz', name: ['INCOIS PFZ advisory', 'INCOIS PFZ सल्ला'], detail: ['Potential fishing zones', 'संभाव्य मासेमारी क्षेत्रे'] },
  { key: 'open_meteo_marine', name: ['Open-Meteo marine', 'Open-Meteo सागरी'], detail: ['Waves & wind observations', 'लाटा व वारा निरीक्षण'] },
  { key: 'global_fishing_watch', name: ['Global Fishing Watch', 'Global Fishing Watch'], detail: ['Historical vessel activity', 'ऐतिहासिक नौका हालचाल'] },
];

function age(s: SourceFreshnessState, mr: boolean): string {
  if (s.age_days != null) return mr ? `${s.age_days} दिवसांपूर्वी` : `${s.age_days} d old`;
  if (s.age_minutes == null) return '';
  const m = Math.round(s.age_minutes);
  if (m < 60) return mr ? `${m} मिनिटे` : `${m} min old`;
  const h = Math.round(m / 60);
  return mr ? `${h} तास` : h < 48 ? `${h} h old` : `${Math.round(h / 24)} d old`;
}

export function FreshnessHUD({ freshness, isMarathi }: { freshness: SourceFreshness; isMarathi: boolean }) {
  const mr = isMarathi;
  return (
    <ul className="list">
      {SOURCES.map(({ key, name, detail }) => {
        const s = freshness[key];
        if (!s) return null;
        return (
          <li key={key} className="list-row">
            <div className="list-row-main">
              <div className="list-row-title">{name[mr ? 1 : 0]}</div>
              <div className="list-row-sub">
                {detail[mr ? 1 : 0]}
                {s.data_timestamp && <> · <span className="num">{fmtDateTime(s.data_timestamp)}</span></>}
                {age(s, mr) && <> · {age(s, mr)}</>}
              </div>
            </div>
            <StatusBadge meta={freshnessMeta(s.status)} mr={mr} />
          </li>
        );
      })}
    </ul>
  );
}

export default FreshnessHUD;
