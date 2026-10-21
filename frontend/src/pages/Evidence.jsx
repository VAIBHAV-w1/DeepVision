import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';

export function Evidence({ onNavigate, initialCameraId, initialAlertId, selectedId }) {
  const [evidenceList, setEvidenceList] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [currentType, setCurrentType] = useState('all');
  const [cameraId, setCameraId] = useState(initialCameraId || '');
  const [alertId, setAlertId] = useState(initialAlertId || '');
  const [search, setSearch] = useState('');
  const [stats, setStats] = useState({ total_count: 0, snapshots_count: 0, videos_count: 0 });
  const [loading, setLoading] = useState(true);

  const fetchEvidence = async () => {
    try {
      setLoading(true);
      const params = {};
      if (currentType !== 'all') params.type = currentType;
      if (cameraId) params.camera_id = cameraId;
      if (alertId) params.alert_id = alertId;
      if (search) params.q = search;

      const data = await api.evidence.list(params);
      if (data) {
        const items = data.evidence || data.items || [];
        setEvidenceList(items);
        setCameras(data.cameras || []);
        setStats({
          total_count: data.total_count ?? items.length,
          snapshots_count: data.snapshots_count ?? items.filter(e => e.evidence_type === 'snapshot').length,
          videos_count: data.videos_count ?? items.filter(e => e.evidence_type === 'video').length,
        });
      }
    } catch (err) {
      console.warn('Failed to load evidence:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEvidence();
  }, [currentType, cameraId, alertId]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchEvidence();
  };

  return (
    <div className="evidence-page-container">
      {/* Operational Header */}
      <div className="hero-editorial-wrap" style={{ marginBottom: '1.25rem' }}>
        <div className="editorial-badge-pill" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#10b981', padding: '4px 12px', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em', marginBottom: '8px' }}>
          <span>PRESERVED ARTIFACTS</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: '1.6rem', fontWeight: 700, margin: '2px 0 6px 0', letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
          Evidence Vault
        </h1>
        <p className="editorial-hero-subtitle" style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0 }}>
          Review preserved evidence frames and recorded clips associated with security detection events.
        </p>
      </div>

      {/* Compact Metric Badges */}
      <div className="summary-grid" style={{ marginBottom: '2rem' }}>
        <div className="summary-card">
          <div className="summary-data">
            <span className="summary-value">{stats.total_count}</span>
            <span className="summary-label">Total Evidence Items</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <circle cx="8.5" cy="8.5" r="1.5"></circle>
              <polyline points="21 15 16 10 5 21"></polyline>
            </svg>
          </div>
        </div>

        <div className="summary-card">
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--color-primary, #38bdf8)' }}>{stats.snapshots_count}</span>
            <span className="summary-label">Forensic Snapshots</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z"></path>
              <circle cx="12" cy="13" r="4"></circle>
            </svg>
          </div>
        </div>

        <div className="summary-card">
          <div className="summary-data">
            <span className="summary-value" style={{ color: 'var(--color-live, #10b981)' }}>{stats.videos_count}</span>
            <span className="summary-label">Video Clips</span>
          </div>
          <div className="summary-icon-wrap">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="23 7 16 12 23 17 23 7"></polygon>
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
            </svg>
          </div>
        </div>
      </div>

      {/* Controls & Filters Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', margin: 0 }}>
          {/* Type Filter Tabs */}
          <div className="cameras-toolbar-left" style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setCurrentType('all')}
              className={`btn btn-secondary btn-sm ${currentType === 'all' ? 'active' : ''}`}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setCurrentType('snapshot')}
              className={`btn btn-secondary btn-sm ${currentType === 'snapshot' ? 'active' : ''}`}
            >
              Snapshots
            </button>
            <button
              type="button"
              onClick={() => setCurrentType('video')}
              className={`btn btn-secondary btn-sm ${currentType === 'video' ? 'active' : ''}`}
            >
              Video Clips
            </button>
          </div>

          {/* Camera Selector */}
          <select
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem', padding: '0.2rem 1.8rem 0.2rem 0.8rem' }}
          >
            <option value="">All Cameras</option>
            {cameras.map((cam) => (
              <option key={cam.id} value={cam.id}>{cam.name}</option>
            ))}
          </select>

          {/* Search Input */}
          <div style={{ position: 'relative', width: '220px' }}>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search filename..."
              className="form-control"
              style={{ height: '38px', fontSize: '0.84rem', paddingLeft: '2.2rem' }}
            />
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>

          <button type="submit" className="btn btn-secondary btn-sm" style={{ height: '38px' }}>Filter</button>
          {(currentType !== 'all' || cameraId || alertId || search) && (
            <button
              type="button"
              onClick={() => { setCurrentType('all'); setCameraId(''); setAlertId(''); setSearch(''); }}
              className="btn btn-ghost btn-sm"
              style={{ height: '38px' }}
            >
              Reset
            </button>
          )}
        </form>
      </div>

      {/* Evidence Grid */}
      {evidenceList.length > 0 ? (
        <div className="camera-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {evidenceList.map((item) => (
            <div key={item.id} className="camera-card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ position: 'relative', width: '100%', height: '180px', background: 'var(--bg-canvas, #090d16)', overflow: 'hidden', borderTopLeftRadius: 'var(--radius-lg)', borderTopRightRadius: 'var(--radius-lg)' }}>
                {item.file_available && item.preview_url ? (
                  item.evidence_type === 'snapshot' ? (
                    <img
                      src={item.preview_url}
                      alt={item.alert_title || item.file_name || 'Evidence artifact'}
                      loading="lazy"
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        const fallback = e.currentTarget.nextElementSibling;
                        if (fallback) fallback.style.display = 'flex';
                      }}
                    />
                  ) : (
                    <video
                      src={item.preview_url}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      controls
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        const fallback = e.currentTarget.nextElementSibling;
                        if (fallback) fallback.style.display = 'flex';
                      }}
                    />
                  )
                ) : null}

                {/* Graceful Forensic Storage Artifact Display */}
                <div
                  className="forensic-fallback-card"
                  style={{
                    display: item.file_available ? 'none' : 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100%',
                    color: 'var(--text-secondary)',
                    fontSize: '0.82rem',
                    padding: '1.25rem',
                    textAlign: 'center',
                    background: 'var(--bg-surface-raised, #151e33)',
                    borderBottom: '1px solid var(--border-color)',
                  }}
                >
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary, #10b981)" strokeWidth="1.8" style={{ marginBottom: '8px', opacity: 0.85 }}>
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                    <circle cx="12" cy="11" r="3"></circle>
                  </svg>
                  <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.84rem' }}>
                    {item.file_available ? 'Forensic File Ready' : 'Preserved in Vault'}
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '4px', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.file_name || `evidence_${item.id}.dat`}
                  </span>
                </div>

                <div style={{ position: 'absolute', top: '0.5rem', left: '0.5rem', right: '0.5rem', display: 'flex', justifyContent: 'space-between', pointerEvents: 'none' }}>
                  <span className="badge" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: '#fff', fontSize: '0.70rem' }}>
                    {(item.evidence_type || 'evidence').toUpperCase()}
                  </span>
                  <span className="badge" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: '#fff', fontSize: '0.70rem' }}>
                    {item.camera_name || 'Channel 01'}
                  </span>
                </div>
              </div>

              <div style={{ padding: '1rem', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '4px' }}>
                    {item.alert_title || item.title || item.file_name || `Evidence #${item.id}`}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {formatDate(item.created_at || item.captured_at)}
                  </div>
                </div>

                <div style={{ marginTop: '1rem', display: 'flex', gap: '8px' }}>
                  {item.download_url && (
                    <a
                      href={item.download_url}
                      download
                      className="btn btn-secondary btn-sm"
                      style={{ flex: 1, justifyContent: 'center', textDecoration: 'none' }}
                    >
                      Download
                    </a>
                  )}
                  {item.alert_id && (
                    <button
                      type="button"
                      onClick={() => onNavigate('alerts', { selectedId: item.alert_id })}
                      className="btn btn-ghost btn-sm"
                      title="Open linked incident workspace"
                    >
                      Incident
                    </button>
                  )}
                  {item.camera_id && (
                    <button
                      type="button"
                      onClick={() => onNavigate('camera-preview', { id: item.camera_id })}
                      className="btn btn-ghost btn-sm"
                    >
                      Feed
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '4rem 1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>
            {loading ? 'Querying forensic evidence vault...' : 'No forensic evidence records found.'}
          </p>
        </div>
      )}
    </div>
  );
}

export default Evidence;
