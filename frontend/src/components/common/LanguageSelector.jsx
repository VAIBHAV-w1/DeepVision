import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from '../../i18n/i18nContext';

/**
 * DeepVision Language Selector Component
 * Strictly supports English, Hindi (हिंदी), and Kannada (ಕನ್ನಡ).
 * Provides immediate in-place language switching, keyboard accessibility, and ARIA attributes.
 */
export function LanguageSelector({ compact = false, idPrefix = '' }) {
  const { language, setLanguage, languages, t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

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

  const handleSelect = (code) => {
    setLanguage(code);
    setIsOpen(false);
  };

  const buttonId = idPrefix ? `btn-language-selector-${idPrefix}` : 'btn-language-selector';

  return (
    <div
      className="language-selector-wrapper"
      ref={dropdownRef}
      style={{ position: 'relative', display: 'inline-block' }}
    >
      <button
        type="button"
        id={buttonId}
        className="nav-btn lang-toggle-btn"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label={`Select Language - Current: ${currentLang.name}`}
        title={`Select Language / भाषा चुनें / ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: compact ? '4px 10px' : '6px 12px',
          fontSize: '0.82rem',
          borderRadius: 'var(--dv-radius-sm, 4px)',
          border: '1px solid var(--dv-border-default, #24324A)',
          background: 'var(--dv-surface-1, #101826)',
          color: 'var(--dv-text-primary, #F8FAFC)',
          cursor: 'pointer',
          fontFamily: 'inherit',
          transition: 'all 0.15s ease',
        }}
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--dv-cyan-500, #00E5FF)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span style={{ fontWeight: 600 }}>{currentLang.nativeName}</span>
        {!compact && (
          <span style={{ fontSize: '0.72rem', color: 'var(--dv-text-muted, #64748B)' }}>
            ({currentLang.name})
          </span>
        )}
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{
            transform: isOpen ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s',
            opacity: 0.7,
          }}
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div
          className="lang-dropdown-menu"
          role="listbox"
          aria-label="Available Languages"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 1000,
            minWidth: '180px',
            background: 'var(--dv-surface-0, #0C121D)',
            border: '1px solid var(--dv-border-default, #24324A)',
            borderRadius: 'var(--dv-radius-md, 8px)',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.6), 0 8px 10px -6px rgba(0, 0, 0, 0.5)',
            overflow: 'hidden',
            padding: '4px',
          }}
        >
          {languages.map((l) => {
            const isSelected = l.code === language;
            const optId = idPrefix ? `lang-option-${idPrefix}-${l.code}` : `lang-option-${l.code}`;
            return (
              <button
                key={l.code}
                type="button"
                id={optId}
                role="option"
                aria-selected={isSelected}
                onClick={() => handleSelect(l.code)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '0.82rem',
                  border: 'none',
                  borderRadius: 'var(--dv-radius-sm, 4px)',
                  background: isSelected ? 'var(--dv-cyan-soft, rgba(0, 210, 255, 0.12))' : 'transparent',
                  color: isSelected ? 'var(--dv-cyan-500, #00D2FF)' : 'var(--dv-text-primary, #F8FAFC)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontWeight: isSelected ? 700 : 500,
                  transition: 'background 0.1s ease',
                }}
              >
                <span>{l.nativeName} ({l.name})</span>
                {isSelected && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default LanguageSelector;
