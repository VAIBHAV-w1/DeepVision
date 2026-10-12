import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { formatDate } from '../utils/formatters';
import { useToast } from '../components/common/Toast';

export function Recordings({ initialCameraId, selectedId, onNavigate }) {
  const [recordings, setRecordings] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [cameraId, setCameraId] = useState(initialCameraId || '');
  const [typeFilter, setTypeFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(24);
  const [numPages, setNumPages] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [totalSize, setTotalSize] = useState('0 B');
  const [loading, setLoading] = useState(true);
  const [activeRecording, setActiveRecording] = useState(null);
  const [videoError, setVideoError] = useState(false);
  const { addToast } = useToast();

  const fetchRecordings = async (targetPage = page) => {
    try {
      setLoading(true);
      const params = {
        page: targetPage,
        per_page: perPage,
      };
      if (cameraId) params.camera_id = cameraId;
      if (search) params.q = search;
      if (typeFilter !== 'all') params.type = typeFilter;

      const data = await api.recordings.list(params);
      if (data) {
        const recList = data.recordings || [];
        setRecordings(recList);
        setCameras(data.cameras || []);
        setTotalCount(data.total_count ?? recList.length);
        setTotalSize(data.formatted_total_size || '0 B');
        setNumPages(data.num_pages || 1);
        setPage(data.current_page || targetPage);
        setHasNext(!!data.has_next);
        setHasPrev(!!data.has_previous);

        if (selectedId && !activeRecording) {
          const matched = recList.find((r) => r.id === Number(selectedId));
          if (matched) {
            handleOpenPlayback(matched);
          }
        }
      }
    } catch (err) {
      console.warn('Failed to load recordings:', err);
      addToast('Failed to load surveillance recordings.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setPage(1);
    fetchRecordings(1);
  }, [cameraId, typeFilter, perPage]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchRecordings(1);
  };

  const handlePageChange = (newPage) => {
    if (newPage < 1 || newPage > numPages) return;
    setPage(newPage);
    fetchRecordings(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleOpenPlayback = (item) => {
    if (!item.file_exists) {
      addToast('This recording file has been archived from storage and is no longer available for playback.', 'warning');
      return;
    }
    setVideoError(false);
    setActiveRecording(item);
  };

  return (
    <div className="recordings-page-container">
      {/* Operational Header */}
      <div className="hero-editorial-wrap" style={{ marginBottom: '1.25rem' }}>
        <div className="editorial-badge-pill" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#10b981', padding: '4px 12px', borderRadius: '9999px', fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.06em', marginBottom: '8px' }}>
          <span>VIDEO ARCHIVE</span>
        </div>
        <h1 className="editorial-hero-title" style={{ fontSize: '1.6rem', fontWeight: 700, margin: '2px 0 6px 0', letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
          Surveillance Recordings
        </h1>
        <p className="editorial-hero-subtitle" style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', margin: 0 }}>
          Search, playback, and download security footage captured by optical camera channels.
        </p>
      </div>

      {/* Controls & Filters Bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', margin: 0 }}>
          {/* Filter by Camera */}
          <select
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            className="form-select"
            style={{ width: 'auto', height: '38px', fontSize: '0.84rem', padding: '0.2rem 1.8rem 0.2rem 0.8rem' }}
          >
            <option value="">All Cameras</option>
            {cameras.map((cam) => (
              <option key={cam.id} value={cam.id}>
                {cam.name}
              </option>
            ))}
          </select>

          {/* Type Filter Buttons */}
          <div className="btn-group" style={{ display: 'inline-flex' }}>
            <button
              type="button"
              onClick={() => setTypeFilter('all')}
              className={`btn btn-sm ${typeFilter === 'all' ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ height: '38px', fontSize: '0.82rem' }}
            >
              All Types
            </button>
            <button
              type="button"
              onClick={() => setTypeFilter('anomaly')}
              className={`btn btn-sm ${typeFilter === 'anomaly' ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ height: '38px', fontSize: '0.82rem' }}
            >
              Anomalies Only
            </button>
            <button
              type="button"
              onClick={() => setTypeFilter('continuous')}
              className={`btn btn-sm ${typeFilter === 'continuous' ? 'btn-secondary' : 'btn-ghost'}`}
              style={{ height: '38px', fontSize: '0.82rem' }}
            >
              Continuous Only
            </button>
          </div>

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
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
            >
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
          </div>

          <button type="submit" className="btn btn-secondary btn-sm" style={{ height: '38px' }}>
            Filter
          </button>
          {(cameraId || search || typeFilter !== 'all') && (
            <button
              type="button"
              onClick={() => { setCameraId(''); setSearch(''); setTypeFilter('all'); }}
              className="btn btn-ghost btn-sm"
              style={{ height: '38px' }}
            >
              Reset
            </button>
          )}
        </form>

        {/* Storage Metadata */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
          <span>
            Total Archived: <strong style={{ color: 'var(--text-main)' }}>{totalCount}</strong>
          </span>
          <span>
            Storage: <strong style={{ color: 'var(--text-main)' }}>{totalSize}</strong>
          </span>
        </div>
      </div>

      {/* Visual Media Library Grid */}
      {recordings.length > 0 ? (
        <>
          <div className="recordings-grid">
            {recordings.map((item) => {
              const isAnomaly = item.filename?.includes('ANOMALY');
              return (
                <div key={item.id} className="recording-card" data-camera-name={item.camera_name || 'Default'}>
                  {/* 16:9 Video Thumbnail / Click to Play */}
                  <div
                    className="recording-thumb-wrap"
                    onClick={() => handleOpenPlayback(item)}
                    style={{ cursor: item.file_exists ? 'pointer' : 'default', opacity: item.file_exists ? 1 : 0.65 }}
                  >
                    <button
                      type="button"
                      className="recording-play-btn"
                      aria-label="Play recording"
                      disabled={!item.file_exists}
                      style={{ opacity: item.file_exists ? 1 : 0.4 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <polygon points="6 3 20 12 6 21 6 3"></polygon>
                      </svg>
                    </button>

                    {/* Floating In-Feed Badges */}
                    <div style={{ position: 'absolute', top: '0.75rem', left: '0.75rem', right: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', pointerEvents: 'none' }}>
                      {isAnomaly ? (
                        <span className="status-pill status-warn" style={{ background: 'rgba(245, 158, 11, 0.9)', color: '#000000', fontWeight: 800, fontSize: '0.68rem', border: 'none' }}>
                          ANOMALY
                        </span>
                      ) : (
                        <span className="status-pill" style={{ background: 'rgba(11, 15, 23, 0.75)', color: '#ffffff', fontSize: '0.68rem', border: 'none' }}>
                          RECORDING
                        </span>
                      )}

                      <span className="camera-meta-chip">
                        {Math.round(item.duration_seconds || 0)}s
                      </span>
                    </div>
                  </div>

                  {/* Meta Information */}
                  <div className="recording-meta">
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
                      <div>
                        <div className="recording-title" title={item.filename}>
                          {item.camera_name || 'Channel 01'}
                        </div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                          {formatDate(item.started_at)}
                        </div>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                          {item.formatted_size}
                        </span>
                        {!item.file_exists && (
                          <span style={{ display: 'block', fontSize: '0.65rem', color: 'var(--color-critical, #ef4444)', fontWeight: 600, marginTop: '2px' }}>
                            FILE ARCHIVED
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Card Action Buttons */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.75rem', borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                      <button
                        type="button"
                        onClick={() => handleOpenPlayback(item)}
                        className="btn btn-secondary btn-sm"
                        style={{ flex: 1, fontSize: '0.78rem' }}
                        disabled={!item.file_exists}
                      >
                        <span>{item.file_exists ? 'Play Clip' : 'Unavailable'}</span>
                      </button>
                      {item.file_exists && item.download_url && (
                        <a
                          href={item.download_url}
                          download
                          className="btn btn-ghost btn-sm"
                          title="Download MP4"
                          style={{ padding: '0.25rem 0.5rem' }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M 21 15 v 4 a 2 2 0 0 1 -2 2 H 5 a 2 2 0 0 1 -2 -2 v -4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                          </svg>
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination Controls */}
          <div
            className="recordings-pagination"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '1rem',
              marginTop: '2rem',
              padding: '1rem 0',
              borderTop: '1px solid var(--border-color)',
            }}
          >
            <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
              Showing Page <strong style={{ color: 'var(--text-main)' }}>{page}</strong> of <strong style={{ color: 'var(--text-main)' }}>{numPages}</strong> ({totalCount} total recordings)
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => handlePageChange(1)}
                disabled={page <= 1}
                className="btn btn-ghost btn-sm"
                title="First Page"
              >
                &laquo; First
              </button>
              <button
                type="button"
                onClick={() => handlePageChange(page - 1)}
                disabled={!hasPrev || page <= 1}
                className="btn btn-secondary btn-sm"
              >
                &lsaquo; Previous
              </button>

              <span style={{ fontSize: '0.84rem', padding: '0 0.5rem', color: 'var(--text-main)', fontWeight: 600 }}>
                {page} / {numPages}
              </span>

              <button
                type="button"
                onClick={() => handlePageChange(page + 1)}
                disabled={!hasNext || page >= numPages}
                className="btn btn-secondary btn-sm"
              >
                Next &rsaquo;
              </button>
              <button
                type="button"
                onClick={() => handlePageChange(numPages)}
                disabled={page >= numPages}
                className="btn btn-ghost btn-sm"
                title="Last Page"
              >
                Last &raquo;
              </button>

              <select
                value={perPage}
                onChange={(e) => setPerPage(Number(e.target.value))}
                className="form-select"
                style={{ width: 'auto', height: '32px', fontSize: '0.8rem', padding: '0.1rem 1.6rem 0.1rem 0.6rem', marginLeft: '0.5rem' }}
              >
                <option value={24}>24 / page</option>
                <option value={48}>48 / page</option>
                <option value={96}>96 / page</option>
              </select>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '4rem 1.5rem', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <h3 style={{ fontSize: '1.15rem', color: 'var(--text-main)', marginBottom: '0.5rem' }}>No Recordings Found</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', maxWidth: '400px', margin: '0 auto 1.5rem' }}>
            {loading ? 'Scanning surveillance storage...' : 'No security recordings match your search or filter criteria. Continuous archives will appear here once cameras are actively recording.'}
          </p>
          {(cameraId || search || typeFilter !== 'all') && (
            <button
              type="button"
              onClick={() => { setCameraId(''); setSearch(''); setTypeFilter('all'); }}
              className="btn btn-secondary btn-sm"
            >
              Reset Filters
            </button>
          )}
        </div>
      )}

      {/* Global Video Player Modal with HTTP 206 Range Seeking */}
      {activeRecording && (
        <div
          id="videoModal"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backdropFilter: 'blur(4px)',
          }}
          onClick={(e) => { if (e.target.id === 'videoModal') setActiveRecording(null); }}
        >
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', width: '92%', maxWidth: '900px', overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color)' }}>
              <div>
                <h4 id="videoModalTitle" style={{ margin: 0, fontSize: '1rem', color: 'var(--text-main)', fontWeight: 600 }}>
                  {activeRecording.camera_name || 'Channel 01'} &mdash; {activeRecording.filename}
                </h4>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Recorded: {formatDate(activeRecording.started_at)} &bull; {activeRecording.formatted_size}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {activeRecording.download_url && (
                  <a
                    href={activeRecording.download_url}
                    download
                    className="btn btn-ghost btn-sm"
                    title="Download Video File"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M 21 15 v 4 a 2 2 0 0 1 -2 2 H 5 a 2 2 0 0 1 -2 -2 v -4"></path>
                      <polyline points="7 10 12 15 17 10"></polyline>
                      <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setActiveRecording(null)}
                  className="btn btn-ghost btn-icon"
                  style={{ padding: '0.25rem' }}
                  aria-label="Close modal"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>
            </div>

            <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0, background: '#000' }}>
              {videoError ? (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#f8fafc',
                    padding: '2rem',
                    textAlign: 'center',
                  }}
                >
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5" style={{ marginBottom: '0.75rem' }}>
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                  </svg>
                  <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: '0.25rem' }}>Playback Error</div>
                  <div style={{ fontSize: '0.84rem', color: '#94a3b8', maxWidth: '400px' }}>
                    The video format or media codec could not be decoded by the browser. You can download the MP4 directly to view in an external player.
                  </div>
                </div>
              ) : (
                <video
                  id="modalVideoPlayer"
                  controls
                  playsInline
                  autoPlay
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}
                  src={activeRecording.stream_url}
                  onError={() => setVideoError(true)}
                >
                  Your browser does not support HTML5 video playback.
                </video>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Recordings;
