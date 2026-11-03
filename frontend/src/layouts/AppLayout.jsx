import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTranslation } from '../i18n/i18nContext';
import LanguageSelector from '../components/common/LanguageSelector';
import ThemeToggle from '../components/common/ThemeToggle';
import useNotifications from '../hooks/useNotifications';
import Footer from '../components/common/Footer';

export function AppLayout({ children, activePage, pageParams, setActivePage }) {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const { unreadCount } = useNotifications();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [clockStr, setClockStr] = useState('');
  const profileMenuRef = useRef(null);

  // Digital Live HUD Clock matching Figure 7.1.2 ("Nov 01, 2026 11:24 AM")
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const mon = months[now.getMonth()];
      const day = String(now.getDate()).padStart(2, '0');
      const yr = now.getFullYear();
      let hrs = now.getHours();
      const ampm = hrs >= 12 ? 'PM' : 'AM';
      hrs = hrs % 12 || 12;
      const min = String(now.getMinutes()).padStart(2, '0');
      setClockStr(`${mon} ${day}, ${yr} ${hrs}:${min} ${ampm}`);
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

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

  // Active navigation detection: strictly 5 primary destinations
  const isDashboard = activePage === 'dashboard' || activePage === 'overview';
  const isCameras = activePage === 'cameras' || activePage === 'surveillance' || activePage === 'live';
  const isNotifications = activePage === 'notifications' || activePage === 'alerts' || activePage === 'recordings' || activePage === 'evidence' || activePage === 'cases';
  const isSettings = activePage === 'settings';
  const isHelp = activePage === 'help' || activePage === 'support';

  // Strictly 5 Primary Navigation Items
  const navItems = [
    {
      id: 'dashboard',
      label: t('nav.dashboard', 'Dashboard'),
      active: isDashboard,
      onClick: () => setActivePage('dashboard'),
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
      onClick: () => setActivePage('cameras'),
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
      onClick: () => setActivePage('notifications'),
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
      onClick: () => setActivePage('settings'),
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
      onClick: () => setActivePage('help'),
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
    <div className="deepvision-enterprise-shell" style={{
      display: 'flex',
      minHeight: '100vh',
      backgroundColor: '#070b13',
      color: '#f8fafc',
      fontFamily: 'var(--font-sans, system-ui, sans-serif)',
    }}>
      {/* 1. Left Vertical Sidebar (Desktop) matching Figure 7.1.2 */}
      <aside className="enterprise-sidebar" style={{
        width: '215px',
        backgroundColor: '#0a0f1d',
        borderRight: '1px solid #162035',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        height: '100vh',
        zIndex: 50,
      }}>
        <div>
          {/* Logo Brand Header */}
          <div
            onClick={() => setActivePage('dashboard')}
            role="button"
            tabIndex={0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '1.25rem 1.25rem 1.5rem 1.25rem',
              cursor: 'pointer',
              borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
            }}
          >
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #2563eb, #38bdf8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 10px rgba(37, 99, 235, 0.35)',
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2">
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <span style={{ fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
              DeepVision
            </span>
          </div>

          {/* Navigation Links */}
          <nav style={{ padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                    padding: '9px 14px',
                    borderRadius: '8px',
                    border: 'none',
                    background: active ? '#2563eb' : 'transparent',
                    color: active ? '#ffffff' : '#94a3b8',
                    fontSize: '0.88rem',
                    fontWeight: active ? 700 : 500,
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background 0.15s, color 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                      e.currentTarget.style.color = '#f8fafc';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.background = 'transparent';
                      e.currentTarget.style.color = '#94a3b8';
                    }
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', opacity: active ? 1 : 0.85 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span style={{
                      background: '#ef4444',
                      color: '#fff',
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      padding: '1px 6px',
                      borderRadius: '10px',
                    }}>
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        
      </aside>

            {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          id="mobile-drawer-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            zIndex: 1000,
            display: 'flex',
          }}
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            id="mobile-drawer-content"
            style={{
              width: '280px',
              maxWidth: '80%',
              backgroundColor: '#0a0f1d',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              padding: '16px',
              gap: '12px',
              boxShadow: '4px 0 20px rgba(0, 0, 0, 0.6)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: '12px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
              <span style={{ fontWeight: 800, fontSize: '1.1rem', color: '#fff' }}>DeepVision</span>
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.2rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {navItems.map((item) => (
                <button
                  key={`mobile-${item.id}`}
                  id={`mobile-nav-${item.id}`}
                  type="button"
                  onClick={() => {
                    item.onClick();
                    setMobileMenuOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: 'none',
                    background: item.active ? '#2563eb' : 'transparent',
                    color: item.active ? '#ffffff' : '#94a3b8',
                    fontSize: '0.90rem',
                    fontWeight: item.active ? 700 : 500,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  {item.icon}
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {Boolean(item.badge && item.badge > 0) && (
                    <span style={{ background: '#ef4444', color: '#fff', fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '10px' }}>
                      {item.badge}
                    </span>
                  )}
                </button>
              ))}
            </nav>
          </div>
        </div>
      )}

      {/* 2. Main Viewport Area */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        backgroundColor: '#070b13',
      }}>
        {/* Top Header matching Figure 7.1.2 */}
        <header style={{
          height: '56px',
          backgroundColor: '#0a0f1d',
          borderBottom: '1px solid #162035',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}>
          {/* Left: Mobile hamburger & breadcrumb */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              type="button"
              className="mobile-hamburger"
              onClick={() => setMobileMenuOpen(true)}
              style={{
                display: 'none',
                background: 'none',
                border: 'none',
                color: '#fff',
                cursor: 'pointer',
                padding: '4px',
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
          </div>

          {/* Right Controls: Datetime, Language, Notification Bell, User Avatar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            {/* Live Datetime Pill matching Figure 7.1.2 ("Nov 01, 2026 11:24 AM") */}
            <div style={{
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '6px',
              padding: '4px 12px',
              fontSize: '0.80rem',
              color: '#94a3b8',
              fontFamily: 'monospace',
              fontWeight: 600,
            }}>
              {clockStr}
            </div>

            {/* Language Selector (EN / HI / KN) */}
            <LanguageSelector compact />

            {/* Notification Bell Icon */}
            <div
              onClick={() => setActivePage('notifications', { tab: 'incidents' })}
              role="button"
              tabIndex={0}
              style={{
                position: 'relative',
                width: '32px',
                height: '32px',
                borderRadius: '6px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: '#94a3b8',
              }}
              title="Notifications"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
              </svg>
              {unreadCount > 0 && (
                <span style={{
                  position: 'absolute',
                  top: '-3px',
                  right: '-3px',
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: '#ef4444',
                }} />
              )}
            </div>

            {/* User Profile Avatar with dropdown */}
            <div ref={profileMenuRef} style={{ position: 'relative' }}>
              <div
                onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
                role="button"
                tabIndex={0}
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #38bdf8, #2563eb)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  color: '#fff',
                  cursor: 'pointer',
                  border: '2px solid #162035',
                }}
                title={user?.email || 'User Profile'}
              >
                {userInitial}
              </div>

              {profileDropdownOpen && (
                <div style={{
                  position: 'absolute',
                  top: '42px',
                  right: 0,
                  width: '210px',
                  background: '#111827',
                  border: '1px solid #1f293d',
                  borderRadius: '8px',
                  boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
                  padding: '8px',
                  zIndex: 100,
                }}>
                  <div style={{ padding: '8px 10px', borderBottom: '1px solid #1f293d' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#f8fafc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {user?.full_name || 'Operator'}
                    </div>
                    <div style={{ fontSize: '0.74rem', color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {user?.email || 'vaibhav@deepvision.ai'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => { setProfileDropdownOpen(false); logout(); }}
                    style={{
                      width: '100%',
                      background: 'none',
                      border: 'none',
                      padding: '8px 10px',
                      color: '#ef4444',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      textAlign: 'left',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      marginTop: '4px',
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
                    onMouseLeave={(e) => e.currentTarget.style.background = 'none'}
                  >
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main style={{
          flex: 1,
          padding: '24px 28px 48px 28px',
          overflowY: 'auto',
        }}>
          {children}
        </main>

        <Footer />
      </div>
    </div>
  );
}

export default AppLayout;
