import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';
import { useToast } from '../components/common/Toast';

export function Notifications({ onNavigate }) {
  const [notifications, setNotifications] = useState([]);
  const [filter, setFilter] = useState('all');
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();

  const fetchNotifications = async () => {
    try {
      setLoading(true);
      const data = await api.notifications.list({ status: filter });
      if (data) {
        const list = data.notifications || [];
        setNotifications(list);
        setUnreadCount(data.unread_count ?? list.filter(n => !n.is_read).length);
      }
    } catch (err) {
      console.warn('Failed to load notifications:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, [filter]);

  const handleMarkAsRead = async (id) => {
    try {
      const res = await api.notifications.markAsRead(id);
      if (res && res.success) {
        addToast('Notification marked as read', 'info');
        fetchNotifications();
      }
    } catch {
      addToast('Failed to mark notification as read', 'error');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      const res = await api.notifications.markAllAsRead();
      if (res && res.success) {
        addToast('All notifications marked as read', 'success');
        fetchNotifications();
      }
    } catch {
      addToast('Failed to mark all as read', 'error');
    }
  };

  const filtered = notifications.filter((n) => {
    if (filter === 'unread') return !n.is_read;
    if (filter === 'read') return n.is_read;
    return true;
  });

  return (
    <div className="notifications-page-container">
      {/* Editorial Header */}
      <div className="hero-editorial-wrap">
        <div className="editorial-badge-pill">
          <span>Security Inbox</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.25rem)', marginBottom: '0.5rem' }}>
          Security Notifications
        </h1>
        <p className="editorial-hero-subtitle" style={{ marginBottom: '2rem' }}>
          Review, acknowledge, and resolve dispatch notifications triggered by real-time surveillance rules.
        </p>
      </div>

      {/* Controls & Actions Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        {/* Filter Tabs */}
        <div className="cameras-toolbar-left" style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`btn btn-secondary btn-sm ${filter === 'all' ? 'active' : ''}`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setFilter('unread')}
            className={`btn btn-secondary btn-sm ${filter === 'unread' ? 'active' : ''}`}
          >
            Unread ({unreadCount})
          </button>
          <button
            type="button"
            onClick={() => setFilter('read')}
            className={`btn btn-secondary btn-sm ${filter === 'read' ? 'active' : ''}`}
          >
            Read
          </button>
        </div>

        {/* Actions */}
        <div>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={handleMarkAllRead}
              className="btn btn-secondary btn-sm"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>Mark All as Read</span>
            </button>
          )}
        </div>
      </div>

      {/* Notifications List */}
      {filtered.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filtered.map((n) => (
            <div
              key={n.id}
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-lg)',
                padding: '1rem 1.25rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '1rem',
                borderLeft: !n.is_read ? '4px solid var(--color-primary, #38bdf8)' : undefined,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', flex: 1 }}>
                <div style={{ marginTop: '0.2rem' }}>
                  {!n.is_read ? (
                    <span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', background: 'var(--color-primary, #38bdf8)' }}></span>
                  ) : (
                    <span style={{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%', background: 'var(--text-muted)', opacity: 0.4 }}></span>
                  )}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-main)' }}>
                      {n.title || n.alert?.title || 'Security Notification'}
                    </span>
                    {n.alert && (
                      <>
                        <span className={`status-pill ${n.alert.severity === 'critical' ? 'status-offline' : n.alert.severity === 'high' ? 'status-warn' : 'status-live'}`} style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>
                          {n.alert.severity?.toUpperCase()}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          &bull; {n.alert.camera_name || 'Channel 01'}
                        </span>
                      </>
                    )}
                  </div>

                  <p style={{ margin: '0 0 0.4rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {n.message || n.alert?.message}
                  </p>

                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {formatDate(n.created_at)}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {Boolean(n.alert_id || n.alert?.id) && (
                  <button
                    type="button"
                    onClick={() => onNavigate('alerts', { selectedId: n.alert_id || n.alert?.id })}
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '4px' }}
                    title="Open alert incident workspace"
                  >
                    <span>View Incident</span>
                    <span aria-hidden="true">&rarr;</span>
                  </button>
                )}
                {!n.is_read && (
                  <button
                    type="button"
                    onClick={() => handleMarkAsRead(n.id)}
                    className="btn btn-ghost btn-sm"
                    title="Mark as read"
                    style={{ fontSize: '0.78rem' }}
                  >
                    Mark Read
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '4rem 1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
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
