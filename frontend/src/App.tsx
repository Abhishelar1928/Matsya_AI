/**
 * MatsyaAI Maharashtra — application root.
 * Providers (language, data) → shell (sidebar / top bar / mobile nav) → routed page.
 */

import './App.css';
import { AppShell } from './components/AppShell';
import { DataProvider } from './lib/data';
import { LangProvider } from './lib/lang';
import { useLocation } from './lib/router';
import { Districts } from './pages/Districts';
import { FishingZones } from './pages/FishingZones';
import { MapPage } from './pages/MapPage';
import { Navigation } from './pages/Navigation';
import { Overview } from './pages/Overview';
import { Safety } from './pages/Safety';
import { Weather } from './pages/Weather';

function Routed() {
  const loc = useLocation();
  let page;
  switch (loc.route) {
    case 'zones': page = <FishingZones loc={loc} />; break;
    case 'map': page = <MapPage loc={loc} />; break;
    case 'safety': page = <Safety />; break;
    case 'weather': page = <Weather loc={loc} />; break;
    case 'navigation': page = <Navigation loc={loc} />; break;
    case 'districts': page = <Districts />; break;
    default: page = <Overview />;
  }
  return <AppShell route={loc.route}>{page}</AppShell>;
}

function App() {
  return (
    <LangProvider>
      <DataProvider>
        <Routed />
      </DataProvider>
    </LangProvider>
  );
}

export default App;
