import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services/api';
import { cameraService } from '../services/camera';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';
import CameraLivePlayer from '../components/common/CameraLivePlayer';

/**
 * DeepVision Unified Surveillance & Analytics Console
 * 
 * Merges Live Video Surveillance with Real-Time Neural Analytics:
 * - Multi-camera grid layouts: 1x1, 2x2, 3x3, 4x4 and Fullscreen
 * - Dual viewing modes: RAW STREAM (1280x720 HD) & DETECTION & TRACKING (YOLO11n + ByteTrack)
 * - Live snapshot capture & manual MP4 clip recording with visual REC indicator
 * - Real-time telemetry: class distribution, active track IDs, FPS gauges, latency, zone intrusions
 * - Collapsible analytics panel docked on the right (72%/28% desktop split)
 * - Scoped recent camera alerts with one-click jump to forensic investigation
 */
export function Surveillance({ initialCameraId = 4, onNavigate, embedded = false }) {
  const { t } = useTranslation();
  const { addToast } = useToast();

  // Camera Inventory State
  const [cameras, setCameras] = useState([]);
  const [selectedCamId, setSelectedCamId] = useState(() => Number(initialCameraId) || 4);
  const [gridMode, setGridMode] = useState('1x1'); // '1x1' | '2x2' | '3x3' | '4x4'
  const [activeMode, setActiveMode] = useState(() => {
    const saved = localStorage.getItem('deepvision_default_mode');
    return saved === 'raw' ? 'raw' : 'tracking';
  });

  // Recording & Snapshot States
  const [isRecording, setIsRecording] = useState(false);
  const [recLoading, setRecLoading] = useState(false);
  const [recDuration, setRecDuration] = useState(0);

  // Layout & UI States
  const [showAnalyticsPanel, setShowAnalyticsPanel] = useState(true);
  const [clockStr, setClockStr] = useState('');
  const [activeMobileTab, setActiveMobileTab] = useState('video'); // 'video' | 'analytics' for mobile

  // Telemetry & Analytics State for Selected Camera
  const [telemetry, setTelemetry] = useState({
    fps: 0,
    capture_fps: 15.0,
    inference_fps: 0,
    latency_ms: 0,
    detections: 0,
    tracks: [],
    zones: [],
    active_intrusions: [],
    status: 'online',
  });
  const [recentAlerts, setRecentAlerts] = useState([]);
  const [telemetryLoading, setTelemetryLoading] = useState(false);

  // Sync initial camera ID
  useEffect(() => {
    const parsed = Number(initialCameraId);
    if (!Number.isNaN(parsed) && parsed > 0) {
      setSelectedCamId(parsed);
    }
  }, [initialCameraId]);

  // Digital Live HUD Clock honoring operator 12h/24h preference
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const fmt = localStorage.getItem('deepvision_clock_format') || '24h';
      const datePart = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
      if (fmt === '12h') {
        const rawHours = now.getHours();
        const suffix = rawHours >= 12 ? 'PM' : 'AM';
        const h12 = rawHours % 12 || 12;
        setClockStr(`${datePart} ${pad(h12)}:${pad(now.getMinutes())}:${pad(now.getSeconds())} ${suffix}`);
      } else {
        setClockStr(`${datePart} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`);
      }
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  // Recording Timer
  useEffect(() => {
    let interval = null;
    if (isRecording) {
      interval = setInterval(() => {
        setRecDuration((prev) => prev + 1);
      }, 1000);
    } else {
      setRecDuration(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isRecording]);

  // Keyboard Shortcuts: 1 = RAW, 2 = TRACKING, F = Fullscreen
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key === '1') {
        setActiveMode('raw');
        addToast(`Mode: ${t('surveillance.modeRaw', 'RAW STREAM')}`, 'info');
      } else if (e.key === '2') {
        setActiveMode('tracking');
        addToast(`Mode: ${t('surveillance.modeTracking', 'DETECTION & TRACKING')}`, 'info');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [addToast, t]);

  // Load Camera Channels
  const loadCameras = useCallback(async () => {
    try {
      const camRes = await api.cameras.list();
      const cams = Array.isArray(camRes?.cameras) ? camRes.cameras : (Array.isArray(camRes) ? camRes : []);
      if (cams.length > 0) {
        setCameras(cams);
        const exists = cams.some((c) => Number(c.id) === Number(selectedCamId));
        if (!exists) {
          const preferred = cams.find((c) => c.id === 4 && c.status === 'online') ||
                           cams.find((c) => c.status === 'online') ||
                           cams[0];
          if (preferred) setSelectedCamId(preferred.id);
        }
      }
    } catch {
      // Silent retry on next interval
    }
  }, [selectedCamId]);

  useEffect(() => {
    loadCameras();
    const interval = setInterval(loadCameras, 10000);
    return () => clearInterval(interval);
  }, [loadCameras]);

  // Fetch Telemetry & Recent Alerts for Selected Camera
  const fetchCameraAnalytics = useCallback(async (camId) => {
    if (!camId) return;
    try {
      setTelemetryLoading(true);
      // Fetch stats
      const statsRes = await api.cameras.getStats(camId);
      if (statsRes) {
        setTelemetry({
          fps: statsRes.fps || 0,
          capture_fps: statsRes.capture_fps || 15.0,
          inference_fps: statsRes.inference_fps || statsRes.ai_fps || 0,
          latency_ms: statsRes.latency_ms || 0,
          detections: statsRes.detections || (statsRes.tracks ? statsRes.tracks.length : 0),
          tracks: statsRes.tracks || [],
          zones: statsRes.zones || [],
          active_intrusions: statsRes.active_intrusions || [],
          status: statsRes.status || 'online',
        });
        if (typeof statsRes.is_recording === 'boolean') {
          setIsRecording(statsRes.is_recording);
        }
      }

      // Fetch recent alerts scoped to this camera
      const alertsRes = await api.alerts.list({ camera_id: camId, page_size: 5 });
      const alertsList = alertsRes?.alerts || alertsRes?.results || (Array.isArray(alertsRes) ? alertsRes : []);
      setRecentAlerts(alertsList.slice(0, 5));
    } catch {
      // Graceful fallback
    } finally {
      setTelemetryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCameraAnalytics(selectedCamId);
    const interval = setInterval(() => {
      fetchCameraAnalytics(selectedCamId);
    }, 2500);
    return () => clearInterval(interval);
  }, [selectedCamId, fetchCameraAnalytics]);

  // Handle Manual Clip Recording Start / Stop
  const handleToggleRecording = async () => {
    if (!selectedCamId) return;
    setRecLoading(true);
    try {
      if (isRecording) {
        const res = await cameraService.stopRecording(selectedCamId);
        if (res && res.success) {
          setIsRecording(false);
          addToast(t('monitor.recordingSaved', 'Recording finalized & saved to Video Archives'), 'success');
        } else {
          setIsRecording(false);
          addToast(res?.message || 'Recording stopped (no valid frames captured)', 'warning');
        }
      } else {
        const res = await cameraService.startRecording(selectedCamId);
        if (res && res.success) {
          setIsRecording(true);
          addToast(t('monitor.recordingStarted', 'Live video recording started'), 'success');
        } else {
          addToast(res?.message || 'Failed to start recording', 'error');
        }
      }
    } catch (err) {
      addToast(err?.message || 'Recording operation failed', 'error');
    } finally {
      setRecLoading(false);
    }
  };

  // Handle Forensic Snapshot Capture
  const handleCaptureSnapshot = async () => {
    if (!selectedCamId) return;
    try {
      const res = await cameraService.captureSnapshot(selectedCamId);
      if (res && res.success === true) {
        addToast(t('monitor.snapshotSaved', 'Snapshot captured and saved to Evidence Vault'), 'success');
      } else {
        addToast(res?.message || res?.error || 'Camera offline or no valid video frame available', 'warning');
      }
    } catch (err) {
      addToast(err?.message || 'Snapshot capture failed', 'error');
    }
  };

  const selectedCam = cameras.find((c) => Number(c.id) === Number(selectedCamId)) || {
    id: selectedCamId,
    name: `Cam-${String(selectedCamId).padStart(2, '0')}`,
    status: 'online',
    source_type: 'webcam',
    source: '0',
    location: 'Primary Perimeter',
  };

  const onlineCameras = cameras.filter((c) => c.status === 'online');

  // Compute Class Distribution from current active tracks
  const classCounts = (telemetry.tracks || []).reduce((acc, trk) => {
    const rawClass = (trk.class_name || trk.label || trk.class || 'unknown').toLowerCase();
    const cName = rawClass === 'cell phone' || rawClass === 'mobile phone' ? 'phone' : rawClass;
    acc[cName] = (acc[cName] || 0) + 1;
    return acc;
  }, {});

  const classColorMap = {
    person: '#00E5FF',
    car: '#10B981',
    truck: '#059669',
    bus: '#34D399',
    phone: '#F59E0B',
    dog: '#EC4899',
    cat: '#A855F7',
    backpack: '#6366F1',
    handbag: '#8B5CF6',
    bottle: '#3B82F6',
    laptop: '#06B6D4',
  };

  // Determine grid camera slots
  const getGridCameras = () => {
    if (gridMode === '1x1') {
      return [selectedCam];
    }
    const count = gridMode === '2x2' ? 4 : gridMode === '3x3' ? 9 : 16;
    const slots = [];
    for (let i = 0; i < count; i++) {
      if (i < cameras.length) {
        slots.push(cameras[i]);
      } else {
        // Placeholder or wrap around
        slots.push(cameras[i % (cameras.length || 1)] || selectedCam);
      }
    }
    return slots;
  };

  const formatSecs = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  return (
    <div className="surveillance-unified-workspace" style={{ maxWidth: '1800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      {/* 1. Header Toolbar */}
      <header
        className="surveillance-toolbar"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '12px 18px',
          backgroundColor: 'var(--bg-surface, #0B111E)',
          border: '1px solid var(--border-color, #1A2436)',
          borderRadius: '8px',
        }}
      >
        {/* Left: Active Camera Status & Channel Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: selectedCam.status === 'online' ? '#10B981' : '#64748B',
                boxShadow: selectedCam.status === 'online' ? '0 0 10px rgba(16, 185, 129, 0.6)' : 'none',
              }}
            />
            <h1 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main, #F8FAFC)', margin: 0, letterSpacing: '-0.02em' }}>
              {selectedCam.name}
            </h1>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '0.70rem',
                fontWeight: 700,
                backgroundColor: selectedCam.status === 'online' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                color: selectedCam.status === 'online' ? '#10B981' : '#94A3B8',
                border: `1px solid ${selectedCam.status === 'online' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(100, 116, 139, 0.3)'}`,
              }}
            >
              {selectedCam.status === 'online' ? 'ONLINE' : 'STANDBY'}
            </span>
          </div>

          {/* Quick Channel Switcher Pills */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflowX: 'auto', maxWidth: '420px', padding: '2px 0' }}>
            {cameras.map((cam) => {
              const isCur = Number(cam.id) === Number(selectedCamId);
              return (
                <button
                  key={cam.id}
                  type="button"
                  onClick={() => setSelectedCamId(cam.id)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '5px',
                    fontSize: '0.74rem',
                    fontWeight: isCur ? 700 : 500,
                    backgroundColor: isCur ? '#2563EB' : 'rgba(255, 255, 255, 0.04)',
                    color: isCur ? '#FFFFFF' : '#94A3B8',
                    border: isCur ? '1px solid #3B82F6' : '1px solid rgba(255, 255, 255, 0.08)',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {cam.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Center: Grid Layout Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: '#070B13', padding: '3px 6px', borderRadius: '6px', border: '1px solid #1A2436' }}>
          <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600, paddingRight: '4px' }}>Grid:</span>
          {['1x1', '2x2', '3x3', '4x4'].map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGridMode(g)}
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '0.72rem',
                fontWeight: gridMode === g ? 700 : 500,
                backgroundColor: gridMode === g ? '#00D2FF' : 'transparent',
                color: gridMode === g ? '#080C14' : '#94A3B8',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {g}
            </button>
          ))}
        </div>

        {/* Right: Mode Switcher & Clock */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Stream Mode Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', backgroundColor: '#070B13', padding: '3px 4px', borderRadius: '6px', border: '1px solid #1A2436' }}>
            <button
              type="button"
              onClick={() => setActiveMode('raw')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '0.74rem',
                fontWeight: activeMode === 'raw' ? 700 : 500,
                backgroundColor: activeMode === 'raw' ? '#2563EB' : 'transparent',
                color: activeMode === 'raw' ? '#FFFFFF' : '#94A3B8',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              RAW STREAM
            </button>
            <button
              type="button"
              onClick={() => setActiveMode('tracking')}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '0.74rem',
                fontWeight: activeMode === 'tracking' ? 700 : 500,
                backgroundColor: activeMode === 'tracking' ? '#00D2FF' : 'transparent',
                color: activeMode === 'tracking' ? '#080C14' : '#94A3B8',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              AI DETECTION & TRACKING
            </button>
          </div>

          {/* Toggle Analytics Dock */}
          <button
            type="button"
            onClick={() => setShowAnalyticsPanel(!showAnalyticsPanel)}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '0.75rem',
              fontWeight: 600,
              backgroundColor: showAnalyticsPanel ? 'rgba(0, 210, 255, 0.1)' : 'transparent',
              color: showAnalyticsPanel ? '#00D2FF' : '#94A3B8',
              border: '1px solid #1A2436',
              cursor: 'pointer',
            }}
          >
            {showAnalyticsPanel ? 'Hide Analytics' : 'Show Analytics'}
          </button>

          {/* HUD Clock */}
          <div style={{ fontFamily: 'monospace', fontSize: '0.80rem', color: '#00D2FF', fontWeight: 600 }}>
            {clockStr}
          </div>
        </div>
      </header>

      {/* 2. Main Surveillance Console: Video Grid (Left) + Analytics Panel (Right) */}
      <div
        className="surveillance-split-layout"
        style={{
          display: 'grid',
          gridTemplateColumns: showAnalyticsPanel ? 'minmax(0, 1fr) 360px' : 'minmax(0, 1fr)',
          gap: '16px',
          alignItems: 'start',
        }}
      >
        {/* LEFT COLUMN: Video Viewport Grid & Quick Operational Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', minWidth: 0 }}>
          
          {/* Video Grid Canvas */}
          <div
            className="video-grid-canvas"
            style={{
              backgroundColor: '#05070C',
              border: '1px solid #1A2436',
              borderRadius: '8px',
              padding: gridMode === '1x1' ? '0' : '8px',
              overflow: 'hidden',
              display: 'grid',
              gap: '8px',
              gridTemplateColumns: gridMode === '1x1' ? '1fr' : gridMode === '2x2' ? 'repeat(2, 1fr)' : gridMode === '3x3' ? 'repeat(3, 1fr)' : 'repeat(4, 1fr)',
            }}
          >
            {getGridCameras().map((cam, idx) => {
              const isPrimary = Number(cam.id) === Number(selectedCamId);
              return (
                <div
                  key={`${cam.id}-${idx}`}
                  onClick={() => {
                    if (gridMode !== '1x1') {
                      setSelectedCamId(cam.id);
                      setGridMode('1x1'); // click-to-expand
                      addToast(`Focused on ${cam.name}`, 'info');
                    }
                  }}
                  style={{
                    position: 'relative',
                    cursor: gridMode !== '1x1' ? 'pointer' : 'default',
                    border: isPrimary && gridMode !== '1x1' ? '2px solid #00D2FF' : 'none',
                    borderRadius: '6px',
                    overflow: 'hidden',
                  }}
                >
                  <CameraLivePlayer
                    camera={cam}
                    activeMode={activeMode}
                    onModeChange={setActiveMode}
                    compact={gridMode !== '1x1'}
                    isRecording={isPrimary ? isRecording : false}
                    onToggleRecording={isPrimary ? handleToggleRecording : null}
                    onSnapshotTaken={() => addToast(t('surveillance.snapshotSaved', 'Snapshot captured and saved to Evidence Vault'), 'success')}
                  />
                  {gridMode !== '1x1' && (
                    <div style={{
                      position: 'absolute',
                      top: '8px',
                      left: '8px',
                      backgroundColor: 'rgba(5, 7, 12, 0.75)',
                      backdropFilter: 'blur(4px)',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      fontSize: '0.70rem',
                      fontWeight: 700,
                      color: '#F8FAFC',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                    }}>
                      {cam.name} &bull; {cam.status === 'online' ? 'LIVE' : 'OFFLINE'}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Operational Ribbon: Snapshot, Recording, Quick Health Indicators */}
          <div
            className="surveillance-operational-ribbon"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '12px 16px',
              backgroundColor: 'var(--bg-surface, #0B111E)',
              border: '1px solid var(--border-color, #1A2436)',
              borderRadius: '8px',
            }}
          >
            {/* Action Buttons */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                id="btn-surveillance-snapshot"
                onClick={handleCaptureSnapshot}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 14px',
                  borderRadius: '6px',
                  backgroundColor: '#070B13',
                  border: '1px solid #1A2436',
                  color: '#F8FAFC',
                  fontSize: '0.80rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'background 0.15s ease',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <span>{t('surveillance.takeSnapshot', 'Take Snapshot')}</span>
              </button>

              <button
                type="button"
                id="btn-surveillance-record"
                onClick={handleToggleRecording}
                disabled={recLoading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 14px',
                  borderRadius: '6px',
                  backgroundColor: isRecording ? 'rgba(239, 68, 68, 0.15)' : '#070B13',
                  border: isRecording ? '1px solid #EF4444' : '1px solid #1A2436',
                  color: isRecording ? '#EF4444' : '#F8FAFC',
                  fontSize: '0.80rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: isRecording ? '#EF4444' : '#64748B',
                    animation: isRecording ? 'pulse 1s infinite' : 'none',
                  }}
                />
                <span>{isRecording ? `REC [${formatSecs(recDuration)}]` : 'Record Clip'}</span>
              </button>
            </div>

            {/* Quality Telemetry Indicators */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '0.78rem', color: '#94A3B8', fontFamily: 'monospace' }}>
              <div>
                Resolution: <strong style={{ color: '#F8FAFC' }}>1280x720 HD</strong>
              </div>
              <div>
                Capture: <strong style={{ color: '#10B981' }}>{telemetry.capture_fps || 15.0} FPS</strong>
              </div>
              <div>
                Inference: <strong style={{ color: '#00D2FF' }}>{telemetry.inference_fps || 0} FPS</strong>
              </div>
              <div>
                Latency: <strong style={{ color: telemetry.latency_ms > 100 ? '#F59E0B' : '#10B981' }}>{telemetry.latency_ms || 0}ms</strong>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Docked Real-Time Camera Analytics Panel */}
        {showAnalyticsPanel && (
          <aside
            className="surveillance-analytics-sidebar"
            style={{
              backgroundColor: 'var(--bg-surface, #0B111E)',
              border: '1px solid var(--border-color, #1A2436)',
              borderRadius: '8px',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1A2436', paddingBottom: '10px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '0.94rem', fontWeight: 800, color: '#F8FAFC' }}>
                  Camera Analytics
                </h3>
                <span style={{ fontSize: '0.72rem', color: '#64748B' }}>
                  Live Telemetry &bull; {selectedCam.name}
                </span>
              </div>
              <span style={{
                padding: '2px 8px',
                borderRadius: '10px',
                backgroundColor: 'rgba(0, 210, 255, 0.1)',
                color: '#00D2FF',
                fontSize: '0.70rem',
                fontWeight: 700,
                border: '1px solid rgba(0, 210, 255, 0.25)',
              }}>
                LIVE SYNC
              </span>
            </div>

            {/* Metric Summary Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              <div style={{ backgroundColor: '#070B13', border: '1px solid #1A2436', borderRadius: '6px', padding: '10px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.68rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>Detections</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#00D2FF', marginTop: '2px' }}>
                  {telemetry.detections || 0}
                </div>
              </div>
              <div style={{ backgroundColor: '#070B13', border: '1px solid #1A2436', borderRadius: '6px', padding: '10px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.68rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>Tracks</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#10B981', marginTop: '2px' }}>
                  {(telemetry.tracks || []).length}
                </div>
              </div>
              <div style={{ backgroundColor: '#070B13', border: '1px solid #1A2436', borderRadius: '6px', padding: '10px 8px', textAlign: 'center' }}>
                <div style={{ fontSize: '0.68rem', color: '#64748B', fontWeight: 600, textTransform: 'uppercase' }}>Intrusions</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: (telemetry.active_intrusions || []).length > 0 ? '#EF4444' : '#64748B', marginTop: '2px' }}>
                  {(telemetry.active_intrusions || []).length}
                </div>
              </div>
            </div>

            {/* Class Distribution Breakdown */}
            <div>
              <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#F8FAFC', marginBottom: '8px', display: 'flex', justifyContent: 'space-between' }}>
                <span>Detected Classes</span>
                <span style={{ fontSize: '0.70rem', color: '#64748B' }}>In-Frame</span>
              </div>
              {Object.keys(classCounts).length === 0 ? (
                <div style={{ padding: '12px', textAlign: 'center', backgroundColor: '#070B13', border: '1px dashed #1A2436', borderRadius: '6px', fontSize: '0.76rem', color: '#64748B' }}>
                  No objects currently detected in view
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {Object.entries(classCounts).map(([cls, count]) => {
                    const color = classColorMap[cls] || '#94A3B8';
                    const pct = Math.round((count / (telemetry.detections || 1)) * 100);
                    return (
                      <div key={cls} style={{ backgroundColor: '#070B13', border: '1px solid #1A2436', borderRadius: '6px', padding: '8px 10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', fontWeight: 700, color: '#F8FAFC', textTransform: 'capitalize' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: color }} />
                            {cls}
                          </span>
                          <span style={{ fontSize: '0.74rem', fontWeight: 800, color }}>{count}</span>
                        </div>
                        <div style={{ width: '100%', height: '4px', backgroundColor: 'rgba(255, 255, 255, 0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: '2px' }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Active Track IDs */}
            <div>
              <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#F8FAFC', marginBottom: '8px' }}>
                Active Tracking IDs (ByteTrack)
              </div>
              {(telemetry.tracks || []).length === 0 ? (
                <div style={{ padding: '12px', textAlign: 'center', backgroundColor: '#070B13', border: '1px dashed #1A2436', borderRadius: '6px', fontSize: '0.76rem', color: '#64748B' }}>
                  Zero active tracking IDs
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                  {(telemetry.tracks || []).map((trk, i) => (
                    <div
                      key={trk.track_id || i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 10px',
                        backgroundColor: '#070B13',
                        border: '1px solid #1A2436',
                        borderRadius: '6px',
                        fontSize: '0.74rem',
                      }}
                    >
                      <span style={{ color: '#00D2FF', fontWeight: 700, fontFamily: 'monospace' }}>
                        ID: {trk.track_id || i + 1}
                      </span>
                      <span style={{ color: '#F8FAFC', textTransform: 'capitalize' }}>
                        {trk.class_name || trk.label || 'Person'}
                      </span>
                      <span style={{ color: '#10B981', fontWeight: 600 }}>
                        {Math.round((trk.confidence || 0.85) * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* AI Performance Gauges */}
            <div style={{ backgroundColor: '#070B13', border: '1px solid #1A2436', borderRadius: '6px', padding: '10px 12px' }}>
              <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#F8FAFC', marginBottom: '8px' }}>
                Engine Performance
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.74rem' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#94A3B8', marginBottom: '3px' }}>
                    <span>Inference FPS</span>
                    <span style={{ color: '#00D2FF', fontWeight: 700 }}>{telemetry.inference_fps || 0} / 30 FPS</span>
                  </div>
                  <div style={{ width: '100%', height: '4px', backgroundColor: 'rgba(255, 255, 255, 0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, ((telemetry.inference_fps || 0) / 30) * 100)}%`, height: '100%', backgroundColor: '#00D2FF' }} />
                  </div>
                </div>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#94A3B8', marginBottom: '3px' }}>
                    <span>Capture FPS</span>
                    <span style={{ color: '#10B981', fontWeight: 700 }}>{telemetry.capture_fps || 15} / 30 FPS</span>
                  </div>
                  <div style={{ width: '100%', height: '4px', backgroundColor: 'rgba(255, 255, 255, 0.08)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, ((telemetry.capture_fps || 15) / 30) * 100)}%`, height: '100%', backgroundColor: '#10B981' }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Alerts Scoped to Selected Camera */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '0.76rem', fontWeight: 700, color: '#F8FAFC' }}>
                  Recent Camera Alerts
                </span>
                {onNavigate && (
                  <button
                    type="button"
                    onClick={() => onNavigate('notifications', { tab: 'incidents' })}
                    style={{ background: 'none', border: 'none', color: '#00D2FF', fontSize: '0.70rem', cursor: 'pointer', padding: 0 }}
                  >
                    All Alerts &rarr;
                  </button>
                )}
              </div>
              {recentAlerts.length === 0 ? (
                <div style={{ padding: '12px', textAlign: 'center', backgroundColor: '#070B13', border: '1px dashed #1A2436', borderRadius: '6px', fontSize: '0.74rem', color: '#64748B' }}>
                  No recent security alerts for this camera
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {recentAlerts.map((alt) => {
                    const sev = (alt.severity || 'medium').toLowerCase();
                    const sevColor = sev === 'critical' ? '#EF4444' : sev === 'high' ? '#F97316' : sev === 'medium' ? '#F59E0B' : '#3B82F6';
                    return (
                      <div
                        key={alt.id}
                        onClick={() => {
                          if (onNavigate) {
                            onNavigate('notifications', { tab: 'incidents', incident: alt.id });
                          }
                        }}
                        style={{
                          padding: '8px 10px',
                          backgroundColor: '#070B13',
                          border: '1px solid #1A2436',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          transition: 'border-color 0.15s',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#00D2FF')}
                        onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#1A2436')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2px' }}>
                          <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#F8FAFC' }}>
                            {alt.event_type || alt.title || 'Security Anomaly'}
                          </span>
                          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: sevColor, textTransform: 'uppercase' }}>
                            {sev}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.68rem', color: '#64748B' }}>
                          {alt.created_at || 'Just now'} &bull; View Forensic &rarr;
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </aside>
        )}
      </div>

    </div>
  );
}

export default Surveillance;
