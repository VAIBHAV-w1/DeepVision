import React, { useState } from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentEvidence({ evidenceItems = [], alertId }) {
  const [selectedPreview, setSelectedPreview] = useState(null);

  if (!evidenceItems || evidenceItems.length === 0) {
    return (
      <div className="incident-evidence-card" style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-lg)',
        padding: '1.25rem',
        marginBottom: '1.5rem',
      }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 0.5rem 0', color: 'var(--text-secondary)' }}>
          Forensic Evidence Artifacts (0)
        </h3>
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem' }}>
          No forensic evidence files captured for this incident.
        </p>
      </div>
    );
  }

  return (
    <div className="incident-evidence-card" style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem',
      marginBottom: '1.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
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
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          Forensic Evidence Artifacts ({evidenceItems.length})
        </h3>
        <span className="badge" style={{ fontSize: '0.72rem', background: 'var(--bg-surface-raised)', border: '1px solid var(--border-color)' }}>
          Alert-Scoped Artifacts
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
        {evidenceItems.map((ev) => {
          const isVideo = ev.evidence_type === 'video';
          const sizeStr = ev.file_size ? `${(ev.file_size / (1024 * (isVideo ? 1024 : 1))).toFixed(1)} ${isVideo ? 'MB' : 'KB'}` : 'Archived';

          return (
            <div
              key={ev.id}
              style={{
                background: 'var(--bg-surface-raised)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: '0.75rem 1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '0.75rem',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                  <span className="badge" style={{ fontSize: '0.66rem', textTransform: 'uppercase' }}>
                    {ev.evidence_type}
                  </span>
                  <span style={{ fontSize: '0.80rem', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {ev.file_name}
                  </span>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Size: {sizeStr} • {formatDate(ev.captured_at)}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                {ev.preview_url && (
                  <button
                    type="button"
                    onClick={() => setSelectedPreview(ev)}
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.72rem', padding: '3px 7px' }}
                    title="Preview Artifact"
                  >
                    Preview
                  </button>
                )}
                {ev.download_url && (
                  <a
                    href={ev.download_url}
                    download
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.72rem', padding: '3px 7px' }}
                  >
                    Save
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Inline Evidence Preview Modal */}
      {selectedPreview && (
        <div
          className="modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '1rem',
          }}
          onClick={() => setSelectedPreview(null)}
        >
          <div
            className="modal-dialog"
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '720px',
              width: '100%',
              overflow: 'hidden',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.75rem 1.25rem',
              borderBottom: '1px solid var(--border-color)',
              background: 'var(--bg-surface-raised)',
            }}>
              <span style={{ fontWeight: 600, fontSize: '0.90rem' }}>
                {selectedPreview.file_name} ({selectedPreview.evidence_type?.toUpperCase()})
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedPreview(null)}
                style={{ padding: '2px 8px' }}
              >
                ✕ Close
              </button>
            </div>

            <div style={{ background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '280px', maxHeight: '500px' }}>
              {selectedPreview.evidence_type === 'video' ? (
                <video
                  src={selectedPreview.preview_url}
                  controls
                  autoPlay
                  playsInline
                  style={{ width: '100%', maxHeight: '480px', objectFit: 'contain' }}
                >
                  Your browser does not support video.
                </video>
              ) : (
                <img
                  src={selectedPreview.preview_url}
                  alt={selectedPreview.file_name}
                  style={{ width: '100%', maxHeight: '480px', objectFit: 'contain' }}
                />
              )}
            </div>

            <div style={{ padding: '0.75rem 1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-surface)' }}>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                Captured: {formatDate(selectedPreview.captured_at)}
              </span>
              {selectedPreview.download_url && (
                <a
                  href={selectedPreview.download_url}
                  download
                  className="btn btn-primary btn-sm"
                  style={{ fontSize: '0.76rem' }}
                >
                  Download File
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default IncidentEvidence;
