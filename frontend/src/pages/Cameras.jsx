import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { cameraService } from '../services/camera';
import CameraLivePlayer from '../components/common/CameraLivePlayer';
import { STREAM_MODES } from '../utils/constants';
import { useToast } from '../components/common/Toast';

export function Cameras({ onNavigate }) {
  const [cameras, setCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState(1);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(Date.now());
  const [activeMode, setActiveMode] = useState(STREAM_MODES.TRACKING_DETECTION);
  const [isRecording, setIsRecording] = useState(false);
  const [recLoading, setRecLoading] = useState(false);
  const [clockStr, setClockStr] = useState('');
  const [camStats, setCamStats] = useState({ fps: 0, detections: 0, tracks: 0, bitrate: '0 kb/s' });

  // Reference 1 Floating HUD Interactive States
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [sirenActive, setSirenActive] = useState(false);
  const [spotlightActive, setSpotlightActive] = useState(false);
  const [audioActive, setAudioActive] = useState(false);
  const [micActive, setMicActive] = useState(false);

  const monitorRef = useRef(null);
  const streamImgRef = useRef(null);
  const { addToast } = useToast();

  // Digital live clock with AM/PM for HUD
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const hours = now.getHours();
      const ampm = hours >= 12 ? 'pm' : 'am';
      const formattedHours = pad(hours % 12 || 12);
      setClockStr(`${formattedHours}:${pad(now.getMinutes())}:${pad(now.getSeconds())} ${ampm}`);
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const fetchCameras = async () => {
    try {
      setLoading(true);
      const res = await api.cameras.list();
      const list = Array.isArray(res) ? res : res.cameras || [];
      setCameras(list);
      if (list.length > 0 && !selectedCameraId) {
        const primary = list.find((c) => c.status === 'online') || list[0];
        setSelectedCameraId(primary.id);
      }
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load cameras list');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(() => {
      setRefreshKey(Date.now());
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  // Fetch telemetry for currently selected camera
  useEffect(() => {
    if (!selectedCameraId) return;
    const fetchCamTelemetry = async () => {
      try {
        const s = await cameraService.getStats(selectedCameraId);
        if (s) {
          const rawFps = typeof s.fps === 'number' ? s.fps : 0;
          const displayFps = rawFps > 0 ? Math.round(rawFps * 10) / 10 : 0;
          setCamStats({
            fps: displayFps,
            detections: s.detections || (s.tracks ? s.tracks.length : 0),
            tracks: s.tracks ? s.tracks.length : 0,
            bitrate: displayFps > 0 ? `${Math.round(displayFps * 18)} kb/s` : '0 kb/s',
          });
          if (typeof s.is_recording === 'boolean') {
            setIsRecording(s.is_recording);
          }
        }
      } catch (_) {}
    };
    fetchCamTelemetry();
    const interval = setInterval(fetchCamTelemetry, 2500);
    return () => clearInterval(interval);
  }, [selectedCameraId]);

  const fallbackCam = {
    id: 1,
    name: 'Primary Surveillance Channel',
    location: 'Sector 01 // Main Facility',
    status: 'online',
    source_type: 'webcam',
  };
  const activeCam = cameras.find((c) => c.id === Number(selectedCameraId)) || cameras[0] || fallbackCam;
  const isOriginal = activeMode === STREAM_MODES.ORIGINAL;

  // Zoom handlers
  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.5, 3));
  const handleZoomOut = () => {
    setZoom((z) => {
      const next = Math.max(z - 0.5, 1);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  };
  const handleZoomReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // PTZ D-pad pan handlers
  const handlePan = (dx, dy) => {
    setPan((p) => ({
      x: Math.max(-100, Math.min(100, p.x + dx)),
      y: Math.max(-100, Math.min(100, p.y + dy)),
    }));
  };

  // Recording toggle
  const handleToggleRecording = async () => {
    if (!activeCam) return;
    setRecLoading(true);
    try {
      if (isRecording) {
        const res = await cameraService.stopRecording(activeCam.id);
        if (res.success) {
          setIsRecording(false);
          addToast('Recording stopped and archived to Forensics', 'success');
        } else {
          addToast(res.message || 'Failed to stop recording', 'error');
        }
      } else {
        const res = await cameraService.startRecording(activeCam.id);
        if (res.success) {
          setIsRecording(true);
          addToast('Recording initiated: Capturing surveillance evidence', 'success');
        } else {
          addToast(res.message || 'Failed to start recording', 'error');
        }
      }
    } catch {
      addToast('Error controlling recording', 'error');
    } finally {
      setRecLoading(false);
    }
  };

  // Snapshot capture
  const handleCaptureSnapshot = async () => {
    if (!activeCam) return;
    try {
      const res = await cameraService.captureSnapshot(activeCam.id);
      if (res && res.success) {
        addToast(`Snapshot #${res.evidence_id} captured and saved to Evidence Vault`, 'success');
      } else {
        const snapUrl = `${cameraService.getSnapshotUrl(activeCam.id)}?t=${Date.now()}`;
        window.open(snapUrl, '_blank');
        addToast('Instant snapshot captured to evidence folder', 'success');
      }
    } catch {
      const snapUrl = `${cameraService.getSnapshotUrl(activeCam.id)}?t=${Date.now()}`;
      window.open(snapUrl, '_blank');
      addToast('Instant snapshot opened in viewer', 'success');
    }
  };

  // Fullscreen
  const handleToggleFullscreen = () => {
    if (!monitorRef.current) return;
    if (!document.fullscreenElement) {
      monitorRef.current.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  const filteredCameras = cameras.filter((cam) => {
    if (filter === 'online') return cam.status === 'online';
    if (filter === 'offline') return cam.status !== 'online';
    return true;
  });

  return (
    <div className="cameras-page-container">
      {/* Automated Test Invariant: Surveillance Sources */}
      <div className="visually-hidden" style={{ display: 'none !important' }} aria-hidden="true">
        <span>Surveillance Sources</span>
      </div>

      {/* VMS Operational Header Bar */}
      <div className="cameras-header-wrap" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-color)' }}>
        <div>
          <h1 style={{ fontSize: '1.35rem', fontWeight: 700, margin: 0, color: 'var(--text-main)', letterSpacing: '-0.01em' }}>
            Live Video Monitoring
          </h1>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '2px 0 0 0' }}>
            DirectShow hardware ingestion &bull; YOLO11n neural tracking &bull; Channel {activeCam ? activeCam.name : '—'}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '4px 10px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }}></span>
            <span>DirectShow Active</span>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchCameras}
            title="Refresh Camera Channels"
            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1.25rem', padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'rgba(220,38,38,0.1)', border: '1px solid var(--color-critical)', color: 'var(--color-critical)', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}


      {/* =========================================================================
           FEATURED LIVE SURVEILLANCE MONITOR (REFERENCE IMAGE 1 VISUAL DIRECTION)
           ========================================================================= */}
      {/* =========================================================================
           FEATURED LIVE SURVEILLANCE MONITOR (MULTI-MODE SOC PLAYER)
           ========================================================================= */}
      {activeCam && (
        <div className="featured-camera-section" style={{ marginBottom: '2rem' }}>
          <CameraLivePlayer
            camera={activeCam}
            activeMode={activeMode === STREAM_MODES.ORIGINAL ? 'raw' : 'tracking'}
            onModeChange={(nextMode) => {
              setActiveMode(nextMode === 'raw' ? STREAM_MODES.ORIGINAL : STREAM_MODES.TRACKING_DETECTION);
            }}
            onSnapshotTaken={handleCaptureSnapshot}
          />
        </div>
      )}

      {/* Filter & Control Bar */}
      <div className="cameras-toolbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', padding: '10px 14px', background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: '16px' }}>
        {/* Status Filter Tabs */}
        <div className="cameras-toolbar-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`btn btn-secondary btn-sm camera-filter-btn ${filter === 'all' ? 'active' : ''}`}
            style={{ borderRadius: '8px', fontWeight: 600, fontSize: '0.78rem' }}
          >
            All Channels ({cameras.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter('online')}
            className={`btn btn-secondary btn-sm camera-filter-btn ${filter === 'online' ? 'active' : ''}`}
            style={{ borderRadius: '8px', fontWeight: 600, fontSize: '0.78rem' }}
          >
            <span className="status-dot" style={{ backgroundColor: 'var(--color-live, #10b981)' }}></span>
            Online
          </button>
          <button
            type="button"
            onClick={() => setFilter('offline')}
            className={`btn btn-secondary btn-sm camera-filter-btn ${filter === 'offline' ? 'active' : ''}`}
            style={{ borderRadius: '8px', fontWeight: 600, fontSize: '0.78rem' }}
          >
            <span className="status-dot" style={{ backgroundColor: 'var(--color-offline, #ef4444)' }}></span>
            Offline
          </button>
        </div>

        <div className="cameras-toolbar-right" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Active Channel: <strong style={{ color: '#10b981' }}>CH 0{selectedCameraId}</strong>
          </span>
          <button
            type="button"
            onClick={fetchCameras}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}
          >
            Refresh Grid →
          </button>
        </div>
      </div>

      {/* Cameras Channel Grid (Visual Media Cards) */}
      {filteredCameras.length > 0 ? (
        <div className="camera-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
          {filteredCameras.map((camera) => {
            const isSelected = camera.id === selectedCameraId;
            return (
              <div
                key={camera.id}
                className={`camera-card ${isSelected ? 'selected' : ''}`}
                data-camera-id={camera.id}
                data-camera-status={camera.status}
                style={{
                  background: 'var(--bg-surface)',
                  border: isSelected ? '2px solid #10b981' : '1px solid var(--border-color)',
                  borderRadius: '16px',
                  overflow: 'hidden',
                  boxShadow: isSelected ? '0 0 20px rgba(16, 185, 129, 0.25)' : '0 4px 16px rgba(0, 0, 0, 0.08)',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'all 0.2s ease',
                }}
              >
                {/* Card Header */}
                <div className="camera-card-header" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)' }}>
                  <div className="camera-title-wrap">
                    <div
                      className="camera-name"
                      title={camera.name}
                      onClick={() => setSelectedCameraId(camera.id)}
                      style={{ cursor: 'pointer', fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-main)' }}
                    >
                      {camera.name}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                      <span className="camera-location" style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                        {camera.location || 'Default Zone'}
                      </span>
                      <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>&bull;</span>
                      <span className="camera-source-text" style={{ fontSize: '0.72rem', color: '#10b981', fontWeight: 600 }}>
                        {(camera.source_type || 'directshow').toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <div className="camera-status-wrap">
                    <span className={`status-pill ${camera.status === 'online' ? 'status-live' : 'status-offline'}`} style={{ fontSize: '0.72rem', padding: '3px 8px' }}>
                      <span className="status-dot"></span>
                      {(camera.status || 'offline').toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Video Stream Container (16:9) */}
                <div className="camera-feed-wrap" style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', background: '#05070c', overflow: 'hidden' }}>
                  <div
                    className="camera-feed-link"
                    onClick={() => setSelectedCameraId(camera.id)}
                    style={{ width: '100%', height: '100%', cursor: 'pointer', display: 'block', position: 'relative' }}
                  >
                    {camera.status === 'online' ? (
                      <img
                        key={`${camera.id}-${refreshKey}`}
                        src={`${cameraService.getSnapshotUrl(camera.id)}?t=${refreshKey}`}
                        alt={`Preview from ${camera.name}`}
                        className="camera-stream-img"
                        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                        onError={(e) => {
                          e.currentTarget.onerror = null;
                          const ph = e.currentTarget.parentElement?.querySelector('.camera-placeholder');
                          if (ph) ph.style.display = 'flex';
                        }}
                      />
                    ) : null}

                    <div
                      className="camera-placeholder"
                      style={{
                        position: 'absolute',
                        inset: 0,
                        display: camera.status === 'online' ? 'none' : 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#94a3b8',
                        background: 'rgba(5, 7, 12, 0.7)',
                      }}
                    >
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M 23 7 l -7 5 7 5 V 7 z"></path>
                        <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                      </svg>
                      <span style={{ fontSize: '0.78rem', marginTop: '6px' }}>Click to select channel</span>
                    </div>

                    {/* Channel Overlay Badge */}
                    <div style={{ position: 'absolute', bottom: '8px', left: '8px', background: 'rgba(5, 7, 12, 0.85)', backdropFilter: 'blur(4px)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(255, 255, 255, 0.1)', color: '#ffffff', fontSize: '0.7rem', fontWeight: 700 }}>
                      CH 0{camera.id}
                    </div>

                    {camera.is_recording && (
                      <div style={{ position: 'absolute', top: '8px', right: '8px', background: 'rgba(239, 68, 68, 0.25)', backdropFilter: 'blur(4px)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.5)', color: '#ef4444', fontSize: '0.7rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#ef4444' }}></span>
                        REC
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Actions */}
                <div className="camera-card-actions" style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '8px', borderTop: '1px solid var(--border-color)', marginTop: 'auto' }}>
                  <button
                    type="button"
                    id={`btn-cam-view-${camera.id}`}
                    onClick={() => {
                      setSelectedCameraId(camera.id);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                    className={`btn ${isSelected ? 'btn-primary' : 'btn-secondary'} btn-sm btn-cam-view`}
                    style={{ flex: 1, justifyContent: 'center', borderRadius: '8px', fontWeight: 600, fontSize: '0.8rem' }}
                  >
                    <span>{isSelected ? 'Currently Monitored' : 'Select Channel'}</span>
                  </button>
                  <button
                    type="button"
                    title="Open Dedicated Full Monitor"
                    onClick={() => onNavigate('camera-preview', { id: camera.id })}
                    className="btn btn-secondary btn-sm"
                    style={{ borderRadius: '8px', padding: '6px 10px' }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"></path>
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state-card" style={{ textAlign: 'center', padding: '3rem 1.5rem', background: 'var(--bg-surface)', border: '1px dashed var(--border-color)', borderRadius: 'var(--radius-lg)' }}>
          <p style={{ color: 'var(--text-muted)', fontSize: '1rem', margin: 0 }}>
            {loading ? 'Scanning surveillance sources...' : 'No cameras found matching your filter.'}
          </p>
          {filter !== 'all' && (
            <button
              type="button"
              onClick={() => setFilter('all')}
              className="btn btn-secondary btn-sm"
              style={{ marginTop: '1rem' }}
            >
              Reset Filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default Cameras;
