/**
 * MatsyaAI Maharashtra — Simple i18n Provider
 *
 * Lightweight translation system supporting English and Marathi.
 * Can be upgraded to a full i18n library (react-intl, i18next) later.
 */

import en, { type TranslationKey } from './en';
import mr from './mr';

export type Locale = 'en' | 'mr';

const translations: Record<Locale, Record<string, string>> = {
  en: en as unknown as Record<string, string>,
  mr,
};

let currentLocale: Locale = 'en';

/**
 * Set the active locale.
 */
export function setLocale(locale: Locale): void {
  currentLocale = locale;
}

/**
 * Get the active locale.
 */
export function getLocale(): Locale {
  return currentLocale;
}

/**
 * Translate a key to the current locale string.
 * Falls back to English if the key is missing in the target locale.
 */
export function t(key: TranslationKey): string {
  return translations[currentLocale]?.[key] ?? translations.en[key] ?? key;
}
