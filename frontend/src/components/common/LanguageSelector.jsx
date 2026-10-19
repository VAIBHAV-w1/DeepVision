/**
 * DeepVision Language Selector Component (LanguageSelector.jsx)
 * Supports all 22 Scheduled Languages of India + English.
 * Accessible dropdown with search filter and native script display.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from '../../i18n/i18nContext';

export function LanguageSelector({ compact = false }) {
  const { language, setLanguage, languages, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const dropdownRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const currentLang = languages.find((l) => l.code === language) || languages[0];

  const filteredLanguages = languages.filter((l) =>
    l.name.toLowerCase().includes(search.toLowerCase()) ||
    l.nativeName.toLowerCase().includes(search.toLowerCase()) ||
    l.code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="language-selector-wrapper" ref={dropdownRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        className="nav-btn lang-toggle-btn"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label="Select Language - 22 Scheduled Indian Languages"
        title="Select Language / भाषा चुनें (22 Indian Languages)"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: compact ? '4px 8px' : '6px 12px',
          fontSize: '0.82rem',
          borderRadius: '6px',
          border: '1px solid var(--border-color, #334155)',
          background: 'var(--card-bg, #1e293b)',
          color: 'var(--text-primary, #f8fafc)',
          cursor: 'pointer',
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span style={{ fontWeight: 600 }}>{currentLang.nativeName}</span>
        {!compact && (
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted, #94a3b8)', marginLeft: '2px' }}>
            ({currentLang.name})
          </span>
        )}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div
          className="lang-dropdown-menu"
          role="listbox"
          aria-label="Available Indian Languages"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 1000,
            width: '280px',
            maxHeight: '380px',
            background: 'var(--card-bg, #1e293b)',
            border: '1px solid var(--border-color, #334155)',
            borderRadius: '8px',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Header & Search */}
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-color, #334155)', background: 'rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-primary, #10b981)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Indian Languages (22 + EN)
              </span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted, #94a3b8)' }}>
                {languages.length} options
              </span>
            </div>
            <input
              type="text"
              placeholder="Search / खोजें / ಹುಡುಕಿ..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
              style={{
                width: '100%',
                padding: '6px 10px',
                fontSize: '0.8rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color, #334155)',
                background: 'var(--input-bg, #0f172a)',
                color: 'var(--text-primary, #f8fafc)',
                outline: 'none',
              }}
            />
          </div>

          {/* Languages list */}
          <div style={{ overflowY: 'auto', flex: 1, padding: '4px 0' }}>
            {filteredLanguages.length === 0 ? (
              <div style={{ padding: '16px', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted, #94a3b8)' }}>
                No language found matching "{search}"
              </div>
            ) : (
              filteredLanguages.map((l) => {
                const isSelected = l.code === language;
                return (
                  <button
                    key={l.code}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => {
                      setLanguage(l.code);
                      setIsOpen(false);
                      setSearch('');
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      padding: '8px 14px',
                      background: isSelected ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
                      color: isSelected ? 'var(--color-primary, #10b981)' : 'var(--text-primary, #f8fafc)',
                      border: 'none',
                      textAlign: 'left',
                      cursor: 'pointer',
                      fontSize: '0.82rem',
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontWeight: isSelected ? 700 : 500 }}>
                        {l.nativeName}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted, #94a3b8)' }}>
                        {l.name} {l.dir === 'rtl' ? '• RTL' : ''}
                      </span>
                    </div>
                    {isSelected && (
                      <span style={{ color: 'var(--color-primary, #10b981)', fontSize: '0.85rem' }}>✓</span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
