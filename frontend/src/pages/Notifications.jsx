import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';
import Alerts from './Alerts';
import Cases from './Cases';
import Evidence from './Evidence';
import Recordings from './Recordings';

export function Notifications({ onNavigate, pageParams = {} }) {
  const tabs = ['notifications', 'alerts', 'incidents', 'cases', 'recordings', 'evidence'];
  const activeTab = tabs.includes(pageParams.tab) ? pageParams.tab : 'notifications';
  const handleWorkspaceNavigate = (page, params = {}) => {
    if (['alerts', 'security-events'].includes(page)) {
      onNavigate('notifications', { tab: 'alerts', ...(params.id ? { id: params.id } : {}) });
      return;
    }
    if (['incidents'].includes(page)) {
      onNavigate('notifications', { tab: 'incidents', ...(params.incident ? { incident: params.incident } : {}), ...(params.id ? { incident: params.id } : {}) });
      return;
    }
    if (['cases', 'evidence', 'recordings'].includes(page)) { onNavigate('notifications', { ...params, tab: page }); return; }
    onNavigate(page, params);
  };
  const { t } = useTranslation();
  const { addToast } = useToast();

  const [notifications, setNotifications] = useState([]);
  const [filter, setFilter] = useState('all'); // 'all' | 'unread' | 'read'
  const [page, setPage] = useState(1);
  const [numPages, setNumPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalAll, setTotalAll] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchNotifications = useCallback(async () => {
    try {
      setLoading(true);
      const params = { page, per_page: 25 };
      if (filter === 'unread' || filter === 'read') {
        params.status = filter;
      }
      const data = await api.notifications.list(params);
      if (data) {
        const list = data.notifications || [];
        setNotifications(list);
        setUnreadCount(data.unread_count ?? list.filter((n) => !n.is_read).length);
        setTotalCount(data.total_count ?? list.length);
        setTotalAll(data.total_all ?? data.total_count ?? list.length);
        setNumPages(data.num_pages || 1);
      }
    } catch (err) {
      console.warn('Failed to load notifications:', err);
    } finally {
      setLoading(false);
    }
  }, [filter, page]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleFilterChange = (nextFilter) => {
    setPage(1);
    setFilter(nextFilter);
  };

  const handleMarkAsRead = async (id) => {
    try {
      const res = await api.notifications.markRead(id);
      if (res && (res.success || res.status === 'ok')) {
        addToast('Notification marked as read', 'info');
        window.dispatchEvent(new CustomEvent('notifications:updated'));
        fetchNotifications();
      }
    } catch {
      addToast('Failed to mark notification as read', 'error');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      const res = await api.notifications.markAllRead();
      if (res && (res.success || res.status === 'ok')) {
        addToast('All notifications marked as read', 'success');
        window.dispatchEvent(new CustomEvent('notifications:updated'));
        fetchNotifications();
      }
    } catch {
      addToast('Failed to mark all as read', 'error');
    }
  };

  const readCount = Math.max(0, totalAll - unreadCount);

  const tabLabels = {
    notifications: t('notifications.title', 'Notifications'),
    alerts: t('nav.alerts', 'Alerts'),
    incidents: t('nav.incidents', 'Incidents'),
    cases: t('nav.cases', 'Cases'),
    recordings: t('nav.recordings', 'Recordings'),
    evidence: t('nav.evidence', 'Evidence'),
  };
  const workspaceTabs = (
    <nav aria-label={t('notifications.workspace', 'Security workspace')} className="security-workspace-tabs" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20, borderBottom: '1px solid var(--border-color)', paddingBottom: 12 }}>
      {tabs.map((tab) => (
        <button key={tab} type="button" className={`btn btn-sm ${activeTab === tab ? 'btn-primary' : 'btn-secondary'}`} aria-current={activeTab === tab ? 'page' : undefined} onClick={() => onNavigate('notifications', { tab })}>{tabLabels[tab]}</button>
      ))}
    </nav>
  );
  if (activeTab === 'alerts') return <section>{workspaceTabs}<Alerts onNavigate={handleWorkspaceNavigate} onSelectAlert={(id) => onNavigate('notifications', { tab: 'incidents', incident: id })} /></section>;
  if (activeTab === 'incidents') return <section>{workspaceTabs}<Alerts onNavigate={handleWorkspaceNavigate} selectedId={pageParams.incident || pageParams.id || pageParams.alert_id} /></section>;
  if (activeTab === 'cases') return <section>{workspaceTabs}<Cases onNavigate={handleWorkspaceNavigate} selectedId={pageParams.id} initialAlertId={pageParams.alert_id} /></section>;
  if (activeTab === 'recordings') return <section>{workspaceTabs}<Recordings onNavigate={handleWorkspaceNavigate} initialCameraId={pageParams.camera_id} selectedId={pageParams.id} /></section>;
  if (activeTab === 'evidence') return <section>{workspaceTabs}<Evidence onNavigate={handleWorkspaceNavigate} initialAlertId={pageParams.alert_id} selectedId={pageParams.id} /></section>;

  return (
    <div className="notifications-page-container" style={{ maxWidth: '1400px', margin: '0 auto' }}>
      {workspaceTabs}
      {/* Operational Header */}
      <div className="hero-editorial-wrap" style={{ marginBottom: '1.25rem' }}>
        <h1 style={{ fontSize: '1.35rem', fontWeight: 800, margin: '0 0 4px 0', color: 'var(--text-main)' }}>
          {t('notifications.title', 'System Notifications')}
        </h1>
        <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0 }}>
          {t('notifications.subtitle', 'Real-time alert notices and operational security telemetry')}
        </p>
      </div>

      {/* Controls & Actions Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
          padding: '12px 16px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-lg)',
          marginBottom: '1.25rem',
        }}
      >
        {/* Filter Tabs */}
        <div className="cameras-toolbar-left" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            id="notif-filter-all"
            onClick={() => handleFilterChange('all')}
            className={`btn btn-secondary btn-sm ${filter === 'all' ? 'active' : ''}`}
            style={{
              backgroundColor: filter === 'all' ? 'var(--dv-cyan-500, #00D2FF)' : undefined,
              color: filter === 'all' ? '#080C14' : undefined,
              fontWeight: 700,
            }}
          >
            All ({totalAll})
          </button>
          <button
            type="button"
            id="notif-filter-unread"
            onClick={() => handleFilterChange('unread')}
            className={`btn btn-secondary btn-sm ${filter === 'unread' ? 'active' : ''}`}
            style={{
              backgroundColor: filter === 'unread' ? 'var(--dv-cyan-500, #00D2FF)' : undefined,
              color: filter === 'unread' ? '#080C14' : undefined,
              fontWeight: 700,
            }}
          >
            Unread ({unreadCount})
          </button>
          <button
            type="button"
            id="notif-filter-read"
            onClick={() => handleFilterChange('read')}
            className={`btn btn-secondary btn-sm ${filter === 'read' ? 'active' : ''}`}
            style={{
              backgroundColor: filter === 'read' ? 'var(--dv-cyan-500, #00D2FF)' : undefined,
              color: filter === 'read' ? '#080C14' : undefined,
              fontWeight: 700,
            }}
          >
            Read ({readCount})
          </button>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Showing {notifications.length} of {totalCount}
          </span>
          {unreadCount > 0 && (
            <button
              type="button"
              id="btn-mark-all-read"
              onClick={handleMarkAllRead}
              className="btn btn-secondary btn-sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>{t('notifications.markAllRead', 'Mark All Read')}</span>
            </button>
          )}
        </div>
      </div>

      {/* Notifications List */}
      {notifications.length > 0 ? (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {notifications.map((n) => {
              const targetAlertId = n.alert_id || n.alert?.id;
              const sev = (n.severity || n.alert?.severity || 'info').toLowerCase();
              const cameraLabel = n.camera_name || n.alert?.camera_name || 'System';
              const timestamp = n.created_at || n.alert?.detected_at;

              return (
                <div
                  key={n.id}
                  className="notification-item-card"
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '0.95rem 1.2rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '1rem',
                    borderLeft: !n.is_read ? '4px solid var(--dv-cyan-500, #00D2FF)' : undefined,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.9rem', flex: 1, minWidth: '240px' }}>
                    <div style={{ marginTop: '0.3rem' }}>
                      {!n.is_read ? (
                        <span
                          style={{
                            display: 'inline-block',
                            width: '9px',
                            height: '9px',
                            borderRadius: '50%',
                            background: 'var(--dv-cyan-500, #00D2FF)',
                            boxShadow: '0 0 6px rgba(0, 210, 255, 0.5)',
                          }}
                        />
                      ) : (
                        <span
                          style={{
                            display: 'inline-block',
                            width: '9px',
                            height: '9px',
                            borderRadius: '50%',
                            background: 'var(--text-muted)',
                            opacity: 0.35,
                          }}
                        />
                      )}
                    </div>

                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.92rem', color: 'var(--text-main)' }}>
                          {n.title || n.alert?.title || 'Security Notification'}
                        </span>
                        <span
                          className={`status-pill ${sev === 'critical' ? 'status-offline' : sev === 'high' || sev === 'warning' ? 'status-warn' : 'status-live'}`}
                          style={{ fontSize: '0.65rem', padding: '0.1rem 0.45rem', fontWeight: 700 }}
                        >
                          {sev.toUpperCase()}
                        </span>
                        <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          &bull; {cameraLabel}
                        </span>
                      </div>

                      <p style={{ margin: '0 0 0.35rem 0', fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        {n.message || n.alert?.message}
                      </p>

                      <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {timestamp ? formatDate(timestamp) : 'Timestamp recorded'}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {Boolean(targetAlertId) && (
                      <button
                        type="button"
                        id={`btn-view-incident-${n.id}`}
                        onClick={() => onNavigate('notifications', { tab: 'incidents', incident: targetAlertId })}
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '0.78rem', display: 'inline-flex', alignItems: 'center', gap: '4px', fontWeight: 700 }}
                        title="Open alert incident workspace"
                      >
                        <span>View Incident</span>
                        <span aria-hidden="true">&rarr;</span>
                      </button>
                    )}
                    {!n.is_read && (
                      <button
                        type="button"
                        id={`btn-mark-read-${n.id}`}
                        onClick={() => handleMarkAsRead(n.id)}
                        className="btn btn-secondary btn-sm"
                        title="Mark as read"
                        style={{ fontSize: '0.76rem' }}
                      >
                        {t('notifications.markRead', 'Mark Read')}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination Controls */}
          {numPages > 1 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '12px',
                marginTop: '1.5rem',
              }}
            >
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn btn-secondary btn-sm"
              >
                &larr; Previous
              </button>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                Page {page} of {numPages}
              </span>
              <button
                type="button"
                disabled={page >= numPages}
                onClick={() => setPage((p) => Math.min(numPages, p + 1))}
                className="btn btn-secondary btn-sm"
              >
                Next &rarr;
              </button>
            </div>
          )}
        </>
      ) : (
        <div
          className="empty-state-card"
          style={{
            textAlign: 'center',
            padding: '4rem 1.5rem',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)',
          }}
        >
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}
          >
            <path d="M 18 8 A 6 6 0 0 0 6 8 c 0 7 -3 9 -3 9 h 18 s -3 -2 -3 -9"></path>
            <path d="M 13.73 21 a 2 2 0 0 1 -3.46 0"></path>
          </svg>
          <h3 style={{ fontSize: '1.15rem', color: 'var(--text-main)', marginBottom: '0.5rem' }}>No Notifications Found</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', maxWidth: '400px', margin: '0 auto' }}>
            {loading ? 'Retrieving notifications...' : 'You are completely caught up! No notifications match the active filter.'}
          </p>
        </div>
      )}
    </div>
  );
}

export default Notifications;
