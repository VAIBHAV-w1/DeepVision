import React, { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../services/api';
import cameraService from '../../services/camera';
import { useTranslation } from '../../i18n/i18nContext';

/**
 * CameraLivePlayer — Clean, Camera-First Surveillance Monitor
 * 
 * Strict Surveillance Modes: Exactly TWO primary viewing modes:
 * 1. RAW STREAM — actual live camera footage without detection annotations.
 * 2. DETECTION & TRACKING — real live camera footage with real YOLO11n detections and ByteTrack tracking.
 * 
 * Zero synthetic streams, zero test patterns, zero demo fallbacks.
 */
export function CameraLivePlayer(props) {
  const {
    camera,
    activeMode: activeModeProp,
    mode: modeProp,
    onModeChange,
    onSnapshotTaken,
    compact = false,
    stats = null,
    isRecording = false,
    onToggleRecording = null,
    cameraId: propCameraId,
    cameraName: propCameraName,
  } = props;
  const { t } = useTranslation();
  const cameraId = camera?.id || propCameraId || 4;
  const cameraName = camera?.name || propCameraName || `Camera 0${cameraId}`;
  const cameraLocation = camera?.location || 'Primary Sector';
  const isCameraOnline = camera?.status === 'online';

  // Mode: 'raw' (RAW STREAM) | 'tracking' (DETECTION & TRACKING)
  const effectiveModeProp = activeModeProp || modeProp || 'tracking';
  const [mode, setMode] = useState(effectiveModeProp === 'raw' ? 'raw' : 'tracking');
  const [streamKey, setStreamKey] = useState(Date.now());
  const [isLoaded, setIsLoaded] = useState(false);
  const [isError, setIsError] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [liveStats, setLiveStats] = useState(stats || {});
  const [localRecording, setLocalRecording] = useState(isRecording);
  const [recLoading, setRecLoading] = useState(false);

  // Restricted Zone Interactive Editor (Phase 4)
  const [isZoneEditorOpen, setIsZoneEditorOpen] = useState(false);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState(null);
  const [currentRect, setCurrentRect] = useState(null);
  const [zoneName, setZoneName] = useState('Front Perimeter');
  const [zonesList, setZonesList] = useState([]);
  const [savingZone, setSavingZone] = useState(false);
  const overlaySvgRef = useRef(null);

  // Digital Zoom & Pan
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [clockStr, setClockStr] = useState('');

  const containerRef = useRef(null);
  const imgRef = useRef(null);

  // Synchronize recording state with parent
  useEffect(() => {
    setLocalRecording(isRecording);
  }, [isRecording]);

  // Live Stream Telemetry Polling (every 1.5 seconds)
  useEffect(() => {
    let active = true;
    const fetchTelemetry = async () => {
      try {
        const res = await fetch(`/api/cameras/${cameraId}/stats/`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          if (active) {
            setLiveStats(data);
            if (typeof data.is_recording === 'boolean') {
              setLocalRecording(data.is_recording);
            }
          }
        }
      } catch (_) {}
    };
    fetchTelemetry();
    const timer = setInterval(fetchTelemetry, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [cameraId]);

  // Live HUD Clock (honors operator 12h/24h setting)
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const fmt = localStorage.getItem('deepvision_clock_format') || '24h';
      if (fmt === '12h') {
        const hours = now.getHours();
        const ampm = hours >= 12 ? 'PM' : 'AM';
        const formattedHours = pad(hours % 12 || 12);
        setClockStr(`${formattedHours}:${pad(now.getMinutes())}:${pad(now.getSeconds())} ${ampm}`);
      } else {
        setClockStr(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`);
      }
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  // Sync with prop
  useEffect(() => {
    const nextMode = (activeModeProp || modeProp) === 'raw' ? 'raw' : 'tracking';
    if (nextMode !== mode) {
      setMode(nextMode);
      setStreamKey(Date.now());
    }
  }, [activeModeProp, modeProp]);

  // Clean stream when switching to a different cameraId
  const prevCameraIdRef = useRef(cameraId);
  useEffect(() => {
    if (prevCameraIdRef.current !== cameraId) {
      prevCameraIdRef.current = cameraId;
      setIsLoaded(false);
      setIsError(false);
      setStreamKey(Date.now());
    }
  }, [cameraId]);

  // Abort active MJPEG HTTP stream strictly on component unmount (captures DOM node before React nulls ref)
  useEffect(() => {
    const imgEl = imgRef.current;
    return () => {
      if (imgEl) {
        imgEl.src = '';
        imgEl.removeAttribute('src');
      }
    };
  }, []);

  // Fullscreen event listener
  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  const handleModeSwitch = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setIsLoaded(false);
    setIsError(false);
    setStreamKey(Date.now());
    if (onModeChange) {
      onModeChange(newMode);
    }
  };

  const handleRetry = () => {
    setIsError(false);
    setIsLoaded(false);
    setStreamKey(Date.now());
  };

  // Zoom controls
  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.25, 3));
  const handleZoomOut = () => {
    setZoom((z) => {
      const next = Math.max(z - 0.25, 1);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  };
  const handleZoomReset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Pan controls
  const handlePan = (direction) => {
    if (zoom <= 1) return;
    const step = 30;
    setPan((p) => {
      if (direction === 'up') return { ...p, y: p.y + step };
      if (direction === 'down') return { ...p, y: p.y - step };
      if (direction === 'left') return { ...p, x: p.x + step };
      if (direction === 'right') return { ...p, x: p.x - step };
      if (direction === 'center') return { x: 0, y: 0 };
      return p;
    });
  };

  // Fullscreen toggle
  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  // Snapshot capture
  const handleSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      const res = await cameraService.captureSnapshot(cameraId);
      if (onSnapshotTaken) {
        onSnapshotTaken(res);
      }
    } catch (e) {
      if (onSnapshotTaken) {
        onSnapshotTaken({ success: false, error: e.message });
      }
    } finally {
      setSnapshotLoading(false);
    }
  };

  // Record Clip Toggle (accessible to ordinary users and operators)
  const handleRecordClick = async () => {
    if (onToggleRecording) {
      onToggleRecording();
      return;
    }
    setRecLoading(true);
    try {
      if (localRecording) {
        const res = await cameraService.stopRecording(cameraId);
        if (res && res.success !== false) {
          setLocalRecording(false);
          if (onSnapshotTaken) {
            onSnapshotTaken({ success: true, message: 'Surveillance recording saved to archive.' });
          }
        }
      } else {
        const res = await cameraService.startRecording(cameraId);
        if (res && res.success !== false) {
          setLocalRecording(true);
          if (onSnapshotTaken) {
            onSnapshotTaken({ success: true, message: 'Continuous recording started.' });
          }
        }
      }
    } catch (err) {
      console.error('Recording operation error:', err);
    } finally {
      setRecLoading(false);
    }
  };

  // Zone Management API calls (via CSRF-aware API client)
  const fetchCameraZones = useCallback(async () => {
    try {
      const data = await api.cameras.getZones(cameraId);
      if (data && Array.isArray(data.zones)) {
        setZonesList(data.zones);
      }
    } catch (_) {}
  }, [cameraId]);

  useEffect(() => {
    fetchCameraZones();
  }, [fetchCameraZones]);

  // Zone drawing mouse handlers (maps viewport coordinates to 1280x720 video space)
  const getSvgCoords = (e) => {
    if (!overlaySvgRef.current) return { x: 0, y: 0 };
    const rect = overlaySvgRef.current.getBoundingClientRect();
    const x = Math.round(Math.max(0, Math.min(1280, ((e.clientX - rect.left) / rect.width) * 1280)));
    const y = Math.round(Math.max(0, Math.min(720, ((e.clientY - rect.top) / rect.height) * 720)));
    return { x, y };
  };

  const handleZoneMouseDown = (e) => {
    if (!isZoneEditorOpen) return;
    const pt = getSvgCoords(e);
    setIsDrawing(true);
    setDrawStart(pt);
    setCurrentRect({ x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y });
  };

  const handleZoneMouseMove = (e) => {
    if (!isZoneEditorOpen || !isDrawing || !drawStart) return;
    const pt = getSvgCoords(e);
    setCurrentRect({
      x1: Math.min(drawStart.x, pt.x),
      y1: Math.min(drawStart.y, pt.y),
      x2: Math.max(drawStart.x, pt.x),
      y2: Math.max(drawStart.y, pt.y),
    });
  };

  const handleZoneMouseUp = () => {
    if (!isZoneEditorOpen || !isDrawing) return;
    setIsDrawing(false);
  };

  const handleSaveDrawnZone = async () => {
    if (!currentRect || Math.abs(currentRect.x2 - currentRect.x1) < 20 || Math.abs(currentRect.y2 - currentRect.y1) < 20) {
      if (onSnapshotTaken) {
        onSnapshotTaken({ success: false, error: 'Draw a rectangular perimeter zone on the video first.' });
      }
      return;
    }
    setSavingZone(true);
    try {
      const cleanName = zoneName.trim() || 'Front Perimeter';
      const res = await api.cameras.createZone(cameraId, {
        name: cleanName,
        x1: currentRect.x1,
        y1: currentRect.y1,
        x2: currentRect.x2,
        y2: currentRect.y2,
        enabled: true,
      });
      if (res && (res.zone || res.success !== false)) {
        setCurrentRect(null);
        await fetchCameraZones();
        if (onSnapshotTaken) {
          onSnapshotTaken({ success: true, message: `Restricted zone '${cleanName}' saved & active.` });
        }
      }
    } catch (err) {
      console.error('Save zone error:', err);
      if (onSnapshotTaken) {
        onSnapshotTaken({ success: false, error: err.message || 'Failed to save restricted zone.' });
      }
    } finally {
      setSavingZone(false);
    }
  };

  const handleApplyWebcamPreset = () => {
    // Preset: 1280x720 centered perimeter (360, 100 to 920, 640)
    setCurrentRect({ x1: 360, y1: 100, x2: 920, y2: 640 });
    setZoneName('Front Perimeter');
  };

  const handleDeleteZone = async (zoneId) => {
    try {
      await api.cameras.deleteZone(cameraId, zoneId);
      fetchCameraZones();
    } catch (_) {}
  };

  const handleToggleZone = async (zoneId) => {
    try {
      await api.cameras.toggleZone(cameraId, zoneId);
      fetchCameraZones();
    } catch (_) {}
  };

  // Stream URL based on current mode
  const streamUrl = mode === 'raw'
    ? `/api/cameras/${cameraId}/stream/original/?t=${streamKey}`
    : `/api/cameras/${cameraId}/stream/tracking/?t=${streamKey}`;

  // Truthful live telemetry (zero fabricated fallback FPS numbers)
  const measuredFps = typeof liveStats?.fps === 'number' && liveStats.fps > 0 ? liveStats.fps : 0;
  const cameraFpsStr = measuredFps > 0 ? `${measuredFps.toFixed(1)} FPS` : (isLoaded && !isError ? 'Syncing...' : '0.0 FPS');
  const aiFps = typeof liveStats?.ai_fps === 'number' && liveStats.ai_fps > 0 ? liveStats.ai_fps : 0;
  const detectionsCount = liveStats?.detections ?? liveStats?.tracks?.length ?? 0;
  const zones = zonesList.length > 0 ? zonesList.filter((z) => z.enabled !== false) : (liveStats?.zones || []);
  const activeIntrusions = liveStats?.active_intrusions || [];
  const hasIntrusion = activeIntrusions.length > 0;

  return (
    <div
      ref={containerRef}
      className="camera-live-player camera-live-player-container"
      data-camera-id={cameraId}
      data-view-mode={mode}
      style={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: compact ? '6px' : '10px',
        background: 'var(--bg-surface, #0f172a)',
        border: '1px solid var(--border-color, rgba(255, 255, 255, 0.12))',
        borderRadius: '6px',
        padding: compact ? '8px' : '12px',
        boxSizing: 'border-box',
      }}
    >
      {/* 1. Header Toolbar with EXACTLY TWO Viewing Modes */}
      <div
        className="camera-player-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px',
          paddingBottom: '8px',
          borderBottom: '1px solid var(--border-color, rgba(255, 255, 255, 0.08))',
        }}
      >
        {/* Left: Two-Option Viewing Mode Switch */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            className="surveillance-mode-segmented"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              background: 'rgba(0, 0, 0, 0.4)',
              padding: '3px',
              borderRadius: '4px',
              border: '1px solid var(--border-color, rgba(255, 255, 255, 0.14))',
            }}
          >
            <button
              type="button"
              id="btn-mode-raw"
              data-mode="raw"
              className={`viewmode-btn ${mode === 'raw' ? 'active' : ''}`}
              onClick={() => handleModeSwitch('raw')}
              title="Actual live camera footage without detection annotations"
              style={{
                background: mode === 'raw' ? 'var(--color-primary, #10b981)' : 'transparent',
                color: mode === 'raw' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
                border: 'none',
                padding: '5px 12px',
                borderRadius: '3px',
                fontSize: '0.76rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>{t('monitor.modeRaw', 'RAW STREAM')}</span>
            </button>

            <button
              type="button"
              id="btn-mode-tracking"
              data-mode="tracking"
              className={`viewmode-btn ${mode === 'tracking' ? 'active' : ''}`}
              onClick={() => handleModeSwitch('tracking')}
              title="Real live camera footage with real YOLO11n detections and ByteTrack tracking overlays"
              style={{
                background: mode === 'tracking' ? 'var(--color-primary, #10b981)' : 'transparent',
                color: mode === 'tracking' ? '#ffffff' : 'var(--text-secondary, #94a3b8)',
                border: 'none',
                padding: '5px 12px',
                borderRadius: '3px',
                fontSize: '0.76rem',
                fontWeight: 700,
                letterSpacing: '0.03em',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>{t('monitor.modeTracking', 'DETECTION & TRACKING')}</span>
            </button>
          </div>
        </div>

        {/* Right: Operational Status & Telemetry Strip */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: '4px',
              background: isCameraOnline ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${isCameraOnline ? '#10b981' : '#ef4444'}`,
              fontSize: '0.72rem',
              fontWeight: 700,
              color: isCameraOnline ? '#10b981' : '#ef4444',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isCameraOnline ? '#10b981' : '#ef4444',
                animation: isCameraOnline ? 'pulse-dot 1.4s infinite' : 'none',
              }}
            />
            <span>{isCameraOnline ? 'SIGNAL ONLINE' : 'SIGNAL OFFLINE'}</span>
          </div>

          <span
            id="camera-fps-badge"
            style={{
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.74rem',
              color: '#ffffff',
              background: 'rgba(0, 0, 0, 0.45)',
              padding: '3px 8px',
              borderRadius: '4px',
              border: '1px solid var(--border-color, rgba(255, 255, 255, 0.15))',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <strong style={{ color: '#10b981' }}>{cameraFpsStr}</strong>
            {mode === 'tracking' && aiFps > 0 && (
              <span style={{ color: '#94a3b8', fontSize: '0.70rem' }}>
                • AI {aiFps.toFixed(1)} FPS
              </span>
            )}
          </span>
        </div>
      </div>

      {/* 2. Main Live Camera Viewport (Maximized, High-Density Aspect Ratio) */}
      <div
        className="camera-monitor-frame live-monitor"
        id="videoViewerContainer"
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16 / 9',
          background: '#040711',
          borderRadius: '4px',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Loading Spinner */}
        {!isLoaded && !isError && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              background: 'rgba(11, 15, 25, 0.85)',
              zIndex: 3,
            }}
          >
            <div
              style={{
                width: '28px',
                height: '28px',
                border: '2px solid rgba(255, 255, 255, 0.15)',
                borderTopColor: 'var(--color-primary, #10b981)',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontFamily: 'var(--font-mono, monospace)' }}>
              Acquiring Live Footage CH 0{cameraId}...
            </span>
          </div>
        )}

        {/* Live Decoded MJPEG Stream Image */}
        <img
          ref={imgRef}
          id="camera-live-stream"
          src={streamUrl}
          data-camera-id={cameraId}
          data-mode={mode}
          alt={`${cameraName} Live Surveillance Stream`}
          className="liveview-stream-img"
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: isError ? 'none' : 'block',
            transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
            transition: 'transform 120ms ease-out',
          }}
          onLoad={() => {
            setIsLoaded(true);
            setIsError(false);
          }}
          onError={() => {
            setIsError(true);
            setIsLoaded(false);
          }}
        />

        {/* Interactive Restricted Zone Canvas Overlay (Phase 4) */}
        {isZoneEditorOpen && (
          <svg
            ref={overlaySvgRef}
            id="camera-zone-overlay"
            viewBox="0 0 1280 720"
            preserveAspectRatio="none"
            onMouseDown={handleZoneMouseDown}
            onMouseMove={handleZoneMouseMove}
            onMouseUp={handleZoneMouseUp}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              zIndex: 10,
              cursor: isDrawing ? 'crosshair' : 'crosshair',
              userSelect: 'none',
              background: 'rgba(0, 0, 0, 0.25)',
            }}
          >
            {/* Render existing zones */}
            {zonesList.map((z) => {
              const zw = Math.max(10, z.x2 - z.x1);
              const zh = Math.max(10, z.y2 - z.y1);
              return (
                <g key={z.id}>
                  <rect
                    x={z.x1}
                    y={z.y1}
                    width={zw}
                    height={zh}
                    fill={z.enabled ? 'rgba(245, 158, 11, 0.18)' : 'rgba(100, 116, 139, 0.12)'}
                    stroke={z.enabled ? '#f59e0b' : '#64748b'}
                    strokeWidth="3"
                    strokeDasharray="6 4"
                  />
                  <text
                    x={z.x1 + 10}
                    y={z.y1 + 24}
                    fill="#f59e0b"
                    fontSize="16"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    ZONE: {z.name} {z.enabled ? '' : '(INACTIVE)'}
                  </text>
                </g>
              );
            })}

            {/* Render active drawn rectangle */}
            {currentRect && (
              <g>
                <rect
                  x={currentRect.x1}
                  y={currentRect.y1}
                  width={Math.max(4, currentRect.x2 - currentRect.x1)}
                  height={Math.max(4, currentRect.y2 - currentRect.y1)}
                  fill="rgba(239, 68, 68, 0.25)"
                  stroke="#ef4444"
                  strokeWidth="3.5"
                />
                <rect
                  x={currentRect.x1}
                  y={currentRect.y1}
                  width={Math.min(320, Math.max(160, currentRect.x2 - currentRect.x1))}
                  height="26"
                  fill="rgba(15, 23, 42, 0.9)"
                />
                <text
                  x={currentRect.x1 + 6}
                  y={currentRect.y1 + 18}
                  fill="#ffffff"
                  fontSize="13"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  NEW: {zoneName} ({Math.round(currentRect.x1)},{Math.round(currentRect.y1)})
                </text>
              </g>
            )}
          </svg>
        )}

        {/* Connection Failure / Bridge Offline Screen (No Synthetic Fallback) */}
        {isError && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '1.5rem',
              textAlign: 'center',
              background: 'rgba(11, 15, 25, 0.95)',
              color: '#ffffff',
              zIndex: 5,
            }}
          >
            <svg
              width="36"
              height="36"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#ef4444"
              strokeWidth="2"
              style={{ marginBottom: '0.75rem' }}
            >
              <line x1="1" y1="1" x2="23" y2="23" />
              <path d="M21 21H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3m3-3h6l2 3h4a2 2 0 0 1 2 2v9.34" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <div style={{ fontSize: '0.92rem', fontWeight: 700, marginBottom: '0.25rem' }}>
              {t('monitor.signalInterrupted', 'Camera Signal Interrupted')}
            </div>
            <div
              style={{
                fontSize: '0.78rem',
                color: '#94a3b8',
                maxWidth: '420px',
                marginBottom: '1rem',
                lineHeight: 1.5,
              }}
            >
              {t('monitor.signalInterruptedDesc', 'The selected camera source is currently offline or unreachable. Verify the physical connection or network stream address.')}
            </div>
            <button
              type="button"
              onClick={handleRetry}
              className="btn btn-primary btn-sm"
              style={{ padding: '6px 16px', fontSize: '0.78rem' }}
            >
              {t('monitor.retryConnection', 'Retry Connection')}
            </button>
          </div>
        )}

        {/* Top Floating HUD Bar */}
        <div
          style={{
            position: 'absolute',
            top: '10px',
            left: '10px',
            right: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            pointerEvents: 'none',
            zIndex: 4,
          }}
        >
          {/* Top-Left: Channel & Source Badge */}
          <div
            className="hud-pill-top-left"
            style={{
              pointerEvents: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '4px 10px',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isCameraOnline ? '#10b981' : '#ef4444',
              }}
            />
            <span style={{ fontWeight: 700 }}>Channel 0{cameraId} &bull; LIVE</span>
            <span style={{ color: 'rgba(255, 255, 255, 0.6)' }}>&bull;</span>
            <span style={{ color: 'rgba(255, 255, 255, 0.9)' }}>{cameraName}</span>
          </div>

          {/* Top-Right: Mode & Clock */}
          <div
            className="hud-pill-top-right"
            style={{
              pointerEvents: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '4px 10px',
              borderRadius: '4px',
              color: '#f8fafc',
              fontSize: '0.72rem',
              fontWeight: 600,
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            {hasIntrusion ? (
              <span style={{ color: '#ef4444', fontWeight: 800 }}>
                [!] RESTRICTED AREA INTRUSION DETECTED
              </span>
            ) : mode === 'tracking' ? (
              <span style={{ color: '#10b981', fontWeight: 700 }}>
                {zones.length > 0 ? `ZONE MONITORED (${zones[0].name}) • ` : ''}YOLO11n + ByteTrack ({detectionsCount} Objects)
              </span>
            ) : (
              <span style={{ color: '#38bdf8', fontWeight: 700 }}>
                RAW STREAM (UNANNOTATED)
              </span>
            )}
            <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>|</span>
            <span>{clockStr}</span>
          </div>
        </div>

        {/* Bottom-Left Zoom HUD Indicator */}
        {zoom > 1 && (
          <div
            style={{
              position: 'absolute',
              bottom: '12px',
              left: '12px',
              zIndex: 4,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.16)',
              padding: '3px 8px',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '0.72rem',
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            <span>ZOOM: {zoom.toFixed(2)}x</span>
            <button
              type="button"
              onClick={handleZoomReset}
              style={{
                background: 'rgba(255, 255, 255, 0.15)',
                border: 'none',
                color: '#fff',
                fontSize: '0.68rem',
                padding: '2px 5px',
                borderRadius: '2px',
                cursor: 'pointer',
              }}
            >
              Reset
            </button>
          </div>
        )}
      </div>

      {/* 3. Bottom Operational Control Strip */}
      <div
        className="camera-player-controls"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '8px',
          paddingTop: '4px',
        }}
      >
        {/* Left Actions: Snapshot & Recording */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            id="btn-camera-snapshot"
            onClick={handleSnapshot}
            disabled={snapshotLoading}
            className="btn btn-secondary btn-sm"
            style={{
              padding: '5px 12px',
              fontSize: '0.78rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <span>{snapshotLoading ? t('monitor.capturing', 'Capturing...') : t('monitor.snapshot', 'Snapshot')}</span>
          </button>

          <button
            type="button"
            id="btn-camera-record"
            onClick={handleRecordClick}
            disabled={recLoading}
            className={`btn btn-sm ${localRecording ? 'btn-danger' : 'btn-secondary'}`}
            style={{
              padding: '5px 12px',
              fontSize: '0.78rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: localRecording ? '#ffffff' : '#ef4444',
                animation: localRecording ? 'pulse-dot 1s infinite' : 'none',
              }}
            />
            <span>{localRecording ? t('monitor.stopRecording', 'Stop Recording') : t('surveillance.startRecording', 'Record Clip')}</span>
          </button>

          {/* Interactive Zone Editor Toggle (Phase 4) */}
          <button
            type="button"
            id="btn-toggle-zone-editor"
            onClick={() => setIsZoneEditorOpen(!isZoneEditorOpen)}
            className={`btn btn-sm ${isZoneEditorOpen ? 'btn-primary' : 'btn-secondary'}`}
            style={{
              padding: '5px 12px',
              fontSize: '0.78rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="3 3" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <span>{isZoneEditorOpen ? 'Close Perimeter Editor' : 'Configure Perimeter'}</span>
          </button>
        </div>

        {/* Right Tools: Zoom, PTZ D-pad & Fullscreen */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            type="button"
            onClick={handleZoomIn}
            className="btn btn-secondary btn-sm"
            title="Digital Zoom In"
            style={{ padding: '5px 9px', fontSize: '0.75rem' }}
          >
            +
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            className="btn btn-secondary btn-sm"
            title="Digital Zoom Out"
            style={{ padding: '5px 9px', fontSize: '0.75rem' }}
          >
            &minus;
          </button>

          <button
            type="button"
            id="btn-camera-fullscreen"
            onClick={handleToggleFullscreen}
            className="btn btn-secondary btn-sm"
            title="Toggle Fullscreen"
            style={{
              padding: '5px 10px',
              fontSize: '0.75rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 3 21 3 21 9" />
              <polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" />
              <line x1="3" y1="21" x2="10" y2="14" />
            </svg>
            <span>{isFullscreen ? 'Exit' : 'Fullscreen'}</span>
          </button>
        </div>
      </div>

      {/* 4. Interactive Security Perimeter Zone Editor Drawer (Phase 4) */}
      {isZoneEditorOpen && (
        <div
          id="camera-zone-editor-drawer"
          style={{
            marginTop: '8px',
            padding: '12px 14px',
            background: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid var(--border-color, rgba(255, 255, 255, 0.14))',
            borderRadius: '6px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
              <strong style={{ fontSize: '0.84rem', color: '#f8fafc' }}>
                Restricted Perimeter Zone Configuration (Camera 0{cameraId})
              </strong>
            </div>
            <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
              Click and drag directly on the video above to define boundaries
            </span>
          </div>

          {/* Form Strip */}
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Zone Name</label>
              <input
                type="text"
                id="input-zone-name"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                placeholder="e.g. Front Perimeter"
                style={{
                  background: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(255, 255, 255, 0.16)',
                  color: '#ffffff',
                  padding: '5px 10px',
                  borderRadius: '4px',
                  fontSize: '0.78rem',
                  minWidth: '180px',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Coordinates (1280x720 Native)</label>
              <span
                id="zone-coords-display"
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.78rem',
                  color: currentRect ? '#00e5ff' : '#64748b',
                  background: 'rgba(0, 0, 0, 0.3)',
                  padding: '5px 10px',
                  borderRadius: '4px',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                }}
              >
                {currentRect
                  ? `[${currentRect.x1}, ${currentRect.y1}] to [${currentRect.x2}, ${currentRect.y2}]`
                  : 'Draw on video or click Preset'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', marginTop: 'auto' }}>
              <button
                type="button"
                id="btn-save-zone"
                onClick={handleSaveDrawnZone}
                disabled={savingZone || !currentRect}
                className="btn btn-primary btn-sm"
                style={{ padding: '6px 14px', fontSize: '0.78rem' }}
              >
                {savingZone ? 'Saving...' : 'Save Restricted Zone'}
              </button>

              <button
                type="button"
                id="btn-preset-webcam-zone"
                onClick={handleApplyWebcamPreset}
                className="btn btn-secondary btn-sm"
                style={{ padding: '6px 12px', fontSize: '0.78rem' }}
                title="Apply standard centered restricted zone for direct testing"
              >
                Apply Webcam 0 Preset
              </button>

              {currentRect && (
                <button
                  type="button"
                  onClick={() => setCurrentRect(null)}
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '6px 10px', fontSize: '0.78rem' }}
                >
                  Clear Box
                </button>
              )}
            </div>
          </div>

          {/* Active Configured Zones List */}
          {zonesList.length > 0 && (
            <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '8px' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '6px' }}>Active Camera Zones:</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {zonesList.map((z) => (
                  <div
                    key={z.id}
                    className="zone-item-badge"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      background: z.enabled ? 'rgba(245, 158, 11, 0.12)' : 'rgba(100, 116, 139, 0.12)',
                      border: `1px solid ${z.enabled ? '#f59e0b' : '#64748b'}`,
                      borderRadius: '4px',
                      padding: '4px 8px',
                      fontSize: '0.74rem',
                      color: z.enabled ? '#f59e0b' : '#94a3b8',
                    }}
                  >
                    <span><strong>{z.name}</strong> ({z.x1},{z.y1} to {z.x2},{z.y2})</span>
                    <button
                      type="button"
                      onClick={() => handleToggleZone(z.id)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: z.enabled ? '#10b981' : '#64748b',
                        cursor: 'pointer',
                        fontSize: '0.70rem',
                        fontWeight: 700,
                      }}
                      title="Toggle Active Status"
                    >
                      {z.enabled ? 'ACTIVE' : 'INACTIVE'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteZone(z.id)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#ef4444',
                        cursor: 'pointer',
                        fontSize: '0.74rem',
                        padding: '0 2px',
                      }}
                      title="Delete Zone"
                    >
                      &times;
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default CameraLivePlayer;
