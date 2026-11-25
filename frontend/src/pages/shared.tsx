/** Page-level building blocks shared across sections. */

import { AlertTriangle, ArrowRight, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button, Callout, Card, LinkButton, Skeleton } from '../components/ui';
import { useData } from '../lib/data';
import { useLang } from '../lib/lang';
import { fmtDateTime } from '../lib/format';
import { href } from '../lib/router';
import { safetyMeta } from '../lib/status';

export function SafetyCallout({ withLink = true }: { withLink?: boolean }) {
  const { summary, warnings } = useData();
  const { mr, tr } = useLang();
  if (!summary) return null;
  const meta = safetyMeta(summary.marine_safety.overall_status);
  return (
    <Callout
      tone={meta.tone}
      icon={meta.icon}
      title={meta.label[mr ? 1 : 0]}
      meta={
        <>
          <span>{tr('Source', 'स्रोत')}: {summary.marine_safety.authority}</span>
          {warnings?.issued_at && <span>{tr('Bulletin issued', 'बुलेटिन जारी')} {fmtDateTime(warnings.issued_at)}</span>}
          {warnings?.valid_until && <span>{tr('Valid until', 'वैध')} {fmtDateTime(warnings.valid_until)}</span>}
          <span>{tr('Determined independently of the AI model', 'AI मॉडेलपासून स्वतंत्रपणे ठरवलेले')}</span>
        </>
      }
      action={withLink ? <LinkButton href={href('safety')} size="sm" icon={ArrowRight}>{tr('Details', 'तपशील')}</LinkButton> : undefined}
    >
      {mr ? meta.description[1] : summary.marine_safety.message || meta.description[0]}
    </Callout>
  );
}

export function PageState({ children }: { children: ReactNode }) {
  const { summary, loading, error, refresh } = useData();
  const { tr } = useLang();
  if (summary) return <>{children}</>;
  if (loading) {
    return (
      <div className="stack" aria-busy="true">
        <Skeleton height={72} />
        <div className="grid-kpi">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={104} />)}</div>
        <Skeleton height={420} />
      </div>
    );
  }
  return (
    <Card>
      <div className="empty">
        <AlertTriangle aria-hidden />
        <div className="empty-title">{tr('Could not load marine data', 'सागरी डेटा लोड झाला नाही')}</div>
        <div>{error}</div>
        <div className="page-actions" style={{ marginTop: 8 }}>
          <Button variant="primary" icon={RefreshCw} onClick={refresh}>{tr('Try again', 'पुन्हा प्रयत्न करा')}</Button>
        </div>
      </div>
    </Card>
  );
}

export function Disclaimer() {
  const { tr } = useLang();
  return (
    <footer className="app-footer">
      <span>
        <strong className="text-secondary fw-500">{tr('Predicted activity', 'अपेक्षित हालचाल')}:</strong>{' '}
        {tr(
          'derived from historical Global Fishing Watch vessel tracking. It does not predict fish presence, biomass or catch.',
          'Global Fishing Watch च्या ऐतिहासिक नौका हालचालींवरून काढलेली. माशांची उपस्थिती, प्रमाण किंवा पकड यांचा अंदाज नाही.',
        )}
      </span>
      <span>
        <strong className="text-secondary fw-500">{tr('Marine safety', 'सागरी सुरक्षा')}:</strong>{' '}
        {tr(
          'determined only from official IMD/INCOIS warnings and forecast thresholds — never by the AI model. Missing or expired data is never shown as safe.',
          'केवळ अधिकृत IMD/INCOIS चेतावण्या व अंदाज मर्यादांवरून ठरवली जाते — AI मॉडेलद्वारे कधीही नाही. अनुपलब्ध किंवा कालबाह्य डेटा कधीही सुरक्षित दाखवला जात नाही.',
        )}
      </span>
    </footer>
  );
}
