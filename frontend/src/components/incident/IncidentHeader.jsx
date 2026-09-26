import React from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentHeader({ alert, onBack, onAcknowledge, onResolve, onNavigate, onOpenCaseModal }) {
  if (!alert) return null;

  const severityClass = alert.severity === 'critical' ? 'status-offline' : alert.severity === 'high' ? 'status-warn' : 'status-live';

  return (
    <div className="incident-header-card" data-alert-id={alert.id} style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem 1.5rem',
      marginBottom: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.75rem' }}>
        <button
          type="button"
          id="btn-back-to-inbox"
          onClick={onBack}
          className="btn btn-ghost btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', padding: '4px 10px' }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          Back to Incident Inbox
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={`status-pill ${severityClass}`} style={{ fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.05em' }}>
            {alert.severity ? alert.severity.toUpperCase() : 'MEDIUM'}
          </span>
          <span className="badge" style={{
            fontSize: '0.75rem',
            textTransform: 'uppercase',
            background: alert.status === 'resolved' ? 'rgba(16, 185, 129, 0.15)' : alert.status === 'acknowledged' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
            color: alert.status === 'resolved' ? 'var(--color-live, #10b981)' : alert.status === 'acknowledged' ? 'var(--color-warn, #f59e0b)' : 'var(--color-offline, #ef4444)',
            border: '1px solid currentColor',
          }}>
            {alert.status || 'NEW'}
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.4rem 0', color: 'var(--text-primary)' }}>
            {alert.title || alert.event_type || 'Security Incident'}
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', color: 'var(--text-secondary)', fontSize: '0.84rem' }}>
            <span>
              <strong>Camera:</strong> {alert.camera_name || `Camera ${alert.camera_id}`}
            </span>
            <span>•</span>
            <span>
              <strong>Zone:</strong> {alert.location || 'Perimeter Sector 1'}
            </span>
            <span>•</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>
              <strong>Detected:</strong> {formatDate(alert.detected_at)}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
          {alert.status === 'new' && (
            <button
              type="button"
              onClick={() => onAcknowledge(alert.id)}
              className="btn btn-secondary btn-sm"
              style={{ fontWeight: 600 }}
            >
              Acknowledge
            </button>
          )}

          {alert.status !== 'resolved' && (
            <button
              type="button"
              onClick={() => onResolve(alert.id)}
              className="btn btn-primary btn-sm"
              style={{ fontWeight: 600 }}
            >
              Resolve Incident
            </button>
          )}

          {alert.camera_id && (
            <button
              type="button"
              onClick={() => onNavigate && onNavigate('camera-preview', { id: alert.camera_id })}
              className="btn btn-ghost btn-sm"
            >
              Live Feed
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default IncidentHeader;
