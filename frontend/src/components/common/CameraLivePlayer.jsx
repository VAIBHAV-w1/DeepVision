import React, { useState, useEffect, useRef, useCallback } from 'react';
import cameraService from '../../services/camera';

/**
 * CameraLivePlayer — Enterprise SOC Multi-Mode Surveillance Player
 * Supports:
 * - Mode A: Browser Local Webcam (Direct hardware via getUserMedia + device enumeration + real FPS/resolution)
 * - Mode B: Edge Surveillance Gateway (DirectShow host bridge / OpenCV YOLO stream via backend)
 * - Mode C: SOC Synthetic Test Pattern (Deterministic canvas test feed for automated calibration & testing)
 */
export function CameraLivePlayer({
  camera,
  activeMode = 'tracking',
  onModeChange,
  onSnapshotTaken,
  compact = false,
  autoStartWebcam = false,
}) {
  const cameraId = camera?.id || 1;
  const cameraName = camera?.name || `Camera ${cameraId}`;
  const cameraLocation = camera?.location || 'Sector 01';

  // Access Modes: 'browser' | 'edge' | 'test_pattern'
  const [sourceMode, setSourceMode] = useState('browser');
  
  // Mode A: Browser Webcam State
  const [webcamActive, setWebcamActive] = useState(false);
  const [webcamLoading, setWebcamLoading] = useState(false);
  const [webcamError, setWebcamError] = useState(null);
  const [videoDevices, setVideoDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [streamStats, setStreamStats] = useState({ fps: 0, frameCount: 0, resolution: '—' });

  // Mode B: Edge Gateway State
  const [edgeGatewayError, setEdgeGatewayError] = useState(false);
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
  const streamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const frameCounterRef = useRef({ count: 0, lastTime: performance.now(), currentFps: 0 });

  // Clock tick
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setClockStr(now.toTimeString().split(' ')[0]);
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
        } catch (e) {
          // ignore
        }
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

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      // Enumerate available devices once permission is granted
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = devices.filter((d) => d.kind === 'videoinput');
        setVideoDevices(videoInputs);
        if (!deviceIdToUse && videoInputs.length > 0) {
          const currentTrack = stream.getVideoTracks()[0];
          const trackSettings = currentTrack?.getSettings ? currentTrack.getSettings() : {};
          if (trackSettings.deviceId) {
            setSelectedDeviceId(trackSettings.deviceId);
          }
        }
      } catch (enumErr) {
        // Enumerate fallback
      }

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current
            ?.play()
            .then(() => {
              setWebcamActive(true);
              setWebcamLoading(false);
              startFrameCounter();
            })
            .catch((playErr) => {
              setWebcamError(`Autoplay error: ${playErr.message}`);
              setWebcamLoading(false);
            });
        };
      }
    } catch (err) {
      setWebcamLoading(false);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setWebcamError('Camera permission denied by browser. Please grant permission in browser settings.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setWebcamError('No physical camera device detected on this system.');
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setWebcamError('Camera hardware is currently in use by another application or DirectShow bridge.');
      } else {
        setWebcamError(`Camera error: ${err.message || err.name}`);
      }
    }
  }, [stopWebcam]);

  // Frame advance counter using requestVideoFrameCallback or requestAnimationFrame
  const startFrameCounter = useCallback(() => {
    frameCounterRef.current = { count: 0, lastTime: performance.now(), currentFps: 0 };

    const updateFrameTelemetry = () => {
      const video = videoRef.current;
      if (!video || video.paused || video.ended) return;

      frameCounterRef.current.count += 1;
      const now = performance.now();
      const elapsed = now - frameCounterRef.current.lastTime;

      if (elapsed >= 1000) {
        const calculatedFps = Math.round((frameCounterRef.current.count * 1000) / elapsed);
        frameCounterRef.current.currentFps = calculatedFps;
        frameCounterRef.current.count = 0;
        frameCounterRef.current.lastTime = now;

        setStreamStats({
          fps: calculatedFps,
          frameCount: frameCounterRef.current.count,
          resolution: video.videoWidth && video.videoHeight ? `${video.videoWidth}x${video.videoHeight}` : '1280x720',
        });
      }

      if ('requestVideoFrameCallback' in HTMLVideoElement.prototype && video.requestVideoFrameCallback) {
        video.requestVideoFrameCallback(updateFrameTelemetry);
      } else {
        animationFrameRef.current = requestAnimationFrame(updateFrameTelemetry);
      }
    };

    if (videoRef.current) {
      if ('requestVideoFrameCallback' in HTMLVideoElement.prototype && videoRef.current.requestVideoFrameCallback) {
        videoRef.current.requestVideoFrameCallback(updateFrameTelemetry);
      } else {
        animationFrameRef.current = requestAnimationFrame(updateFrameTelemetry);
      }
    }
  }, []);

  // Cleanup on unmount or source change
  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, [stopWebcam]);

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
    let measuredFps = 30;

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

      // Moving target box simulation (YOLO Detection)
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
      ctx.fillText('TARGET [PERSON] 94%', targetX + 4, targetY - 6);

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
        measuredFps = Math.round((frameNum * 1000) / (now - lastTime));
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
  const handleZoomOut = () => setZoom((z) => Math.max(z - 0.25, 1));
  const handleResetPan = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
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
      let snapshotDataUrl = null;

      if (sourceMode === 'browser' && videoRef.current) {
        const video = videoRef.current;
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        snapshotDataUrl = canvas.toDataURL('image/jpeg', 0.92);
      } else if (sourceMode === 'test_pattern' && canvasRef.current) {
        snapshotDataUrl = canvasRef.current.toDataURL('image/jpeg', 0.92);
      } else {
        // Mode B: Server API capture
        try {
          const res = await cameraService.captureSnapshot(cameraId);
          if (res?.snapshot_url) {
            snapshotDataUrl = res.snapshot_url;
          }
        } catch (e) {
          snapshotDataUrl = cameraService.getSnapshotUrl(cameraId);
        }
      }

      if (snapshotDataUrl) {
        // Offer download link
        const a = document.createElement('a');
        a.href = snapshotDataUrl;
        a.download = `DeepVision_Snapshot_CAM0${cameraId}_${Date.now()}.jpg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        if (onSnapshotTaken) {
          onSnapshotTaken(snapshotDataUrl);
        }
      }
    } finally {
      setSnapshotLoading(false);
    }
  };

  const edgeStreamUrl = cameraService.getStreamUrl(
    cameraId,
    isOriginalMode ? 'raw' : 'tracking'
  );

  return (
    <div
      ref={containerRef}
      className="camera-live-player-container"
      style={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        background: 'var(--bg-surface, #0f172a)',
        border: '1px solid var(--border-color)',
        borderRadius: '6px',
        padding: compact ? '8px' : '14px',
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
          gap: '10px',
          paddingBottom: '8px',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {/* Source Mode Tabs */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(0,0,0,0.3)', padding: '3px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
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
              borderRadius: '3px',
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
            id="btn-source-edge"
            onClick={() => {
              stopWebcam();
              setSourceMode('edge');
            }}
            style={{
              background: sourceMode === 'edge' ? 'var(--color-primary)' : 'transparent',
              color: sourceMode === 'edge' ? '#ffffff' : 'var(--text-secondary)',
              border: 'none',
              padding: '4px 10px',
              borderRadius: '3px',
              fontSize: '0.74rem',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            Edge Gateway
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
              borderRadius: '3px',
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
              background:
                sourceMode === 'browser'
                  ? webcamActive
                    ? 'rgba(16, 185, 129, 0.15)'
                    : 'rgba(239, 68, 68, 0.15)'
                  : sourceMode === 'test_pattern'
                  ? 'rgba(59, 130, 246, 0.15)'
                  : camera?.status === 'online'
                  ? 'rgba(16, 185, 129, 0.15)'
                  : 'rgba(239, 68, 68, 0.15)',
              border: `1px solid ${
                sourceMode === 'browser'
                  ? webcamActive
                    ? '#10b981'
                    : '#ef4444'
                  : sourceMode === 'test_pattern'
                  ? '#3b82f6'
                  : camera?.status === 'online'
                  ? '#10b981'
                  : '#ef4444'
              }`,
              fontSize: '0.72rem',
              fontWeight: 700,
              color:
                sourceMode === 'browser'
                  ? webcamActive
                    ? '#10b981'
                    : '#ef4444'
                  : sourceMode === 'test_pattern'
                  ? '#3b82f6'
                  : camera?.status === 'online'
                  ? '#10b981'
                  : '#ef4444',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor:
                  sourceMode === 'browser'
                    ? webcamActive
                      ? '#10b981'
                      : '#ef4444'
                    : sourceMode === 'test_pattern'
                    ? '#3b82f6'
                    : camera?.status === 'online'
                    ? '#10b981'
                    : '#ef4444',
              }}
            />
            <span>
              {sourceMode === 'browser'
                ? webcamActive
                  ? 'WEBCAM LIVE'
                  : 'WEBCAM STANDBY'
                : sourceMode === 'test_pattern'
                ? 'CALIBRATION PATTERN'
                : camera?.status === 'online'
                ? 'GATEWAY ONLINE'
                : 'GATEWAY STANDBY'}
            </span>
          </div>

          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              color: 'var(--text-muted)',
              background: 'rgba(0,0,0,0.3)',
              padding: '3px 8px',
              borderRadius: '4px',
              border: '1px solid var(--border-color)',
            }}
          >
            {sourceMode === 'browser' && webcamActive
              ? `${streamStats.fps} FPS // ${streamStats.resolution}`
              : sourceMode === 'test_pattern'
              ? '30 FPS // 1280x720'
              : 'MJPEG // 24 FPS'}
          </span>
        </div>
      </div>

      {/* 2. Main Live Video Monitor Canvas */}
      <div
        className="camera-monitor-frame"
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
        {/* MODE A: Browser Webcam Video Element */}
        {sourceMode === 'browser' && (
          <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <video
              ref={videoRef}
              id="camera-webcam-stream"
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
                transition: 'transform 150ms ease-out',
                display: webcamActive ? 'block' : 'none',
              }}
            />

            {/* Standby / Initial Prompt */}
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
                    borderRadius: '50%',
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
                    style={{ padding: '8px 18px', fontWeight: 700 }}
                  >
                    {webcamLoading ? 'Accessing Camera Hardware...' : 'Activate Camera'}
                  </button>

                  <button
                    type="button"
                    onClick={() => setSourceMode('test_pattern')}
                    className="btn btn-secondary btn-sm"
                    style={{ padding: '8px 18px' }}
                  >
                    Run Test Pattern
                  </button>
                </div>

                {/* Device Selector Dropdown if multiple devices found */}
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

        {/* MODE B: Edge Surveillance Gateway (DirectShow Bridge / OpenCV stream) */}
        {sourceMode === 'edge' && (
          <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <img
              key={edgeReloadKey}
              id="camera-live-stream"
              src={edgeStreamUrl}
              data-camera-id={cameraId}
              alt={`${cameraName} Live Stream`}
              className="liveview-stream-img"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: `scale(${zoom}) translate(${pan.x}px, ${pan.y}px)`,
                transition: 'transform 150ms ease-out',
                display: edgeGatewayError ? 'none' : 'block',
              }}
              onError={() => setEdgeGatewayError(true)}
              onLoad={() => setEdgeGatewayError(false)}
            />

            {edgeGatewayError && (
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
                  background: 'rgba(11, 15, 25, 0.94)',
                  color: '#ffffff',
                }}
              >
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" style={{ marginBottom: '0.75rem' }}>
                  <path d="M 23 7 l -7 5 7 5 V 7 z" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  <line x1="2" y1="2" x2="22" y2="22" stroke="#ef4444" strokeWidth="2" />
                </svg>
                <div style={{ fontSize: '0.96rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                  Edge Surveillance Gateway Standby
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', maxWidth: '400px', marginBottom: '1.25rem' }}>
                  The local DirectShow / RTSP host bridge on 127.0.0.1:8554 is private and not exposed to cloud serverless origins.
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setEdgeGatewayError(false);
                      setEdgeReloadKey(Date.now());
                    }}
                    className="btn btn-secondary btn-sm"
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
                  >
                    Use Browser Camera
                  </button>
                </div>
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

        {/* Floating Top HUD Status Strip */}
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
          {/* Channel Name */}
          <div
            style={{
              pointerEvents: 'auto',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '4px 10px',
              borderRadius: '4px',
              color: '#ffffff',
              fontSize: '0.74rem',
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
            }}
          >
            CH 0{cameraId}: {cameraName} &bull; {cameraLocation}
          </div>

          {/* Clock Strip */}
          <div
            style={{
              pointerEvents: 'auto',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '4px 10px',
              borderRadius: '4px',
              color: '#f8fafc',
              fontSize: '0.74rem',
              fontWeight: 600,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {clockStr}
          </div>
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
          gap: '10px',
          paddingTop: '6px',
        }}
      >
        {/* Left: AI Mode Toggle & Stop/Start */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {sourceMode === 'browser' && webcamActive && (
            <button
              type="button"
              id="btn-stop-webcam"
              onClick={stopWebcam}
              className="btn btn-secondary btn-sm"
              style={{ padding: '5px 12px', fontSize: '0.78rem', color: '#ef4444' }}
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
            style={{ padding: '5px 12px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M 23 19 a 2 2 0 0 1 -2 2 H 3 a 2 2 0 0 1 -2 -2 V 8 a 2 2 0 0 1 2 -2 h 4 l 2 -3 h 6 l 2 3 h 4 a 2 2 0 0 1 2 2 z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
            <span>{snapshotLoading ? 'Saving...' : 'Save Snapshot'}</span>
          </button>
        </div>

        {/* Right: PTZ Zoom & Fullscreen */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button
            type="button"
            onClick={handleZoomIn}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem' }}
            title="Digital Zoom In"
          >
            + Zoom
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem' }}
            title="Digital Zoom Out"
          >
            - Zoom
          </button>
          {zoom > 1 && (
            <button
              type="button"
              onClick={handleResetPan}
              className="btn btn-secondary btn-sm"
              style={{ padding: '5px 10px', fontSize: '0.75rem' }}
            >
              Reset ({zoom.toFixed(1)}x)
            </button>
          )}
          <button
            type="button"
            onClick={handleToggleFullscreen}
            className="btn btn-secondary btn-sm"
            style={{ padding: '5px 10px', fontSize: '0.75rem' }}
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
