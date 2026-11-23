import React from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentAnalysis({ analysis, onOpenIncident }) {
  if (!analysis) return null;

  const confidencePct = Math.round((analysis.confidence ?? 0.85) * 100);
  const riskScore = Number(analysis.risk_score ?? 50);
  const riskLevel = String(analysis.risk_level || analysis.severity || 'medium').toUpperCase();
  const correlated = Array.isArray(analysis.correlated_alerts) ? analysis.correlated_alerts : [];
  const supportingEvidence = Array.isArray(analysis.supporting_evidence) ? analysis.supporting_evidence : [];
  const nextSteps = Array.isArray(analysis.recommended_next_steps) ? analysis.recommended_next_steps : [];
  const slaPolicy = analysis.sla_policy || null;
  const secSan = analysis.security_sanitization || {};

  const riskColor =
    riskLevel === 'CRITICAL' ? '#ef4444'
      : riskLevel === 'HIGH' ? '#f59e0b'
      : riskLevel === 'MEDIUM' ? '#38bdf8'
      : '#10b981';

  return (
    <div className="incident-analysis-card" style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem',
      marginBottom: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '1rem' }}>
        <h3 style={{
          fontSize: '0.95rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          margin: 0,
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
          AI SOC Evidence-Linked Analysis
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="badge" style={{ fontSize: '0.72rem', fontWeight: 700, color: riskColor, border: `1px solid ${riskColor}` }}>
            RISK {riskScore}/100 ({riskLevel})
          </span>
          {slaPolicy && (
            <span className="badge" style={{ fontSize: '0.72rem', background: 'var(--bg-surface-raised)', border: '1px solid var(--border-color)' }}>
              SLA: {String(slaPolicy.sla_state || '').replace(/_/g, ' ').toUpperCase()} ({slaPolicy.elapsed_minutes}m / {slaPolicy.initial_response_minutes}m)
            </span>
          )}
          {secSan.prompt_injection_detected && (
            <span className="badge" style={{ fontSize: '0.72rem', color: '#f59e0b', border: '1px solid #f59e0b' }}>
              UNTRUSTED TEXT SANITIZED
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.85rem', marginBottom: '1rem' }}>
        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Event Classification
          </div>
          <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {analysis.classification || (analysis.event_type || 'Unknown').replace(/_/g, ' ').toUpperCase()}
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Tracked Entity ID
          </div>
          <div style={{ fontSize: '0.9rem', fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
            {analysis.track_id ? `#TRK-${analysis.track_id}` : 'Cluster / Global'}
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            AI Confidence
          </div>
          <div style={{ fontSize: '0.9rem', fontWeight: 700, color: confidencePct > 80 ? 'var(--color-live, #10b981)' : 'var(--color-warn, #f59e0b)' }}>
            {confidencePct}%
          </div>
        </div>

        <div style={{ background: 'var(--bg-surface-raised)', padding: '0.75rem', borderRadius: 'var(--radius-md)' }}>
          <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px' }}>
            Monitored Sector
          </div>
          <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {analysis.location || 'Channel 01'}
          </div>
        </div>
      </div>

      {(analysis.explanation || analysis.message) && (
        <div style={{
          background: 'rgba(255, 255, 255, 0.02)',
          borderLeft: '3px solid var(--accent-color, #3b82f6)',
          padding: '0.75rem 1rem',
          borderRadius: '0 var(--radius-md) var(--radius-md) 0',
          fontSize: '0.85rem',
          color: 'var(--text-secondary)',
          marginBottom: '1rem',
          lineHeight: 1.5,
        }}>
          <strong>Evidence-Linked Assessment:</strong> {analysis.explanation || analysis.message}
        </div>
      )}

      {supportingEvidence.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
            Supporting Evidence Citations ({supportingEvidence.length})
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {supportingEvidence.map((item, idx) => (
              <span key={idx} className="badge" style={{ fontSize: '0.72rem', background: 'var(--bg-surface-raised)', border: '1px solid var(--border-color)' }}>
                [{String(item.kind || 'evidence').toUpperCase()}] {item.label} {item.timestamp ? `• ${formatDate(item.timestamp)}` : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {nextSteps.length > 0 && (
        <div style={{ marginBottom: correlated.length > 0 ? '1rem' : 0 }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
            Supervised Operator Next Steps
          </div>
          <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {nextSteps.map((s, idx) => (
              <li key={idx}>{s.step}</li>
            ))}
          </ul>
        </div>
      )}

      {correlated.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.85rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
            Correlated Alerts (±30 min window · {correlated.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {correlated.slice(0, 5).map((rel) => (
              <div
                key={rel.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  background: 'var(--bg-surface-raised)',
                  fontSize: '0.78rem',
                }}
              >
                <div>
                  <strong>#{rel.id}</strong> {rel.title}{' '}
                  <span style={{ color: 'var(--text-muted)' }}>({rel.correlation_basis})</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {formatDate(rel.detected_at)}
                  </span>
                  {typeof onOpenIncident === 'function' && (
                    <button
                      type="button"
                      onClick={() => onOpenIncident(rel.id)}
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: '0.72rem', padding: '2px 8px' }}
                    >
                      Inspect
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default IncidentAnalysis;
