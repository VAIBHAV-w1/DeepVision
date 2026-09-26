import React from 'react';

export function IncidentAnalysis({ analysis }) {
  if (!analysis) return null;

  const confidencePct = Math.round((analysis.confidence || 0.85) * 100);

  return (
    <div className="incident-analysis-card" style={{
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
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        AI Forensic Telemetry & Analysis
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Event Classification
          </div>
          <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {(analysis.event_type || 'Unknown').replace(/_/g, ' ').toUpperCase()}
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            ByteTrack Entity ID
          </div>
          <div style={{ fontSize: '0.92rem', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
            {analysis.track_id ? `#TRK-${analysis.track_id}` : 'Cluster / Global'}
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            AI Confidence
          </div>
          <div style={{ fontSize: '0.92rem', fontWeight: 700, color: confidencePct > 80 ? 'var(--color-live, #10b981)' : 'var(--color-warn, #f59e0b)' }}>
            {confidencePct}%
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Monitored Sector
          </div>
          <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {analysis.location || 'Channel 01'}
          </div>
        </div>
      </div>

      {analysis.message && (
        <div style={{
          background: 'rgba(255, 255, 255, 0.02)',
          borderLeft: '3px solid var(--accent-color, #3b82f6)',
          padding: '0.75rem 1rem',
          borderRadius: '0 var(--radius-md) var(--radius-md) 0',
          fontSize: '0.86rem',
          color: 'var(--text-secondary)',
        }}>
          <strong>Analysis Reasoning:</strong> {analysis.message}
        </div>
      )}
    </div>
  );
}

export default IncidentAnalysis;
