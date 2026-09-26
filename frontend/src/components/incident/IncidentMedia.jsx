import React, { useState } from 'react';

export function IncidentMedia({ primaryMedia, evidenceItems, onNavigate }) {
  const [activeTab, setActiveTab] = useState('video'); // 'video' | 'snapshot'
  const video = primaryMedia?.video;
  const snapshot = primaryMedia?.snapshot;
  const recording = primaryMedia?.recording;

  const hasVideo = !!video?.preview_url;
  const hasSnapshot = !!snapshot?.preview_url;

  return (
    <div className="incident-media-panel" style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      marginBottom: '1.5rem',
    }}>
      {/* Panel Header & Media Mode Switcher */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1.25rem',
        borderBottom: '1px solid var(--border-color)',
        background: 'var(--bg-surface-raised)',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            id="btn-tab-video"
            onClick={() => setActiveTab('video')}
            className={`btn btn-sm ${activeTab === 'video' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: '0.78rem', padding: '4px 12px' }}
          >
            Video Clip {hasVideo ? `(${video.duration_seconds || 8}s)` : ''}
          </button>
          <button
            type="button"
            id="btn-tab-snapshot"
            onClick={() => setActiveTab('snapshot')}
            className={`btn btn-sm ${activeTab === 'snapshot' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: '0.78rem', padding: '4px 12px' }}
          >
            Snapshot Keyframe
          </button>
        </div>

        {/* Audio Availability Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {video?.has_audio ? (
            <span className="badge" style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--color-live, #10b981)',
              border: '1px solid var(--color-live, #10b981)',
              fontSize: '0.72rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
              </svg>
              Audio Available
            </span>
          ) : (
            <span className="badge" title="Source camera device captures video pins only without multiplexed audio" style={{
              background: 'rgba(148, 163, 184, 0.12)',
              color: 'var(--text-muted, #94a3b8)',
              border: '1px solid var(--border-color)',
              fontSize: '0.72rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                <line x1="23" y1="9" x2="17" y2="15"></line>
                <line x1="17" y1="9" x2="23" y2="15"></line>
              </svg>
              Audio Unavailable
            </span>
          )}

          {recording?.view_url && (
            <span
              className="badge"
              style={{
                background: 'rgba(59, 130, 246, 0.12)',
                color: 'var(--color-primary, #3b82f6)',
                border: '1px solid var(--border-color)',
                fontSize: '0.72rem',
              }}
            >
              Continuous Recording Attached
            </span>
          )}
        </div>
      </div>

      {/* Media Display Area */}
      <div style={{ position: 'relative', width: '100%', minHeight: '340px', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {activeTab === 'video' ? (
          hasVideo ? (
            <video
              key={video.preview_url}
              src={video.preview_url}
              controls
              playsInline
              preload="metadata"
              style={{ width: '100%', maxHeight: '480px', objectFit: 'contain' }}
            >
              Your browser does not support the video tag.
            </video>
          ) : (
            <div style={{ textAlign: 'center', padding: '3rem 1.5rem', color: 'var(--text-muted)' }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.5, marginBottom: '0.5rem' }}>
                <polygon points="23 7 16 12 23 17 23 7"></polygon>
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
              </svg>
              <p style={{ margin: 0, fontSize: '0.88rem' }}>No rolling buffer video clip recorded for this incident.</p>
            </div>
          )
        ) : (
          hasSnapshot ? (
            <img
              id="incident-snapshot-img"
              className="incident-snapshot-img"
              src={snapshot.preview_url}
              alt="Forensic Snapshot"
              style={{ width: '100%', maxHeight: '480px', objectFit: 'contain' }}
            />
          ) : (
            <div style={{ textAlign: 'center', padding: '3rem 1.5rem', color: 'var(--text-muted)' }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.5, marginBottom: '0.5rem' }}>
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              <p style={{ margin: 0, fontSize: '0.88rem' }}>No keyframe snapshot captured for this incident.</p>
            </div>
          )
        )}
      </div>

      {/* Media Metadata Footer */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1.25rem',
        background: 'var(--bg-surface)',
        fontSize: '0.80rem',
        color: 'var(--text-secondary)',
        flexWrap: 'wrap',
        gap: '0.5rem',
      }}>
        <div>
          {hasVideo && (
            <span>
              <strong>Clip Archive:</strong> {video.file_name} ({((video.file_size || 0) / (1024 * 1024)).toFixed(1)} MB)
            </span>
          )}
        </div>
        <div>
          {hasVideo && video.download_url && (
            <a
              href={video.download_url}
              download
              className="btn btn-ghost btn-sm"
              style={{ fontSize: '0.75rem', padding: '2px 8px' }}
            >
              Download MP4
            </a>
          )}
          {hasSnapshot && snapshot.download_url && (
            <a
              href={snapshot.download_url}
              download
              className="btn btn-ghost btn-sm"
              style={{ fontSize: '0.75rem', padding: '2px 8px', marginLeft: '6px' }}
            >
              Download JPG
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default IncidentMedia;
