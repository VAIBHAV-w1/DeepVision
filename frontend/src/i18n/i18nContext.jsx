/**
 * DeepVision Internationalization Context (i18nContext.jsx)
 * Supports strictly three enterprise languages:
 * 1. English ('en') - Default
 * 2. हिंदी ('hi')
 * 3. ಕನ್ನಡ ('kn')
 *
 * Provides:
 * - Reactive global language switching without page reloads
 * - LocalStorage persistence across browser refreshes
 * - Interpolation for dynamic placeholders ({name}, {count}, etc.)
 * - Locale-aware date, time, and number formatting
 * - Document attribute updates (lang, dir)
 * - Missing-translation detection and auditing
 */

import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import { SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE } from './languages';
import { translations } from './translations';

const I18nContext = createContext(null);

// Global audit set for missing translations
if (typeof window !== 'undefined') {
  window.__deepvision_missing_keys = window.__deepvision_missing_keys || new Set();
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    try {
      const saved = localStorage.getItem('deepvision_lang');
      if (saved && SUPPORTED_LANGUAGES.some((l) => l.code === saved)) {
        return saved;
      }
    } catch {
      // ignore
    }
    return DEFAULT_LANGUAGE;
  });

  const currentLangObj = useMemo(() => {
    return SUPPORTED_LANGUAGES.find((l) => l.code === language) || SUPPORTED_LANGUAGES[0];
  }, [language]);

  const dir = currentLangObj.dir || 'ltr';

  // Apply HTML document attributes on language/direction change
  useEffect(() => {
    try {
      document.documentElement.lang = language;
      document.documentElement.dir = dir;
      document.documentElement.setAttribute('data-language', language);
    } catch {
      // ignore in non-DOM environments
    }
  }, [language, dir]);

  const setLanguage = useCallback((code) => {
    if (!SUPPORTED_LANGUAGES.some((l) => l.code === code)) {
      code = DEFAULT_LANGUAGE;
    }
    setLanguageState(code);
    try {
      localStorage.setItem('deepvision_lang', code);
    } catch {
      // ignore
    }
    // Dispatch custom event for non-react listeners if needed
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('deepvision:language-changed', { detail: { code } }));
    }
  }, []);

  useEffect(() => {
    window.__setDeepVisionLanguage = setLanguage;
    const handleLangEvent = (e) => {
      if (e.detail?.code) setLanguage(e.detail.code);
    };
    window.addEventListener('deepvision:set-language', handleLangEvent);
    return () => {
      delete window.__setDeepVisionLanguage;
      window.removeEventListener('deepvision:set-language', handleLangEvent);
    };
  }, [setLanguage]);

  /**
   * Safe string translation helper with fallback chain and parameter interpolation:
   * 1. translations[language][key]
   * 2. translations['en'][key]
   * 3. fallback (if provided)
   * 4. key itself
   */
  const t = useCallback((key, fallback, params) => {
    if (!key) return '';

    // Handle (key, params) where fallback was omitted
    if (fallback && typeof fallback === 'object' && params === undefined) {
      params = fallback;
      fallback = undefined;
    }

    let translatedStr = undefined;
    const langDict = translations[language];

    if (langDict && langDict[key] !== undefined) {
      translatedStr = langDict[key];
    } else {
      // Track missing key in active language
      if (typeof window !== 'undefined' && window.__deepvision_missing_keys) {
        window.__deepvision_missing_keys.add(`${language}:${key}`);
      }

      const defaultDict = translations[DEFAULT_LANGUAGE];
      if (defaultDict && defaultDict[key] !== undefined) {
        translatedStr = defaultDict[key];
      }
    }

    if (translatedStr === undefined) {
      translatedStr = fallback !== undefined ? fallback : key;
    }

    // Parameter interpolation: {varName}
    if (params && typeof params === 'object' && typeof translatedStr === 'string') {
      Object.keys(params).forEach((paramKey) => {
        const val = params[paramKey] !== undefined && params[paramKey] !== null ? params[paramKey] : '';
        translatedStr = translatedStr.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), String(val));
      });
    }

    return translatedStr;
  }, [language]);

  /**
   * Format dates in Asia/Kolkata timezone with IST indicator or customized locale format.
   */
  const formatDateIST = useCallback((dateInput, options = {}) => {
    if (!dateInput) return '-';
    try {
      const d = typeof dateInput === 'string' || typeof dateInput === 'number' ? new Date(dateInput) : dateInput;
      if (isNaN(d.getTime())) return String(dateInput);
      const locale = language === 'en' ? 'en-IN' : `${language}-IN`;
      const formatted = d.toLocaleString(locale, {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        ...options,
      });
      return `${formatted} IST`;
    } catch {
      return String(dateInput);
    }
  }, [language]);

  /**
   * Format numbers using locale-aware conventions.
   */
  const formatNumber = useCallback((num, options = {}) => {
    if (num === null || num === undefined || isNaN(num)) return '0';
    try {
      const locale = language === 'en' ? 'en-IN' : `${language}-IN`;
      return new Intl.NumberFormat(locale, options).format(num);
    } catch {
      return String(num);
    }
  }, [language]);

  const value = useMemo(() => ({
    language,
    currentLang: currentLangObj,
    setLanguage,
    t,
    dir,
    languages: SUPPORTED_LANGUAGES,
    formatDateIST,
    formatNumber,
  }), [language, currentLangObj, setLanguage, t, dir, formatDateIST, formatNumber]);

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider');
  }
  return context;
}
