import React, { useState, useEffect, useRef } from 'react';

export function ThemeToggle({ compact = false }) {
  const [themePref, setThemePref] = useState(() => {
    return localStorage.getItem('deepvision_theme') || 'dark';
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    const applyTheme = (theme) => {
      let resolved = theme;
      if (theme === 'system') {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        resolved = prefersDark ? 'dark' : 'light';
      }
      document.documentElement.setAttribute('data-theme', resolved);
      localStorage.setItem('deepvision_theme', theme);
    };

    applyTheme(themePref);

    const mediaListener = (e) => {
      if (localStorage.getItem('deepvision_theme') === 'system') {
        document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      }
    };

    const matcher = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    matcher?.addEventListener('change', mediaListener);
    return () => matcher?.removeEventListener('change', mediaListener);
  }, [themePref]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';

  const toggleQuick = () => {
    const next = themePref === 'dark' ? 'light' : 'dark';
    setThemePref(next);
  };

  return (
    <div className="theme-menu-wrap" ref={menuRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="btn btn-secondary btn-icon theme-toggle-btn"
        id="btn-theme-toggle"
        title="Toggle Theme"
        aria-label="Toggle Theme"
        onClick={toggleQuick}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: compact ? '32px' : '36px',
          height: compact ? '32px' : '36px',
          borderRadius: '8px',
          border: '1px solid var(--border-color)',
          background: 'var(--bg-surface)',
          color: 'var(--text-main)',
          cursor: 'pointer',
        }}
      >
        {isLight ? (
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="5"></circle>
            <line x1="12" y1="1" x2="12" y2="3"></line>
            <line x1="12" y1="21" x2="12" y2="23"></line>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
            <line x1="1" y1="12" x2="3" y2="12"></line>
            <line x1="21" y1="12" x2="23" y2="12"></line>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
          </svg>
        ) : (
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M 21 12.79 A 9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79 z"></path>
          </svg>
        )}
      </button>
    </div>
  );
}

export default ThemeToggle;
