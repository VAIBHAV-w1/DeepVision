import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../i18n/i18nContext';
import LanguageSelector from '../components/common/LanguageSelector';
import ThemeToggle from '../components/common/ThemeToggle';
import useNotifications from '../hooks/useNotifications';

/**
 * DeepVision 4.0 — Unified Enterprise AppLayout
 * Faithful reconstruction of Figures 7.1.2 through 7.1.10.
 *
 * Implements strictly 5 primary navigation destinations:
 * 1. Dashboard
 * 2. Cameras
 * 3. Notifications
 * 4. Settings
 * 5. Help
 */
export function AppLayout({ children, activePage, pageParams, setActivePage }) {
  const { user, logout } = useAuth();
  const { t, language } = useTranslation();
  const { unreadCount } = useNotifications();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [clockStr, setClockStr] = useState('Nov 01, 2026 | 11:24 AM');
  const profileMenuRef = useRef(null);

  // Live HUD Digital Clock matching Figure 7.1.2 ("Nov 01, 2026 | 11:24 AM")
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      if (language === 'hi' || language === 'kn') {
        try {
          const locale = language === 'hi' ? 'hi-IN' : 'kn-IN';
          const dateStr = now.toLocaleDateString(locale, { month: 'short', day: '2-digit', year: 'numeric' });
          const timeStr = now.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: true });
          setClockStr(`${dateStr} | ${timeStr}`);
          return;
        } catch (_) {
          // fallback
        }
      }
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const mon = months[now.getMonth()];
      const day = String(now.getDate()).padStart(2, '0');
      const yr = now.getFullYear();
      let hrs = now.getHours();
      const ampm = hrs >= 12 ? 'PM' : 'AM';
      hrs = hrs % 12 || 12;
      const min = String(now.getMinutes()).padStart(2, '0');
      setClockStr(`${mon} ${day}, ${yr} | ${hrs}:${min} ${ampm}`);
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, [language]);

  // Update browser document title dynamically with localized brand and active page
  useEffect(() => {
    const brand = t('brand.name', 'DeepVision');
    const page = t('nav.' + activePage, activePage);
    document.title = `${brand} — ${page}`;
  }, [activePage, language, t]);

  // Close profile dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target)) {
        setProfileDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Canonical destination matching: strictly 5 primary destinations
  const isDashboard = activePage === 'dashboard' || activePage === 'overview';
  const isCameras = activePage === 'cameras' || activePage === 'surveillance' || activePage === 'live';
  const isNotifications = activePage === 'notifications' || activePage === 'alerts' || activePage === 'recordings' || activePage === 'evidence' || activePage === 'cases';
  const isSettings = activePage === 'settings';
  const isHelp = activePage === 'help' || activePage === 'support';

  // Navigation Items matching Figure 7.1.2 Sidebar
  const navItems = [
    {
      id: 'dashboard',
      label: t('nav.dashboard', 'Dashboard'),
      active: isDashboard,
      onClick: () => {
        setActivePage('dashboard');
        setMobileMenuOpen(false);
      },
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        </svg>
      ),
    },
    {
      id: 'cameras',
      label: t('nav.cameras', 'Cameras'),
      active: isCameras,
      onClick: () => {
        setActivePage('cameras');
        setMobileMenuOpen(false);
      },
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M23 7l-7 5 7 5V7z" />
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
        </svg>
      ),
    },
    {
      id: 'notifications',
      label: t('nav.notifications', 'Notifications'),
      active: isNotifications,
      badge: unreadCount,
      onClick: () => {
        setActivePage('notifications');
        setMobileMenuOpen(false);
      },
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      ),
    },
    {
      id: 'settings',
      label: t('nav.settings', 'Settings'),
      active: isSettings,
      onClick: () => {
        setActivePage('settings');
        setMobileMenuOpen(false);
      },
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
    },
    {
      id: 'help',
      label: t('nav.help', 'Help'),
      active: isHelp,
      onClick: () => {
        setActivePage('help');
        setMobileMenuOpen(false);
      },
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
    },
  ];

  const userInitial = (user?.full_name || user?.email || 'V')[0].toUpperCase();

  return (
    <div className="deepvision-enterprise-shell">
      {/* 1. Left Vertical Sidebar (Desktop) matching Figure 7.1.2 */}
      <aside className="enterprise-sidebar">
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflowY: 'auto' }}>
          {/* Logo Brand Header matching Figure 7.1.2 */}
          <div
            onClick={() => setActivePage('dashboard')}
            role="button"
            tabIndex={0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '1.25rem 1.25rem 1.5rem 1.25rem',
              cursor: 'pointer',
              borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
              flexShrink: 0,
            }}
          >
            {/* Surveillance Camera Logo with optical reticle */}
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #00C9FF 0%, #0072FF 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 14px rgba(0, 201, 255, 0.4)',
                flexShrink: 0,
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-label="DeepVision Surveillance Camera Emblem">
                <path d="M4 17.5v3.5h5" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.5 7.5h13l4.5 3" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M2.5 9h11.5l4 3v3l-4 3H2.5a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 2.5 9z" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="7.5" cy="13.5" r="2.2" stroke="#00F5D4" strokeWidth="1.8" />
                <circle cx="7.5" cy="13.5" r="0.8" fill="#00F5D4" />
                <line x1="19.5" y1="13.5" x2="22.5" y2="13.5" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <span
              style={{
                fontSize: '1.2rem',
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: '#FFFFFF',
              }}
            >
              {t('brand.name', 'DeepVision')}
            </span>
          </div>

          {/* Navigation Links with exact Figure 7.1.2 violet active pill */}
          <nav style={{ padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {navItems.map((item) => {
              const active = item.active;
              const btnId = `nav-${item.id}`;
              return (
                <button
                  key={item.id}
                  id={btnId}
                  data-nav-id={item.id}
                  type="button"
                  onClick={item.onClick}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: 'none',
                    background: active
                      ? 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)'
                      : 'transparent',
                    color: active ? '#FFFFFF' : '#94A3B8',
                    fontSize: '0.88rem',
                    fontWeight: active ? 700 : 500,
                    cursor: 'pointer',
                    textAlign: 'left',
                    boxShadow: active ? '0 4px 12px rgba(99, 102, 241, 0.35)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                      e.currentTarget.style.color = '#FFFFFF';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = '#94A3B8';
                    }
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', opacity: active ? 1 : 0.85 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span
                      style={{
                        background: '#EF4444',
                        color: '#FFFFFF',
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        padding: '1px 6px',
                        borderRadius: '10px',
                      }}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User Account Bar Permanently Anchored at Bottom */}
        <div
          style={{
            padding: '1rem',
            borderTop: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            flexShrink: 0,
            marginTop: 'auto',
            backgroundColor: '#0B0F19',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #3B82F6, #1E40AF)',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.85rem',
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {userInitial}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div
                style={{
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  color: '#F8FAFC',
                  whiteSpace: 'nowrap',
                  textOverflow: 'ellipsis',
                  overflow: 'hidden',
                }}
              >
                {user?.full_name || t('common.operator', 'Operator')}
              </div>
              <div style={{ fontSize: '0.7rem', color: '#64748B', textTransform: 'capitalize' }}>
                {user?.role === 'admin' ? t('common.admin', 'Administrator') : t('common.surveillance', 'Surveillance')}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={logout}
            title={t('auth.signOut', 'Sign Out')}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#64748B',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = '#EF4444')}
            onMouseLeave={(e) => (e.currentTarget.style.color = '#64748B')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </aside>

      {/* 2. Main Content Area */}
      <div className="enterprise-main-viewport">
        {/* Top Header Row matching Figure 7.1.2 */}
        <header className="enterprise-header">
          {/* Mobile hamburger menu trigger */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              type="button"
              id="btn-mobile-menu-toggle"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="mobile-nav-toggle"
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94A3B8',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '4px',
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div style={{ fontSize: '0.9rem', color: '#64748B', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: '#94A3B8' }}>{t('brand.name', 'DeepVision')}</span>
              <span>/</span>
              <span style={{ color: '#F8FAFC', fontWeight: 600 }}>
                {t('nav.' + activePage, activePage)}
              </span>
            </div>
          </div>

          {/* Right Header Controls matching Figure 7.1.2 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            {/* Live HUD Date/Time Card */}
            <div
              id="dashboard-hud-clock"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '6px 12px',
                fontSize: '0.82rem',
                color: '#CBD5E1',
                fontWeight: 600,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              <span>{clockStr}</span>
            </div>

            {/* Notification Bell with Badge */}
            <button
              type="button"
              id="header-notification-bell"
              onClick={() => setActivePage('notifications')}
              style={{
                position: 'relative',
                background: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#94A3B8',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = '#FFFFFF';
                e.currentTarget.style.borderColor = '#38BDF8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = '#94A3B8';
                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)';
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              {unreadCount > 0 && (
                <span
                  style={{
                    position: 'absolute',
                    top: '-2px',
                    right: '-2px',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: '#EF4444',
                    boxShadow: '0 0 6px #EF4444',
                  }}
                />
              )}
            </button>

            {/* Language Switcher */}
            <LanguageSelector compact />

            {/* Theme Toggle */}
            <ThemeToggle compact />

            {/* User Avatar Circle */}
            <div
              onClick={() => setActivePage('settings')}
              role="button"
              tabIndex={0}
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #3B82F6, #1E40AF)',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.88rem',
                fontWeight: 700,
                cursor: 'pointer',
                border: '2px solid rgba(255, 255, 255, 0.12)',
              }}
            >
              {userInitial}
            </div>
          </div>
        </header>

        {/* Page Body Viewport — Independently Scrolling Right Content */}
        <main className="enterprise-main-content">
          {children}
        </main>
      </div>

      {/* Mobile Drawer Navigation */}
      {mobileMenuOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            zIndex: 100,
            display: 'flex',
          }}
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            style={{
              width: '270px',
              backgroundColor: '#0B0F19',
              height: '100%',
              padding: '1.25rem 1rem 1rem 1rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', paddingBottom: '0.75rem', borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '8px',
                      background: 'linear-gradient(135deg, #00C9FF, #0072FF)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: '0 0 12px rgba(0, 201, 255, 0.4)',
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-label="DeepVision Surveillance Camera Emblem">
                      <path d="M4 17.5v3.5h5" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M2.5 7.5h13l4.5 3" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M2.5 9h11.5l4 3v3l-4 3H2.5a1.5 1.5 0 0 1-1.5-1.5v-6A1.5 1.5 0 0 1 2.5 9z" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <circle cx="7.5" cy="13.5" r="2.2" stroke="#00F5D4" strokeWidth="1.8" />
                      <circle cx="7.5" cy="13.5" r="0.8" fill="#00F5D4" />
                      <line x1="19.5" y1="13.5" x2="22.5" y2="13.5" stroke="#00F5D4" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </div>
                  <span style={{ fontSize: '1.15rem', fontWeight: 800, color: '#FFFFFF' }}>
                    {t('brand.name', 'DeepVision')}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#94A3B8',
                    cursor: 'pointer',
                    padding: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  aria-label="Close menu"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {navItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={item.onClick}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      width: '100%',
                      padding: '10px 14px',
                      borderRadius: '8px',
                      border: 'none',
                      background: item.active
                        ? 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)'
                        : 'transparent',
                      color: item.active ? '#FFFFFF' : '#94A3B8',
                      fontSize: '0.9rem',
                      fontWeight: item.active ? 700 : 500,
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    {item.icon}
                    <span style={{ flex: 1 }}>{item.label}</span>
                    {Boolean(item.badge && item.badge > 0) && (
                      <span
                        style={{
                          background: '#EF4444',
                          color: '#FFFFFF',
                          fontSize: '0.68rem',
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: '10px',
                        }}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Mobile User Account Bar permanently anchored at bottom */}
            <div
              style={{
                paddingTop: '1rem',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '10px',
                flexShrink: 0,
                marginTop: 'auto',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #3B82F6, #1E40AF)',
                    color: '#FFFFFF',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  {userInitial}
                </div>
                <div style={{ overflow: 'hidden' }}>
                  <div
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#F8FAFC',
                      whiteSpace: 'nowrap',
                      textOverflow: 'ellipsis',
                      overflow: 'hidden',
                    }}
                  >
                    {user?.full_name || t('common.operator', 'Operator')}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: '#64748B', textTransform: 'capitalize' }}>
                    {user?.role === 'admin' ? t('common.admin', 'Administrator') : t('common.surveillance', 'Surveillance')}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                title={t('auth.signOut', 'Sign Out')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748B',
                  cursor: 'pointer',
                  padding: '6px',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AppLayout;
