import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useTranslation } from '../../i18n/i18nContext';
import { LanguageSelector } from './LanguageSelector';
import Logo from './Logo';
import { api } from '../../services/api';

export function Navbar({ activePage, setActivePage, unreadNotifCount = 0 }) {
  const { logout } = useAuth();
  const { t } = useTranslation();
  const [themePref, setThemePref] = useState(() => localStorage.getItem('deepvision_theme') || 'dark');
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [systemHealth, setSystemHealth] = useState('checking');
  const themeMenuRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const health = await api.system.health();
        if (mounted) setSystemHealth(health?.status === 'healthy' ? 'online' : 'degraded');
      } catch {
        if (mounted) setSystemHealth('offline');
      }
    };
    checkHealth();
    const timer = setInterval(checkHealth, 15000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  // Apply theme logic
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

  const isOverviewActive = activePage === 'overview' || activePage === 'dashboard';
  const isCamerasActive = activePage === 'cameras' || ['live', 'surveillance', 'monitor', 'camera-preview'].includes(activePage);
  const isNotifsActive = ['notifications', 'alerts', 'security-events', 'recordings', 'evidence', 'cases'].includes(activePage);
  const isSettingsActive = activePage === 'settings';
  const isHelpActive = activePage === 'help' || activePage === 'support';
  const navItems = [
    { key: 'dashboard', targetPage: 'dashboard', label: t('nav.dashboard', 'Dashboard'), active: isOverviewActive },
    { key: 'cameras', targetPage: 'cameras', label: t('nav.cameras', 'Cameras'), active: isCamerasActive },
    { key: 'notifications', targetPage: 'notifications', label: t('nav.notifications', 'Notifications'), badge: unreadNotifCount, active: isNotifsActive },
    { key: 'settings', targetPage: 'settings', label: t('nav.settings', 'Settings'), active: isSettingsActive },
    { key: 'help', targetPage: 'help', label: t('nav.help', 'Help'), active: isHelpActive },
  ];

  const handleNavClick = (item) => {
    if (typeof item === 'string') {
      setActivePage(item);
    } else {
      setActivePage(item.targetPage);
    }
    setMobileMenuOpen(false);
  };

  const handleSelectTheme = (val) => {
    setThemePref(val);
    setThemeMenuOpen(false);
  };

  const resolvedIsLight = themePref === 'light' || (themePref === 'system' && window.matchMedia && !window.matchMedia('(prefers-color-scheme: dark)').matches);
  const healthLabel = {
    checking: t('nav.systemChecking', 'Checking system'),
    online: t('nav.systemOnline', 'System operational'),
    degraded: t('nav.systemDegraded', 'System degraded'),
    offline: t('nav.systemOffline', 'System unavailable'),
  }[systemHealth];
  const healthColor = systemHealth === 'online' ? '#10b981' : systemHealth === 'checking' ? '#94a3b8' : '#ef4444';

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
          <a href="#overview" onClick={(e) => { e.preventDefault(); handleNavClick('overview'); }} className="brand-link">
            <Logo size="sm" />
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
                  id={`mobile-nav-${item.key}`}
                  onClick={(e) => { e.preventDefault(); handleNavClick(item); }}
                  className={`mobile-nav-link ${item.active ? 'active' : ''}`}
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
                <LanguageSelector compact idPrefix="mobile" />
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

      {/* Sleek Top Navigation Bar */}
      <header className="app-header">
        <div className="app-header-inner">
          {/* Left: Brand Identity */}
          <a
            href="#overview"
            onClick={(e) => { e.preventDefault(); handleNavClick('overview'); }}
            className="brand-link"
          >
            <Logo size="sm" />
          </a>

          {/* Center: Clean 10-Item Plain Language Navigation */}
          <nav className="nav-links-center" aria-label="Main Navigation">
            {navItems.map((item) => {
              const isActive = item.active;
              return (
                <a
                  key={item.key}
                  id={`nav-${item.key}`}
                  href={`#${item.key}`}
                  onClick={(e) => { e.preventDefault(); handleNavClick(item); }}
                  className={`nav-link-pill ${isActive ? 'active' : ''}`}
                  style={{
                    border: isActive ? '1px solid var(--dv-cyan-glow, rgba(0, 210, 255, 0.35))' : '1px solid transparent',
                    background: isActive ? 'var(--dv-cyan-soft, rgba(0, 210, 255, 0.10))' : undefined,
                    color: isActive ? 'var(--dv-cyan-500, #00D2FF)' : undefined,
                    fontWeight: 700,
                  }}
                >
                  {isActive && <span style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: 'var(--dv-cyan-500, #00D2FF)', display: 'inline-block', flexShrink: 0 }}></span>}
                  <span>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span className="nav-badge">{item.badge}</span>
                  )}
                </a>
              );
            })}
          </nav>

          {/* Right: Status, Language Selector, Theme, User Controls */}
          <div className="nav-controls-right">
            {/* Live System Operational Status */}
            <div
              className="soc-status-badge-top"
              title={healthLabel}
              role="status"
              aria-live="polite"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 8px',
                borderRadius: '4px',
                background: systemHealth === 'online' ? 'rgba(16, 185, 129, 0.08)' : 'rgba(148, 163, 184, 0.08)',
                border: `1px solid ${healthColor}40`,
                fontSize: '0.71rem',
                color: healthColor,
                fontWeight: 700,
                letterSpacing: '0.03em',
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: healthColor, display: 'inline-block', flexShrink: 0 }}></span>
              <span className="soc-status-text">{healthLabel}</span>
            </div>

            {/* Tri-Lingual Language Selector (EN / HI / KN) */}
            <LanguageSelector compact />

            {/* Theme Switcher (3-Way: Dark / Light / System) */}
            <div className="theme-menu-wrap" ref={themeMenuRef} style={{ position: 'relative' }}>
              <button
                type="button"
                className="btn btn-secondary btn-icon"
                id="btn-theme-toggle"
                title={t('nav.theme', 'Appearance')}
                aria-label={t('nav.theme', 'Appearance')}
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
                    <span>{t('settings.themeDark', 'Dark Theme')}</span>
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
                    <span>{t('settings.themeLight', 'Light Theme')}</span>
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
                    <span>{t('settings.themeSystem', 'Follow System')}</span>
                  </button>
                </div>
              )}
            </div>

            {/* User Profile & Sign Out Dropdown */}
            <div className="user-profile-menu" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                id="btn-signout"
                onClick={logout}
                className="btn btn-ghost btn-sm"
                title={t('nav.logout', 'Sign Out')}
                style={{
                  fontSize: '0.8rem',
                  padding: '5px 10px',
                  color: 'var(--dv-text-secondary, #94A3B8)',
                }}
              >
                <span>{t('nav.logout', 'Sign Out')}</span>
              </button>
            </div>

            {/* Mobile Hamburger Menu Toggle Button */}
            <button
              type="button"
              className="btn btn-ghost btn-icon mobile-nav-toggle"
              aria-label="Toggle mobile navigation menu"
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
