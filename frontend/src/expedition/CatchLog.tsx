/**
 * Catch log: quick offline form (species, weight, notes) with GPS + time auto-filled.
 */

import { useEffect, useState, type FormEvent } from 'react';
import { addCatch, listCatches, newUuid } from './db';
import { Badge, Button, Card, colors } from './ui';
import type { CatchRecord } from './types';
import type { Fix } from './useGeolocation';
import { t } from '../i18n';

interface Props {
  expeditionId: string;
  isMarathi: boolean;
  fix: Fix | null;
  onBack: () => void;
}

const SPECIES: { en: string; mr: string }[] = [
  { en: 'Pomfret', mr: 'पापलेट' },
  { en: 'Bombay duck', mr: 'बोंबील' },
  { en: 'Mackerel', mr: 'बांगडा' },
  { en: 'Sardine', mr: 'तारली' },
  { en: 'Prawn', mr: 'कोळंबी' },
  { en: 'Surmai (Seer fish)', mr: 'सुरमई' },
  { en: 'Rawas (Indian salmon)', mr: 'रावस' },
  { en: 'Squid', mr: 'माकूळ' },
  { en: 'Tuna', mr: 'कुपा' },
  { en: 'Other', mr: 'इतर' },
];

export function CatchLog({ expeditionId, isMarathi, fix, onBack }: Props) {
  const [species, setSpecies] = useState(SPECIES[0].en);
  const [weight, setWeight] = useState('');
  const [notes, setNotes] = useState('');
  const [rows, setRows] = useState<CatchRecord[]>([]);
  const [saved, setSaved] = useState(false);

  const reload = () => listCatches(expeditionId).then(setRows);
  useEffect(() => { void reload(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [expeditionId]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await addCatch({
      client_uuid: newUuid(),
      expedition_id: expeditionId,
      recorded_at: new Date().toISOString(),
      latitude: fix?.latitude ?? null,
      longitude: fix?.longitude ?? null,
      species,
      weight_kg: weight ? Number(weight) : null,
      notes: notes || null,
      synced: 0,
    });
    setWeight('');
    setNotes('');
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    await reload();
  };

  return (
    <div>
      <Card title={`${t('exp_log_catch')}`}>
        <form onSubmit={submit}>
          <label className="field-label" style={{ display: 'block', marginBottom: 6 }}>{t('exp_species')}</label>
          <select value={species} onChange={(e) => setSpecies(e.target.value)} className="input" style={{ marginBottom: 10 }}>
            {SPECIES.map((s) => <option key={s.en} value={s.en}>{isMarathi ? `${s.mr} (${s.en})` : s.en}</option>)}
          </select>
          <label className="field-label" style={{ display: 'block', marginBottom: 6 }}>{t('exp_weight')}</label>
          <input type="number" inputMode="decimal" min="0" step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)} className="input" style={{ marginBottom: 10 }} />
          <label className="field-label" style={{ display: 'block', marginBottom: 6 }}>{t('exp_notes')}</label>
          <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} className="input" style={{ marginBottom: 10 }} />
          <div style={{ fontSize: 12, color: colors.muted, marginBottom: 10 }}>
            {fix ? `${fix.latitude.toFixed(4)}°N, ${fix.longitude.toFixed(4)}°E` : t('exp_waiting_gps')} · {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Button type="submit" style={{ flex: 1 }}>{saved ? (isMarathi ? 'जतन झाले' : 'Saved') : t('exp_save')}</Button>
            <Button variant="secondary" onClick={onBack}>{t('exp_at_sea')}</Button>
          </div>
        </form>
      </Card>

      {rows.length > 0 && (
        <Card title={`${rows.length} ${isMarathi ? 'नोंदी' : 'records'}`}>
          {rows.map((r) => (
            <div key={r.client_uuid} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: `1px solid ${colors.border}`, fontSize: 13 }}>
              <span><strong>{r.species}</strong>{r.weight_kg !== null ? ` · ${r.weight_kg} kg` : ''}{r.notes ? ` · ${r.notes}` : ''}</span>
              <span style={{ color: colors.muted }}>{new Date(r.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} <Badge color={r.synced ? colors.green : colors.amber}>{r.synced ? 'synced' : 'pending'}</Badge></span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
