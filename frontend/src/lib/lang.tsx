/**
 * Language context (English / Marathi). `tr(en, mr)` keeps copy next to the UI
 * that uses it; the key-based i18n in ../i18n stays in sync via setLocale.
 */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setLocale } from '../i18n';

interface LangValue {
  mr: boolean;
  toggle: () => void;
  tr: (en: string, mr: string) => string;
}

const LangContext = createContext<LangValue>({ mr: false, toggle: () => {}, tr: (en) => en });

export function LangProvider({ children }: { children: ReactNode }) {
  const [mr, setMr] = useState<boolean>(() => localStorage.getItem('matsya.lang') === 'mr');
  useEffect(() => {
    setLocale(mr ? 'mr' : 'en');
    localStorage.setItem('matsya.lang', mr ? 'mr' : 'en');
    document.documentElement.lang = mr ? 'mr' : 'en';
  }, [mr]);
  const value = useMemo<LangValue>(() => ({ mr, toggle: () => setMr((v) => !v), tr: (en, m) => (mr ? m : en) }), [mr]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangValue {
  return useContext(LangContext);
}
