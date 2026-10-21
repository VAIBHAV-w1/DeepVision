import React, { useState, useEffect, useRef } from 'react';
import { useCamera } from '../hooks/useCamera';
import { cameraService } from '../services/camera';
import { useToast } from '../components/common/Toast';
import { STREAM_MODES } from '../utils/constants';

export function CameraPreview({ cameraId, onNavigate }) {
  const {
    camera,
    mode,
    isRecording,
    stats,
    loading,
    error,
    toggleMode,
    startRecording,
    stopRecording,
    refreshCamera,
    streamUrl,
  } = useCamera(cameraId);

  const [clockStr, setClockStr] = useState('');
  const [switching, setSwitching] = useState(false);
  const [switchLabel, setSwitchLabel] = useState('');
  const [recordingLoading, setRecordingLoading] = useState(false);

  // Reference Image 1 Interactive Overlay States (Software Digital Zoom & Pan)
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const monitorRef = useRef(null);
  const streamImgRef = useRef(null);
  const { addToast } = useToast();

  // Digital live clock
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

  // Clean stream on unmount
  useEffect(() => {
    return () => {
      if (streamImgRef.current) {
        streamImgRef.current.src = '';
      }
    };
  }, []);

  // Mode switcher
  const handleSwitchMode = (newMode) => {
    if (newMode === mode) return;
    setSwitching(true);
    setSwitchLabel(newMode === STREAM_MODES.ORIGINAL ? 'Switching to Original Feed…' : 'Switching to Tracking + Detection…');
    if (streamImgRef.current) {
      streamImgRef.current.src = '';
    }
    toggleMode(newMode);
    setTimeout(() => {
      setSwitching(false);
    }, 1200);
  };

  // Fullscreen toggle
  const handleToggleFullscreen = () => {
    if (!monitorRef.current) return;
    if (!document.fullscreenElement) {
      monitorRef.current.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  // Snapshot capture
  const handleCaptureSnapshot = async () => {
    try {
      const res = await cameraService.captureSnapshot(cameraId);
      if (res && res.success) {
        addToast(`Snapshot #${res.evidence_id} captured and saved to Evidence Vault`, 'success');
      } else {
        const snapUrl = `${cameraService.getSnapshotUrl(cameraId)}?t=${Date.now()}`;
        window.open(snapUrl, '_blank');
        addToast('Snapshot captured and opened in Evidence Viewer', 'success');
      }
    } catch {
      const snapUrl = `${cameraService.getSnapshotUrl(cameraId)}?t=${Date.now()}`;
      window.open(snapUrl, '_blank');
      addToast('Instant snapshot opened in viewer', 'success');
    }
  };

  // Recording toggle
  const handleToggleRecording = async () => {
    setRecordingLoading(true);
    if (isRecording) {
      const res = await stopRecording();
      if (res.success) {
        addToast(res.message, 'success');
      } else {
        addToast(res.message, 'error');
      }
    } else {
      const res = await startRecording();
      if (res.success) {
        addToast(res.message, 'success');
      } else {
        addToast(res.message, 'error');
      }
    }
    setRecordingLoading(false);
  };

  // Zoom handlers
  const handleZoomIn = () => {
    setZoom((prev) => Math.min(prev + 0.5, 3));
    addToast(`Zoom: ${Math.min(zoom + 0.5, 3)}X`, 'info');
  };

  const handleZoomOut = () => {
    setZoom((prev) => {
      const next = Math.max(prev - 0.5, 1);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  };

  const handleZoomReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    addToast('Digital zoom reset to 1X', 'info');
  };

  // PTZ D-pad pan handlers
  const handlePtz = (direction) => {
    const step = 25;
    if (direction === 'up') setPan((p) => ({ ...p, y: p.y + step }));
    if (direction === 'down') setPan((p) => ({ ...p, y: p.y - step }));
    if (direction === 'left') setPan((p) => ({ ...p, x: p.x + step }));
    if (direction === 'right') setPan((p) => ({ ...p, x: p.x - step }));
    if (direction === 'center') {
      setPan({ x: 0, y: 0 });
      setZoom(1);
      addToast('PTZ Recentered to default home position', 'info');
    }
  };

  // Stream reload handler
  const handleReloadStream = () => {
    if (streamImgRef.current && camera) {
      const modeParam = mode === STREAM_MODES.ORIGINAL ? 'raw' : 'tracking';
      streamImgRef.current.src = `${cameraService.getStreamUrl(camera.id, modeParam)}&_t=${Date.now()}`;
      addToast('Surveillance stream reloaded', 'info');
    }
  };

  const isOriginal = mode === STREAM_MODES.ORIGINAL;
  const fpsDisplay = typeof stats?.fps === 'number' && stats.fps > 0 ? stats.fps : (camera?.status === 'online' ? 24 : 0);

  return (
    <div className="camera-preview-container">
      {/* 1. Top Navigation & Channel Header */}
      <div className="preview-topbar">
        <button
          type="button"
          onClick={() => onNavigate('cameras')}
          className="preview-back-link"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          <span>Back to Cameras</span>
        </button>

        <div className="preview-channel-badge">
          <span className={`status-pill ${camera?.status === 'online' ? 'status-live' : 'status-offline'}`}>
            <span className="status-dot"></span>
            <span>CHANNEL 0{cameraId}</span>
          </span>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1.25rem', padding: '10px 14px', borderRadius: '8px', background: 'rgba(220,38,38,0.1)', border: '1px solid var(--color-critical)', color: 'var(--color-critical)' }}>
          {error}
        </div>
      )}

      {/* 2. Responsive 3-Column Surveillance Grid */}
      <div className="camera-preview-grid">
        {/* =====================================================================
             COLUMN 1: COMPACT CAMERA INFORMATION PANEL
             ===================================================================== */}
        <div className="preview-panel preview-panel-left">
          <div className="preview-card-header">
            <div className="preview-camera-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M 23 7 l -7 5 7 5 V 7 z"></path>
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
              </svg>
            </div>
            <div className="preview-card-title-wrap">
              <h2 className="preview-camera-name" title={camera?.name || `Camera 0${cameraId}`}>
                {camera?.name || `Camera 0${cameraId}`}
              </h2>
              <span className="preview-camera-sub">{camera?.location || 'Primary Sector'}</span>
            </div>
          </div>

          <div className="preview-status-row">
            <div className="status-indicator-live">
              <span className="status-dot status-dot-live"></span>
              <span>Camera LIVE</span>
            </div>
            <div className="badge-ai-status" id="aiRunningBadge">
              <span className="status-dot status-dot-live"></span>
              <span>AI RUNNING</span>
            </div>
          </div>

          <div className="preview-specs-table">
            <div className="specs-row">
              <span className="specs-label">Source</span>
              <span className="specs-val">{(camera?.source_type || 'DIRECTSHOW').toUpperCase()}</span>
            </div>
            <div className="specs-row">
              <span className="specs-label">Resolution</span>
              <span className="specs-val" id="telemetryResolution">
                {stats?.width && stats?.height ? `${stats.width} × ${stats.height}` : '1280 × 720'}
              </span>
            </div>
            <div className="specs-row">
              <span className="specs-label">Stream Mode</span>
              <span className="specs-val mode-highlight" id="telemetryMode">
                {isOriginal ? 'Original' : 'Tracking + Detection'}
              </span>
            </div>
            <div className="specs-row">
              <span className="specs-label">Status</span>
              <span className="specs-val" id="telemetryUptime" style={{ color: '#10b981' }}>Active Surveillance</span>
            </div>
          </div>

          <div className="preview-panel-actions" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={() => onNavigate('recordings', { camera: cameraId })}
              className="btn btn-secondary btn-sm preview-btn"
              style={{ width: '100%', justifyContent: 'space-between' }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <circle cx="12" cy="12" r="3"></circle>
                </svg>
                <span>Recordings</span>
              </span>
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#10b981', fontSize: '0.72rem', padding: '2px 6px', borderRadius: '4px' }}>
                View
              </span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate('alerts', { camera: cameraId })}
              className="btn btn-secondary btn-sm preview-btn"
              style={{ width: '100%', justifyContent: 'space-between' }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M 10.29 3.86 L 1.82 18 a 2 2 0 0 0 1.71 3 h 16.94 a 2 2 0 0 0 1.71 -3 L 13.71 3.86 a 2 2 0 0 0 -3.42 0 z"></path>
                  <line x1="12" y1="9" x2="12" y2="13"></line>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                <span>Alerts</span>
              </span>
              <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.2)', color: '#f59e0b', fontSize: '0.72rem', padding: '2px 6px', borderRadius: '4px' }}>
                View
              </span>
            </button>

            <button
              type="button"
              onClick={() => onNavigate('alerts', { camera_id: cameraId })}
              className="btn btn-secondary btn-sm preview-btn"
              style={{ width: '100%', justifyContent: 'flex-start', gap: '0.4rem' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              <span>Camera Alerts &amp; Forensics</span>
            </button>
          </div>
        </div>

        {/* =====================================================================
             COLUMN 2: CENTER LIVE MONITOR WITH REFERENCE IMAGE 1 FLOATING HUD
             ===================================================================== */}
        <div className="preview-center-col">
          <div className="live-monitor glassy-frame" id="videoViewerContainer" ref={monitorRef}>
            {/* Live Real MJPEG Stream with Zoom & Pan Transform */}
            <div style={{ width: '100%', height: '100%', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img
                ref={streamImgRef}
                id="camera-live-stream"
                src={streamUrl}
                data-camera-id={cameraId}
                data-active-mode={mode}
                alt={`${camera?.name || 'Camera'} Live Surveillance Stream`}
                className="liveview-stream-img"
                style={{
                  transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
                  transition: 'transform 200ms ease-out',
                }}
                onError={(e) => {
                  e.currentTarget.onerror = null;
                  e.currentTarget.src = cameraService.getSnapshotUrl(cameraId);
                }}
              />
            </div>

            {/* Offline Overlay */}
            {camera && camera.status !== 'online' && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  background: 'rgba(11, 15, 25, 0.88)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  zIndex: 8,
                  color: '#f8fafc',
                  padding: '1.5rem',
                  textAlign: 'center',
                }}
              >
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5" style={{ marginBottom: '0.75rem' }}>
                  <line x1="1" y1="1" x2="23" y2="23"></line>
                  <path d="M 21 21 l -4.35 -4.35"></path>
                  <path d="M 16 16 v 1 a 2 2 0 0 1 -2 2 H 4 a 2 2 0 0 1 -2 -2 V 7 a 2 2 0 0 1 2 -2 h 2"></path>
                  <rect x="2" y="7" width="14" height="12" rx="2" ry="2" strokeDasharray="4 4"></rect>
                </svg>
                <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.25rem' }}>Camera Signal Offline</div>
                <div style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: '340px' }}>
                  Source disconnected. The surveillance engine will automatically reacquire when available.
                </div>
              </div>
            )}

            {/* -------------------------------------------------------------
                REFERENCE IMAGE 1: TOP FLOATING PILLS
                ------------------------------------------------------------- */}
            {/* Left Top Pill: Live indicator with Bitrate/FPS */}
            {(() => {
              const isOnline = camera?.status === 'online';
              const isLive = isOnline && fpsDisplay > 0;
              return (
                <div className="hud-pill-top-left">
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: isLive ? '#10b981' : isOnline ? '#f59e0b' : '#ef4444', animation: isLive ? 'pulse-dot 1.2s infinite' : undefined }}></span>
                  <span style={{ fontWeight: 700 }}>{isLive ? 'LIVE' : isOnline ? 'STANDBY' : 'OFFLINE'}</span>
                  <span style={{ color: 'rgba(255,255,255,0.7)', fontWeight: 500, fontSize: '0.72rem' }}>{fpsDisplay > 0 ? `${Math.round(fpsDisplay * 18)} kb/s` : '0 kb/s'}</span>
                </div>
              );
            })()}

            {/* Center Top Pill: Camera Location / Name */}
            <div className="hud-pill-top-center">
              <span>{camera?.name || 'Front Door'}</span>
            </div>

            {/* Right Top Pill: Daylight Icon + Live Digital Clock */}
            <div className="hud-pill-top-right">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2.2">
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
              </svg>
              <span>{clockStr}</span>
            </div>

            {/* -------------------------------------------------------------
                REFERENCE IMAGE 1: LEFT FLOATING ACTION BAR
                ------------------------------------------------------------- */}
            <div className="hud-actions-left">
              {/* Detection Mode Toggle */}
              <button
                type="button"
                className={`hud-icon-btn ${!isOriginal ? 'active' : ''}`}
                onClick={() => handleSwitchMode(isOriginal ? STREAM_MODES.TRACKING_DETECTION : STREAM_MODES.ORIGINAL)}
                title={isOriginal ? 'Enable YOLO11n + ByteTrack' : 'Switch to Raw Feed'}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                </svg>
              </button>

              {/* HD Resolution Badge */}
              <button
                type="button"
                className="hud-icon-btn"
                title="High Definition Stream"
                style={{ fontWeight: 800, fontSize: '0.72rem', letterSpacing: '0.04em' }}
              >
                HD
              </button>

              {/* Stream Reload Button */}
              <button
                type="button"
                className="hud-icon-btn"
                onClick={handleReloadStream}
                title="Reload Camera Stream"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
                </svg>
              </button>
            </div>

            {/* -------------------------------------------------------------
                REFERENCE IMAGE 1: RIGHT FLOATING ACTION BAR
                ------------------------------------------------------------- */}
            <div className="hud-actions-right">
              {/* Snapshot Button */}
              <button
                type="button"
                className="hud-icon-btn"
                onClick={handleCaptureSnapshot}
                title="Capture Snapshot Image to Evidence Vault"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z"></path>
                  <circle cx="12" cy="13" r="4"></circle>
                </svg>
              </button>

              {/* Record Toggle Button */}
              <button
                type="button"
                className={`hud-icon-btn ${isRecording ? 'recording-active' : ''}`}
                onClick={handleToggleRecording}
                disabled={recordingLoading}
                title={isRecording ? 'Stop MP4 Recording & Save to Archive' : 'Start MP4 Video Recording'}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill={isRecording ? '#ef4444' : 'none'} stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="8"></circle>
                  <circle cx="12" cy="12" r="3"></circle>
                </svg>
              </button>

              {/* Digital Zoom Reset */}
              <button
                type="button"
                className="hud-icon-btn"
                onClick={handleZoomReset}
                title="Reset Software Digital Zoom & Pan (1X)"
                style={{ fontWeight: 700, fontSize: '0.72rem' }}
              >
                1X
              </button>

              {/* Fullscreen Expand */}
              <button
                type="button"
                className="hud-icon-btn"
                onClick={handleToggleFullscreen}
                title="Toggle Fullscreen"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="15 3 21 3 21 9"></polyline>
                  <polyline points="9 21 3 21 3 15"></polyline>
                  <line x1="21" y1="3" x2="14" y2="10"></line>
                  <line x1="3" y1="21" x2="10" y2="14"></line>
                </svg>
              </button>
            </div>

            {/* -------------------------------------------------------------
                REFERENCE IMAGE 1: BOTTOM LEFT ZOOM CONTROLS PILL
                ------------------------------------------------------------- */}
            <div className="hud-zoom-pill">
              <button type="button" className="hud-zoom-btn" onClick={handleZoomOut} title="Zoom Out">
                &minus;
              </button>
              <span className="hud-zoom-indicator">{zoom}X</span>
              <button type="button" className="hud-zoom-btn" onClick={handleZoomIn} title="Zoom In">
                &#43;
              </button>
            </div>

            {/* -------------------------------------------------------------
                REFERENCE IMAGE 1: BOTTOM RIGHT CIRCULAR PTZ CONTROLLER
                ------------------------------------------------------------- */}
            <div className="hud-ptz-dial" title="PTZ Directional Control">
              <button type="button" className="ptz-btn ptz-up" onClick={() => handlePtz('up')} title="Tilt Up">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="12 4 4 18 20 18"></polygon>
                </svg>
              </button>
              <button type="button" className="ptz-btn ptz-left" onClick={() => handlePtz('left')} title="Pan Left">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="4 12 18 4 18 20"></polygon>
                </svg>
              </button>
              <button type="button" className="ptz-btn ptz-center" onClick={() => handlePtz('center')} title="Center / Reset Position">
              </button>
              <button type="button" className="ptz-btn ptz-right" onClick={() => handlePtz('right')} title="Pan Right">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="20 12 6 4 6 20"></polygon>
                </svg>
              </button>
              <button type="button" className="ptz-btn ptz-down" onClick={() => handlePtz('down')} title="Tilt Down">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="12 20 4 6 20 6"></polygon>
                </svg>
              </button>
            </div>

            {/* Mode Switching Spinner Overlay */}
            {switching && (
              <div className="mode-switch-overlay" id="modeSwitchOverlay" style={{ display: 'flex' }}>
                <div className="mode-switch-overlay-inner">
                  <svg className="mode-switch-spinner" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                    <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48 2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48 2.83-2.83" />
                  </svg>
                  <span className="mode-switch-label" id="modeSwitchLabel">
                    {switchLabel}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* =====================================================================
             COLUMN 3: CONTROLS & AI INFORMATION PANEL
             ===================================================================== */}
        <div className="preview-panel preview-panel-right">
          <div className="panel-section">
            <div className="panel-section-title">Surveillance Feed Mode</div>
            <div className="viewmode-segmented-control">
              <button
                type="button"
                className={`viewmode-btn ${isOriginal ? 'active' : ''}`}
                data-mode="raw"
                onClick={() => handleSwitchMode(STREAM_MODES.ORIGINAL)}
                title="Clean raw CCTV feed without AI annotations"
                id="btn-mode-original"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                  <line x1="8" y1="21" x2="16" y2="21"></line>
                </svg>
                <span>Original</span>
              </button>

              <button
                type="button"
                className={`viewmode-btn ${!isOriginal ? 'active' : ''}`}
                data-mode="tracking"
                onClick={() => handleSwitchMode(STREAM_MODES.TRACKING_DETECTION)}
                title="YOLO11n detection + ByteTrack multi-object tracking"
                id="btn-mode-tracking"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M 3 12 h 3 m 12 0 h 3 m -9 -9 v 3 m 0 12 v 3"></path>
                </svg>
                <span>Tracking + AI</span>
              </button>
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Recording &amp; Snapshot</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                type="button"
                className={`btn btn-sm ${isRecording ? 'btn-danger' : 'btn-secondary'}`}
                onClick={handleToggleRecording}
                disabled={recordingLoading}
                style={{ width: '100%', justifyContent: 'center', gap: '6px' }}
              >
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: isRecording ? '#ef4444' : 'currentColor',
                    animation: isRecording ? 'pulse 1s infinite' : 'none',
                  }}
                ></span>
                <span>{isRecording ? 'Stop Recording' : 'Start Recording'}</span>
              </button>

              <div className="quick-actions-grid">
                <button
                  type="button"
                  className="btn-quick-action"
                  onClick={handleCaptureSnapshot}
                  title="Capture Snapshot"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z"></path>
                    <circle cx="12" cy="13" r="4"></circle>
                  </svg>
                  <span>Snapshot</span>
                </button>

                <button
                  type="button"
                  className="btn-quick-action"
                  onClick={handleToggleFullscreen}
                  title="Toggle Fullscreen"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M 8 3 H 5 a 2 2 0 0 0 -2 2 v 3 m 18 0 V 5 a 2 2 0 0 0 -2 -2 h -3 m 0 18 h 3 a 2 2 0 0 0 2 -2 v -3 M 3 16 v 3 a 2 2 0 0 0 2 2 h 3"></path>
                  </svg>
                  <span>Fullscreen</span>
                </button>
              </div>
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Neural Engine Telemetry</div>
            <div className="preview-specs-table">
              <div className="specs-row">
                <span className="specs-label">Detector</span>
                <span className="specs-val mode-highlight">YOLO11n (CPU)</span>
              </div>
              <div className="specs-row">
                <span className="specs-label">Tracker</span>
                <span className="specs-val">ByteTrack</span>
              </div>
              <div className="specs-row">
                <span className="specs-label">Active Tracks</span>
                <span className="specs-val" id="aiActiveTracks" style={{ color: 'var(--color-live, #10b981)' }}>
                  {Array.isArray(stats?.tracks) ? stats.tracks.length : (typeof stats?.tracks === 'number' ? stats.tracks : 0)} tracks
                </span>
              </div>
              <div className="specs-row">
                <span className="specs-label">Inference FPS</span>
                <span className="specs-val" id="hudFps">
                  {fpsDisplay} FPS
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CameraPreview;
