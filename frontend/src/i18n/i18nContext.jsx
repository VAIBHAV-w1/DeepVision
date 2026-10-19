/**
 * DeepVision Internationalization Context (i18nContext.jsx)
 * Supports all 22 Scheduled Indian Languages + English.
 * Provides fallback to English, RTL layout for Urdu/Kashmiri/Sindhi,
 * locale-aware date/number formatting, and persistent language selection.
 */

import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import { SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE } from './languages';
import { translations } from './translations';

const I18nContext = createContext(null);

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
      if (dir === 'rtl') {
        document.documentElement.classList.add('rtl-layout');
      } else {
        document.documentElement.classList.remove('rtl-layout');
      }
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
  }, []);

  /**
   * Safe string translation helper with fallback chain:
   * 1. translations[language][key]
   * 2. translations['en'][key]
   * 3. fallback (if provided)
   * 4. key itself
   */
  const t = useCallback((key, fallback) => {
    if (!key) return '';
    const langDict = translations[language];
    if (langDict && langDict[key] !== undefined) {
      return langDict[key];
    }
    const defaultDict = translations[DEFAULT_LANGUAGE];
    if (defaultDict && defaultDict[key] !== undefined) {
      return defaultDict[key];
    }
    return fallback !== undefined ? fallback : key;
  }, [language]);

  /**
   * Format dates in Asia/Kolkata timezone with IST indicator.
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
