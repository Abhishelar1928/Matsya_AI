import React from 'react';
import type { SourceFreshness, SourceFreshnessState } from '../types/map';

interface FreshnessHUDProps {
  freshness: SourceFreshness;
  isMarathi: boolean;
}

const getStatusDisplay = (state: SourceFreshnessState, isMarathi: boolean, isGFW = false) => {
  const { status, data_timestamp, age_days } = state;

  let label = '';
  let color = '#aaa';
  let dateText = '';

  if (isGFW) {
    if (status === 'CACHED_HISTORICAL') {
      label = isMarathi ? 'ऐतिहासिक डेटा' : 'Historical data';
      color = '#ffb300';
      if (age_days !== null && age_days !== undefined) {
        dateText = isMarathi ? `${age_days} दिवसांपूर्वीचा डेटा` : `Based on data from ${age_days} days ago`;
      }
    } else {
      label = isMarathi ? 'डेटा अनुपलब्ध' : 'Data unavailable';
      color = '#ff5252';
    }
  } else {
    switch (status) {
      case 'LIVE':
        label = isMarathi ? 'वर्तमान' : 'Current';
        color = '#00e676';
        break;
      case 'STALE':
        label = isMarathi ? 'डेटा जुना असू शकतो' : 'Data may be outdated';
        color = '#ffb300';
        break;
      case 'UNAVAILABLE':
        label = isMarathi ? 'डेटा अनुपलब्ध' : 'Data unavailable';
        color = '#ff5252';
        break;
      case 'ERROR':
        label = isMarathi ? 'स्रोत तात्पुरता अनुपलब्ध' : 'Source temporarily unavailable';
        color = '#ff5252';
        break;
      default:
        label = status;
        break;
    }

    if (data_timestamp) {
      const d = new Date(data_timestamp);
      dateText = `${isMarathi ? 'अद्यतनित:' : 'Updated:'} ${d.toLocaleDateString()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
    }
  }

  return { label, color, dateText };
};

const FreshnessCard: React.FC<{
  title: string;
  state: SourceFreshnessState;
  isMarathi: boolean;
  isGFW?: boolean;
}> = ({ title, state, isMarathi, isGFW }) => {
  const { label, color, dateText } = getStatusDisplay(state, isMarathi, isGFW);

  return (
    <div style={{
      background: 'rgba(15, 34, 61, 0.7)',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '8px',
      padding: '12px',
      flex: 1,
      minWidth: '200px'
    }}>
      <div style={{ fontSize: '11px', color: '#90caf9', textTransform: 'uppercase', fontWeight: 600, marginBottom: '6px' }}>
        {title}
      </div>
      <div style={{ fontSize: '12px', color: '#aaa', marginBottom: '4px' }}>
        {dateText || (isMarathi ? 'तारीख अनुपलब्ध' : 'Date unavailable')}
      </div>
      <div style={{ fontSize: '13px', fontWeight: 700, color: color }}>
        {label}
      </div>
    </div>
  );
};

export const FreshnessHUD: React.FC<FreshnessHUDProps> = ({ freshness, isMarathi }) => {
  if (!freshness) return null;

  return (
    <section style={{ marginBottom: '24px' }}>
      <h3 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 800, color: '#00e5ff' }}>
        📡 {isMarathi ? 'डेटा अद्यतन स्थिती' : 'DATA STATUS'}
      </h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
        <FreshnessCard 
          title="INCOIS PFZ" 
          state={freshness.incois_pfz} 
          isMarathi={isMarathi} 
        />
        <FreshnessCard 
          title="IMD Marine Warning" 
          state={freshness.imd_marine_warnings} 
          isMarathi={isMarathi} 
        />
        <FreshnessCard 
          title="Marine Conditions" 
          state={freshness.open_meteo_marine} 
          isMarathi={isMarathi} 
        />
        <FreshnessCard 
          title="Fishing Activity" 
          state={freshness.global_fishing_watch} 
          isMarathi={isMarathi} 
          isGFW={true}
        />
      </div>
    </section>
  );
};
