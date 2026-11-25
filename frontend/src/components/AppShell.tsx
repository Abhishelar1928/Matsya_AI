/**
 * Application shell: sidebar navigation (drawer on tablet/mobile), top bar with
 * data status + language toggle, and a bottom tab bar on phones.
 */

import { useEffect, useState, type ReactNode } from 'react';
import {
  CloudSun, Compass, Fish, Languages, LayoutDashboard, Map as MapIcon, MapPinned, Menu, RefreshCw, ShieldCheck, WifiOff,
  type LucideIcon,
} from 'lucide-react';
import { href, type RouteId } from '../lib/router';
import { useLang } from '../lib/lang';
import { useData } from '../lib/data';
import { fmtTime } from '../lib/format';
import { useOnline } from '../expedition/components/ExpeditionMode';
import { Badge, Button } from './ui';

interface NavItem { id: RouteId; icon: LucideIcon; label: [string, string]; mobile?: string }

const NAV: { section: [string, string]; items: NavItem[] }[] = [
  {
    section: ['Monitor', 'निरीक्षण'],
    items: [
      { id: 'overview', icon: LayoutDashboard, label: ['Overview', 'आढावा'] },
      { id: 'map', icon: MapIcon, label: ['Marine map', 'सागरी नकाशा'] },
      { id: 'zones', icon: Fish, label: ['Fishing zones', 'मासेमारी क्षेत्रे'] },
    ],
  },
  {
    section: ['Conditions', 'परिस्थिती'],
    items: [
      { id: 'safety', icon: ShieldCheck, label: ['Safety', 'सुरक्षा'] },
      { id: 'weather', icon: CloudSun, label: ['Weather', 'हवामान'] },
      { id: 'districts', icon: MapPinned, label: ['Districts', 'जिल्हे'] },
    ],
  },
  {
    section: ['At sea', 'समुद्रात'],
    items: [{ id: 'navigation', icon: Compass, label: ['Navigation', 'मार्गदर्शन'] }],
  },
];

const MOBILE: { id: RouteId; label: [string, string] }[] = [
  { id: 'overview', label: ['Overview', 'आढावा'] },
  { id: 'map', label: ['Map', 'नकाशा'] },
  { id: 'zones', label: ['Zones', 'क्षेत्रे'] },
  { id: 'safety', label: ['Safety', 'सुरक्षा'] },
  { id: 'navigation', label: ['Navigate', 'मार्ग'] },
];
const ALL = NAV.flatMap((s) => s.items);

export function AppShell({ route, children }: { route: RouteId; children: ReactNode }) {
  const { mr, toggle, tr } = useLang();
  const { summary, loading, refresh, lastUpdated } = useData();
  const online = useOnline();
  const [drawer, setDrawer] = useState(false);

  useEffect(() => { setDrawer(false); }, [route]);

  const current = ALL.find((i) => i.id === route);
  const dataStatus = summary?.metadata.data_freshness_status;

  return (
    <div className={`shell${drawer ? ' drawer-open' : ''}`}>
      <aside className="sidebar" aria-label={tr('Main navigation', 'मुख्य मेनू')}>
        <div className="brand">
          <div className="brand-mark"><Fish size={18} strokeWidth={2.2} aria-hidden /></div>
          <div>
            <div className="brand-name">MatsyaAI</div>
            <div className="brand-region">{tr('Maharashtra Coast', 'महाराष्ट्र किनारा')}</div>
          </div>
        </div>
        <nav>
          {NAV.map((group) => (
            <div key={group.section[0]}>
              <div className="nav-section">{group.section[mr ? 1 : 0]}</div>
              {group.items.map((item) => (
                <a key={item.id} className="nav-link" href={href(item.id)} aria-current={route === item.id ? 'page' : undefined}>
                  <item.icon aria-hidden />
                  {item.label[mr ? 1 : 0]}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span>{tr('Data: INCOIS · IMD · Open-Meteo · GFW', 'डेटा: INCOIS · IMD · Open-Meteo · GFW')}</span>
          <span>{tr('Decision support only. Follow official advisories.', 'केवळ निर्णय सहाय्य. अधिकृत सल्ल्यांचे पालन करा.')}</span>
        </div>
      </aside>
      <div className="backdrop" onClick={() => setDrawer(false)} aria-hidden />

      <div className="main">
        <header className="topbar">
          <Button variant="ghost" icon={Menu} className="menu-btn" onClick={() => setDrawer(true)} aria-label={tr('Open menu', 'मेनू उघडा')} />
          <div className="brand-compact">
            <div className="brand-mark" style={{ width: 28, height: 28 }}><Fish size={16} aria-hidden /></div>
            <span className="brand-name">MatsyaAI</span>
          </div>
          <div className="topbar-title">
            {tr('Maharashtra Coast', 'महाराष्ट्र किनारा')} <span aria-hidden>/</span> <strong>{current?.label[mr ? 1 : 0]}</strong>
          </div>
          <div className="topbar-spacer" />
          {!online && <Badge tone="neutral" icon={WifiOff}>{tr('Offline', 'ऑफलाइन')}</Badge>}
          {online && dataStatus && (
            <span className="hide-sm text-xs text-muted" title={tr('Last refreshed', 'शेवटचे अद्ययावत')}>
              {tr('Updated', 'अद्ययावत')} {fmtTime(lastUpdated)}
            </span>
          )}
          <Button variant="ghost" icon={RefreshCw} onClick={refresh} disabled={loading} aria-label={tr('Refresh data', 'डेटा रीफ्रेश करा')} className="hide-sm" />
          <Button variant="secondary" size="sm" icon={Languages} onClick={toggle} aria-label={tr('Switch to Marathi', 'Switch to English')}>
            {mr ? 'English' : 'मराठी'}
          </Button>
        </header>

        <main className="content" id="main">{children}</main>
      </div>

      <nav className="mobile-nav" aria-label={tr('Quick navigation', 'जलद मेनू')}>
        {MOBILE.map(({ id, label }) => {
          const item = ALL.find((i) => i.id === id)!;
          return (
            <a key={id} href={href(id)} aria-current={route === id ? 'page' : undefined}>
              <item.icon aria-hidden />
              <span>{label[mr ? 1 : 0]}</span>
            </a>
          );
        })}
      </nav>
    </div>
  );
}
