import React, { useState } from 'react';
import { formatDate } from '../../utils/formatters';

export function IncidentRecording({ recording, alertId }) {
  const [isPlaying, setIsPlaying] = useState(false);

  if (!recording || !recording.view_url) {
    return (
      <div className="incident-recording-card" style={{
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
            <circle cx="12" cy="12" r="10"></circle>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
          Surveillance Recording
        </h3>
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem' }}>
          No continuous recording is associated with this incident.
        </p>
      </div>
    );
  }

  const durationStr = recording.duration_seconds
    ? `${Math.floor(recording.duration_seconds / 60)}m ${Math.floor(recording.duration_seconds % 60)}s`
    : 'Full Segment';
  const sizeMb = recording.file_size
    ? `${(recording.file_size / (1024 * 1024)).toFixed(1)} MB`
    : null;

  return (
    <div className="incident-recording-card" style={{
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
            <circle cx="12" cy="12" r="10"></circle>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
          Incident Recording Segment
        </h3>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {recording.download_url && (
            <a
              href={recording.download_url}
              download
              className="btn btn-secondary btn-sm"
              style={{ fontSize: '0.74rem', padding: '3px 8px' }}
            >
              Download MP4
            </a>
          )}
          <button
            type="button"
            id="btn-toggle-recording-play"
            onClick={() => setIsPlaying(!isPlaying)}
            className={`btn btn-sm ${isPlaying ? 'btn-ghost' : 'btn-primary'}`}
            style={{ fontSize: '0.74rem', padding: '3px 10px' }}
          >
            {isPlaying ? 'Close Player' : 'Play Recording'}
          </button>
        </div>
      </div>

      <div style={{
        background: 'var(--bg-surface-raised)',
        padding: '0.85rem 1rem',
        borderRadius: 'var(--radius-md)',
        marginBottom: isPlaying ? '1rem' : 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text-primary)', marginBottom: '3px', fontFamily: 'var(--font-mono)' }}>
            {recording.filename || `Recording #${recording.id}`}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
            Started: {formatDate(recording.started_at)} • Duration: {durationStr} {sizeMb ? `• ${sizeMb}` : ''}
          </div>
        </div>

        <span className="badge" style={{ fontSize: '0.70rem', background: 'rgba(16, 185, 129, 0.12)', color: 'var(--color-live, #10b981)', border: '1px solid var(--color-live, #10b981)' }}>
          HTTP 206 Verified
        </span>
      </div>

      {isPlaying && (
        <div style={{ marginTop: '0.75rem', background: '#000', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          <video
            src={recording.view_url}
            controls
            autoPlay
            playsInline
            style={{ width: '100%', maxHeight: '420px', objectFit: 'contain' }}
          >
            Your browser does not support the video tag.
          </video>
        </div>
      )}
    </div>
  );
}

export default IncidentRecording;
