import React from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentTimeline({ timeline = [] }) {
  if (!timeline || timeline.length === 0) {
    return (
      <div className="incident-timeline-card" style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.25rem',
        marginBottom: '1.5rem',
      }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 1rem 0', color: 'var(--text-secondary)' }}>
          Incident Forensic Timeline
        </h3>
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>No timeline milestones recorded.</p>
      </div>
    );
  }

  return (
    <div className="incident-timeline-card" style={{
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
        margin: '0 0 1.25rem 0',
        color: 'var(--text-secondary)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"></circle>
          <polyline points="12 6 12 12 16 14"></polyline>
        </svg>
        Incident Forensic Timeline
      </h3>

      <div style={{ position: 'relative', paddingLeft: '1.5rem' }}>
        {/* Timeline connector bar */}
        <div style={{
          position: 'absolute',
          left: '7px',
          top: '8px',
          bottom: '16px',
          width: '2px',
          background: 'var(--border-color)',
        }} />

        {timeline.map((item, idx) => (
          <div key={item.id || idx} style={{ position: 'relative', marginBottom: idx === timeline.length - 1 ? 0 : '1.25rem' }}>
            {/* Timeline node icon */}
            <div style={{
              position: 'absolute',
              left: '-1.5rem',
              top: '3px',
              width: '16px',
              height: '16px',
              borderRadius: '50%',
              background: item.type === 'resolved' ? 'var(--color-live, #10b981)' : item.type === 'acknowledged' ? 'var(--color-warn, #f59e0b)' : 'var(--accent-color, #3b82f6)',
              border: '2px solid var(--bg-surface)',
              boxShadow: '0 0 0 2px var(--border-color)',
            }} />

            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {item.title}
                </span>
                <span style={{ fontSize: '0.74rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  {formatDate(item.timestamp)}
                </span>
              </div>
              {item.description && (
                <p style={{ margin: '2px 0 0 0', fontSize: '0.80rem', color: 'var(--text-secondary)' }}>
                  {item.description}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default IncidentTimeline;
