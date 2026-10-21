import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useTranslation } from '../../i18n/i18nContext';
import { LanguageSelector } from './LanguageSelector';
import Logo from './Logo';

export function Navbar({ activePage, setActivePage, unreadNotifCount = 0 }) {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const [themePref, setThemePref] = useState(() => localStorage.getItem('deepvision_theme') || 'dark');
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const themeMenuRef = useRef(null);

  // Apply theme logic matching original theme.js
  useEffect(() => {
    function resolveTheme(pref) {
      if (pref === 'system') {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      return pref;
    }

    const resolved = resolveTheme(themePref);
    document.documentElement.setAttribute('data-theme', resolved);
    document.documentElement.setAttribute('data-theme-pref', themePref);
    localStorage.setItem('deepvision_theme', themePref);

    const mediaListener = (e) => {
      if (localStorage.getItem('deepvision_theme') === 'system') {
        document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      }
    };

    const matcher = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    matcher?.addEventListener('change', mediaListener);
    return () => matcher?.removeEventListener('change', mediaListener);
  }, [themePref]);

  // Click outside to close theme dropdown
  useEffect(() => {
    function handleClickOutside(event) {
      if (themeMenuRef.current && !themeMenuRef.current.contains(event.target)) {
        setThemeMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const navItems = [
    { key: 'dashboard', label: t('nav.dashboard', 'Dashboard') },
    { key: 'cameras', label: t('nav.cameras', 'Live Feeds') },
    { key: 'alerts', label: t('nav.alerts', 'Security Alerts') },
    { key: 'recordings', label: t('nav.recordings', 'Recordings') },
    { key: 'evidence', label: t('nav.evidence', 'Evidence Vault') },
    { key: 'cases', label: t('nav.cases', 'Incident Cases') },
    { key: 'notifications', label: t('nav.notifications', 'Notifications'), badge: unreadNotifCount },
    { key: 'help', label: t('nav.help', 'Help & Support') },
  ];

  const handleNavClick = (key) => {
    setActivePage(key);
    setMobileMenuOpen(false);
  };

  const handleSelectTheme = (val) => {
    setThemePref(val);
    setThemeMenuOpen(false);
  };

  const resolvedIsLight = themePref === 'light' || (themePref === 'system' && window.matchMedia && !window.matchMedia('(prefers-color-scheme: dark)').matches);

  return (
    <>
      {/* Mobile Navigation Drawer Backdrop */}
      <div
        className={`sidebar-backdrop ${mobileMenuOpen ? 'active' : ''}`}
        id="sidebarBackdrop"
        onClick={() => setMobileMenuOpen(false)}
        style={{ display: mobileMenuOpen ? 'block' : 'none' }}
      ></div>

      {/* Mobile Slide-Over Drawer */}
      <aside className={`app-sidebar ${mobileMenuOpen ? 'open' : ''}`} id="appSidebar" style={{ transform: mobileMenuOpen ? 'translateX(0)' : undefined }}>
        <div className="mobile-drawer-header">
          <a href="#dashboard" onClick={(e) => { e.preventDefault(); handleNavClick('dashboard'); }} className="brand-link">
            <Logo size="sm" subtext="SURVEILLANCE SOC" />
          </a>
          <button
            type="button"
            className="btn btn-ghost btn-icon mobile-nav-toggle"
            aria-label="Close menu"
            onClick={() => setMobileMenuOpen(false)}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <nav className="sidebar-nav">
          <ul className="mobile-nav-links">
            {navItems.map((item) => (
              <li key={item.key}>
                <a
                  href={`#${item.key}`}
                  onClick={(e) => { e.preventDefault(); handleNavClick(item.key); }}
                  className={`mobile-nav-link ${activePage === item.key ? 'active' : ''}`}
                >
                  <span>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span className="nav-badge" style={{ marginLeft: 'auto' }}>{item.badge}</span>
                  )}
                </a>
              </li>
            ))}
            <li style={{ marginTop: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ padding: '0 8px' }}>
                <LanguageSelector compact />
              </div>
              <button
                type="button"
                onClick={() => { setMobileMenuOpen(false); logout(); }}
                className="mobile-nav-link"
                style={{ width: '100%', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', color: 'var(--color-danger, #ef4444)' }}
              >
                <span>{t('nav.logout', 'Sign Out')}</span>
              </button>
            </li>
          </ul>
        </nav>
      </aside>

      {/* Reference Style Sleek Top Navigation Bar */}
      <header className="app-header">
        <div className="app-header-inner">
          {/* Left: Brand Identity */}
          <a
            href="#dashboard"
            onClick={(e) => { e.preventDefault(); handleNavClick('dashboard'); }}
            className="brand-link"
          >
            <Logo size="md" subtext="SURVEILLANCE SOC" />
          </a>


          {/* Center: Minimal Top Navigation Links */}
          <nav className="nav-links-center" aria-label="Main Navigation">
            {navItems.map((item) => {
              const isActive = activePage === item.key;
              return (
                <a
                  key={item.key}
                  id={`nav-${item.key}`}
                  href={`#${item.key}`}
                  onClick={(e) => { e.preventDefault(); handleNavClick(item.key); }}
                  className={`nav-link-pill ${isActive ? 'active' : ''}`}
                  style={{
                    border: isActive ? '1px solid rgba(16, 185, 129, 0.35)' : '1px solid transparent',
                    background: isActive ? 'rgba(16, 185, 129, 0.10)' : undefined,
                    color: isActive ? '#10b981' : undefined,
                    fontWeight: 700,
                  }}
                >
                  {isActive && <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }}></span>}
                  <span>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span className="nav-badge">{item.badge}</span>
                  )}
                </a>
              );
            })}
          </nav>


          {/* Right: Status, Theme, User Controls */}
          <div className="nav-controls-right">
            {/* Live SOC Status Indicator */}
            <div className="soc-status-badge-top" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '4px 10px', borderRadius: '4px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', fontSize: '0.72rem', color: '#10b981', fontWeight: 700, letterSpacing: '0.04em' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', boxShadow: '0 0 6px #10b981', display: 'inline-block' }}></span>
              <span>SOC ONLINE</span>
            </div>

            {/* Indian Language Selector (22 Languages + EN) */}
            <LanguageSelector />

            {/* Theme Switcher (3-Way: Dark / Light / System) */}
            <div className="theme-menu-wrap" ref={themeMenuRef} style={{ position: 'relative' }}>
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                id="btn-theme-toggle"
                title="Toggle Theme"
                aria-label="Toggle Theme"
                onClick={() => setThemeMenuOpen(!themeMenuOpen)}
              >
                <span id="theme-active-icon">
                  {resolvedIsLight ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M 21 12.79 A 9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79 z"></path>
                    </svg>
                  )}
                </span>
              </button>

              {themeMenuOpen && (
                <div className="theme-dropdown show" id="theme-dropdown-menu" style={{ display: 'flex', flexDirection: 'column', position: 'absolute', right: 0, top: 'calc(100% + 8px)', zIndex: 1100 }}>
                  <button
                    type="button"
                    className={`theme-option ${themePref === 'dark' ? 'active' : ''}`}
                    onClick={() => handleSelectTheme('dark')}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M 21 12.79 A 9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79 z"></path>
                    </svg>
                    <span>Dark Mode</span>
                  </button>
                  <button
                    type="button"
                    className={`theme-option ${themePref === 'light' ? 'active' : ''}`}
                    onClick={() => handleSelectTheme('light')}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
                    <span>Light Mode</span>
                  </button>
                  <button
                    type="button"
                    className={`theme-option ${themePref === 'system' ? 'active' : ''}`}
                    onClick={() => handleSelectTheme('system')}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                      <line x1="8" y1="21" x2="16" y2="21"></line>
                      <line x1="12" y1="17" x2="12" y2="21"></line>
                    </svg>
                    <span>System Auto</span>
                  </button>
                </div>
              )}
            </div>

            {/* User Profile Avatar & Name Block */}
            <div className="user-profile-badge" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div className="user-avatar-circle">
                {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
              </div>
              <div className="user-name-role">
                <span className="user-display-name">{user?.full_name || 'Operator'}</span>
                <span className="user-display-role">{user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : 'User'}</span>
              </div>
              <button
                type="button"
                onClick={() => logout()}
                className="btn btn-secondary btn-sm"
                title="Log Out"
                style={{ padding: '4px 10px', fontSize: '0.78rem', marginLeft: '6px' }}
              >
                Sign Out
              </button>
            </div>

            {/* Mobile Hamburger Button */}
            <button
              type="button"
              className="mobile-nav-toggle"
              aria-label="Open navigation menu"
              onClick={() => setMobileMenuOpen(true)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
      </header>
    </>
  );
}

export default Navbar;
