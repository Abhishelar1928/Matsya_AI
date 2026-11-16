/**
 * Status vocabulary. Status colours are reserved and always ship with an icon
 * and a text label — never colour alone. NO_WARNING_DATA is never green.
 */

import {
  AlertTriangle, CheckCircle2, CircleSlash, Clock, OctagonAlert, ShieldAlert, ShieldCheck, ShieldQuestion,
  type LucideIcon,
} from 'lucide-react';

export type Tone = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

export interface StatusMeta {
  tone: Tone;
  icon: LucideIcon;
  label: [string, string];
  short: [string, string];
  description: [string, string];
}

export const SAFETY: Record<string, StatusMeta> = {
  UNSAFE: {
    tone: 'danger', icon: OctagonAlert,
    label: ['Unsafe — do not venture out', 'असुरक्षित — समुद्रात जाऊ नका'],
    short: ['Unsafe', 'असुरक्षित'],
    description: ['An active severe marine warning is in force.', 'तीव्र सागरी चेतावणी लागू आहे.'],
  },
  CAUTION: {
    tone: 'warning', icon: ShieldAlert,
    label: ['Caution advised', 'सावधानता बाळगा'],
    short: ['Caution', 'सावधान'],
    description: ['Rough sea or strong wind in parts of the coast.', 'किनाऱ्याच्या काही भागांत खवळलेला समुद्र किंवा जोरदार वारा.'],
  },
  SAFE_CONFIRMED: {
    tone: 'success', icon: ShieldCheck,
    label: ['Normal conditions confirmed', 'सामान्य परिस्थितीची पुष्टी'],
    short: ['Normal', 'सामान्य'],
    description: ['An active official bulletin confirms normal sea conditions.', 'सक्रिय अधिकृत बुलेटिन सामान्य परिस्थितीची पुष्टी करते.'],
  },
  NO_WARNING_DATA: {
    tone: 'neutral', icon: ShieldQuestion,
    label: ['Safety not confirmed', 'सुरक्षिततेची पुष्टी नाही'],
    short: ['Unconfirmed', 'अपुष्ट'],
    description: ['Official warning data is missing or outdated. Check port signals before sailing.', 'अधिकृत चेतावणी माहिती उपलब्ध नाही किंवा जुनी आहे. निघण्यापूर्वी बंदर सिग्नल तपासा.'],
  },
};

export function safetyMeta(status: string | null | undefined): StatusMeta {
  return SAFETY[status ?? ''] ?? SAFETY.NO_WARNING_DATA;
}

export const FRESHNESS: Record<string, StatusMeta> = {
  LIVE: { tone: 'success', icon: CheckCircle2, label: ['Current', 'वर्तमान'], short: ['Live', 'थेट'], description: ['', ''] },
  STALE: { tone: 'warning', icon: Clock, label: ['Outdated', 'जुना'], short: ['Stale', 'जुना'], description: ['', ''] },
  CACHED_HISTORICAL: { tone: 'warning', icon: Clock, label: ['Historical', 'ऐतिहासिक'], short: ['Historical', 'ऐतिहासिक'], description: ['', ''] },
  DEMO_HISTORICAL: { tone: 'info', icon: Clock, label: ['Demo data', 'डेमो डेटा'], short: ['Demo', 'डेमो'], description: ['', ''] },
  ERROR: { tone: 'danger', icon: AlertTriangle, label: ['Source error', 'स्रोत त्रुटी'], short: ['Error', 'त्रुटी'], description: ['', ''] },
  UNAVAILABLE: { tone: 'neutral', icon: CircleSlash, label: ['Unavailable', 'अनुपलब्ध'], short: ['Unavailable', 'अनुपलब्ध'], description: ['', ''] },
};

export function freshnessMeta(status: string | null | undefined): StatusMeta {
  return FRESHNESS[status ?? ''] ?? FRESHNESS.UNAVAILABLE;
}

/** IMD severity → tone (mirrors backend SafetyGate severity buckets). */
export function severityTone(severity: string): Tone {
  const s = severity.toUpperCase();
  if (['SEVERE', 'VERY_SEVERE', 'EXTREMELY_SEVERE'].includes(s)) return 'danger';
  if (['MODERATE', 'CAUTION', 'WARNING', 'ROUGH_SEA'].includes(s)) return 'warning';
  if (['NONE', 'NORMAL', 'NIL', 'ALL_CLEAR', 'SAFE'].includes(s)) return 'success';
  return 'neutral';
}

export function humanize(code: string): string {
  return code.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
