/**
 * Catch log: offline catch form backed by approved Maharashtra species catalogue,
 * optional quantity / duration / market value, and historical voyage summary
 * computed strictly from real persisted IndexedDB records.
 */

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { addCatch, listAllCatches, listCatches, newUuid } from '../services/expeditionDb';
import { MAHARASHTRA_SPECIES, type SpeciesEntry } from '../services/speciesCatalogue';
import { Badge, Button, Card, colors } from './ExpeditionPrimitives';
import type { CatchRecord } from '../types/expeditionTypes';
import type { Fix } from '../hooks/useGeolocation';
import { t } from '../../i18n';

interface Props {
  expeditionId: string;
  isMarathi: boolean;
  fix: Fix | null;
  catalogue?: SpeciesEntry[];
  onBack: () => void;
}

export function CatchLog({ expeditionId, isMarathi, fix, catalogue, onBack }: Props) {
  const speciesList = catalogue && catalogue.length > 0 ? catalogue : MAHARASHTRA_SPECIES;
  const [speciesId, setSpeciesId] = useState(speciesList[0].id);
  const [weight, setWeight] = useState('');
  const [quantity, setQuantity] = useState('');
  const [durationMin, setDurationMin] = useState('');
  const [valueInr, setValueInr] = useState('');
  const [notes, setNotes] = useState('');
  const [rows, setRows] = useState<CatchRecord[]>([]);
  const [allRows, setAllRows] = useState<CatchRecord[]>([]);
  const [saved, setSaved] = useState(false);

  const reload = async () => {
    const [cur, all] = await Promise.all([listCatches(expeditionId), listAllCatches()]);
    setRows(cur);
    setAllRows(all);
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expeditionId]);

  const selectedSpecies = speciesList.find((s) => s.id === speciesId) ?? speciesList[0];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await addCatch({
      client_uuid: newUuid(),
      expedition_id: expeditionId,
      recorded_at: new Date().toISOString(),
      latitude: fix?.latitude ?? null,
      longitude: fix?.longitude ?? null,
      species: selectedSpecies.en,
      species_id: selectedSpecies.id,
      weight_kg: weight ? Number(weight) : null,
      quantity: quantity ? Math.round(Number(quantity)) : null,
      fishing_duration_min: durationMin ? Math.round(Number(durationMin)) : null,
      estimated_value_inr: valueInr ? Number(valueInr) : null,
      notes: notes || null,
      synced: 0,
    });
    setWeight('');
    setQuantity('');
    setDurationMin('');
    setValueInr('');
    setNotes('');
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    await reload();
  };

  const summary = useMemo(() => {
    const curKg = rows.reduce((sum, r) => sum + (r.weight_kg ?? 0), 0);
    const curVal = rows.reduce((sum, r) => sum + (r.estimated_value_inr ?? 0), 0);
    const syncedAll = allRows.filter((r) => r.synced === 1);
    const bySpecies = new Map<string, { kg: number; count: number }>();
    for (const r of allRows) {
      const prev = bySpecies.get(r.species) ?? { kg: 0, count: 0 };
      bySpecies.set(r.species, { kg: prev.kg + (r.weight_kg ?? 0), count: prev.count + 1 });
    }
    const topSpecies = [...bySpecies.entries()]
      .sort((a, b) => b[1].kg - a[1].kg || b[1].count - a[1].count)
      .slice(0, 4);
    return {
      curCount: rows.length,
      curKg,
      curVal,
      gpsTaggedCur: rows.filter((r) => r.latitude !== null && r.longitude !== null).length,
      allCount: allRows.length,
      syncedCount: syncedAll.length,
      topSpecies,
    };
  }, [rows, allRows]);

  return (
    <div>
      <Card title={t('exp_log_catch')}>
        <form onSubmit={submit}>
          <label className="field-label" style={{ display: 'block', marginBottom: 6 }}>
            {t('exp_species')}
          </label>
          <select
            value={speciesId}
            onChange={(e) => setSpeciesId(e.target.value)}
            className="select"
            style={{ marginBottom: 10 }}
          >
            {speciesList.map((s) => (
              <option key={s.id} value={s.id}>
                {isMarathi ? `${s.mr} (${s.en})` : `${s.en} — ${s.mr}`}
              </option>
            ))}
          </select>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 10 }}>
            <div>
              <label className="field-label" style={{ display: 'block', marginBottom: 4 }}>{t('exp_weight')}</label>
              <input type="number" inputMode="decimal" min="0" step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)} className="input" />
            </div>
            <div>
              <label className="field-label" style={{ display: 'block', marginBottom: 4 }}>{isMarathi ? 'संख्या (नग)' : 'Quantity (pcs)'}</label>
              <input type="number" inputMode="numeric" min="0" step="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} className="input" />
            </div>
            <div>
              <label className="field-label" style={{ display: 'block', marginBottom: 4 }}>{isMarathi ? 'कालावधी (मिनिटे)' : 'Duration (min)'}</label>
              <input type="number" inputMode="numeric" min="0" step="1" value={durationMin} onChange={(e) => setDurationMin(e.target.value)} className="input" />
            </div>
            <div>
              <label className="field-label" style={{ display: 'block', marginBottom: 4 }}>{isMarathi ? 'अंदाजे मूल्य (₹)' : 'Est. value (₹)'}</label>
              <input type="number" inputMode="decimal" min="0" step="10" value={valueInr} onChange={(e) => setValueInr(e.target.value)} className="input" />
            </div>
          </div>

          <label className="field-label" style={{ display: 'block', marginBottom: 6 }}>{t('exp_notes')}</label>
          <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} className="input" style={{ marginBottom: 10 }} />

          <div style={{ fontSize: 12, color: colors.muted, marginBottom: 10 }}>
            {fix ? `${fix.latitude.toFixed(4)}°N, ${fix.longitude.toFixed(4)}°E` : t('exp_waiting_gps')} ·{' '}
            {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Button type="submit" style={{ flex: 1 }}>
              {saved ? (isMarathi ? 'जतन झाले' : 'Saved') : t('exp_save')}
            </Button>
            <Button variant="secondary" onClick={onBack}>
              {t('exp_at_sea')}
            </Button>
          </div>
        </form>
      </Card>

      {/* Real Device Voyage & Historical Catch Summary */}
      <Card title={isMarathi ? 'पकड सारांश (वास्तविक नोंदींवरून)' : 'Voyage & Catch Summary (Recorded Data Only)'}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, fontSize: 13 }}>
          <div>
            <div style={{ fontSize: 11, color: colors.muted }}>{isMarathi ? 'या मोहिमेतील वजन' : 'This trip total'}</div>
            <div className="num" style={{ fontSize: 18, fontWeight: 700 }}>{summary.curKg.toFixed(1)} kg</div>
            <div style={{ fontSize: 11, color: colors.muted }}>
              {summary.curCount} {isMarathi ? 'नोंदी' : 'entries'} ({summary.gpsTaggedCur} GPS-tagged)
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: colors.muted }}>{isMarathi ? 'अंदाजे मूल्य' : 'Recorded value'}</div>
            <div className="num" style={{ fontSize: 18, fontWeight: 700 }}>₹{summary.curVal.toLocaleString('en-IN')}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: colors.muted }}>{isMarathi ? 'सर्व स्थानिक नोंदी' : 'All device catches'}</div>
            <div className="num" style={{ fontSize: 18, fontWeight: 700 }}>{summary.allCount}</div>
            <div style={{ fontSize: 11, color: colors.muted }}>{summary.syncedCount} synced</div>
          </div>
        </div>
        {summary.topSpecies.length > 0 && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${colors.border}`, fontSize: 12 }}>
            <div style={{ color: colors.muted, marginBottom: 4 }}>{isMarathi ? 'प्रमुख जाती (नोंदवलेल्या)' : 'Species breakdown (recorded)'}:</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {summary.topSpecies.map(([sp, st]) => (
                <Badge key={sp} color={colors.accent}>
                  {sp}: {st.kg.toFixed(1)} kg ({st.count})
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>

      {rows.length > 0 && (
        <Card title={`${rows.length} ${isMarathi ? 'नोंदी' : 'records'}`}>
          {rows.map((r) => (
            <div
              key={r.client_uuid}
              style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderTop: `1px solid ${colors.border}`, fontSize: 13, gap: 8 }}
            >
              <span>
                <strong>{r.species}</strong>
                {r.weight_kg !== null ? ` · ${r.weight_kg} kg` : ''}
                {r.quantity ? ` · ${r.quantity} pcs` : ''}
                {r.estimated_value_inr ? ` · ₹${r.estimated_value_inr}` : ''}
                {r.notes ? ` · ${r.notes}` : ''}
              </span>
              <span style={{ color: colors.muted, whiteSpace: 'nowrap' }}>
                {new Date(r.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{' '}
                <Badge color={r.synced ? colors.green : colors.amber}>{r.synced ? 'synced' : 'pending'}</Badge>
              </span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
