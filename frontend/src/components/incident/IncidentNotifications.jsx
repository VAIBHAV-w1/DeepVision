import React from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentNotifications({ notifications = [] }) {
  if (!notifications || notifications.length === 0) {
    return (
      <div className="incident-notifications-card" style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.25rem',
        marginBottom: '1.5rem',
      }}>
        <h3 style={{
          fontSize: '0.95rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          margin: '0 0 0.5rem 0',
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
          </svg>
          Security Dispatch Notifications (0)
        </h3>
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.82rem' }}>
          No notifications generated for this incident.
        </p>
      </div>
    );
  }

  return (
    <div className="incident-notifications-card" style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem',
      marginBottom: '1.5rem',
    }}>
      <h3 style={{
        fontSize: '0.95rem',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        margin: '0 0 1rem 0',
        color: 'var(--text-secondary)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
        </svg>
        Security Dispatch Notifications ({notifications.length})
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {notifications.map((notif) => (
          <div
            key={notif.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'var(--bg-surface-raised)',
              padding: '0.6rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.80rem',
            }}
          >
            <div>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                SOC Dispatch #{notif.id}
              </span>
              <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>
                Dispatched {formatDate(notif.created_at)}
              </span>
            </div>
            <div>
              <span className={`status-pill ${notif.is_read ? 'status-live' : 'status-warn'}`} style={{ fontSize: '0.68rem' }}>
                {notif.is_read ? 'READ' : 'QUEUED / UNREAD'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default IncidentNotifications;
