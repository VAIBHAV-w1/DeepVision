import React, { useState, useEffect, useRef, useCallback } from 'react';
import cameraService from '../../services/camera';

/**
 * CameraLivePlayer — Enterprise SOC Multi-Mode Surveillance Player
 * Supports:
 * - Mode B: Edge Surveillance Gateway (DirectShow host bridge / OpenCV YOLO11n + ByteTrack stream via backend) [DEFAULT]
 * - Mode A: Browser Local Webcam (Direct hardware via getUserMedia + device enumeration + real FPS/resolution)
 * - Mode C: SOC Synthetic Test Pattern (Deterministic canvas test feed for automated calibration & testing)
 */
export function CameraLivePlayer({
  camera,
  activeMode = 'tracking',
  onModeChange,
  onSnapshotTaken,
  compact = false,
  autoStartWebcam = false,
  stats = null,
}) {
  const cameraId = camera?.id || 1;
  const cameraName = camera?.name || `Camera ${cameraId}`;
  const cameraLocation = camera?.location || 'Sector 01';

  // Access Modes: 'edge' (default) | 'browser' | 'test_pattern'
  const [sourceMode, setSourceMode] = useState('edge');

  // Mode A: Browser Webcam State
  const [webcamActive, setWebcamActive] = useState(false);
  const [webcamLoading, setWebcamLoading] = useState(false);
  const [webcamError, setWebcamError] = useState(null);
  const [videoDevices, setVideoDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [streamStats, setStreamStats] = useState({ fps: 0, frameCount: 0, resolution: '—' });

  // Mode B: Edge Gateway State
  const [edgeGatewayError, setEdgeGatewayError] = useState(false);
  const [hasDecodedFrames, setHasDecodedFrames] = useState(false);
  const [edgeReloadKey, setEdgeReloadKey] = useState(Date.now());

  // Interactive Controls
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isOriginalMode, setIsOriginalMode] = useState(activeMode === 'raw');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [clockStr, setClockStr] = useState('');

  // Refs
  const containerRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamImgRef = useRef(null);
  const streamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const frameCounterRef = useRef({ count: 0, lastTime: performance.now(), currentFps: 0 });

  // Clock tick
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

  // Sync mode changes with parent
  useEffect(() => {
    setIsOriginalMode(activeMode === 'raw');
  }, [activeMode]);

  // Handle Fullscreen Change listener
  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  // ---------------------------------------------------------------------------
  // MODE A: Browser Webcam (getUserMedia) Lifecycle & Frame Metering
  // ---------------------------------------------------------------------------
  const stopWebcam = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (_) {}
      });
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setWebcamActive(false);
    setStreamStats({ fps: 0, frameCount: 0, resolution: '—' });
  }, []);

  const startWebcam = useCallback(async (deviceIdToUse) => {
    stopWebcam();
    setWebcamLoading(true);
    setWebcamError(null);

    if (!navigator?.mediaDevices?.getUserMedia) {
      setWebcamError('Browser mediaDevices API not supported or requires secure context (HTTPS/localhost).');
      setWebcamLoading(false);
      return;
    }

    try {
      const constraints = {
        video: {
          deviceId: deviceIdToUse ? { exact: deviceIdToUse } : undefined,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      };

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = mediaStream;

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        await videoRef.current.play().catch(() => {});
      }

      setWebcamActive(true);
      setWebcamLoading(false);

      // Enumerate available video inputs for selector dropdown
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const vDevices = devices.filter((d) => d.kind === 'videoinput');
        setVideoDevices(vDevices);
        if (!selectedDeviceId && vDevices.length > 0) {
          setSelectedDeviceId(vDevices[0].deviceId);
        }
      } catch (_) {}

      // Measure real advancing frames via requestVideoFrameCallback or rAF
      frameCounterRef.current = { count: 0, lastTime: performance.now(), currentFps: 0 };

      const updateFrameTelemetry = (_now, metadata) => {
        const currentCounter = frameCounterRef.current;
        currentCounter.count += 1;

        const currentTime = performance.now();
        const delta = currentTime - currentCounter.lastTime;

        if (delta >= 1000) {
          const fps = Math.round((currentCounter.count * 1000) / delta);
          currentCounter.currentFps = fps;
          currentCounter.count = 0;
          currentCounter.lastTime = currentTime;

          const res = videoRef.current
            ? `${videoRef.current.videoWidth || 1280}x${videoRef.current.videoHeight || 720}`
            : '1280x720';

          setStreamStats({
            fps,
            frameCount: metadata?.presentedFrames || currentCounter.count,
            resolution: res,
          });
        }

        const video = videoRef.current;
        if (video && !video.paused && !video.ended) {
          if ('requestVideoFrameCallback' in HTMLVideoElement.prototype && video.requestVideoFrameCallback) {
            video.requestVideoFrameCallback(updateFrameTelemetry);
          } else {
            animationFrameRef.current = requestAnimationFrame(updateFrameTelemetry);
          }
        }
      };

      if (videoRef.current) {
        if ('requestVideoFrameCallback' in HTMLVideoElement.prototype && videoRef.current.requestVideoFrameCallback) {
          videoRef.current.requestVideoFrameCallback(updateFrameTelemetry);
        } else {
          animationFrameRef.current = requestAnimationFrame(updateFrameTelemetry);
        }
      }
    } catch (err) {
      setWebcamLoading(false);
      setWebcamActive(false);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setWebcamError('Camera permission denied by user. Allow camera access in browser settings.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setWebcamError('No camera hardware found on this system.');
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setWebcamError('Camera hardware is currently in use by another application.');
      } else {
        setWebcamError(err.message || 'Failed to start camera hardware.');
      }
    }
  }, [stopWebcam, selectedDeviceId]);

  // Cleanup on unmount or source change
  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, [stopWebcam]);

  // Synchronize active webcam stream to video element whenever source mode or webcamActive changes
  useEffect(() => {
    if (sourceMode === 'browser' && streamRef.current && videoRef.current) {
      if (videoRef.current.srcObject !== streamRef.current) {
        videoRef.current.srcObject = streamRef.current;
      }
      videoRef.current.play().catch(() => {});
    }
  }, [sourceMode, webcamActive]);

  // Periodic active frame verification for edge stream (clears error overlay once frames decode)
  useEffect(() => {
    if (sourceMode !== 'edge') return;
    const interval = setInterval(() => {
      const img = streamImgRef.current;
      if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
        setHasDecodedFrames(true);
        setEdgeGatewayError(false);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [sourceMode, edgeReloadKey]);

  // Handle autoStartWebcam
  useEffect(() => {
    if (sourceMode === 'browser' && autoStartWebcam && !webcamActive && !webcamLoading) {
      startWebcam(selectedDeviceId);
    }
  }, [sourceMode, autoStartWebcam, webcamActive, webcamLoading, startWebcam, selectedDeviceId]);

  // ---------------------------------------------------------------------------
  // MODE C: SOC Synthetic Test Pattern Generator (Canvas)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (sourceMode !== 'test_pattern') return;

    let animId;
    let targetX = 120;
    let targetY = 140;
    let dx = 2.4;
    let dy = 1.6;
    let frameNum = 0;
    let lastTime = performance.now();

    const renderTestPattern = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;

      // Dark SOC canvas background
      ctx.fillStyle = '#070b14';
      ctx.fillRect(0, 0, w, h);

      // Grid Lines
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
      ctx.lineWidth = 1;
      for (let x = 0; x < w; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Moving target box simulation (Calibration Target)
      targetX += dx;
      targetY += dy;
      if (targetX < 40 || targetX > w - 160) dx = -dx;
      if (targetY < 40 || targetY > h - 140) dy = -dy;

      // Bounding box
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      ctx.strokeRect(targetX, targetY, 120, 90);

      // Label
      ctx.fillStyle = '#10b981';
      ctx.fillRect(targetX, targetY - 20, 120, 20);
      ctx.fillStyle = '#040711';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('TARGET [CALIBRATION]', targetX + 4, targetY - 6);

      // Center crosshair
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.4)';
      ctx.beginPath();
      ctx.moveTo(w / 2 - 20, h / 2);
      ctx.lineTo(w / 2 + 20, h / 2);
      ctx.moveTo(w / 2, h / 2 - 20);
      ctx.lineTo(w / 2, h / 2 + 20);
      ctx.stroke();

      // Top-Left Telemetry
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.font = '12px monospace';
      ctx.fillText(`DEEPVISION SOC CALIBRATION // CH 0${cameraId}`, 20, 30);
      ctx.fillStyle = '#94a3b8';
      ctx.font = '11px monospace';
      ctx.fillText(`UTC TIMESTAMP: ${new Date().toISOString()}`, 20, 48);
      ctx.fillText(`FRAME SEQUENCE: ${frameNum} // 1280x720`, 20, 64);

      // Bottom Bar
      ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
      ctx.fillRect(0, h - 28, w, 28);
      ctx.fillStyle = '#10b981';
      ctx.fillText('STATUS: SIMULATED SYNTHETIC FEED ACTIVE (30.0 FPS)', 20, h - 10);

      frameNum += 1;
      const now = performance.now();
      if (now - lastTime >= 1000) {
        setStreamStats({
          fps: 30,
          frameCount: frameNum,
          resolution: '1280x720',
        });
        lastTime = now;
      }

      animId = requestAnimationFrame(renderTestPattern);
    };

    animId = requestAnimationFrame(renderTestPattern);
    return () => {
      if (animId) cancelAnimationFrame(animId);
    };
  }, [sourceMode, cameraId]);

  // ---------------------------------------------------------------------------
  // Action Handlers: Zoom, Pan, Snapshot, Fullscreen
  // ---------------------------------------------------------------------------
  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.25, 3));
  const handleZoomOut = () => {
    setZoom((z) => {
      const next = Math.max(z - 0.25, 1);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  };
  const handleResetPan = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handlePtz = (direction) => {
    const step = 25;
    if (direction === 'up') setPan((p) => ({ ...p, y: p.y + step }));
    if (direction === 'down') setPan((p) => ({ ...p, y: p.y - step }));
    if (direction === 'left') setPan((p) => ({ ...p, x: p.x + step }));
    if (direction === 'right') setPan((p) => ({ ...p, x: p.x - step }));
    if (direction === 'center') {
      setPan({ x: 0, y: 0 });
      setZoom(1);
    }
  };

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  const handleCaptureSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      if (sourceMode === 'edge') {
        const res = await cameraService.captureSnapshot(cameraId);
        if (onSnapshotTaken) {
          onSnapshotTaken(res);
        }
      } else if (sourceMode === 'browser' && videoRef.current) {
        const video = videoRef.current;
        const offscreen = document.createElement('canvas');
        offscreen.width = video.videoWidth || 1280;
        offscreen.height = video.videoHeight || 720;
        const ctx = offscreen.getContext('2d');
        ctx.drawImage(video, 0, 0, offscreen.width, offscreen.height);
        const snapshotDataUrl = offscreen.toDataURL('image/jpeg', 0.85);

        if (onSnapshotTaken) {
          onSnapshotTaken(snapshotDataUrl);
        }
      } else if (sourceMode === 'test_pattern' && canvasRef.current) {
        const snapshotDataUrl = canvasRef.current.toDataURL('image/jpeg', 0.85);
        if (onSnapshotTaken) {
          onSnapshotTaken(snapshotDataUrl);
        }
      }
    } catch (_) {
      // ignore
    } finally {
      setSnapshotLoading(false);
    }
  };

  const edgeStreamUrl = cameraService.getStreamUrl(
    cameraId,
    isOriginalMode ? 'raw' : 'tracking'
  );

  const displayFps =
    sourceMode === 'browser' && webcamActive
      ? streamStats.fps
      : sourceMode === 'test_pattern'
      ? 30
      : typeof stats?.fps === 'number' && stats.fps > 0
      ? stats.fps
      : camera?.status === 'online'
      ? 24
      : 0;

  const displayBitrate = displayFps > 0 ? `${Math.round(displayFps * 18)} kb/s` : '0 kb/s';

  const isLive =
    sourceMode === 'browser'
      ? webcamActive
      : sourceMode === 'test_pattern'
      ? true
      : camera?.status === 'online' && !edgeGatewayError;

  return (
    <div
      ref={containerRef}
      className="camera-live-player-container"
      style={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        background: 'var(--bg-surface, #0f172a)',
        border: '1px solid var(--border-color)',
        borderRadius: '4px',
        padding: compact ? '8px' : '12px',
        boxSizing: 'border-box',
      }}
    >
      {/* 1. Header Toolbar with Source Selector & Status */}
      <div
        className="camera-player-header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '8px',
          paddingBottom: '8px',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {/* Source Mode Tabs */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            background: 'rgba(0,0,0,0.3)',
            padding: '3px',
            borderRadius: '4px',
            border: '1px solid var(--border-color)',
          }}
        >
          <button
            type="button"
            id="btn-source-edge"
            onClick={() => {
              stopWebcam();
              setSourceMode('edge');
              setEdgeGatewayError(false);
            }}
            style={{
              background: sourceMode === 'edge' ? 'var(--color-primary)' : 'transparent',
              color: sourceMode === 'edge' ? '#ffffff' : 'var(--text-secondary)',
              border: 'none',
              padding: '4px 10px',
              borderRadius: '4px',
              fontSize: '0.74rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>Surveillance Stream (YOLO11n)</span>
            {sourceMode === 'edge' && (
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: !edgeGatewayError ? '#10b981' : '#f59e0b',
                }}
              />
            )}
          </button>

          <button
            type="button"
            id="btn-source-browser"
            onClick={() => {
              setSourceMode('browser');
              setWebcamError(null);
            }}
            style={{
              background: sourceMode === 'browser' ? 'var(--color-primary)' : 'transparent',
              color: sourceMode === 'browser' ? '#ffffff' : 'var(--text-secondary)',
              border: 'none',
              padding: '4px 10px',
              borderRadius: '4px',
              fontSize: '0.74rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>Browser Webcam</span>
            {sourceMode === 'browser' && webcamActive && (
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981' }} />
            )}
          </button>

          <button
            type="button"
            id="btn-source-test"
            onClick={() => {
              stopWebcam();
              setSourceMode('test_pattern');
            }}
            style={{
              background: sourceMode === 'test_pattern' ? 'var(--color-primary)' : 'transparent',
              color: sourceMode === 'test_pattern' ? '#ffffff' : 'var(--text-secondary)',
              border: 'none',
              padding: '4px 10px',
              borderRadius: '4px',
              fontSize: '0.74rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Test Pattern
          </button>
        </div>

        {/* Live Status Badges */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              borderRadius: '4px',
              background: isLive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
              border: `1px solid ${isLive ? '#10b981' : '#f59e0b'}`,
              fontSize: '0.72rem',
              fontWeight: 700,
              color: isLive ? '#10b981' : '#f59e0b',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isLive ? '#10b981' : '#f59e0b',
                animation: isLive ? 'pulse-dot 1.2s infinite' : undefined,
              }}
            />
            <span>
              {sourceMode === 'browser'
                ? webcamActive
                  ? 'WEBCAM LIVE'
                  : 'WEBCAM STANDBY'
                : sourceMode === 'test_pattern'
                ? 'CALIBRATION PATTERN'
                : !edgeGatewayError && camera?.status === 'online'
                ? 'SURVEILLANCE LIVE'
                : 'SURVEILLANCE STANDBY'}
            </span>
          </div>

          <span
            style={{
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: '0.72rem',
              color: 'var(--text-muted)',
              background: 'rgba(0,0,0,0.3)',
              padding: '3px 8px',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
            }}
          >
            {displayFps > 0 ? `${displayFps} FPS // ${displayBitrate}` : 'STANDBY // 0 kb/s'}
          </span>
        </div>
      </div>

      {/* 2. Main Live Video Monitor Canvas */}
      <div
        className="camera-monitor-frame live-monitor glassy-frame"
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
        {/* MODE B (Default): Edge Surveillance Gateway (OpenCV / YOLO11n + ByteTrack stream) */}
        {sourceMode === 'edge' && (
          <div style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
            <img
              key={edgeReloadKey}
              ref={streamImgRef}
              id="camera-live-stream"
              src={edgeStreamUrl}
              data-camera-id={cameraId}
              data-active-mode={isOriginalMode ? 'raw' : 'tracking'}
              alt={`${cameraName} Live Surveillance Stream`}
              className="liveview-stream-img"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
                transition: 'transform 150ms ease-out',
                display: 'block',
              }}
              onError={(e) => {
                const img = e.currentTarget;
                if (!img.dataset.retried) {
                  img.dataset.retried = 'true';
                  img.src = `${cameraService.getSnapshotUrl(cameraId)}?t=${Date.now()}`;
                } else {
                  setEdgeGatewayError(true);
                }
              }}
              onLoad={() => {
                setHasDecodedFrames(true);
                setEdgeGatewayError(false);
              }}
            />

            {edgeGatewayError && !hasDecodedFrames && (
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
                  background: 'rgba(11, 15, 25, 0.88)',
                  color: '#ffffff',
                  zIndex: 8,
                }}
              >
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" style={{ marginBottom: '0.75rem' }}>
                  <path d="M 23 7 l -7 5 7 5 V 7 z" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  <line x1="1" y1="1" x2="23" y2="23" stroke="#ef4444" strokeWidth="2" />
                </svg>
                <div style={{ fontSize: '0.96rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                  Surveillance Engine Ingestion Standby
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', maxWidth: '400px', marginBottom: '1.25rem' }}>
                  DirectShow / RTSP source standby. YOLO11n neural tracker ready. Connect camera hardware or activate local browser camera below.
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setEdgeGatewayError(false);
                      setEdgeReloadKey(Date.now());
                    }}
                    className="btn btn-secondary btn-sm"
                    style={{ borderRadius: '4px' }}
                  >
                    Retry Connection
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSourceMode('browser');
                      startWebcam();
                    }}
                    className="btn btn-primary btn-sm"
                    style={{ borderRadius: '4px' }}
                  >
                    Use Browser Camera
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* MODE A: Browser Webcam Video Element */}
        {sourceMode === 'browser' && (
          <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <video
              ref={(el) => {
                videoRef.current = el;
                if (el && streamRef.current && el.srcObject !== streamRef.current) {
                  el.srcObject = streamRef.current;
                  el.play().catch(() => {});
                }
              }}
              id="camera-webcam-stream"
              autoPlay
              playsInline
              muted
              onLoadedMetadata={(e) => {
                e.currentTarget.play().catch(() => {});
              }}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
                transition: 'transform 150ms ease-out',
                display: webcamActive ? 'block' : 'none',
              }}
            />

            {/* Live Reticle & Detection HUD for Browser Mode */}
            {webcamActive && (
              <div
                className="webcam-hud-overlay"
                style={{
                  position: 'absolute',
                  inset: 0,
                  pointerEvents: 'none',
                  overflow: 'hidden',
                }}
              >
                {/* Center Targeting Reticle */}
                <svg
                  style={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    width: '120px',
                    height: '120px',
                    opacity: 0.65,
                  }}
                  viewBox="0 0 100 100"
                >
                  <circle cx="50" cy="50" r="36" fill="none" stroke="#10b981" strokeWidth="1" strokeDasharray="4 4" />
                  <line x1="50" y1="10" x2="50" y2="30" stroke="#10b981" strokeWidth="1.5" />
                  <line x1="50" y1="70" x2="50" y2="90" stroke="#10b981" strokeWidth="1.5" />
                  <line x1="10" y1="50" x2="30" y2="50" stroke="#10b981" strokeWidth="1.5" />
                  <line x1="70" y1="50" x2="90" y2="50" stroke="#10b981" strokeWidth="1.5" />
                  <circle cx="50" cy="50" r="3" fill="#10b981" />
                </svg>

                {/* Corner HUD Brackets */}
                <div style={{ position: 'absolute', top: 16, left: 16, width: 20, height: 20, borderTop: '2px solid #10b981', borderLeft: '2px solid #10b981' }} />
                <div style={{ position: 'absolute', top: 16, right: 16, width: 20, height: 20, borderTop: '2px solid #10b981', borderRight: '2px solid #10b981' }} />
                <div style={{ position: 'absolute', bottom: 16, left: 16, width: 20, height: 20, borderBottom: '2px solid #10b981', borderLeft: '2px solid #10b981' }} />
                <div style={{ position: 'absolute', bottom: 16, right: 16, width: 20, height: 20, borderBottom: '2px solid #10b981', borderRight: '2px solid #10b981' }} />
              </div>
            )}

            {!webcamActive && (
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
                  background: 'rgba(11, 15, 25, 0.92)',
                  color: '#ffffff',
                }}
              >
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '4px',
                    background: 'rgba(37, 99, 235, 0.15)',
                    border: '1px solid rgba(37, 99, 235, 0.4)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '1rem',
                  }}
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2">
                    <path d="M 23 7 l -7 5 7 5 V 7 z" />
                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  </svg>
                </div>

                <div style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.35rem' }}>
                  Direct Hardware Camera Stream
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', maxWidth: '380px', marginBottom: '1.25rem' }}>
                  Click below to grant browser camera access and stream live hardware frames directly inside the SOC monitor.
                </div>

                {webcamError && (
                  <div
                    style={{
                      background: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid #ef4444',
                      color: '#ef4444',
                      padding: '8px 14px',
                      borderRadius: '4px',
                      fontSize: '0.78rem',
                      maxWidth: '420px',
                      marginBottom: '1rem',
                    }}
                  >
                    {webcamError}
                  </div>
                )}

                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <button
                    type="button"
                    id="btn-start-webcam"
                    onClick={() => startWebcam(selectedDeviceId)}
                    disabled={webcamLoading}
                    className="btn btn-primary btn-sm"
                    style={{ padding: '8px 18px', fontWeight: 700, borderRadius: '4px' }}
                  >
                    {webcamLoading ? 'Accessing Camera Hardware...' : 'Activate Camera'}
                  </button>

                  <button
                    type="button"
                    onClick={() => setSourceMode('test_pattern')}
                    className="btn btn-secondary btn-sm"
                    style={{ padding: '8px 18px', borderRadius: '4px' }}
                  >
                    Run Test Pattern
                  </button>
                </div>

                {/* Device Selector Dropdown */}
                {videoDevices.length > 1 && (
                  <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Device:</span>
                    <select
                      value={selectedDeviceId}
                      onChange={(e) => {
                        setSelectedDeviceId(e.target.value);
                        startWebcam(e.target.value);
                      }}
                      style={{
                        background: '#182232',
                        color: '#ffffff',
                        border: '1px solid var(--border-color)',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                      }}
                    >
                      {videoDevices.map((d, idx) => (
                        <option key={d.deviceId || idx} value={d.deviceId}>
                          {d.label || `Camera ${idx + 1}`}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* MODE C: Synthetic SOC Calibration Test Pattern */}
        {sourceMode === 'test_pattern' && (
          <canvas
            ref={canvasRef}
            id="camera-test-canvas"
            width={1280}
            height={720}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
              transition: 'transform 150ms ease-out',
            }}
          />
        )}

        {/* -------------------------------------------------------------
            FLOATING HUD OVERLAYS (REFERENCE IMAGE 1 DIRECTION)
            ------------------------------------------------------------- */}
        {/* Top Floating Status Strip */}
        <div
          style={{
            position: 'absolute',
            top: '12px',
            left: '12px',
            right: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            pointerEvents: 'none',
            zIndex: 10,
          }}
        >
          {/* Top-Left: Live indicator with Bitrate/FPS */}
          <div
            className="hud-pill-top-left"
            style={{
              pointerEvents: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '5px 12px',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '0.75rem',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: isLive ? '#10b981' : '#f59e0b',
                animation: isLive ? 'pulse-dot 1.2s infinite' : undefined,
              }}
            />
            <span style={{ fontWeight: 700 }}>{isLive ? 'LIVE' : 'STANDBY'}</span>
            <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.72rem' }}>{displayBitrate}</span>
            <span style={{ color: isLive ? '#10b981' : 'rgba(255,255,255,0.7)', fontWeight: 700, fontSize: '0.72rem' }}>
              {displayFps} FPS
            </span>
          </div>

          {/* Top-Center: Channel Name */}
          <div
            className="hud-pill-top-center"
            style={{
              pointerEvents: 'auto',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '5px 12px',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '0.75rem',
              fontWeight: 700,
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            CH 0{cameraId}: {cameraName} &bull; {cameraLocation}
          </div>

          {/* Top-Right: Clock & Reset Zoom */}
          <div
            className="hud-pill-top-right"
            style={{
              pointerEvents: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '5px 10px',
              borderRadius: '4px',
              color: '#f8fafc',
              fontSize: '0.74rem',
              fontWeight: 600,
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
            </svg>
            <span>{clockStr}</span>
            {zoom > 1 && (
              <button
                type="button"
                onClick={handleResetPan}
                style={{
                  background: 'rgba(255,255,255,0.15)',
                  border: 'none',
                  color: '#ffffff',
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: '3px',
                  cursor: 'pointer',
                }}
                title="Reset zoom to 1X"
              >
                1X
              </button>
            )}
            <button
              type="button"
              onClick={handleToggleFullscreen}
              style={{
                background: 'none',
                border: 'none',
                color: '#ffffff',
                cursor: 'pointer',
                padding: '2px',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Toggle Fullscreen"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15 3 21 3 21 9"></polyline>
                <polyline points="9 21 3 21 3 15"></polyline>
                <line x1="21" y1="3" x2="14" y2="10"></line>
                <line x1="3" y1="21" x2="10" y2="14"></line>
              </svg>
            </button>
          </div>
        </div>

        {/* Bottom-Left: Zoom In/Out Pill */}
        <div
          className="hud-zoom-pill"
          style={{
            position: 'absolute',
            bottom: '14px',
            left: '14px',
            zIndex: 15,
            display: 'inline-flex',
            alignItems: 'center',
            background: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.16)',
            borderRadius: '4px',
            padding: '3px 6px',
            gap: '4px',
          }}
        >
          <button
            type="button"
            className="hud-zoom-btn"
            onClick={handleZoomOut}
            title="Zoom Out"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '1rem',
              width: '24px',
              height: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '4px',
            }}
          >
            &minus;
          </button>
          <span
            className="hud-zoom-indicator"
            style={{
              fontSize: '0.74rem',
              fontWeight: 700,
              color: '#ffffff',
              padding: '0 6px',
              fontFamily: 'var(--font-mono, monospace)',
            }}
          >
            {zoom.toFixed(1)}X
          </span>
          <button
            type="button"
            className="hud-zoom-btn"
            onClick={handleZoomIn}
            title="Zoom In"
            style={{
              background: 'transparent',
              border: 'none',
              color: '#ffffff',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '1rem',
              width: '24px',
              height: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '4px',
            }}
          >
            &#43;
          </button>
        </div>

        {/* Bottom-Right: Circular PTZ Controller D-pad */}
        <div
          className="hud-ptz-dial"
          title="PTZ Directional Control"
          style={{
            position: 'absolute',
            bottom: '14px',
            right: '14px',
            zIndex: 15,
            width: '94px',
            height: '94px',
            borderRadius: '4px',
            background: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.16)',
            display: 'grid',
            gridTemplateAreas:
              '".    up    ." "left center right" ".    down  ."',
            alignItems: 'center',
            justifyItems: 'center',
            padding: '4px',
            boxSizing: 'border-box',
          }}
        >
          <button
            type="button"
            className="ptz-btn ptz-up"
            onClick={() => handlePtz('up')}
            title="Tilt Up"
            style={{ gridArea: 'up', background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', borderRadius: '4px', padding: '2px' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="12 4 4 18 20 18"></polygon>
            </svg>
          </button>
          <button
            type="button"
            className="ptz-btn ptz-left"
            onClick={() => handlePtz('left')}
            title="Pan Left"
            style={{ gridArea: 'left', background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', borderRadius: '4px', padding: '2px' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="4 12 18 4 18 20"></polygon>
            </svg>
          </button>
          <button
            type="button"
            className="ptz-btn ptz-center"
            onClick={() => handlePtz('center')}
            title="Center Reset Position"
            style={{ gridArea: 'center', width: '12px', height: '12px', borderRadius: '50%', background: 'rgba(255,255,255,0.4)', border: 'none', cursor: 'pointer' }}
          />
          <button
            type="button"
            className="ptz-btn ptz-right"
            onClick={() => handlePtz('right')}
            title="Pan Right"
            style={{ gridArea: 'right', background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', borderRadius: '4px', padding: '2px' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="20 12 6 4 6 20"></polygon>
            </svg>
          </button>
          <button
            type="button"
            className="ptz-btn ptz-down"
            onClick={() => handlePtz('down')}
            title="Tilt Down"
            style={{ gridArea: 'down', background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', borderRadius: '4px', padding: '2px' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="12 20 4 6 20 6"></polygon>
            </svg>
          </button>
        </div>
      </div>

      {/* 3. Bottom Interactive Control Strip */}
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
        {/* Left: Feed Mode Switcher & Snapshot */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {sourceMode === 'browser' && webcamActive && (
            <button
              type="button"
              id="btn-stop-webcam"
              onClick={stopWebcam}
              className="btn btn-secondary btn-sm"
              style={{ padding: '5px 12px', fontSize: '0.78rem', color: '#ef4444', borderRadius: '4px' }}
            >
              Stop Camera
            </button>
          )}

          {sourceMode === 'edge' && (
            <button
              type="button"
              id="btn-mode-toggle"
              onClick={() => {
                const nextIsOriginal = !isOriginalMode;
                setIsOriginalMode(nextIsOriginal);
                if (onModeChange) onModeChange(nextIsOriginal ? 'raw' : 'tracking');
              }}
              className="btn btn-secondary btn-sm"
              style={{
                padding: '5px 12px',
                fontSize: '0.78rem',
                color: !isOriginalMode ? '#10b981' : undefined,
                fontWeight: 600,
                borderRadius: '4px',
              }}
            >
              Mode: {!isOriginalMode ? 'YOLO AI Tracking' : 'Original Raw'}
            </button>
          )}

          {/* Snapshot Trigger */}
          <button
            type="button"
            id="btn-camera-snapshot"
            onClick={handleCaptureSnapshot}
            disabled={snapshotLoading}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 12px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px', borderRadius: '4px' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <span>{snapshotLoading ? 'Saving...' : 'Save Snapshot'}</span>
          </button>
        </div>

        {/* Right: Quick actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            type="button"
            onClick={handleZoomIn}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem', borderRadius: '4px' }}
            title="Digital Zoom In"
          >
            + Zoom
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem', borderRadius: '4px' }}
            title="Digital Zoom Out"
          >
            - Zoom
          </button>
          <button
            type="button"
            onClick={handleToggleFullscreen}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem', borderRadius: '4px' }}
            title="Toggle Fullscreen"
          >
            {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CameraLivePlayer;
