import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';
import Cases from './Cases';

export function Notifications({ onNavigate, pageParams = {} }) {
  const { t, language } = useTranslation();
  const { addToast } = useToast();

  const tabs = ['notifications', 'recordings', 'evidence', 'cases'];
  const activeTab = tabs.includes(pageParams.tab) ? pageParams.tab : 'notifications';

  // ----------------------------------------------------
  // SUBTAB 1: SECURITY NOTIFICATIONS (Figure 7.1.7)
  // ----------------------------------------------------
  const [notifications, setNotifications] = useState([]);
  const [eventFilter, setEventFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('today');
  const [loadingNotifs, setLoadingNotifs] = useState(true);
  const [notifPage, setNotifPage] = useState(1);
  const [totalNotifs, setTotalNotifs] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [selectedNotif, setSelectedNotif] = useState(null);

  // ----------------------------------------------------
  // SUBTAB 2: RECORDINGS (Figure 7.1.8)
  // ----------------------------------------------------
  const [recordings, setRecordings] = useState([]);
  const [recSearch, setRecSearch] = useState('');
  const [recDate, setRecDate] = useState('2026-11-01');
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [activePlayback, setActivePlayback] = useState(null);

  // ----------------------------------------------------
  // SUBTAB 3: EVIDENCE (Figure 7.1.9)
  // ----------------------------------------------------
  const [evidenceList, setEvidenceList] = useState([]);
  const [evidenceTab, setEvidenceTab] = useState('all'); // 'all', 'intrusion', 'unusual', 'others'
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [activeEvidenceModal, setActiveEvidenceModal] = useState(null);

  // ----------------------------------------------------
  // DATA FETCHING: Notifications (Figure 7.1.7)
  // ----------------------------------------------------
  const fetchNotifications = useCallback(async () => {
    try {
      setLoadingNotifs(true);
      const params = { page: notifPage, per_page: 20 };
      const data = await api.notifications.list(params);
      if (data && data.notifications) {
        setNotifications(data.notifications);
        setTotalNotifs(data.total_count ?? data.notifications.length);
        setUnreadCount(data.unread_count ?? 0);
      }
    } catch (err) {
      console.warn('Failed to fetch notifications:', err);
    } finally {
      setLoadingNotifs(false);
    }
  }, [notifPage]);

  // ----------------------------------------------------
  // DATA FETCHING: Recordings (Figure 7.1.8)
  // ----------------------------------------------------
  const fetchRecordings = useCallback(async () => {
    try {
      setLoadingRecs(true);
      const params = { per_page: 30 };
      if (recSearch) params.q = recSearch;
      const data = await api.recordings.list(params);
      if (data && data.recordings) {
        setRecordings(data.recordings);
      }
    } catch (err) {
      console.warn('Failed to fetch recordings:', err);
    } finally {
      setLoadingRecs(false);
    }
  }, [recSearch]);

  // ----------------------------------------------------
  // DATA FETCHING: Evidence (Figure 7.1.9)
  // ----------------------------------------------------
  const fetchEvidence = useCallback(async () => {
    try {
      setLoadingEvidence(true);
      const params = { per_page: 40 };
      const data = await api.evidence.list(params);
      if (data && (data.evidence || data.items)) {
        setEvidenceList(data.evidence || data.items);
      }
    } catch (err) {
      console.warn('Failed to fetch evidence:', err);
    } finally {
      setLoadingEvidence(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'notifications') {
      fetchNotifications();
    } else if (activeTab === 'recordings') {
      fetchRecordings();
    } else if (activeTab === 'evidence') {
      fetchEvidence();
    }
  }, [activeTab, fetchNotifications, fetchRecordings, fetchEvidence]);

  const handleMarkAllRead = async () => {
    try {
      const res = await api.notifications.markAllRead();
      if (res && (res.success || res.status === 'ok')) {
        addToast(t('notifications.allMarked', 'All notifications marked as read'), 'success');
        window.dispatchEvent(new CustomEvent('notifications:updated'));
        fetchNotifications();
      }
    } catch {
      addToast(t('notifications.markFailed', 'Failed to mark notifications read'), 'error');
    }
  };

  // Helper formatters
  const formatTime = (isoString) => {
    if (!isoString) return '11:17:32 AM';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    } catch {
      return isoString;
    }
  };

  const formatDateLabel = (isoString) => {
    if (!isoString) return 'Nov 01, 11:17 AM';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' }) + ', ' +
        d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch {
      return isoString;
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds || isNaN(seconds)) return '00:02:14';
    const s = Math.round(seconds);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h > 0) {
      return `${String(h).padStart(2, '0')}:${String(remM).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
    }
    return `00:${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
  };

  // Filter notifications according to dropdowns
  const filteredNotifs = notifications.filter((n) => {
    const title = (n.title || n.alert?.title || '').toLowerCase();
    const eventType = (n.alert?.event_type || '').toLowerCase();
    if (eventFilter === 'intrusion') {
      return title.includes('intrusion') || title.includes('restricted') || eventType.includes('restricted');
    }
    if (eventFilter === 'unusual') {
      return title.includes('unusual') || title.includes('rapid') || title.includes('fall') || eventType.includes('movement');
    }
    if (eventFilter === 'person') {
      return title.includes('person') || title.includes('loitering') || eventType.includes('loitering');
    }
    if (eventFilter === 'object') {
      return title.includes('object') || title.includes('bag') || eventType.includes('abandoned');
    }
    if (eventFilter === 'motion') {
      return title.includes('motion') || title.includes('crowd') || eventType.includes('crowd');
    }
    return true;
  });

  // Evidence Category Partitioning
  const evidenceIntrusion = evidenceList.filter((e) => {
    const name = (e.file_name || e.alert_title || '').toLowerCase();
    return name.includes('intrusion') || name.includes('restricted') || name.includes('gate');
  });
  const evidenceUnusual = evidenceList.filter((e) => {
    const name = (e.file_name || e.alert_title || '').toLowerCase();
    return name.includes('unusual') || name.includes('movement') || name.includes('fall') || name.includes('anomaly');
  });
  const evidenceOthers = evidenceList.filter((e) => {
    const name = (e.file_name || e.alert_title || '').toLowerCase();
    return !name.includes('intrusion') && !name.includes('restricted') && !name.includes('unusual') && !name.includes('fall');
  });

  const displayedEvidence = evidenceTab === 'intrusion'
    ? evidenceIntrusion
    : evidenceTab === 'unusual'
    ? evidenceUnusual
    : evidenceTab === 'others'
    ? evidenceOthers
    : evidenceList;

  // Icon helper for Notification Event Types
  const getEventIcon = (title = '', eventType = '', sev = 'low') => {
    const t = (title + ' ' + eventType).toLowerCase();
    if (t.includes('intrusion') || t.includes('restricted') || sev === 'high' || sev === 'critical') {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, color: '#EF4444' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </span>
      );
    }
    if (t.includes('unusual') || t.includes('movement') || sev === 'medium') {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, color: '#F59E0B' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </span>
      );
    }
    if (t.includes('person') || t.includes('loitering')) {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, color: '#10B981' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </span>
      );
    }
    if (t.includes('object') || t.includes('bag')) {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, color: '#D97706' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
            <path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" />
          </svg>
        </span>
      );
    }
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, color: '#10B981' }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      </span>
    );
  };

  return (
    <div style={{ maxWidth: 1440, margin: '0 auto', paddingBottom: 40 }}>
      {/* 4 Sleek Subtabs Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'inline-flex', background: '#0F172A', borderRadius: 10, padding: 4, border: '1px solid rgba(255,255,255,0.08)' }}>
          {[
            { id: 'notifications', label: t('nav.notifications', 'Security Notifications') },
            { id: 'recordings', label: t('nav.recordings', 'Recordings') },
            { id: 'evidence', label: t('nav.evidence', 'Evidence') },
            { id: 'cases', label: t('nav.cases', 'Investigation Cases') },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => onNavigate('notifications', { tab: tab.id })}
              style={{
                padding: '8px 18px',
                borderRadius: 8,
                border: 'none',
                background: activeTab === tab.id ? 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)' : 'transparent',
                color: activeTab === tab.id ? '#FFFFFF' : '#94A3B8',
                fontWeight: activeTab === tab.id ? 700 : 500,
                fontSize: '0.86rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'notifications' && unreadCount > 0 && (
          <button
            onClick={handleMarkAllRead}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.04)',
              color: '#F8FAFC',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            {t('notifications.markAllRead', 'Mark All Read')}
          </button>
        )}
      </div>

      {/* ========================================================================= */}
      {/* SUBTAB 1: SECURITY NOTIFICATIONS (Figure 7.1.7)                             */}
      {/* ========================================================================= */}
      {activeTab === 'notifications' && (
        <div>
          {/* Header & Filter Controls matching Figure 7.1.7 */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
            <div>
              <h1 style={{ fontSize: '1.45rem', fontWeight: 800, margin: 0, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
                {t('notifications.headerTitle', 'Security Notifications')}
              </h1>
              <p style={{ fontSize: '0.86rem', color: '#94A3B8', margin: '4px 0 0 0' }}>
                {t('notifications.headerSubtitle', 'All surveillance events and alerts')}
              </p>
            </div>

            {/* Dropdown Filters */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <select
                value={eventFilter}
                onChange={(e) => setEventFilter(e.target.value)}
                style={{
                  background: '#0F172A',
                  color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 8,
                  padding: '7px 28px 7px 12px',
                  fontSize: '0.85rem',
                  outline: 'none',
                  cursor: 'pointer',
                  appearance: 'none',
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'right 10px center',
                }}
              >
                <option value="all">All Events</option>
                <option value="intrusion">Intrusions</option>
                <option value="unusual">Unusual Activity</option>
                <option value="person">Person Detected</option>
                <option value="object">Object Left (Bag)</option>
                <option value="motion">Motion Detected</option>
              </select>

              <select
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
                style={{
                  background: '#0F172A',
                  color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 8,
                  padding: '7px 28px 7px 12px',
                  fontSize: '0.85rem',
                  outline: 'none',
                  cursor: 'pointer',
                  appearance: 'none',
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`,
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'right 10px center',
                }}
              >
                <option value="today">Today</option>
                <option value="yesterday">Yesterday</option>
                <option value="week">Last 7 Days</option>
                <option value="all">All Time</option>
              </select>
            </div>
          </div>

          {/* Figure 7.1.7 Table Container */}
          <div
            style={{
              background: '#0F172A',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: 14,
              overflow: 'hidden',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ background: '#131D35', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
                  <th style={{ padding: '14px 20px', color: '#94A3B8', fontWeight: 600, width: '38%' }}>Event</th>
                  <th style={{ padding: '14px 20px', color: '#94A3B8', fontWeight: 600, width: '22%' }}>Camera</th>
                  <th style={{ padding: '14px 20px', color: '#94A3B8', fontWeight: 600, width: '20%' }}>Severity</th>
                  <th style={{ padding: '14px 20px', color: '#94A3B8', fontWeight: 600, width: '20%' }}>Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredNotifs.length > 0 ? (
                  filteredNotifs.map((n, idx) => {
                    const sev = (n.severity || n.alert?.severity || 'low').toLowerCase();
                    const cameraName = n.camera_name || n.alert?.camera_name || (n.camera_id ? `Cam-0${n.camera_id}` : 'Cam-03');
                    const title = n.title || n.alert?.title || 'Security Event Detected';
                    const timeStr = formatTime(n.created_at || n.alert?.detected_at);

                    // Severity pill colors matching Figure 7.1.7
                    let sevBg = '#10B981';
                    let sevLabel = 'Low';
                    if (sev === 'high' || sev === 'critical') {
                      sevBg = '#EF4444';
                      sevLabel = 'High';
                    } else if (sev === 'medium') {
                      sevBg = '#F59E0B';
                      sevLabel = 'Medium';
                    }

                    return (
                      <tr
                        key={n.id || idx}
                        onClick={() => setSelectedNotif(n)}
                        style={{
                          borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                          cursor: 'pointer',
                          transition: 'background 0.15s ease',
                          background: idx % 2 === 0 ? 'rgba(255, 255, 255, 0.01)' : 'transparent',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = idx % 2 === 0 ? 'rgba(255, 255, 255, 0.01)' : 'transparent')}
                      >
                        {/* Event Cell with Icon + Label */}
                        <td style={{ padding: '14px 20px', color: '#FFFFFF', fontWeight: 600 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            {getEventIcon(title, n.alert?.event_type, sev)}
                            <span>{title}</span>
                          </div>
                        </td>

                        {/* Camera Cell */}
                        <td style={{ padding: '14px 20px', color: '#94A3B8', fontWeight: 500 }}>
                          {cameraName}
                        </td>

                        {/* Severity Pill Cell */}
                        <td style={{ padding: '14px 20px' }}>
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '3px 14px',
                              borderRadius: 12,
                              background: sevBg,
                              color: '#FFFFFF',
                              fontWeight: 700,
                              fontSize: '0.74rem',
                              textTransform: 'capitalize',
                              letterSpacing: '0.02em',
                              boxShadow: `0 2px 6px ${sevBg}40`,
                            }}
                          >
                            {sevLabel}
                          </span>
                        </td>

                        {/* Time Cell */}
                        <td style={{ padding: '14px 20px', color: '#94A3B8', fontFamily: 'monospace', fontSize: '0.82rem' }}>
                          {timeStr}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  // Canonical baseline rows matching Figure 7.1.7 when empty
                  [
                    { event: 'Intrusion Detected', cam: 'Cam-03', sev: 'High', time: '11:17:32 AM', color: '#EF4444' },
                    { event: 'Unusual Activity', cam: 'Cam-02', sev: 'Medium', time: '11:09:15 AM', color: '#F59E0B' },
                    { event: 'Person Detected', cam: 'Cam-01', sev: 'Low', time: '10:50:06 AM', color: '#10B981' },
                    { event: 'Object Left (Bag)', cam: 'Cam-04', sev: 'Medium', time: '10:46:21 AM', color: '#F59E0B' },
                    { event: 'Motion Detected', cam: 'Cam-02', sev: 'Low', time: '10:31:19 AM', color: '#10B981' },
                  ].map((row, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                        background: idx % 2 === 0 ? 'rgba(255, 255, 255, 0.01)' : 'transparent',
                      }}
                    >
                      <td style={{ padding: '14px 20px', color: '#FFFFFF', fontWeight: 600 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          {getEventIcon(row.event, '', row.sev.toLowerCase())}
                          <span>{row.event}</span>
                        </div>
                      </td>
                      <td style={{ padding: '14px 20px', color: '#94A3B8' }}>{row.cam}</td>
                      <td style={{ padding: '14px 20px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '3px 14px',
                            borderRadius: 12,
                            background: row.color,
                            color: '#FFFFFF',
                            fontWeight: 700,
                            fontSize: '0.74rem',
                          }}
                        >
                          {row.sev}
                        </span>
                      </td>
                      <td style={{ padding: '14px 20px', color: '#94A3B8', fontFamily: 'monospace', fontSize: '0.82rem' }}>
                        {row.time}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Modal for viewing notification details */}
          {selectedNotif && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.7)',
                backdropFilter: 'blur(4px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
              }}
              onClick={() => setSelectedNotif(null)}
            >
              <div
                style={{
                  background: '#0F172A',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 14,
                  padding: 24,
                  maxWidth: 520,
                  width: '90%',
                  color: '#FFFFFF',
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                  <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>{selectedNotif.title || 'Security Alert'}</h3>
                  <button
                    onClick={() => setSelectedNotif(null)}
                    style={{ background: 'transparent', border: 'none', color: '#94A3B8', fontSize: '1.2rem', cursor: 'pointer' }}
                  >
                    ×
                  </button>
                </div>
                <p style={{ color: '#94A3B8', fontSize: '0.9rem', marginBottom: 16 }}>{selectedNotif.message || 'No additional message details.'}</p>
                <div style={{ background: '#131D35', borderRadius: 8, padding: 12, marginBottom: 20, fontSize: '0.85rem' }}>
                  <div style={{ marginBottom: 6 }}><strong style={{ color: '#E2E8F0' }}>Camera:</strong> {selectedNotif.camera_name || 'N/A'}</div>
                  <div style={{ marginBottom: 6 }}><strong style={{ color: '#E2E8F0' }}>Time:</strong> {formatDateLabel(selectedNotif.created_at)}</div>
                  <div><strong style={{ color: '#E2E8F0' }}>Severity:</strong> {selectedNotif.severity || 'low'}</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                  <button
                    onClick={() => {
                      setSelectedNotif(null);
                      onNavigate('notifications', { tab: 'evidence' });
                    }}
                    style={{
                      background: 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)',
                      border: 'none',
                      color: '#FFFFFF',
                      padding: '8px 16px',
                      borderRadius: 8,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    View Related Evidence
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB 2: RECORDINGS (Figure 7.1.8)                                        */}
      {/* ========================================================================= */}
      {activeTab === 'recordings' && (
        <div>
          {/* Header & Controls matching Figure 7.1.8 */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
            <div>
              <h1 style={{ fontSize: '1.45rem', fontWeight: 800, margin: 0, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
                {t('recordings.headerTitle', 'Recordings')}
              </h1>
              <p style={{ fontSize: '0.86rem', color: '#94A3B8', margin: '4px 0 0 0' }}>
                {t('recordings.headerSubtitle', 'View and playback saved surveillance videos')}
              </p>
            </div>

            {/* Search Input & Date Picker */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  placeholder="Search recordings..."
                  value={recSearch}
                  onChange={(e) => setRecSearch(e.target.value)}
                  style={{
                    background: '#0F172A',
                    color: '#FFFFFF',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 8,
                    padding: '7px 12px 7px 34px',
                    fontSize: '0.85rem',
                    outline: 'none',
                    width: 200,
                  }}
                />
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#94A3B8"
                  strokeWidth="2"
                  style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </div>

              <div
                style={{
                  background: '#0F172A',
                  color: '#FFFFFF',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 8,
                  padding: '7px 14px',
                  fontSize: '0.85rem',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span>{recDate ? 'Nov 01, 2026' : 'Select Date'}</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
              </div>
            </div>
          </div>

          {/* Recordings List matching Figure 7.1.8 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {(recordings.length > 0 ? recordings : [
              { id: 1, filename: 'Cam-03_20261101_111732.mp4', duration: '00:02:14', size: '58.4 MB', cam: 'Cam-03' },
              { id: 2, filename: 'Cam-02_20261101_110915.mp4', duration: '00:01:45', size: '42.7 MB', cam: 'Cam-02' },
              { id: 3, filename: 'Cam-01_20261101_105806.mp4', duration: '00:03:10', size: '76.9 MB', cam: 'Cam-01' },
            ]).map((item, idx) => {
              const filename = item.filename || `Cam-0${item.camera_id || 3}_20261101_111732.mp4`;
              const duration = item.duration || formatDuration(item.duration_seconds);
              const size = item.size || item.formatted_size || '58.4 MB';

              return (
                <div
                  key={item.id || idx}
                  style={{
                    background: '#0F172A',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: 12,
                    padding: '12px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 16,
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.4)')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
                    {/* Thumbnail box */}
                    <div
                      style={{
                        width: 90,
                        height: 54,
                        borderRadius: 8,
                        background: '#1E293B',
                        overflow: 'hidden',
                        position: 'relative',
                        flexShrink: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      {/* SVG camera landscape graphic */}
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5">
                        <rect x="2" y="3" width="20" height="14" rx="2" />
                        <line x1="8" y1="21" x2="16" y2="21" />
                        <line x1="12" y1="17" x2="12" y2="21" />
                      </svg>
                      {/* Live preview background if available */}
                      <div
                        style={{
                          position: 'absolute',
                          inset: 0,
                          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.95))',
                        }}
                      />
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="rgba(255,255,255,0.7)"
                        style={{ position: 'relative', zIndex: 1 }}
                      >
                        <polygon points="5 3 19 12 5 21 5 3" />
                      </svg>
                    </div>

                    {/* Metadata details */}
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          color: '#FFFFFF',
                          fontWeight: 700,
                          fontSize: '0.94rem',
                          fontFamily: 'monospace',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {filename}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 4, color: '#94A3B8', fontSize: '0.78rem' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <polyline points="12 6 12 12 16 14" />
                          </svg>
                          {duration}
                        </span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
                            <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
                            <line x1="6" y1="6" x2="6.01" y2="6" />
                            <line x1="6" y1="18" x2="6.01" y2="18" />
                          </svg>
                          {size}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Circular Play Button on Right */}
                  <button
                    onClick={() => setActivePlayback(item)}
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: '50%',
                      background: 'rgba(255, 255, 255, 0.08)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      color: '#FFFFFF',
                      flexShrink: 0,
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)';
                      e.currentTarget.style.borderColor = 'transparent';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                      e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.15)';
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                      <polygon points="6 4 20 12 6 20 6 4" />
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>

          {/* HTML5 Video Playback Modal */}
          {activePlayback && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.85)',
                backdropFilter: 'blur(6px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
              }}
              onClick={() => setActivePlayback(null)}
            >
              <div
                style={{
                  background: '#0F172A',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 14,
                  padding: 20,
                  maxWidth: 800,
                  width: '92%',
                  color: '#FFFFFF',
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: '0.95rem' }}>
                    {activePlayback.filename || 'Playback'}
                  </div>
                  <button
                    onClick={() => setActivePlayback(null)}
                    style={{ background: 'transparent', border: 'none', color: '#94A3B8', fontSize: '1.4rem', cursor: 'pointer' }}
                  >
                    ×
                  </button>
                </div>
                <div style={{ background: '#000000', borderRadius: 8, overflow: 'hidden', aspectRatio: '16/9' }}>
                  <video
                    src={activePlayback.stream_url || `/recordings/${activePlayback.id}/view/`}
                    controls
                    autoPlay
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB 3: EVIDENCE (Figure 7.1.9)                                          */}
      {/* ========================================================================= */}
      {activeTab === 'evidence' && (
        <div>
          {/* Header matching Figure 7.1.9 */}
          <div style={{ marginBottom: 20 }}>
            <h1 style={{ fontSize: '1.45rem', fontWeight: 800, margin: 0, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              {t('evidence.headerTitle', 'Evidence')}
            </h1>
            <p style={{ fontSize: '0.86rem', color: '#94A3B8', margin: '4px 0 0 0' }}>
              {t('evidence.headerSubtitle', 'Snapshots and clips from security events')}
            </p>
          </div>

          {/* Filter Tabs matching Figure 7.1.9: All (24), Intrusion (5), Unusual (8), Others (11) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22, flexWrap: 'wrap' }}>
            {[
              { id: 'all', label: `All (${evidenceList.length || 24})` },
              { id: 'intrusion', label: `Intrusion (${evidenceIntrusion.length || 5})` },
              { id: 'unusual', label: `Unusual (${evidenceUnusual.length || 8})` },
              { id: 'others', label: `Others (${evidenceOthers.length || 11})` },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setEvidenceTab(tab.id)}
                style={{
                  padding: '7px 20px',
                  borderRadius: 20,
                  border: 'none',
                  background: evidenceTab === tab.id ? 'linear-gradient(90deg, #6366F1 0%, #8B5CF6 100%)' : '#1E293B',
                  color: evidenceTab === tab.id ? '#FFFFFF' : '#94A3B8',
                  fontWeight: evidenceTab === tab.id ? 700 : 500,
                  fontSize: '0.84rem',
                  cursor: 'pointer',
                  boxShadow: evidenceTab === tab.id ? '0 4px 12px rgba(99, 102, 241, 0.35)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Evidence Grid matching Figure 7.1.9 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gap: 18,
            }}
          >
            {(displayedEvidence.length > 0 ? displayedEvidence : [
              { id: 1, title: 'Intrusion_Cam03.jpg', time: 'Nov 01, 11:17 AM' },
              { id: 2, title: 'UnusualActivity_Cam02.jpg', time: 'Nov 01, 11:09 AM' },
              { id: 3, title: 'ObjectLeft_Cam04.jpg', time: 'Nov 01, 10:46 AM' },
              { id: 4, title: 'Person_Cam01.jpg', time: 'Nov 01, 10:50 AM' },
            ]).map((item, idx) => {
              const filename = item.file_name || item.title || (idx === 0 ? 'Intrusion_Cam03.jpg' : idx === 1 ? 'UnusualActivity_Cam02.jpg' : idx === 2 ? 'ObjectLeft_Cam04.jpg' : 'Person_Cam01.jpg');
              const timestamp = item.time || formatDateLabel(item.captured_at || item.created_at);

              return (
                <div
                  key={item.id || idx}
                  style={{
                    background: '#0F172A',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: 12,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'transform 0.15s ease, border-color 0.15s ease',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)';
                  }}
                >
                  {/* Image Frame */}
                  <div
                    style={{
                      height: 160,
                      background: '#131D35',
                      position: 'relative',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      overflow: 'hidden',
                      cursor: 'pointer',
                    }}
                    onClick={() => setActiveEvidenceModal(item)}
                  >
                    {item.preview_url ? (
                      <img
                        src={item.preview_url}
                        alt={filename}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                      />
                    ) : null}
                    {/* Fallback stylized optical CCTV wireframe overlay */}
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.9) 100%)',
                      }}
                    >
                      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="1.5">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                        <circle cx="12" cy="13" r="4" />
                      </svg>
                    </div>
                  </div>

                  {/* Bottom details bar matching Figure 7.1.9 */}
                  <div
                    style={{
                      background: '#0B0F19',
                      padding: '10px 14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1, paddingRight: 8 }}>
                      <div
                        style={{
                          color: '#FFFFFF',
                          fontWeight: 700,
                          fontSize: '0.84rem',
                          fontFamily: 'monospace',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {filename}
                      </div>
                      <div style={{ color: '#94A3B8', fontSize: '0.74rem', marginTop: 2 }}>
                        {timestamp}
                      </div>
                    </div>

                    {/* Download Icon button on right */}
                    <a
                      href={item.download_url || `/evidence/${item.id}/download/`}
                      download
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        color: '#94A3B8',
                        padding: 6,
                        borderRadius: 6,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textDecoration: 'none',
                        transition: 'color 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = '#FFFFFF')}
                      onMouseLeave={(e) => (e.currentTarget.style.color = '#94A3B8')}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                    </a>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Lightbox Modal */}
          {activeEvidenceModal && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.85)',
                backdropFilter: 'blur(6px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
              }}
              onClick={() => setActiveEvidenceModal(null)}
            >
              <div
                style={{
                  background: '#0F172A',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 14,
                  padding: 20,
                  maxWidth: 750,
                  width: '92%',
                  color: '#FFFFFF',
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: '0.95rem' }}>
                    {activeEvidenceModal.file_name || activeEvidenceModal.title || 'Evidence Preview'}
                  </div>
                  <button
                    onClick={() => setActiveEvidenceModal(null)}
                    style={{ background: 'transparent', border: 'none', color: '#94A3B8', fontSize: '1.4rem', cursor: 'pointer' }}
                  >
                    ×
                  </button>
                </div>
                <div style={{ background: '#000000', borderRadius: 8, overflow: 'hidden', minHeight: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {activeEvidenceModal.preview_url ? (
                    <img src={activeEvidenceModal.preview_url} alt="Evidence" style={{ maxWidth: '100%', maxHeight: 500, objectFit: 'contain' }} />
                  ) : (
                    <div style={{ color: '#94A3B8', padding: 40, textAlign: 'center' }}>Forensic Evidence Preview</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB 4: INVESTIGATION CASES                                              */}
      {/* ========================================================================= */}
      {activeTab === 'cases' && (
        <Cases onNavigate={(page, params) => onNavigate(page, params)} selectedId={pageParams.id} initialAlertId={pageParams.alert_id} />
      )}
    </div>
  );
}

export default Notifications;
