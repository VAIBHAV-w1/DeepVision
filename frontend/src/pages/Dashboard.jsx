import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { useTranslation } from '../i18n/i18nContext';

/**
 * DeepVision 4.0 — Dashboard
 * Exact visual reconstruction of Figure 7.1.2: DeepVision Dashboard Interface.
 */
export function Dashboard({ onNavigate }) {
  const { t } = useTranslation();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.dashboard.getStats();
      setStats(data);
    } catch (err) {
      console.warn('Dashboard fetch stats error, using dynamic baseline:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const timer = setInterval(fetchStats, 8000);
    return () => clearInterval(timer);
  }, [fetchStats]);

  // Derived metrics from genuine backend API
  const totalCameras = stats ? (stats.total_cameras ?? stats.cameras?.length ?? 0) : 0;
  const onlineCameras = stats ? (stats.online_cameras ?? stats.cameras?.filter((c) => c.status === 'online').length ?? 0) : 0;
  const offlineCameras = stats ? (stats.offline_cameras ?? Math.max(0, totalCameras - onlineCameras)) : 0;
  const events24h = stats ? (stats.events_24h ?? stats.new_alerts_count ?? 0) : 0;
  const onlinePct = totalCameras > 0 ? Math.round((onlineCameras / totalCameras) * 100) : 0;

  // System Health telemetry
  const cpuVal = stats?.system_health?.cpu ?? 0;
  const memVal = stats?.system_health?.memory ?? 0;
  const storageVal = stats?.system_health?.storage ?? 0;
  const fpsVal = stats?.system_health?.fps ?? 0;

  // Genuine Recent Events list from backend
  const recentEvents = (stats?.recent_alerts || []).slice(0, 5).map((a) => {
    let relativeTime = t('dashboard.justNow', 'Just now');
    if (a.detected_at) {
      try {
        const diffMs = Date.now() - new Date(a.detected_at).getTime();
        const diffMin = Math.max(1, Math.floor(diffMs / 60000));
        relativeTime = diffMin < 60
          ? t('dashboard.minAgo', '{count} min ago', { count: diffMin })
          : t('dashboard.hAgo', '{count}h ago', { count: Math.floor(diffMin / 60) });
      } catch (_) {
        relativeTime = t('dashboard.recent', 'Recent');
      }
    }

    let title = a.title || 'Security Event Detected';
    const lower = (a.title || a.event_type || '').toLowerCase();
    if (lower.includes('intrusion') || lower.includes('restricted')) {
      title = t('dashboard.intrusionDetected', 'Intrusion Detected');
    } else if (lower.includes('unusual') || lower.includes('fall')) {
      title = t('dashboard.unusualActivity', 'Unusual Activity');
    } else if (lower.includes('person') || lower.includes('loitering')) {
      title = t('dashboard.personDetected', 'Person Detected');
    } else if (lower.includes('motion') || lower.includes('movement')) {
      title = t('dashboard.motionDetected', 'Motion Detected');
    } else if (lower.includes('object') || lower.includes('bag')) {
      title = t('dashboard.objectLeft', 'Object Left (Bag)');
    } else {
      title = t('dashboard.securityEventDetected', 'Security Event Detected');
    }

    return {
      id: a.id,
      title,
      camera: a.camera_name || (a.camera_id ? `Cam-0${a.camera_id}` : 'System'),
      time: a.relative_time || relativeTime,
      severity: (a.severity || 'medium').toLowerCase(),
    };
  });

  // SVG Donut Calculations
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const onlineStroke = (onlinePct / 100) * circumference;
  const offlineStroke = circumference - onlineStroke;

  const formatEventTitle = (rawTitle) => {
    if (!rawTitle) return t('notifications.modalAlertDetails', 'Security Alert');
    const s = String(rawTitle).trim();
    const l = s.toLowerCase();
    if (l.includes('unusual movement')) return t('alerts.unusualMovementPerson', 'Unusual Movement Detected (Person)');
    if (l.includes('loitering')) return t('alerts.loiteringPerson', 'Loitering Detected (Person)');
    if (l.includes('unusual activity')) return t('alerts.unusualActivityPerson', 'Unusual Activity Detected (Person)');
    if (l.includes('intrusion')) return t('dashboard.intrusionDetected', 'Intrusion Detected');
    if (l.includes('person detected')) return t('alerts.personDetected', 'Person Detected');
    if (l.includes('object left') || l.includes('bag')) return t('alerts.objectLeftBag', 'Object Left (Bag)');
    if (l.includes('motion detected') || l.includes('motion')) return t('alerts.motionDetected', 'Motion Detected');
    if (l.includes('fall')) return t('dashboard.fallDetected', 'Fall Detected');
    return s;
  };

  const formatCameraName = (rawName) => {
    if (!rawName) return 'Cam-01';
    const s = String(rawName).trim();
    if (s.toLowerCase() === 'webcam 0') return t('cameras.webcam0', 'Webcam 0');
    return s;
  };

  const handleNavigateCameras = () => {
    if (onNavigate) onNavigate('cameras');
    else window.location.hash = '#cameras';
  };

  const handleNavigateAlerts = () => {
    if (onNavigate) onNavigate('notifications');
    else window.location.hash = '#notifications';
  };

  return (
    <div
      className="dashboard-container"
      style={{
        maxWidth: '1440px',
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px',
        color: '#F8FAFC',
        fontFamily: 'var(--font-sans, system-ui, -apple-system, sans-serif)',
      }}
    >
      {/* 1. Header Row matching Figure 7.1.2 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1
            id="dashboard-heading"
            style={{
              fontSize: '1.6rem',
              fontWeight: 800,
              color: '#FFFFFF',
              margin: '0 0 4px 0',
              letterSpacing: '-0.02em',
            }}
          >
            {t('dashboard.title', 'Dashboard')}
          </h1>
          <p
            id="dashboard-subtitle"
            style={{
              fontSize: '0.88rem',
              color: '#94A3B8',
              margin: 0,
            }}
          >
            {t('dashboard.overviewSubtitle', 'Overview of your surveillance system')}
          </p>
        </div>
      </div>

      {/* 2. Four Stat Cards Row matching Figure 7.1.2 */}
      <div
        className="dashboard-stat-cards-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        {/* Card 1: Total Cameras */}
        <div
          onClick={handleNavigateCameras}
          role="button"
          tabIndex={0}
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem 1.4rem',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              backgroundColor: '#1E1B4B',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#818CF8" strokeWidth="2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
          </div>
          <div>
            <div id="metric-total-cameras" style={{ fontSize: '1.9rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>
              {totalCameras}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 600, marginTop: '4px' }}>
              {t('dashboard.totalCameras', 'Total Cameras')}
            </div>
          </div>
        </div>

        {/* Card 2: Online */}
        <div
          onClick={handleNavigateCameras}
          role="button"
          tabIndex={0}
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem 1.4rem',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              backgroundColor: '#064E3B',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#34D399" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div>
            <div id="metric-online-cameras" style={{ fontSize: '1.9rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>
              {onlineCameras}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 600, marginTop: '4px' }}>
              {t('dashboard.online', 'Online')}
            </div>
          </div>
        </div>

        {/* Card 3: Offline */}
        <div
          onClick={handleNavigateCameras}
          role="button"
          tabIndex={0}
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem 1.4rem',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              backgroundColor: '#450A0A',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </div>
          <div>
            <div id="metric-offline-cameras" style={{ fontSize: '1.9rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>
              {offlineCameras}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 600, marginTop: '4px' }}>
              {t('dashboard.offline', 'Offline')}
            </div>
          </div>
        </div>

        {/* Card 4: Events (24h) */}
        <div
          onClick={handleNavigateAlerts}
          role="button"
          tabIndex={0}
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.25rem 1.4rem',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            cursor: 'pointer',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              backgroundColor: '#451A03',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FBBF24" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div>
            <div id="metric-events-24h" style={{ fontSize: '1.9rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>
              {events24h}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 600, marginTop: '4px' }}>
              {t('dashboard.events24h', 'Events (24h)')}
            </div>
          </div>
        </div>
      </div>

      {/* 3. Center Section: Camera Status & Recent Events matching Figure 7.1.2 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))',
          gap: '20px',
        }}
      >
        {/* Left: Camera Status (75% Online Donut Chart) */}
        <div
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <h2 style={{ fontSize: '1rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 1.5rem 0' }}>
            {t('dashboard.cameraStatus', 'Camera Status')}
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3rem', flexWrap: 'wrap' }}>
            {/* SVG Donut Chart */}
            <div style={{ position: 'relative', width: '130px', height: '130px' }}>
              <svg width="130" height="130" viewBox="0 0 130 130">
                {/* Background Track */}
                <circle
                  cx="65"
                  cy="65"
                  r={radius}
                  fill="transparent"
                  stroke="#1E293B"
                  strokeWidth="12"
                />
                {/* Red Offline Arc */}
                <circle
                  cx="65"
                  cy="65"
                  r={radius}
                  fill="transparent"
                  stroke="#EF4444"
                  strokeWidth="12"
                  strokeDasharray={`${circumference} ${circumference}`}
                  strokeDashoffset="0"
                  transform="rotate(-90 65 65)"
                />
                {/* Green Online Arc */}
                <circle
                  cx="65"
                  cy="65"
                  r={radius}
                  fill="transparent"
                  stroke="#10B981"
                  strokeWidth="12"
                  strokeDasharray={`${onlineStroke} ${circumference}`}
                  strokeDashoffset="0"
                  transform="rotate(-90 65 65)"
                  strokeLinecap="round"
                />
              </svg>
              {/* Text inside donut */}
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <span id="donut-percentage" style={{ fontSize: '1.4rem', fontWeight: 800, color: '#FFFFFF', lineHeight: 1 }}>
                  {onlinePct}%
                </span>
                <span style={{ fontSize: '0.72rem', color: '#10B981', fontWeight: 700, marginTop: '2px' }}>
                  {t('common.online', 'Online')}
                </span>
              </div>
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#10B981' }} />
                <span style={{ fontSize: '0.88rem', color: '#CBD5E1', fontWeight: 600 }}>
                  {t('dashboard.onlineCount', 'Online ({count})', { count: onlineCameras })}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#EF4444' }} />
                <span style={{ fontSize: '0.88rem', color: '#CBD5E1', fontWeight: 600 }}>
                  {t('dashboard.offlineCount', 'Offline ({count})', { count: offlineCameras })}
                </span>
              </div>
            </div>
          </div>
          <div style={{ height: '10px' }} />
        </div>

        {/* Right: Recent Events matching Figure 7.1.2 */}
        <div
          style={{
            backgroundColor: '#0F172A',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 700, color: '#FFFFFF', margin: 0 }}>
              {t('dashboard.recentEvents', 'Recent Events')}
            </h2>
            <button
              type="button"
              onClick={handleNavigateAlerts}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#38BDF8',
                fontSize: '0.84rem',
                fontWeight: 600,
                cursor: 'pointer',
                padding: 0,
              }}
            >
              {t('dashboard.viewAll', 'View All')}
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {recentEvents.length > 0 ? (
              recentEvents.map((ev) => (
                <div
                  key={ev.id}
                  onClick={handleNavigateAlerts}
                  role="button"
                  tabIndex={0}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    backgroundColor: '#090E1A',
                    border: '1px solid rgba(255, 255, 255, 0.04)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#090E1A')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {ev.severity === 'high' ? (
                      <span style={{ color: '#EF4444' }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                          <line x1="12" y1="9" x2="12" y2="13" />
                          <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                      </span>
                    ) : ev.severity === 'medium' ? (
                      <span style={{ color: '#F59E0B' }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="12" y1="8" x2="12" y2="12" />
                          <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                      </span>
                    ) : (
                      <span style={{ color: '#38BDF8' }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                          <circle cx="12" cy="7" r="4" />
                        </svg>
                      </span>
                    )}
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#F8FAFC' }}>
                      {formatEventTitle(ev.title)}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <span style={{ fontSize: '0.82rem', color: '#94A3B8', fontWeight: 500 }}>
                      {formatCameraName(ev.camera)}
                    </span>
                    <span style={{ fontSize: '0.78rem', color: '#64748B' }}>
                      {ev.time}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ padding: '24px 16px', textAlign: 'center', color: '#94A3B8', fontSize: '0.86rem' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5" style={{ display: 'block', margin: '0 auto 8px' }}>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span>{t('dashboard.noEvents', 'No recent security events recorded in the last 24 hours.')}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 4. Bottom Row: System Health matching Figure 7.1.2 */}
      <div
        style={{
          backgroundColor: '#0F172A',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '12px',
          padding: '1.25rem 1.5rem',
        }}
      >
        <h2 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 1rem 0' }}>
          {t('dashboard.systemHealth', 'System Health')}
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
          }}
        >
          {/* CPU Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#090E1A', padding: '10px 14px', borderRadius: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" strokeWidth="2">
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="9" y="9" width="6" height="6" />
              <line x1="9" y1="1" x2="9" y2="4" />
              <line x1="15" y1="1" x2="15" y2="4" />
              <line x1="9" y1="20" x2="9" y2="23" />
              <line x1="15" y1="20" x2="15" y2="23" />
              <line x1="20" y1="9" x2="23" y2="9" />
              <line x1="20" y1="15" x2="23" y2="15" />
              <line x1="1" y1="9" x2="4" y2="9" />
              <line x1="1" y1="15" x2="4" y2="15" />
            </svg>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '4px' }}>
                <span style={{ color: '#94A3B8' }}>{t('dashboard.cpu', 'CPU')}</span>
                <span style={{ color: '#F8FAFC', fontWeight: 600 }}>{cpuVal}%</span>
              </div>
              <div style={{ height: '4px', backgroundColor: '#1E293B', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ width: `${cpuVal}%`, height: '100%', backgroundColor: '#38BDF8' }} />
              </div>
            </div>
          </div>

          {/* Memory Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#090E1A', padding: '10px 14px', borderRadius: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818CF8" strokeWidth="2">
              <rect x="2" y="6" width="20" height="12" rx="2" />
              <line x1="6" y1="10" x2="6" y2="14" />
              <line x1="10" y1="10" x2="10" y2="14" />
              <line x1="14" y1="10" x2="14" y2="14" />
              <line x1="18" y1="10" x2="18" y2="14" />
            </svg>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '4px' }}>
                <span style={{ color: '#94A3B8' }}>{t('dashboard.memory', 'Memory')}</span>
                <span style={{ color: '#F8FAFC', fontWeight: 600 }}>{memVal}%</span>
              </div>
              <div style={{ height: '4px', backgroundColor: '#1E293B', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ width: `${memVal}%`, height: '100%', backgroundColor: '#818CF8' }} />
              </div>
            </div>
          </div>

          {/* Storage Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#090E1A', padding: '10px 14px', borderRadius: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#34D399" strokeWidth="2">
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
              <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
            </svg>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '4px' }}>
                <span style={{ color: '#94A3B8' }}>{t('dashboard.storage', 'Storage')}</span>
                <span style={{ color: '#F8FAFC', fontWeight: 600 }}>{storageVal}%</span>
              </div>
              <div style={{ height: '4px', backgroundColor: '#1E293B', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ width: `${storageVal}%`, height: '100%', backgroundColor: '#34D399' }} />
              </div>
            </div>
          </div>

          {/* FPS Gauge Indicator matching Figure 7.1.2 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', backgroundColor: '#090E1A', padding: '10px 14px', borderRadius: '8px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <span style={{ fontSize: '0.84rem', color: '#94A3B8', fontWeight: 600 }}>{t('dashboard.fpsGauge', 'Inference FPS')}</span>
              <span
                id="gauge-fps"
                style={{
                  fontSize: '0.9rem',
                  fontWeight: 800,
                  color: '#10B981',
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  padding: '2px 8px',
                  borderRadius: '6px',
                }}
              >
                {t('dashboard.fps', 'FPS')} {fpsVal}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
