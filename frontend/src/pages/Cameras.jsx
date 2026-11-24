import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api, API_BASE_URL } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../components/common/Toast';
import { Modal } from '../components/common/Modal';
import { useTranslation } from '../i18n/i18nContext';
import {
  RestrictedZoneEditor,
  validatePolygonNormalized,
  normalizeZonePoints,
} from '../components/cameras/RestrictedZoneEditor';

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const DEFAULT_CAMERA_FORM = {
  name: '',
  source_type: 'browser',
  source: '0',
  username: '',
  password: '',
  location: 'Gate-1',
  restricted_entry_enabled: false,
  entry_direction: 'enter',
  schedule_mode: 'always',
  schedule_days: [0, 1, 2, 3, 4, 5, 6],
  schedule_start: '00:00',
  schedule_end: '23:59',
  alert_severity: 'high',
  notification_recipients: '',
  require_alert: true,
  suppress_duplicates: true,
  cooldown_seconds: 30,
  video_quality: 'high',
};

const QUALITY_SETTINGS_MAP = {
  standard: { id: 'standard', label: 'Standard (480p)', maxWidth: 640, maxHeight: 480, jpegQuality: 0.78, intervalMs: 42 },
  high: { id: 'high', label: 'High HD (720p)', maxWidth: 1280, maxHeight: 720, jpegQuality: 0.85, intervalMs: 33 },
  full: { id: 'full', label: 'Full Source (1080p)', maxWidth: 1920, maxHeight: 1080, jpegQuality: 0.91, intervalMs: 33 },
};

function formatBackendLabel(detectorBackend, trackerBackend, t) {
  const b = String(detectorBackend || '').toLowerCase();
  if (b.startsWith('yolo26')) {
    const arch = b.includes('yolo26n') ? 'YOLO26n' : b.includes('yolo26m') ? 'YOLO26m' : 'YOLO26s';
    const rt = b.includes('openvino_gpu')
      ? 'OpenVINO Iris Xe'
      : b.includes('openvino_cpu')
      ? 'OpenVINO CPU'
      : b.includes('onnxruntime')
      ? 'ONNX Runtime CPU'
      : b.includes('opencv_dnn')
      ? 'OpenCV DNN'
      : 'ONNX';
    const trk =
      trackerBackend === 'botsort_reid'
        ? 'BoT-SORT Re-ID'
        : trackerBackend === 'ocsort'
        ? 'OC-SORT'
        : 'ByteTrack';
    return `${arch} (${rt}) + ${trk}`;
  }
  if (detectorBackend === 'yolo11n' || b.startsWith('yolo11n')) {
    return t('cameras.backendYolo', 'YOLO11n + ByteTrack');
  }
  if (detectorBackend === 'opencv_fallback') {
    return t('cameras.backendOpenCV', 'OpenCV Vision Fallback');
  }
  if (detectorBackend === 'initializing') {
    return t('cameras.backendInitializing', 'Initializing AI...');
  }
  if (trackerBackend && trackerBackend !== 'unknown' && trackerBackend !== 'inactive') {
    return `${detectorBackend || 'AI'} (${trackerBackend})`;
  }
  return t('cameras.backendIdle', 'Idle');
}

export function Cameras({ onNavigate, pageParams, initialCameraId }) {
  const { user } = useAuth();
  const isViewer = user?.role === 'viewer';
  const { t } = useTranslation();
  const { addToast } = useToast();

  // Workspace view: 'management' (Camera Cards) | 'live' (Uncluttered Live Monitor)
  const [workspaceView, setWorkspaceView] = useState(() => {
    if (
      pageParams?.tab === 'live' ||
      pageParams?.mode === 'raw' ||
      pageParams?.mode === 'tracking' ||
      pageParams?.mode === 'yolo' ||
      pageParams?.mode === 'zone' ||
      pageParams?.mode === 'perimeter' ||
      pageParams?.camera ||
      pageParams?.id ||
      initialCameraId
    ) {
      return 'live';
    }
    return 'management';
  });

  // EXACT TWO operating modes in Live View: 'raw' | 'tracking'
  const [viewMode, setViewMode] = useState(() => {
    if (pageParams?.mode === 'raw' || pageParams?.mode === 'original') return 'raw';
    return 'tracking';
  });

  const [zoneEditorOpen, setZoneEditorOpen] = useState(() => (
    pageParams?.mode === 'zone' || pageParams?.mode === 'perimeter'
  ));

  useEffect(() => {
    if (pageParams?.mode === 'raw' || pageParams?.mode === 'original') {
      setViewMode('raw');
      setWorkspaceView('live');
      setZoneEditorOpen(false);
    } else if (pageParams?.mode === 'zone' || pageParams?.mode === 'perimeter') {
      setViewMode('tracking');
      setWorkspaceView('live');
      setZoneEditorOpen(true);
    } else if (pageParams?.mode === 'tracking' || pageParams?.mode === 'yolo' || pageParams?.tab === 'live') {
      setViewMode('tracking');
      setWorkspaceView('live');
    } else if (pageParams?.tab === 'management' || pageParams?.tab === 'inventory') {
      setWorkspaceView('management');
    }
  }, [pageParams?.mode, pageParams?.tab]);

  const requestedCameraId = Number(pageParams?.camera || pageParams?.id || initialCameraId || 0) || 1;
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // all | online | offline | restricted
  const [selectedCameraId, setSelectedCameraId] = useState(requestedCameraId);

  useEffect(() => {
    const nextId = Number(pageParams?.camera || pageParams?.id || initialCameraId || 0);
    if (nextId > 0) {
      setSelectedCameraId(nextId);
    }
  }, [pageParams?.camera, pageParams?.id, initialCameraId]);

  // Live Player & Separated Telemetry States
  const [isPlaying, setIsPlaying] = useState(true);
  const [isMuted, setIsMuted] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [isRecordingBusy, setIsRecordingBusy] = useState(false);
  const [measuredFps, setMeasuredFps] = useState(0);
  const [displayFps, setDisplayFps] = useState(0);
  const [measuredAiFps, setMeasuredAiFps] = useState(0);
  const [latencyMs, setLatencyMs] = useState(0);
  const [p50LatencyMs, setP50LatencyMs] = useState(0);
  const [p95LatencyMs, setP95LatencyMs] = useState(0);
  const [frameAgeMs, setFrameAgeMs] = useState(0);
  const [aiProfile, setAiProfile] = useState('lightweight');
  const [browserVideoDims, setBrowserVideoDims] = useState({ w: 1280, h: 720 });
  const [switchingProfile, setSwitchingProfile] = useState(false);
  const [liveResolution, setLiveResolution] = useState('');
  const [liveFourcc, setLiveFourcc] = useState('');
  const [switchingQuality, setSwitchingQuality] = useState(false);
  const [visiblePersonsCount, setVisiblePersonsCount] = useState(0);
  const [activeTracksCount, setActiveTracksCount] = useState(0);
  const [uniquePersonsObserved, setUniquePersonsObserved] = useState(0);
  const [totalDetectionEvents, setTotalDetectionEvents] = useState(0);
  const [activeTracksList, setActiveTracksList] = useState([]);
  const [recentDetections, setRecentDetections] = useState([]);
  const [recentZoneEvents, setRecentZoneEvents] = useState([]);
  const [activeIntrusions, setActiveIntrusions] = useState([]);
  const [detectorBackend, setDetectorBackend] = useState('unknown');
  const [trackerBackend, setTrackerBackend] = useState('unknown');
  const [clipScene, setClipScene] = useState(null);
  const [analyzingScene, setAnalyzingScene] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [streamLoaded, setStreamLoaded] = useState(false);
  const [useSnapshotFallback, setUseSnapshotFallback] = useState(false);
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const [streamTimestamp, setStreamTimestamp] = useState(() => Date.now());
  const [isCapturingSnapshot, setIsCapturingSnapshot] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isSavingCamera, setIsSavingCamera] = useState(false);
  const snapshotUrlRef = useRef(null);
  const viewportContainerRef = useRef(null);

  // Restricted Zones & Visual Polygon Editor State
  const [zones, setZones] = useState([]);
  const [cameraAlerts, setCameraAlerts] = useState([]);
  const [drawTool, setDrawTool] = useState('polygon'); // 'polygon' | 'rectangle'
  const [draftPoints, setDraftPoints] = useState([]);
  const [newZoneName, setNewZoneName] = useState('');
  const [newZoneDirection, setNewZoneDirection] = useState('enter');
  const [editingZone, setEditingZone] = useState(null);
  const [isZoneBusy, setIsZoneBusy] = useState(false);

  // Browser Webcam / Phone Camera Bridge
  const [browserBridgeActive, setBrowserBridgeActive] = useState(false);
  const [browserError, setBrowserError] = useState('');
  const [browserDevices, setBrowserDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const browserVideoRef = useRef(null);
  const browserCanvasRef = useRef(null);
  const browserStreamRef = useRef(null);
  const activeBridgeCamIdRef = useRef(null);
  const streamReloadPendingRef = useRef(false);
  const liveStreamImgRef = useRef(null);
  const streamLoadedRef = useRef(false);
  const streamErrorRef = useRef(false);
  const mjpegFailCountRef = useRef(0);

  // Add / Edit Camera Modal & Delete Confirm
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingCamId, setEditingCamId] = useState(null);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState(null);
  const [newCam, setNewCam] = useState(DEFAULT_CAMERA_FORM);
  const [deleteTargetCam, setDeleteTargetCam] = useState(null);

  const refreshBrowserDevices = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) return [];
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === 'videoinput');
      setBrowserDevices(videoInputs);
      if (videoInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(videoInputs[0].deviceId || '');
      }
      return videoInputs;
    } catch {
      return [];
    }
  }, [selectedDeviceId]);

  const requestBrowserCameraPermission = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      addToast('Browser camera API (getUserMedia) is not supported in this browser.', 'error');
      return [];
    }
    try {
      const probeStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      probeStream.getTracks().forEach((trk) => {
        try { trk.stop(); } catch {}
      });
      const list = await refreshBrowserDevices();
      if (list.length > 0 && newCam.source_type === 'browser') {
        const firstId = list[0].deviceId || '0';
        setSelectedDeviceId((prev) => prev || firstId);
        setNewCam((prev) => ({
          ...prev,
          source: prev.source && prev.source !== '0' ? prev.source : firstId,
        }));
      }
      return list;
    } catch (err) {
      const msg = err?.name === 'NotAllowedError'
        ? 'Camera permission denied by browser. Please allow camera access in site permissions.'
        : err?.message || 'Unable to access browser camera.';
      addToast(msg, 'error');
      return [];
    }
  }, [refreshBrowserDevices, newCam.source_type, addToast]);

  useEffect(() => {
    refreshBrowserDevices();
    if (typeof navigator !== 'undefined' && navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', refreshBrowserDevices);
      return () => {
        navigator.mediaDevices.removeEventListener('devicechange', refreshBrowserDevices);
      };
    }
    return undefined;
  }, [refreshBrowserDevices]);

  useEffect(() => {
    streamLoadedRef.current = streamLoaded;
  }, [streamLoaded]);

  useEffect(() => {
    streamErrorRef.current = streamError;
  }, [streamError]);

  const stopBrowserBridge = useCallback(() => {
    if (browserStreamRef.current) {
      browserStreamRef.current.getTracks().forEach((trk) => {
        try { trk.stop(); } catch {}
      });
      browserStreamRef.current = null;
    }
    if (browserVideoRef.current) {
      browserVideoRef.current.srcObject = null;
    }
    activeBridgeCamIdRef.current = null;
    setBrowserBridgeActive(false);
  }, []);

  useEffect(() => () => stopBrowserBridge(), [stopBrowserBridge]);

  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.cameras.list();
      const list = res.cameras || res.items || (Array.isArray(res) ? res : []);
      if (Array.isArray(list) && list.length > 0) {
        setCameras(list);
        setSelectedCameraId((prev) => (prev && list.some((c) => c.id === Number(prev)) ? prev : list[0].id));
      } else {
        setCameras([]);
      }
    } catch (err) {
      console.warn('Cameras load error:', err);
      setCameras([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCameras();
  }, [fetchCameras]);

  const selectedCam = cameras.find((c) => c.id === Number(selectedCameraId)) || cameras[0] || null;

  useEffect(() => {
    if (!browserBridgeActive || !selectedCam?.id) return undefined;
    const camId = selectedCam.id;
    const handleTabUnload = () => {
      stopBrowserBridge();
      try {
        const csrfMatch = document.cookie.match(/(?:^|;\s*)deepvision_django_csrftoken=([^;]+)/);
        const csrfVal = csrfMatch ? decodeURIComponent(csrfMatch[1]) : '';
        fetch(`${API_BASE_URL}/api/cameras/${camId}/disconnect/`, {
          method: 'POST',
          credentials: 'include',
          keepalive: true,
          headers: csrfVal ? { 'X-CSRFToken': csrfVal } : {},
        }).catch(() => {});
      } catch {}
    };
    window.addEventListener('pagehide', handleTabUnload);
    window.addEventListener('beforeunload', handleTabUnload);
    return () => {
      window.removeEventListener('pagehide', handleTabUnload);
      window.removeEventListener('beforeunload', handleTabUnload);
    };
  }, [browserBridgeActive, selectedCam?.id, stopBrowserBridge]);

  useEffect(() => {
    if (
      browserBridgeActive &&
      activeBridgeCamIdRef.current &&
      selectedCam?.id &&
      Number(activeBridgeCamIdRef.current) !== Number(selectedCam.id)
    ) {
      stopBrowserBridge();
    }
  }, [browserBridgeActive, selectedCam?.id, stopBrowserBridge]);

  useEffect(() => {
    if (selectedCam) {
      setIsRecording(Boolean(selectedCam.is_recording));
    }
  }, [selectedCam?.id, selectedCam?.is_recording]);

  const isCameraLive = Boolean(
    selectedCam &&
      !streamError &&
      (streamLoaded ||
        Boolean(snapshotUrl) ||
        (selectedCam.status === 'online' && measuredFps > 0) ||
        (browserBridgeActive && (displayFps > 0 || measuredFps > 0 || browserStreamRef.current)))
  );

  // Poll live telemetry when viewing Live Monitor (paused or browser-push skips redundant polling; ingest already returns fresh telemetry)
  useEffect(() => {
    if (!selectedCam?.id || workspaceView !== 'live' || !isPlaying) return undefined;
    let active = true;
    const pollStats = async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const stats = await api.cameras.getStats(selectedCam.id);
        if (!active || !stats) return;
        const liveOnline = stats.status === 'online' || Boolean(stats.live);
        if (typeof stats.fps === 'number') setMeasuredFps(liveOnline ? Math.round(stats.fps * 10) / 10 : 0);
        if (typeof stats.ai_fps === 'number') setMeasuredAiFps(liveOnline ? Math.round(stats.ai_fps * 10) / 10 : 0);
        if (typeof stats.latency_ms === 'number') setLatencyMs(liveOnline ? Math.round(stats.latency_ms * 10) / 10 : 0);
        if (typeof stats.p50_latency_ms === 'number') setP50LatencyMs(liveOnline ? Math.round(stats.p50_latency_ms * 10) / 10 : 0);
        if (typeof stats.p95_latency_ms === 'number') setP95LatencyMs(liveOnline ? Math.round(stats.p95_latency_ms * 10) / 10 : 0);
        if (typeof stats.frame_age_ms === 'number') setFrameAgeMs(liveOnline ? Math.round(stats.frame_age_ms * 10) / 10 : 0);
        if (typeof stats.ai_profile === 'string' && stats.ai_profile) setAiProfile(stats.ai_profile);
        if (typeof stats.resolution === 'string') setLiveResolution(liveOnline ? stats.resolution : '');
        if (typeof stats.fourcc === 'string') setLiveFourcc(liveOnline ? stats.fourcc : '');

        if (Array.isArray(stats.tracks)) {
          setActiveTracksList(stats.tracks);
        }
        if (typeof stats.currently_visible_persons === 'number') {
          setVisiblePersonsCount(stats.currently_visible_persons);
        } else if (Array.isArray(stats.tracks)) {
          setVisiblePersonsCount(stats.tracks.filter((x) => String(x.class_name || '').toLowerCase() === 'person').length);
        }
        if (typeof stats.active_tracks === 'number') {
          setActiveTracksCount(stats.active_tracks);
        } else if (Array.isArray(stats.tracks)) {
          setActiveTracksCount(stats.tracks.length);
        }
        if (typeof stats.unique_persons_observed === 'number') {
          setUniquePersonsObserved(stats.unique_persons_observed);
        }
        if (typeof stats.total_detection_events === 'number') {
          setTotalDetectionEvents(stats.total_detection_events);
        }
        if (Array.isArray(stats.recent_detections)) {
          setRecentDetections(stats.recent_detections);
        }
        if (Array.isArray(stats.recent_zone_events)) {
          setRecentZoneEvents(stats.recent_zone_events);
        }
        if (Array.isArray(stats.active_intrusions)) {
          setActiveIntrusions(stats.active_intrusions);
        }
        if (typeof stats.detector_backend === 'string' && stats.detector_backend) {
          setDetectorBackend(stats.detector_backend);
        }
        if (typeof stats.tracker_backend === 'string' && stats.tracker_backend) {
          setTrackerBackend(stats.tracker_backend);
        }
        if (stats.clip_scene && typeof stats.clip_scene === 'object') {
          setClipScene(stats.clip_scene);
        }
        if (typeof stats.is_recording === 'boolean') {
          setIsRecording(stats.is_recording);
        }
        if (stats.status && stats.status !== selectedCam.status) {
          setCameras((prev) => prev.map((c) => (c.id === selectedCam.id ? { ...c, status: stats.status } : c)));
        }
        if (stats.status === 'offline' && (streamLoadedRef.current || snapshotUrlRef.current)) {
          setStreamLoaded(false);
          if (snapshotUrlRef.current) {
            URL.revokeObjectURL(snapshotUrlRef.current);
            snapshotUrlRef.current = null;
          }
          setSnapshotUrl(null);
          setUseSnapshotFallback(false);
          setStreamError(true);
        } else if (stats.status === 'online' && stats.live && streamErrorRef.current && !snapshotUrlRef.current) {
          setStreamError(false);
          setUseSnapshotFallback(false);
          setStreamTimestamp(Date.now());
        }
      } catch {
        // Keep last telemetry sample on transient error
      }
    };
    pollStats();
    const pollMs = browserBridgeActive ? 5000 : viewMode === 'tracking' ? 1800 : 3500;
    const timer = setInterval(pollStats, pollMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selectedCam?.id, selectedCam?.status, workspaceView, viewMode, isPlaying, browserBridgeActive]);

  // Snapshot fallback ONLY if MJPEG stream actually fails or stalls >6.5s on a genuinely live camera (never mask 503 offline!)
  useEffect(() => {
    const camId = selectedCam?.id;
    const canStream = Boolean(
      camId &&
        isPlaying &&
        workspaceView === 'live' &&
        !browserBridgeActive &&
        !(selectedCam?.source_type === 'browser' && selectedCam?.status !== 'online')
    );
    if (!canStream || streamLoaded) {
      if (snapshotUrlRef.current) {
        URL.revokeObjectURL(snapshotUrlRef.current);
        snapshotUrlRef.current = null;
      }
      setSnapshotUrl(null);
      if (!canStream) setUseSnapshotFallback(false);
      return undefined;
    }

    let cancelled = false;
    let pollTimer = null;
    let upgradeTimer = null;
    const abortCtrl = typeof AbortController !== 'undefined' ? new AbortController() : null;

    const armDelayMs = browserBridgeActive ? 2500 : 6500;
    const fallbackArmTimer = (!streamLoaded && !streamError && (browserBridgeActive || selectedCam?.status === 'online'))
      ? setTimeout(() => {
          if (!cancelled) setUseSnapshotFallback(true);
        }, armDelayMs)
      : null;

    const shouldPollSnapshots = (streamError || useSnapshotFallback) && (browserBridgeActive || selectedCam?.status === 'online');
    if (shouldPollSnapshots) {
      if (mjpegFailCountRef.current < 2) {
        upgradeTimer = setInterval(() => {
          if (!cancelled && snapshotUrlRef.current) {
            URL.revokeObjectURL(snapshotUrlRef.current);
            snapshotUrlRef.current = null;
            setSnapshotUrl(null);
            setUseSnapshotFallback(false);
            setStreamError(false);
            setStreamTimestamp(Date.now());
          }
        }, 12000);
      }

      const fetchNextSnapshot = async () => {
        if (cancelled) return;
        if (typeof document !== 'undefined' && document.hidden) {
          pollTimer = setTimeout(fetchNextSnapshot, 400);
          return;
        }
        let nextDelay = 140;
        try {
          const resp = await fetch(
            `${api.cameras.getSnapshotUrl(camId)}?mode=${viewMode}&t=${Date.now()}`,
            { credentials: 'include', cache: 'no-store', signal: abortCtrl?.signal }
          );
          const sigHeader = resp.headers?.get('X-DeepVision-Signal');
          if (!cancelled && resp.ok && sigHeader !== 'offline') {
            const blob = await resp.blob();
            if (!cancelled && blob.size > 512) {
              const objUrl = URL.createObjectURL(blob);
              if (snapshotUrlRef.current) {
                URL.revokeObjectURL(snapshotUrlRef.current);
              }
              snapshotUrlRef.current = objUrl;
              setSnapshotUrl(objUrl);
              setStreamError(false);
            }
          } else if (!cancelled && (resp.status === 503 || sigHeader === 'offline')) {
            if (snapshotUrlRef.current) {
              URL.revokeObjectURL(snapshotUrlRef.current);
              snapshotUrlRef.current = null;
            }
            setSnapshotUrl(null);
            setStreamLoaded(false);
            setStreamError(true);
            setMeasuredFps(0);
            setMeasuredAiFps(0);
            setLatencyMs(0);
            nextDelay = 4500;
          }
        } catch {
          nextDelay = 1500;
        } finally {
          if (!cancelled) {
            pollTimer = setTimeout(fetchNextSnapshot, nextDelay);
          }
        }
      };
      fetchNextSnapshot();
    }

    return () => {
      cancelled = true;
      if (abortCtrl) {
        try { abortCtrl.abort(); } catch {}
      }
      if (fallbackArmTimer) clearTimeout(fallbackArmTimer);
      if (pollTimer) clearTimeout(pollTimer);
      if (upgradeTimer) clearInterval(upgradeTimer);
    };
  }, [selectedCam?.id, selectedCam?.status, isPlaying, workspaceView, browserBridgeActive, streamLoaded, streamError, useSnapshotFallback, viewMode]);

  // Browser Webcam Display FPS Meter (measures true decoded <video> paint cadence independently of AI/upload)
  useEffect(() => {
    if (!browserBridgeActive || !isPlaying || workspaceView !== 'live') {
      setDisplayFps(0);
      return undefined;
    }
    const videoEl = browserVideoRef.current;
    if (!videoEl) return undefined;

    let active = true;
    let rvfcId = null;
    let rafId = null;
    let count = 0;
    let winStart = performance.now();
    let lastVideoTime = -1;

    const recordFrame = (now) => {
      count += 1;
      const elapsed = now - winStart;
      if (elapsed >= 800) {
        if (active) setDisplayFps(Math.round(((count * 1000) / elapsed) * 10) / 10);
        count = 0;
        winStart = now;
      }
      if (videoEl.videoWidth > 0 && videoEl.videoHeight > 0) {
        setBrowserVideoDims((prev) =>
          prev.w === videoEl.videoWidth && prev.h === videoEl.videoHeight
            ? prev
            : { w: videoEl.videoWidth, h: videoEl.videoHeight }
        );
      }
    };

    if (typeof videoEl.requestVideoFrameCallback === 'function') {
      const onVideoFrame = (now) => {
        if (!active) return;
        recordFrame(now);
        rvfcId = videoEl.requestVideoFrameCallback(onVideoFrame);
      };
      rvfcId = videoEl.requestVideoFrameCallback(onVideoFrame);
      return () => {
        active = false;
        if (rvfcId !== null && typeof videoEl.cancelVideoFrameCallback === 'function') {
          try { videoEl.cancelVideoFrameCallback(rvfcId); } catch {}
        }
      };
    }

    const onRaf = (now) => {
      if (!active) return;
      if (videoEl.readyState >= 2 && videoEl.currentTime !== lastVideoTime) {
        lastVideoTime = videoEl.currentTime;
        recordFrame(now);
      }
      rafId = requestAnimationFrame(onRaf);
    };
    rafId = requestAnimationFrame(onRaf);
    return () => {
      active = false;
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [browserBridgeActive, isPlaying, workspaceView, selectedCam?.id]);

  // Browser Webcam Ingest Loop: synchronous video-frame-paced JPEG Blob upload + bounded concurrency (max 2 in-flight, latest-seq ordering)
  useEffect(() => {
    if (!browserBridgeActive || !selectedCam?.id || !isPlaying) return undefined;
    let active = true;
    let inFlightCount = 0;
    let seqCounter = 0;
    let latestAppliedSeq = 0;
    let lastUploadAt = 0;
    let rvfcHandle = null;
    const targetCamId = selectedCam.id;

    const qualityCfg = QUALITY_SETTINGS_MAP[selectedCam?.video_quality] || QUALITY_SETTINGS_MAP.high;
    const minIntervalMs = Math.max(25, (qualityCfg.intervalMs || 33) - 4);

    const pushFrame = () => {
      if (!active || inFlightCount >= 2) return;
      if (typeof document !== 'undefined' && document.hidden) return;
      const nowPerf = performance.now();
      if (nowPerf - lastUploadAt < minIntervalMs) return;
      const videoEl = browserVideoRef.current;
      if (!videoEl || videoEl.readyState < 2 || !videoEl.videoWidth) return;

      lastUploadAt = nowPerf;
      let canvas = browserCanvasRef.current;
      if (!canvas) {
        canvas = document.createElement('canvas');
        browserCanvasRef.current = canvas;
      }
      const targetW = Math.min(qualityCfg.maxWidth, videoEl.videoWidth);
      const targetH = Math.round((videoEl.videoHeight / videoEl.videoWidth) * targetW) || 360;
      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW;
        canvas.height = targetH;
      }
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(videoEl, 0, 0, targetW, targetH);

      inFlightCount += 1;
      const thisSeq = ++seqCounter;

      const sendPayload = async (blob) => {
        try {
          if (!active || !blob) return;
          const res = await api.cameras.ingestFrame(targetCamId, blob, thisSeq);
          if (!active || !res?.success) return;
          setStreamError(false);
          if (streamReloadPendingRef.current) {
            streamReloadPendingRef.current = false;
            setUseSnapshotFallback(false);
            setSnapshotUrl(null);
            setStreamError(false);
            setStreamLoaded(false);
            setStreamTimestamp(Date.now());
          }
          if (thisSeq >= latestAppliedSeq) {
            latestAppliedSeq = thisSeq;
            if (typeof res.fps === 'number') setMeasuredFps(res.fps);
            if (typeof res.ai_fps === 'number') setMeasuredAiFps(res.ai_fps);
            if (typeof res.latency_ms === 'number') setLatencyMs(res.latency_ms);
            if (typeof res.p50_latency_ms === 'number') setP50LatencyMs(res.p50_latency_ms);
            if (typeof res.p95_latency_ms === 'number') setP95LatencyMs(res.p95_latency_ms);
            if (typeof res.frame_age_ms === 'number') setFrameAgeMs(res.frame_age_ms);
            if (typeof res.ai_profile === 'string' && res.ai_profile) setAiProfile(res.ai_profile);
            if (res.frame_width && res.frame_height) {
              setLiveResolution(`${res.frame_width}x${res.frame_height}`);
              setBrowserVideoDims({ w: Number(res.frame_width), h: Number(res.frame_height) });
            }
            const nextTracks = Array.isArray(res.tracks_list) ? res.tracks_list : (Array.isArray(res.tracks) ? res.tracks : null);
            if (nextTracks) setActiveTracksList(nextTracks);
            if (typeof res.currently_visible_persons === 'number') setVisiblePersonsCount(res.currently_visible_persons);
            if (typeof res.active_tracks === 'number') setActiveTracksCount(res.active_tracks);
            if (typeof res.unique_persons_observed === 'number') setUniquePersonsObserved(res.unique_persons_observed);
            if (typeof res.total_detection_events === 'number') setTotalDetectionEvents(res.total_detection_events);
            if (Array.isArray(res.recent_detections)) setRecentDetections(res.recent_detections);
            if (Array.isArray(res.recent_zone_events)) setRecentZoneEvents(res.recent_zone_events);
            if (typeof res.detector_backend === 'string' && res.detector_backend) setDetectorBackend(res.detector_backend);
            if (typeof res.tracker_backend === 'string' && res.tracker_backend) setTrackerBackend(res.tracker_backend);
            if (res.clip_scene && typeof res.clip_scene === 'object') setClipScene(res.clip_scene);
          }
        } catch {
          // Ignore single frame drop
        } finally {
          inFlightCount = Math.max(0, inFlightCount - 1);
        }
      };

      if (typeof canvas.toBlob === 'function') {
        canvas.toBlob((blob) => {
          if (blob) {
            sendPayload(blob);
          } else {
            inFlightCount = Math.max(0, inFlightCount - 1);
          }
        }, 'image/jpeg', qualityCfg.jpegQuality);
      } else {
        sendPayload(canvas.toDataURL('image/jpeg', qualityCfg.jpegQuality));
      }
    };

    const videoEl = browserVideoRef.current;
    if (videoEl && typeof videoEl.requestVideoFrameCallback === 'function') {
      const onFrame = () => {
        if (!active) return;
        pushFrame();
        rvfcHandle = videoEl.requestVideoFrameCallback(onFrame);
      };
      rvfcHandle = videoEl.requestVideoFrameCallback(onFrame);
    }

    const initialTimer = setTimeout(pushFrame, 20);
    const interval = setInterval(pushFrame, qualityCfg.intervalMs);
    return () => {
      active = false;
      clearTimeout(initialTimer);
      clearInterval(interval);
      if (rvfcHandle !== null && videoEl && typeof videoEl.cancelVideoFrameCallback === 'function') {
        try { videoEl.cancelVideoFrameCallback(rvfcHandle); } catch {}
      }
    };
  }, [browserBridgeActive, selectedCam?.id, selectedCam?.video_quality, isPlaying]);

  // Abort active MJPEG stream immediately when leaving Live View, pausing, or unmounting
  useEffect(() => {
    const imgEl = liveStreamImgRef.current;
    if (workspaceView !== 'live' || !isPlaying) {
      if (imgEl && imgEl.src && !imgEl.src.startsWith('blob:')) {
        imgEl.src = '';
      }
    }
    return () => {
      if (imgEl) {
        imgEl.src = '';
      }
    };
  }, [workspaceView, isPlaying, selectedCam?.id, viewMode]);

  const handleSwitchAiProfile = async (nextProfile) => {
    if (switchingProfile || nextProfile === aiProfile) return;
    setSwitchingProfile(true);
    try {
      const res = await api.settings.saveDetection({ ai_profile: nextProfile });
      if (res?.ai_profile) setAiProfile(res.ai_profile);
      if (res?.detector_backend) setDetectorBackend(res.detector_backend);
      addToast(
        nextProfile === 'lightweight'
          ? 'Switched to YOLO26n (High-Speed CPU profile).'
          : 'Switched to YOLO26s (Balanced Accuracy profile).',
        'success'
      );
    } catch (err) {
      addToast(err?.message || 'Failed to switch AI profile', 'error');
    } finally {
      setSwitchingProfile(false);
    }
  };

  useEffect(() => {
    if (browserBridgeActive && browserVideoRef.current && browserStreamRef.current) {
      if (browserVideoRef.current.srcObject !== browserStreamRef.current) {
        browserVideoRef.current.srcObject = browserStreamRef.current;
      }
      browserVideoRef.current.play().catch(() => {});
    }
  }, [browserBridgeActive, workspaceView, viewMode, selectedCam?.id]);

  // Zones & scoped alerts refresh
  const refreshCameraZonesAndAlerts = useCallback(async (camId) => {
    if (!camId) return;
    try {
      const [zRes, aRes] = await Promise.allSettled([
        api.cameras.getZones(camId),
        api.alerts.list({ camera_id: camId, limit: 12 }),
      ]);
      if (zRes.status === 'fulfilled' && zRes.value?.zones) {
        setZones(zRes.value.zones);
      }
      if (aRes.status === 'fulfilled') {
        const rawAlerts = aRes.value?.alerts || aRes.value?.items || (Array.isArray(aRes.value) ? aRes.value : []);
        setCameraAlerts(rawAlerts);
      }
    } catch {
      // ignore transient poll error
    }
  }, []);

  useEffect(() => {
    if (!selectedCam?.id) {
      setZones([]);
      setCameraAlerts([]);
      return;
    }
    mjpegFailCountRef.current = 0;
    setBrowserError('');
    setStreamError(false);
    setStreamLoaded(false);
    setUseSnapshotFallback(false);
    if (snapshotUrlRef.current) {
      URL.revokeObjectURL(snapshotUrlRef.current);
      snapshotUrlRef.current = null;
    }
    setSnapshotUrl(null);
    setStreamTimestamp(Date.now());
    setMeasuredFps(0);
    setMeasuredAiFps(0);
    setLatencyMs(0);
    setP50LatencyMs(0);
    setP95LatencyMs(0);
    setFrameAgeMs(0);
    setActiveTracksList([]);
    setActiveTracksCount(0);
    setVisiblePersonsCount(0);
    setUniquePersonsObserved(0);
    setTotalDetectionEvents(0);
    setRecentDetections([]);
    setRecentZoneEvents([]);
    setActiveIntrusions([]);
    setDetectorBackend('unknown');
    setTrackerBackend('unknown');
    setClipScene(null);
    setDraftPoints([]);
    setEditingZone(null);
    refreshCameraZonesAndAlerts(selectedCam.id);
  }, [selectedCam?.id, refreshCameraZonesAndAlerts]);

  useEffect(() => {
    if (!selectedCam?.id || workspaceView !== 'live' || !isCameraLive) return undefined;
    const timer = setInterval(() => {
      refreshCameraZonesAndAlerts(selectedCam.id);
    }, 4500);
    return () => clearInterval(timer);
  }, [selectedCam?.id, workspaceView, isCameraLive, refreshCameraZonesAndAlerts]);

  // Mode Switch Handler (RAW CAMERA FOOTAGE <-> DETECTION & TRACKING) cleanly reuses existing camera
  const handleSwitchMode = (nextMode) => {
    if (nextMode === viewMode) return;
    setViewMode(nextMode);
    if (nextMode === 'raw') {
      setZoneEditorOpen(false);
    }
    mjpegFailCountRef.current = 0;
    if (snapshotUrlRef.current) {
      URL.revokeObjectURL(snapshotUrlRef.current);
      snapshotUrlRef.current = null;
    }
    setSnapshotUrl(null);
    setUseSnapshotFallback(false);
    setStreamLoaded(false);
    setStreamError(false);
    setStreamTimestamp(Date.now());
  };

  const handleStartBrowserBridge = async (targetCam = null, overrideDeviceId = null) => {
    const camTarget = targetCam && targetCam.id ? targetCam : selectedCam;
    if (!navigator.mediaDevices?.getUserMedia) {
      const msg = 'Browser camera API (getUserMedia) is not supported in this browser.';
      setBrowserError(msg);
      addToast(msg, 'error');
      return;
    }
    try {
      setBrowserError('');
      stopBrowserBridge();
      const storedBrowserDevice =
        camTarget?.source_type === 'browser' && camTarget.source && camTarget.source !== '0' && camTarget.source.length > 8
          ? camTarget.source
          : '';
      const chosenDeviceId = overrideDeviceId || storedBrowserDevice || selectedDeviceId;
      const qualityCfg = QUALITY_SETTINGS_MAP[camTarget?.video_quality] || QUALITY_SETTINGS_MAP.high;
      const defaultFacing = camTarget?.source_type === 'phone' ? 'environment' : 'user';
      const primaryConstraints = chosenDeviceId
        ? { deviceId: { exact: chosenDeviceId }, width: { ideal: qualityCfg.maxWidth }, height: { ideal: qualityCfg.maxHeight }, frameRate: { ideal: 30 } }
        : { facingMode: defaultFacing, width: { ideal: qualityCfg.maxWidth }, height: { ideal: qualityCfg.maxHeight }, frameRate: { ideal: 30 } };

      let mediaStream;
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: primaryConstraints, audio: false });
      } catch (constraintErr) {
        if (chosenDeviceId && (constraintErr?.name === 'OverconstrainedError' || constraintErr?.name === 'NotFoundError')) {
          mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: defaultFacing, width: { ideal: qualityCfg.maxWidth }, height: { ideal: qualityCfg.maxHeight } },
            audio: false,
          });
        } else {
          throw constraintErr;
        }
      }

      const [videoTrack] = mediaStream.getVideoTracks();
      if (videoTrack) {
        videoTrack.addEventListener('ended', () => {
          stopBrowserBridge();
          setBrowserError('Browser camera stream ended or was disconnected.');
          if (camTarget?.id) {
            api.cameras.disconnect(camTarget.id).catch(() => {});
          }
          addToast('Browser camera stream ended.', 'warning');
        }, { once: true });
      }

      browserStreamRef.current = mediaStream;
      activeBridgeCamIdRef.current = camTarget?.id || null;
      streamReloadPendingRef.current = true;
      mjpegFailCountRef.current = 0;
      setBrowserBridgeActive(true);
      setStreamError(false);
      setStreamLoaded(false);
      setUseSnapshotFallback(false);
      await refreshBrowserDevices();
      setTimeout(() => {
        if (browserVideoRef.current && browserStreamRef.current) {
          browserVideoRef.current.srcObject = browserStreamRef.current;
          browserVideoRef.current.play().catch(() => {});
        }
      }, 50);
      addToast(`Connected browser camera for ${camTarget?.name || 'Camera'}`, 'success');
    } catch (err) {
      const msg = err?.name === 'NotAllowedError'
        ? 'Camera permission denied by browser. Allow camera access in site permissions and retry.'
        : err?.name === 'NotFoundError'
        ? 'No compatible camera device found in browser.'
        : err?.message || 'Failed to access browser camera.';
      setBrowserError(msg);
      addToast(msg, 'error');
    }
  };

  const handleCaptureSnapshot = async () => {
    if (!selectedCam?.id) return;
    try {
      setIsCapturingSnapshot(true);
      await api.cameras.snapshot(selectedCam.id);
      addToast(t('surveillance.snapshotSaved', 'Snapshot captured and saved to Evidence Vault'), 'success');
    } catch (err) {
      addToast(err.message || 'Snapshot failed', 'error');
    } finally {
      setIsCapturingSnapshot(false);
    }
  };

  const handleToggleRecording = async () => {
    if (!selectedCam?.id || isRecordingBusy) return;
    try {
      setIsRecordingBusy(true);
      if (isRecording) {
        const res = await api.cameras.stopRecording(selectedCam.id);
        setIsRecording(false);
        setCameras((prev) => prev.map((c) => (c.id === selectedCam.id ? { ...c, is_recording: false } : c)));
        addToast(res?.message || `Recording stopped and saved for ${selectedCam.name}`, 'success');
      } else {
        const res = await api.cameras.startRecording(selectedCam.id);
        if (res?.success || res?.status === 'ok' || res?.status === 'warning') {
          setIsRecording(true);
          setCameras((prev) => prev.map((c) => (c.id === selectedCam.id ? { ...c, is_recording: true } : c)));
          addToast(res?.message || `Recording started on ${selectedCam.name}`, 'success');
        } else {
          addToast(res?.message || 'Unable to start recording', 'error');
        }
      }
    } catch (err) {
      addToast(err.message || 'Recording operation failed', 'error');
    } finally {
      setIsRecordingBusy(false);
    }
  };

  const handleReconnectCamera = async (camObj = selectedCam) => {
    const target = camObj || selectedCam;
    if (!target?.id || isReconnecting) return;
    if (target.source_type === 'browser') {
      setSelectedCameraId(target.id);
      await handleStartBrowserBridge(target);
      return;
    }
    try {
      setIsReconnecting(true);
      setBrowserError('');
      setStreamError(false);
      setStreamLoaded(false);
      setUseSnapshotFallback(false);
      mjpegFailCountRef.current = 0;
      if (snapshotUrlRef.current) {
        URL.revokeObjectURL(snapshotUrlRef.current);
        snapshotUrlRef.current = null;
      }
      setSnapshotUrl(null);

      const res = await api.cameras.testCamera(target.id);
      if (res?.success) {
        try {
          await api.cameras.warm(target.id, true);
        } catch (_) {}
      }
      const newStatus = res?.camera_status || (res?.success ? 'online' : 'offline');
      setCameras((prev) => prev.map((c) => (c.id === target.id ? { ...c, status: newStatus } : c)));
      setStreamTimestamp(Date.now());
      if (res?.success) {
        addToast(`Camera "${target.name}" connected (${res.width || 640}x${res.height || 480})`, 'success');
      } else {
        setStreamError(true);
        addToast(res?.message || `Camera "${target.name}" is unreachable.`, 'warning');
      }
    } catch (err) {
      setStreamError(true);
      addToast(err.message || `Reconnect failed for ${target.name}`, 'error');
    } finally {
      setIsReconnecting(false);
    }
  };

  const handleDisconnectCamera = async (camObj = selectedCam) => {
    const target = camObj || selectedCam;
    if (!target?.id) return;
    try {
      if (browserBridgeActive && selectedCam?.id === target.id) {
        stopBrowserBridge();
      }
      await api.cameras.disconnect(target.id);
      setCameras((prev) => prev.map((c) => (c.id === target.id ? { ...c, status: 'offline', is_recording: false } : c)));
      if (selectedCam?.id === target.id) {
        setStreamLoaded(false);
        setIsRecording(false);
      }
      addToast(`Camera "${target.name}" disconnected`, 'info');
    } catch (err) {
      addToast(err.message || 'Failed to disconnect camera', 'error');
    }
  };

  const confirmRemoveCamera = async () => {
    const camObj = deleteTargetCam;
    if (!camObj?.id) return;
    try {
      if (browserBridgeActive && selectedCam?.id === camObj.id) {
        stopBrowserBridge();
      }
      await api.cameras.remove(camObj.id);
      addToast(`Camera "${camObj.name}" removed from inventory`, 'success');
      setDeleteTargetCam(null);
      fetchCameras();
    } catch (err) {
      addToast(err.message || `Failed to remove camera "${camObj.name}"`, 'error');
    }
  };

  const handleToggleFullscreen = () => {
    const el = viewportContainerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  // Save newly drawn polygon/rectangle or edited existing zone
  const handleSaveZone = async (e) => {
    e?.preventDefault?.();
    if (!selectedCam?.id || isZoneBusy) return;

    const pointsToSave = editingZone ? normalizeZonePoints(editingZone) : draftPoints;
    if (pointsToSave.length < 3) {
      addToast('Draw at least 3 boundary vertices on the video frame first.', 'warning');
      return;
    }
    const validation = validatePolygonNormalized(pointsToSave);
    if (!validation.valid) {
      addToast(validation.error, 'error');
      return;
    }

    const zoneLabel = editingZone
      ? (editingZone.name || '').trim() || `Zone ${editingZone.id}`
      : (newZoneName || '').trim() || `Restricted Zone ${zones.length + 1}`;
    const shapeType = editingZone
      ? (editingZone.shape || (pointsToSave.length === 4 && drawTool === 'rectangle' ? 'rectangle' : 'polygon'))
      : drawTool;

    try {
      setIsZoneBusy(true);
      await api.cameras.createZone(selectedCam.id, {
        zone_id: editingZone?.id,
        name: zoneLabel,
        shape: shapeType,
        points: pointsToSave,
        entry_direction: editingZone ? editingZone.entry_direction : newZoneDirection,
        color: '#ef4444',
        enabled: true,
      });
      setDraftPoints([]);
      setNewZoneName('');
      setEditingZone(null);
      await refreshCameraZonesAndAlerts(selectedCam.id);
      await fetchCameras();
      addToast(`Restricted zone "${zoneLabel}" saved`, 'success');
    } catch (err) {
      addToast(err.message || 'Failed to save restricted zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  const handleEditZoneVertices = useCallback((zoneId, updatedPoints) => {
    setZones((prev) => prev.map((z) => (z.id === zoneId ? { ...z, points: updatedPoints } : z)));
    setEditingZone((prev) => (prev && prev.id === zoneId ? { ...prev, points: updatedPoints } : prev));
  }, []);

  const handleToggleRestrictedZone = async (zoneId) => {
    if (!selectedCam?.id || isZoneBusy) return;
    try {
      setIsZoneBusy(true);
      await api.cameras.toggleZone(selectedCam.id, zoneId);
      await refreshCameraZonesAndAlerts(selectedCam.id);
      await fetchCameras();
    } catch (err) {
      addToast(err.message || 'Failed to toggle zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  const handleDeleteRestrictedZone = async (zoneId) => {
    if (!selectedCam?.id || isZoneBusy) return;
    try {
      setIsZoneBusy(true);
      await api.cameras.deleteZone(selectedCam.id, zoneId);
      if (editingZone?.id === zoneId) setEditingZone(null);
      await refreshCameraZonesAndAlerts(selectedCam.id);
      await fetchCameras();
      addToast('Restricted zone deleted', 'success');
    } catch (err) {
      addToast(err.message || 'Failed to delete zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  const handleOpenAddModal = () => {
    setEditingCamId(null);
    setConnectionTestResult(null);
    setNewCam({ ...DEFAULT_CAMERA_FORM, source: selectedDeviceId || '0' });
    setIsAddModalOpen(true);
  };

  const handleOpenEditModal = (camObj) => {
    if (!camObj) return;
    setEditingCamId(camObj.id);
    setConnectionTestResult(null);
    const sched = camObj.schedule || {};
    setNewCam({
      name: camObj.name || '',
      source_type: camObj.source_type || 'webcam',
      source: String(camObj.source ?? '0'),
      username: '',
      password: '',
      location: camObj.location || 'Gate-1',
      restricted_entry_enabled: Boolean(camObj.restricted_entry_enabled),
      entry_direction: camObj.entry_direction || 'enter',
      schedule_mode: sched.mode || 'always',
      schedule_days: Array.isArray(sched.days) && sched.days.length ? sched.days : [0, 1, 2, 3, 4, 5, 6],
      schedule_start: sched.start_time || '00:00',
      schedule_end: sched.end_time || '23:59',
      alert_severity: camObj.alert_severity || 'high',
      notification_recipients: Array.isArray(camObj.notification_recipients)
        ? camObj.notification_recipients.join(', ')
        : '',
      require_alert: camObj.require_alert !== false,
      suppress_duplicates: camObj.suppress_duplicates !== false,
      cooldown_seconds: Number(camObj.cooldown_seconds || 30),
      video_quality: camObj.video_quality || 'high',
    });
    setIsAddModalOpen(true);
  };

  const handleTestModalConnection = async () => {
    if (newCam.source_type === 'browser') {
      if (!navigator.mediaDevices?.getUserMedia) {
        const msg = 'Browser camera API (getUserMedia) is not supported in this browser.';
        setConnectionTestResult({ success: false, message: msg });
        return;
      }
      try {
        setIsTestingConnection(true);
        setConnectionTestResult(null);
        const chosenId = newCam.source && newCam.source !== '0' ? newCam.source : selectedDeviceId;
        const stream = await navigator.mediaDevices.getUserMedia({
          video: chosenId ? { deviceId: { exact: chosenId } } : { facingMode: 'user' },
          audio: false,
        });
        const trk = stream.getVideoTracks()[0];
        const label = trk?.label || 'Browser Webcam';
        stream.getTracks().forEach((tr) => { try { tr.stop(); } catch {} });
        await refreshBrowserDevices();
        setConnectionTestResult({ success: true, message: `Verified: ${label}` });
      } catch (err) {
        setConnectionTestResult({ success: false, message: err?.message || 'Browser camera test failed.' });
      } finally {
        setIsTestingConnection(false);
      }
      return;
    }

    try {
      setIsTestingConnection(true);
      setConnectionTestResult(null);
      const res = await api.cameras.testConnection(
        newCam.source_type,
        newCam.source,
        newCam.username,
        newCam.password
      );
      setConnectionTestResult(res);
    } catch (err) {
      setConnectionTestResult({ success: false, message: err.message || 'Connection test failed' });
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleAddCameraSubmit = async (e) => {
    e.preventDefault();
    if (!newCam.name.trim() || isSavingCamera) return;
    setIsSavingCamera(true);
    try {
      const payload = {
        name: newCam.name.trim(),
        source_type: newCam.source_type,
        source: newCam.source.trim() || '0',
        location: newCam.location.trim() || 'Default Zone',
        username: newCam.username.trim(),
        password: newCam.password,
        restricted_entry_enabled: Boolean(newCam.restricted_entry_enabled),
        purpose: newCam.restricted_entry_enabled ? 'restricted_entry' : 'general',
        entry_direction: newCam.entry_direction,
        schedule: {
          mode: newCam.schedule_mode,
          days: newCam.schedule_days,
          start_time: newCam.schedule_start,
          end_time: newCam.schedule_end,
        },
        alert_severity: newCam.alert_severity,
        notification_recipients: newCam.notification_recipients,
        require_alert: Boolean(newCam.require_alert),
        suppress_duplicates: Boolean(newCam.suppress_duplicates),
        cooldown_seconds: Number(newCam.cooldown_seconds || 30),
      };

      let savedCam = null;
      if (editingCamId) {
        const updatedRes = await api.cameras.update(editingCamId, payload);
        savedCam = updatedRes?.camera || null;
        addToast(`Camera "${newCam.name}" updated`, 'success');
      } else {
        const createdRes = await api.cameras.create(payload);
        savedCam = createdRes?.camera || null;
        addToast(`Camera "${newCam.name}" registered`, 'success');
      }

      setIsAddModalOpen(false);
      setEditingCamId(null);
      setConnectionTestResult(null);
      await fetchCameras();

      if (savedCam && savedCam.source_type === 'browser' && !editingCamId) {
        setSelectedCameraId(savedCam.id);
        setWorkspaceView('live');
        setViewMode('tracking');
        await handleStartBrowserBridge(savedCam, savedCam.source);
      } else if (savedCam && !editingCamId && payload.restricted_entry_enabled) {
        setSelectedCameraId(savedCam.id);
        setWorkspaceView('live');
        setViewMode('tracking');
        setZoneEditorOpen(true);
      }
    } catch (err) {
      addToast(err.message || `Failed to save camera ${newCam.name}`, 'error');
    } finally {
      setIsSavingCamera(false);
    }
  };

  const filteredCameras = cameras.filter((c) => {
    if (statusFilter === 'online' && c.status !== 'online') return false;
    if (statusFilter === 'offline' && c.status === 'online') return false;
    if (statusFilter === 'restricted' && !c.restricted_entry_enabled) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (c.name || '').toLowerCase().includes(q) || (c.location || '').toLowerCase().includes(q);
    }
    return true;
  });

  const formatTimeShort = (tsVal) => {
    if (!tsVal) return '';
    try {
      const d = typeof tsVal === 'number' ? new Date(tsVal * 1000) : new Date(tsVal);
      if (isNaN(d.getTime())) return String(tsVal);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '';
    }
  };

  const backendBadgeLabel = formatBackendLabel(detectorBackend, trackerBackend, t);

  // =========================================================================
  // RENDER: CAMERA MANAGEMENT CARDS VIEW
  // =========================================================================
  const renderCameraManagement = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
          padding: '16px 20px',
          backgroundColor: 'var(--bg-surface, #0F172A)',
          border: '1px solid var(--border-color, #1E293B)',
          borderRadius: '10px',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: 'var(--text-main, #F8FAFC)' }}>
            {t('cameras.managementTitle', 'Camera Management')}
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: 'var(--text-muted, #94A3B8)' }}>
            {t('cameras.managementSubtitle', 'Manage camera streams, AI monitoring modes, and restricted-entry perimeter policies.')}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('cameras.searchPlaceholder', 'Search name or location...')}
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-body, #090D16)',
              border: '1px solid var(--border-color, #1E293B)',
              borderRadius: '8px',
              color: 'var(--text-main, #F8FAFC)',
              fontSize: '0.84rem',
              minWidth: '210px',
            }}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter cameras"
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--bg-body, #090D16)',
              border: '1px solid var(--border-color, #1E293B)',
              borderRadius: '8px',
              color: 'var(--text-main, #F8FAFC)',
              fontSize: '0.84rem',
            }}
          >
            <option value="all">{t('cameras.filterAll', 'All Cameras')}</option>
            <option value="online">{t('cameras.online', 'Online')}</option>
            <option value="offline">{t('cameras.offline', 'Offline')}</option>
            <option value="restricted">{t('cameras.filterRestricted', 'Restricted-Entry Only')}</option>
          </select>
          {!isViewer && (
            <button
              type="button"
              onClick={handleOpenAddModal}
              className="btn btn-primary btn-sm"
              style={{ padding: '9px 16px', fontWeight: 700, borderRadius: '8px' }}
            >
              + {t('cameras.addCamera', 'Add Camera')}
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted, #94A3B8)' }}>
          {t('common.loading', 'Loading...')}
        </div>
      ) : filteredCameras.length === 0 ? (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            backgroundColor: 'var(--bg-surface, #0F172A)',
            border: '1px dashed var(--border-color, #334155)',
            borderRadius: '12px',
          }}
        >
          <p style={{ margin: '0 0 12px', color: 'var(--text-muted, #94A3B8)' }}>
            {t('cameras.emptyState', 'No cameras match the current filter.')}
          </p>
          {!isViewer && (
            <button type="button" onClick={handleOpenAddModal} className="btn btn-primary btn-sm">
              + {t('cameras.addCamera', 'Add Camera')}
            </button>
          )}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '16px',
          }}
        >
          {filteredCameras.map((cam) => {
            const online = cam.status === 'online';
            const isRestricted = Boolean(cam.restricted_entry_enabled || cam.purpose === 'restricted_entry');
            return (
              <div
                key={cam.id}
                style={{
                  backgroundColor: 'var(--bg-surface, #0F172A)',
                  border: `1px solid ${selectedCameraId === cam.id ? 'rgba(0, 229, 255, 0.45)' : 'var(--border-color, #1E293B)'}`,
                  borderRadius: '12px',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span
                        style={{
                          width: '9px',
                          height: '9px',
                          borderRadius: '50%',
                          backgroundColor: online ? '#10B981' : '#64748B',
                          display: 'inline-block',
                        }}
                      />
                      <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--text-main, #F8FAFC)' }}>
                        {cam.name}
                      </h3>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted, #94A3B8)', marginTop: '3px' }}>
                      {cam.location || 'Default Zone'} · {String(cam.source_type || 'camera').toUpperCase()}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                    <span
                      className={`status-pill ${online ? 'status-live' : 'status-offline'}`}
                      style={{ fontSize: '0.7rem', padding: '2px 8px' }}
                    >
                      {online ? t('cameras.online', 'Online') : t('cameras.offline', 'Offline')}
                    </span>
                    {cam.is_recording && (
                      <span style={{ fontSize: '0.68rem', color: '#EF4444', fontWeight: 700 }}>
                        ● {t('cameras.recordingActive', 'REC')}
                      </span>
                    )}
                  </div>
                </div>

                {/* Purpose & Restricted-Entry Summary */}
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '6px',
                    padding: '8px 10px',
                    backgroundColor: 'var(--bg-body, #090D16)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color, #1E293B)',
                    fontSize: '0.74rem',
                  }}
                >
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontWeight: 700,
                      backgroundColor: isRestricted ? 'rgba(239, 68, 68, 0.14)' : 'rgba(56, 189, 248, 0.12)',
                      color: isRestricted ? '#F87171' : '#38BDF8',
                    }}
                  >
                    {isRestricted
                      ? t('cameras.purposeRestricted', 'Restricted-Entry Camera')
                      : t('cameras.purposeGeneral', 'General Monitoring')}
                  </span>
                  <span style={{ color: 'var(--text-muted, #94A3B8)', alignSelf: 'center' }}>
                    {t('cameras.zonesLabel', 'Zones')}: <strong style={{ color: 'var(--text-main, #F8FAFC)' }}>{cam.zone_count || 0}</strong>
                  </span>
                  {isRestricted && (
                    <span style={{ color: 'var(--text-muted, #94A3B8)', alignSelf: 'center' }}>
                      · {String(cam.alert_severity || 'high').toUpperCase()}
                    </span>
                  )}
                </div>

                {/* Card Action Buttons */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: 'auto' }}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCameraId(cam.id);
                      setWorkspaceView('live');
                      setViewMode('tracking');
                    }}
                    className="btn btn-primary btn-sm"
                    style={{ flex: '1 1 120px' }}
                  >
                    {t('cameras.openLive', 'Live View')}
                  </button>
                  {!isViewer && (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCameraId(cam.id);
                          setWorkspaceView('live');
                          setViewMode('tracking');
                          setZoneEditorOpen(true);
                        }}
                        className="btn btn-secondary btn-sm"
                      >
                        {t('cameras.zonesButton', 'Zones')}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleOpenEditModal(cam)}
                        className="btn btn-secondary btn-sm"
                      >
                        {t('common.edit', 'Edit')}
                      </button>
                      <button
                        type="button"
                        onClick={() => (online ? handleDisconnectCamera(cam) : handleReconnectCamera(cam))}
                        className="btn btn-secondary btn-sm"
                      >
                        {online ? t('cameras.disconnect', 'Disconnect') : t('cameras.reconnect', 'Reconnect')}
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteTargetCam(cam)}
                        className="btn btn-secondary btn-sm"
                        style={{ color: '#F87171', borderColor: 'rgba(248, 113, 113, 0.35)' }}
                      >
                        {t('common.remove', 'Remove')}
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  // =========================================================================
  // RENDER: CLEAN LIVE MONITORING VIEW (TWO MODES ONLY)
  // =========================================================================
  const isBrowserStandby = Boolean(
    selectedCam?.source_type === 'browser' &&
      !browserBridgeActive &&
      selectedCam?.status !== 'online'
  );
  const showDirectBrowserVideo = Boolean(selectedCam && browserBridgeActive && isPlaying);
  const streamImgSrc = selectedCam && !isBrowserStandby && !showDirectBrowserVideo
    ? `${api.cameras.getStreamUrl(selectedCam.id, viewMode)}&t=${streamTimestamp}`
    : '';
  const displayViewportSrc = showDirectBrowserVideo ? '' : (snapshotUrl || streamImgSrc);
  const showOverlays = viewMode === 'tracking';

  const renderLiveMonitor = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Bar: Back + Camera Selector + Exact 2 Mode Buttons + Backend Label */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          padding: '12px 16px',
          backgroundColor: 'var(--bg-surface, #0F172A)',
          border: '1px solid var(--border-color, #1E293B)',
          borderRadius: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => {
              setZoneEditorOpen(false);
              setWorkspaceView('management');
            }}
            className="btn btn-secondary btn-sm"
          >
            ← {t('cameras.backToManagement', 'All Cameras')}
          </button>

          <select
            value={selectedCam?.id || ''}
            onChange={(e) => setSelectedCameraId(Number(e.target.value))}
            aria-label="Select Active Camera"
            style={{
              padding: '7px 12px',
              backgroundColor: 'var(--bg-body, #090D16)',
              border: '1px solid var(--border-color, #1E293B)',
              borderRadius: '8px',
              color: 'var(--text-main, #F8FAFC)',
              fontSize: '0.86rem',
              fontWeight: 600,
            }}
          >
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.location || 'Default'})
              </option>
            ))}
          </select>

          <span
            className={`status-pill ${isCameraLive ? 'status-live' : 'status-offline'}`}
            style={{ fontSize: '0.72rem', padding: '3px 10px' }}
          >
            {isCameraLive ? t('cameras.online', 'Online') : t('cameras.offline', 'Offline')}
          </span>

          {selectedCam?.restricted_entry_enabled && (
            <span
              style={{
                padding: '3px 10px',
                borderRadius: '999px',
                fontSize: '0.72rem',
                fontWeight: 700,
                backgroundColor: 'rgba(239, 68, 68, 0.16)',
                color: '#F87171',
                border: '1px solid rgba(239, 68, 68, 0.35)',
              }}
            >
              {t('cameras.purposeRestrictedBadge', 'Restricted-Entry Camera')}
            </span>
          )}
        </div>

        {/* EXACT TWO OPERATING MODES */}
        <div
          role="tablist"
          aria-label="Camera Operating Modes"
          style={{
            display: 'inline-flex',
            backgroundColor: 'var(--bg-body, #090D16)',
            padding: '4px',
            borderRadius: '8px',
            border: '1px solid var(--border-color, #1E293B)',
            gap: '4px',
          }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'raw'}
            onClick={() => handleSwitchMode('raw')}
            data-testid="mode-raw-btn"
            style={{
              padding: '7px 14px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.78rem',
              fontWeight: 700,
              letterSpacing: '0.03em',
              backgroundColor: viewMode === 'raw' ? '#0891B2' : 'transparent',
              color: viewMode === 'raw' ? '#FFFFFF' : 'var(--text-muted, #94A3B8)',
            }}
          >
            {t('cameras.modeRaw', 'RAW CAMERA FOOTAGE')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'tracking'}
            onClick={() => handleSwitchMode('tracking')}
            data-testid="mode-tracking-btn"
            style={{
              padding: '7px 14px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.78rem',
              fontWeight: 700,
              letterSpacing: '0.03em',
              backgroundColor: viewMode === 'tracking' ? '#0891B2' : 'transparent',
              color: viewMode === 'tracking' ? '#FFFFFF' : 'var(--text-muted, #94A3B8)',
            }}
          >
            {t('cameras.modeTracking', 'DETECTION & TRACKING')}
          </button>
        </div>

        {/* Honest AI Backend & Explicit Speed/Accuracy Profile */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span
            style={{
              fontSize: '0.74rem',
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: '6px',
              backgroundColor:
                String(detectorBackend || '').startsWith('yolo')
                  ? 'rgba(16, 185, 129, 0.14)'
                  : detectorBackend === 'opencv_fallback'
                  ? 'rgba(245, 158, 11, 0.14)'
                  : 'rgba(100, 116, 139, 0.16)',
              color:
                String(detectorBackend || '').startsWith('yolo')
                  ? '#34D399'
                  : detectorBackend === 'opencv_fallback'
                  ? '#FBBF24'
                  : 'var(--text-muted, #94A3B8)',
              border: '1px solid rgba(148, 163, 184, 0.25)',
            }}
          >
            AI: {viewMode === 'raw' ? t('cameras.rawNoOverlay', 'Raw Passthrough') : backendBadgeLabel}
          </span>
          {viewMode === 'tracking' && !isViewer && (
            <select
              aria-label="AI Model Profile"
              value={aiProfile}
              disabled={switchingProfile}
              onChange={(e) => handleSwitchAiProfile(e.target.value)}
              title="YOLO26s provides higher accuracy; YOLO26n runs ~3.3x faster on single-vCPU cloud hosts"
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                backgroundColor: 'var(--bg-body, #090D16)',
                border: '1px solid var(--border-color, #1E293B)',
                color: 'var(--text-main, #F8FAFC)',
                fontSize: '0.72rem',
                fontWeight: 600,
                cursor: switchingProfile ? 'wait' : 'pointer',
              }}
            >
              <option value="lightweight">YOLO26n (Real-Time 30 FPS)</option>
              <option value="balanced">YOLO26s (High Accuracy)</option>
            </select>
          )}
        </div>
      </div>

      {/* Main Split: Left Video + Bottom Controls | Right Telemetry & Zone Config (responsive wrap) */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px',
          alignItems: 'flex-start',
        }}
      >
        {/* Video Viewport + Controls Column */}
        <div
          style={{
            flex: '1 1 600px',
            minWidth: 0,
            backgroundColor: 'var(--bg-surface, #0F172A)',
            border: '1px solid var(--border-color, #1E293B)',
            borderRadius: '12px',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            ref={viewportContainerRef}
            style={{
              position: 'relative',
              width: '100%',
              aspectRatio: '16 / 9',
              backgroundColor: '#020617',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {/* Direct 30 FPS local browser video element when Browser Webcam Bridge is active (~0ms local display latency); hidden 1x1 otherwise */}
            <video
              ref={browserVideoRef}
              muted
              playsInline
              style={
                showDirectBrowserVideo
                  ? {
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain',
                      display: 'block',
                      backgroundColor: '#020617',
                    }
                  : {
                      position: 'absolute',
                      width: '1px',
                      height: '1px',
                      opacity: 0,
                      pointerEvents: 'none',
                    }
              }
            />

            {/* Synchronized Real-Time SVG Tracking HUD when viewing local Browser Video in Detection & Tracking mode */}
            {showDirectBrowserVideo && showOverlays && (
              <svg
                viewBox={`0 0 ${Math.max(320, browserVideoDims.w || 1280)} ${Math.max(180, browserVideoDims.h || 720)}`}
                preserveAspectRatio="xMidYMid meet"
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  zIndex: 4,
                }}
              >
                {activeTracksList.map((trk, idx) => {
                  const box = Array.isArray(trk.bbox) ? trk.bbox : null;
                  if (!box || box.length < 4) return null;
                  const [x1, y1, x2, y2] = box.map((v) => Number(v) || 0);
                  const w = Math.max(8, x2 - x1);
                  const h = Math.max(8, y2 - y1);
                  const clsLower = String(trk.class_name || '').toLowerCase();
                  const isAlertBehav = trk.behavior && trk.behavior !== 'normal' && trk.behavior !== 'walking' && trk.behavior !== 'standing';
                  const color = isAlertBehav ? '#EF4444' : (clsLower === 'person' ? '#10B981' : '#38BDF8');
                  const confPct = typeof trk.confidence === 'number' ? ` ${Math.round(trk.confidence * 100)}%` : '';
                  const label = `${trk.class_name || 'Obj'} ${trk.track_id || ''}${confPct}`.trim();
                  const labelW = Math.max(70, label.length * 8 + 14);
                  const labelY = Math.max(18, y1 - 4);
                  return (
                    <g key={`${trk.track_id || idx}`}>
                      <rect
                        x={x1}
                        y={y1}
                        width={w}
                        height={h}
                        fill="none"
                        stroke={color}
                        strokeWidth={2.5}
                        rx={3}
                      />
                      <rect
                        x={x1}
                        y={Math.max(0, labelY - 18)}
                        width={labelW}
                        height={20}
                        fill={color}
                        fillOpacity={0.85}
                        rx={3}
                      />
                      <text
                        x={x1 + 6}
                        y={Math.max(14, labelY - 4)}
                        fill="#FFFFFF"
                        fontSize={12}
                        fontWeight={700}
                        fontFamily="system-ui, -apple-system, sans-serif"
                      >
                        {label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}

            {selectedCam ? (
              !showDirectBrowserVideo && (
                <img
                  ref={liveStreamImgRef}
                  key={`${selectedCam.id}-${viewMode}-${streamTimestamp}`}
                  src={isPlaying && displayViewportSrc ? displayViewportSrc : undefined}
                  alt={`${selectedCam.name} ${viewMode}`}
                  onLoad={() => {
                    if (!snapshotUrl) {
                      mjpegFailCountRef.current = 0;
                      setStreamLoaded(true);
                    }
                    setStreamError(false);
                  }}
                  onError={() => {
                    if (!snapshotUrl && displayViewportSrc) {
                      mjpegFailCountRef.current += 1;
                      setStreamLoaded(false);
                      setStreamError(true);
                    }
                  }}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    display: displayViewportSrc ? 'block' : 'none',
                    backgroundColor: '#020617',
                  }}
                />
              )
            ) : (
              <div style={{ color: '#94A3B8' }}>{t('cameras.noCameraSelected', 'Select or register a camera')}</div>
            )}

            {/* Restricted-Zone Polygon/Rectangle Interactive Editor Overlay (NEVER shown in RAW mode) */}
            {showOverlays && (
              <RestrictedZoneEditor
                active={zoneEditorOpen}
                zones={zones}
                activeIntrusions={activeIntrusions}
                editingZone={editingZone}
                drawTool={drawTool}
                draftPoints={draftPoints}
                setDraftPoints={setDraftPoints}
                onEditZoneVertices={handleEditZoneVertices}
                showZones={zoneEditorOpen || showDirectBrowserVideo}
              />
            )}

            {(isBrowserStandby || (browserError && !browserBridgeActive)) && !snapshotUrl && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  backgroundColor: 'rgba(2, 6, 23, 0.88)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                  padding: '24px',
                  textAlign: 'center',
                  zIndex: 8,
                }}
              >
                <p style={{ margin: 0, color: browserError ? '#FCA5A5' : '#E2E8F0', fontSize: '0.92rem', fontWeight: 600 }}>
                  {browserError || 'Browser Webcam Ready — grant camera access to start live capture and AI tracking.'}
                </p>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <button type="button" onClick={() => handleStartBrowserBridge(selectedCam)} className="btn btn-primary btn-sm">
                    {browserError ? 'Retry Browser Webcam' : 'Start Browser Webcam'}
                  </button>
                </div>
              </div>
            )}

            {!isBrowserStandby && !browserError && streamError && !snapshotUrl && !browserBridgeActive && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  backgroundColor: 'rgba(2, 6, 23, 0.86)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                  padding: '24px',
                  textAlign: 'center',
                  zIndex: 8,
                }}
              >
                <p style={{ margin: 0, color: '#E2E8F0', fontSize: '0.92rem', fontWeight: 600 }}>
                  {t('cameras.streamUnavailable', 'Live camera stream is currently offline or unreachable.')}
                </p>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <button type="button" onClick={() => handleReconnectCamera(selectedCam)} className="btn btn-primary btn-sm">
                    {t('cameras.reconnect', 'Reconnect Camera')}
                  </button>
                  <button type="button" onClick={() => handleStartBrowserBridge(selectedCam)} className="btn btn-secondary btn-sm">
                    {t('cameras.useBrowserCam', 'Use Browser Webcam')}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Clean High-Contrast Bottom Control Bar */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '10px',
              padding: '10px 14px',
              backgroundColor: 'var(--bg-body, #090D16)',
              borderTop: '1px solid var(--border-color, #1E293B)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => setIsPlaying((p) => !p)}
                className="btn btn-secondary btn-sm"
                title={isPlaying ? 'Pause' : 'Resume'}
              >
                {isPlaying ? t('cameras.pause', 'Pause') : t('cameras.resume', 'Resume')}
              </button>
              <button
                type="button"
                onClick={() => setIsMuted((m) => !m)}
                className="btn btn-secondary btn-sm"
                title="Toggle Audio Mute"
              >
                {isMuted ? t('cameras.muted', 'Muted') : t('cameras.audioOn', 'Audio On')}
              </button>
              <button
                type="button"
                onClick={handleCaptureSnapshot}
                disabled={!selectedCam || isCapturingSnapshot}
                className="btn btn-secondary btn-sm"
              >
                {isCapturingSnapshot ? t('common.saving', 'Saving...') : t('cameras.snapshot', 'Snapshot')}
              </button>
              <button
                type="button"
                onClick={handleToggleRecording}
                disabled={!selectedCam || isRecordingBusy}
                className="btn btn-secondary btn-sm"
                style={
                  isRecording
                    ? { backgroundColor: 'rgba(239, 68, 68, 0.2)', color: '#F87171', borderColor: '#EF4444' }
                    : undefined
                }
              >
                {isRecording ? t('cameras.stopRecord', 'Stop Rec') : t('cameras.startRecord', 'Record')}
              </button>
              <button
                type="button"
                onClick={() => handleReconnectCamera(selectedCam)}
                disabled={isReconnecting}
                className="btn btn-secondary btn-sm"
              >
                {t('cameras.reconnect', 'Reconnect')}
              </button>
              {viewMode === 'tracking' && (
                <button
                  type="button"
                  onClick={() => setZoneEditorOpen((z) => !z)}
                  className={zoneEditorOpen ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                >
                  {zoneEditorOpen ? t('cameras.closeZoneEditor', 'Close Zone Editor') : t('cameras.editZones', 'Edit Zones')}
                </button>
              )}
              <button type="button" onClick={handleToggleFullscreen} className="btn btn-secondary btn-sm">
                {t('cameras.fullscreen', 'Fullscreen')}
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)', fontFamily: 'var(--font-mono, monospace)', flexWrap: 'wrap' }}>
              {liveResolution && (
                <span title={`Active stream codec: ${liveFourcc || 'JPEG'}`}>
                  <strong style={{ color: 'var(--dv-cyan-400, #22D3EE)' }}>{liveResolution}</strong>{liveFourcc ? ` · ${liveFourcc}` : ''}
                </span>
              )}
              {selectedCam && (
                <select
                  aria-label="Stream Video Quality"
                  disabled={switchingQuality}
                  value={selectedCam.video_quality || 'high'}
                  onChange={async (e) => {
                    const nextQ = e.target.value;
                    if (!selectedCam?.id) return;
                    try {
                      setSwitchingQuality(true);
                      await api.cameras.update(selectedCam.id, { video_quality: nextQ });
                      setCameras((prev) => prev.map((c) => (c.id === selectedCam.id ? { ...c, video_quality: nextQ } : c)));
                      setStreamTimestamp(Date.now());
                      addToast(`Video quality set to ${QUALITY_SETTINGS_MAP[nextQ]?.label || nextQ}.`, 'success');
                    } catch (err) {
                      addToast(err?.message || 'Unable to change video quality.', 'error');
                    } finally {
                      setSwitchingQuality(false);
                    }
                  }}
                  style={{
                    backgroundColor: 'var(--bg-surface, #0F172A)',
                    color: 'var(--text-main, #F8FAFC)',
                    border: '1px solid var(--border-color, #1E293B)',
                    borderRadius: '6px',
                    padding: '2px 6px',
                    fontSize: '0.72rem',
                  }}
                >
                  <option value="standard">Quality: Standard (480p)</option>
                  <option value="high">Quality: High HD (720p)</option>
                  <option value="full">Quality: Full Source (Up to 1080p)</option>
                </select>
              )}
              {showDirectBrowserVideo && (
                <span title="Measured local <video> paint cadence">
                  Disp: <strong style={{ color: '#10B981' }}>{displayFps || 0} FPS</strong>
                </span>
              )}
              <span>{t('cameras.fpsShort', 'Cap FPS')}: <strong style={{ color: 'var(--text-main, #F8FAFC)' }}>{measuredFps || 0}</strong></span>
              {viewMode === 'tracking' && (
                <>
                  <span>{t('cameras.aiFpsShort', 'AI FPS')}: <strong style={{ color: 'var(--text-main, #F8FAFC)' }}>{measuredAiFps || 0}</strong></span>
                  <span title={`P50: ${p50LatencyMs || latencyMs || 0}ms | P95: ${p95LatencyMs || latencyMs || 0}ms | Frame Age: ${frameAgeMs || 0}ms`}>
                    {t('cameras.latencyShort', 'Lat')}: <strong style={{ color: 'var(--text-main, #F8FAFC)' }}>{latencyMs || 0}ms</strong>
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right Telemetry & Restricted-Zone Side Panel */}
        <div style={{ flex: '1 1 320px', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {viewMode === 'raw' ? (
            <div
              style={{
                padding: '18px',
                backgroundColor: 'var(--bg-surface, #0F172A)',
                border: '1px solid var(--border-color, #1E293B)',
                borderRadius: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '0.96rem', color: 'var(--text-main, #F8FAFC)' }}>
                {t('cameras.rawPanelTitle', 'Raw Camera Footage Mode')}
              </h3>
              <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-muted, #94A3B8)', lineHeight: 1.5 }}>
                {t('cameras.rawPanelDesc', 'Displaying clean unannotated camera feed with zero AI bounding boxes or overlays. Switch to Detection & Tracking mode to view live detections, tracking IDs, counts, and restricted-zone monitoring.')}
              </p>
              <button type="button" onClick={() => handleSwitchMode('tracking')} className="btn btn-primary btn-sm">
                {t('cameras.switchToTracking', 'Switch to Detection & Tracking')}
              </button>
            </div>
          ) : (
            <>
              {/* 4 Strictly Separated Counts */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                  gap: '10px',
                }}
              >
                {[
                  { label: t('cameras.visiblePersons', 'Visible Persons'), value: visiblePersonsCount, accent: '#10B981', hint: 'Currently in frame' },
                  { label: t('cameras.activeTracks', 'Active Tracks'), value: activeTracksCount, accent: '#38BDF8', hint: 'Confirmed IDs now' },
                  { label: t('cameras.uniqueObserved', 'Unique Observed'), value: uniquePersonsObserved, accent: '#A855F7', hint: 'Distinct in session' },
                  { label: t('cameras.detectionEvents', 'Detection Events'), value: totalDetectionEvents, accent: '#F59E0B', hint: 'Session object logs' },
                ].map((metric) => (
                  <div
                    key={metric.label}
                    style={{
                      padding: '12px',
                      backgroundColor: 'var(--bg-surface, #0F172A)',
                      border: '1px solid var(--border-color, #1E293B)',
                      borderRadius: '10px',
                    }}
                  >
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted, #94A3B8)', fontWeight: 600 }}>{metric.label}</div>
                    <div style={{ fontSize: '1.45rem', fontWeight: 800, color: metric.accent, lineHeight: 1.2, marginTop: '4px' }}>
                      {metric.value}
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted, #64748B)', marginTop: '2px' }}>{metric.hint}</div>
                  </div>
                ))}
              </div>

              {/* Zone Editor & Zones Manager */}
              <div
                style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface, #0F172A)',
                  border: `1px solid ${zoneEditorOpen ? '#0891B2' : 'var(--border-color, #1E293B)'}`,
                  borderRadius: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-main, #F8FAFC)' }}>
                    {t('cameras.restrictedZonesTitle', 'Restricted Zones')} ({zones.length})
                  </h4>
                  <button
                    type="button"
                    onClick={() => setZoneEditorOpen((z) => !z)}
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.72rem', padding: '4px 10px' }}
                  >
                    {zoneEditorOpen ? t('common.done', 'Done') : t('cameras.drawZone', 'Draw / Edit')}
                  </button>
                </div>

                {zoneEditorOpen && (
                  <form onSubmit={handleSaveZone} style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '10px', backgroundColor: 'var(--bg-body, #090D16)', borderRadius: '8px' }}>
                    {!editingZone && (
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          type="button"
                          onClick={() => { setDrawTool('polygon'); setDraftPoints([]); }}
                          className={drawTool === 'polygon' ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                          style={{ flex: 1, fontSize: '0.72rem' }}
                        >
                          Polygon ({draftPoints.length} pts)
                        </button>
                        <button
                          type="button"
                          onClick={() => { setDrawTool('rectangle'); setDraftPoints([]); }}
                          className={drawTool === 'rectangle' ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'}
                          style={{ flex: 1, fontSize: '0.72rem' }}
                        >
                          Rectangle
                        </button>
                      </div>
                    )}

                    <input
                      type="text"
                      value={editingZone ? editingZone.name : newZoneName}
                      onChange={(e) =>
                        editingZone
                          ? setEditingZone({ ...editingZone, name: e.target.value })
                          : setNewZoneName(e.target.value)
                      }
                      placeholder={t('cameras.zoneNamePlaceholder', 'Zone name (e.g. Vault Gate)')}
                      style={{
                        padding: '7px 10px',
                        backgroundColor: 'var(--bg-surface, #0F172A)',
                        border: '1px solid var(--border-color, #1E293B)',
                        borderRadius: '6px',
                        color: 'var(--text-main, #F8FAFC)',
                        fontSize: '0.8rem',
                      }}
                    />

                    <select
                      value={editingZone ? editingZone.entry_direction || 'enter' : newZoneDirection}
                      onChange={(e) =>
                        editingZone
                          ? setEditingZone({ ...editingZone, entry_direction: e.target.value })
                          : setNewZoneDirection(e.target.value)
                      }
                      aria-label="Zone Entry Direction"
                      style={{
                        padding: '7px 10px',
                        backgroundColor: 'var(--bg-surface, #0F172A)',
                        border: '1px solid var(--border-color, #1E293B)',
                        borderRadius: '6px',
                        color: 'var(--text-main, #F8FAFC)',
                        fontSize: '0.78rem',
                      }}
                    >
                      <option value="enter">{t('cameras.dirTriggerEntry', 'Trigger on Entry')}</option>
                      <option value="any">{t('cameras.dirAnyCrossing', 'Any Crossing')}</option>
                      <option value="exit">{t('cameras.dirTriggerExit', 'Trigger on Exit')}</option>
                      <option value="left_to_right">{t('cameras.dirLeftToRight', 'Left to Right')}</option>
                      <option value="right_to_left">{t('cameras.dirRightToLeft', 'Right to Left')}</option>
                    </select>

                    <div style={{ display: 'flex', gap: '6px' }}>
                      {editingZone ? (
                        <button type="button" onClick={() => setEditingZone(null)} className="btn btn-secondary btn-sm" style={{ flex: 1 }}>
                          Cancel Edit
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => setDraftPoints((p) => p.slice(0, -1))}
                            disabled={draftPoints.length === 0}
                            className="btn btn-secondary btn-sm"
                          >
                            Undo Point
                          </button>
                          <button
                            type="button"
                            onClick={() => setDraftPoints([])}
                            disabled={draftPoints.length === 0}
                            className="btn btn-secondary btn-sm"
                          >
                            Clear
                          </button>
                        </>
                      )}
                      <button type="submit" disabled={isZoneBusy} className="btn btn-primary btn-sm" style={{ flex: 1 }}>
                        {isZoneBusy ? 'Saving...' : editingZone ? 'Save Changes' : 'Save Zone'}
                      </button>
                    </div>
                  </form>
                )}

                {zones.length === 0 ? (
                  <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)' }}>
                    {t('cameras.noZonesConfigured', 'No restricted zones configured on this camera yet.')}
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto' }}>
                    {zones.map((z) => (
                      <div
                        key={z.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '7px 9px',
                          backgroundColor: 'var(--bg-body, #090D16)',
                          borderRadius: '6px',
                          border: `1px solid ${activeIntrusions.includes(z.id) ? '#EF4444' : 'var(--border-color, #1E293B)'}`,
                          fontSize: '0.76rem',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 700, color: 'var(--text-main, #F8FAFC)' }}>{z.name}</div>
                          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted, #94A3B8)' }}>
                            {z.shape === 'polygon' ? `Polygon (${z.points?.length || 0} pts)` : 'Rectangle'} · {z.enabled ? 'Active' : 'Paused'}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          {zoneEditorOpen && (
                            <button
                              type="button"
                              onClick={() => setEditingZone(z)}
                              className="btn btn-secondary btn-sm"
                              style={{ padding: '2px 7px', fontSize: '0.68rem' }}
                            >
                              Vertices
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleToggleRestrictedZone(z.id)}
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '2px 7px', fontSize: '0.68rem' }}
                          >
                            {z.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteRestrictedZone(z.id)}
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '2px 7px', fontSize: '0.68rem', color: '#F87171' }}
                          >
                            Del
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Active Tracked Objects */}
              <div
                style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface, #0F172A)',
                  border: '1px solid var(--border-color, #1E293B)',
                  borderRadius: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-main, #F8FAFC)' }}>
                    {t('cameras.clipSceneTitle', 'Scene Understanding (CLIP)')}
                  </h4>
                  <button
                    type="button"
                    disabled={analyzingScene || !isCameraLive}
                    onClick={async () => {
                      if (!selectedCam?.id) return;
                      try {
                        setAnalyzingScene(true);
                        const res = await api.cameras.analyzeScene(selectedCam.id);
                        if (res?.scene) setClipScene(res.scene);
                        addToast(res?.scene?.top_description ? `CLIP: ${res.scene.top_description}` : 'CLIP scene check updated.', 'success');
                      } catch (err) {
                        addToast(err?.message || 'CLIP scene analysis unavailable.', 'warning');
                      } finally {
                        setAnalyzingScene(false);
                      }
                    }}
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: '0.68rem', padding: '3px 8px' }}
                  >
                    {analyzingScene ? 'Analyzing...' : 'Analyze Frame'}
                  </button>
                </div>
                {!clipScene || !clipScene.analyzed ? (
                  <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted, #94A3B8)' }}>
                    {clipScene?.status === 'disabled_by_config'
                      ? 'CLIP scene analysis is disabled by server configuration.'
                      : clipScene?.status === 'unavailable_missing_runtime' || clipScene?.status === 'unavailable'
                        ? 'CLIP runtime unavailable on this host.'
                        : 'Awaiting next scheduled CLIP frame evaluation...'}
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                      <strong style={{ color: clipScene.matched ? '#38BDF8' : 'var(--text-main, #F8FAFC)' }}>
                        {clipScene.matched_description || clipScene.top_description}
                      </strong>
                      <span style={{ fontFamily: 'var(--font-mono)', color: '#10B981' }}>
                        cos {Number(clipScene.top_cosine_similarity ?? 0).toFixed(3)}
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-muted, #94A3B8)', fontSize: '0.69rem' }}>
                      {clipScene.model_name} · {clipScene.device} · {clipScene.inference_ms} ms (uncalibrated cosine similarity)
                    </div>
                  </div>
                )}
              </div>

              <div
                style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface, #0F172A)',
                  border: '1px solid var(--border-color, #1E293B)',
                  borderRadius: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <h4 style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-main, #F8FAFC)' }}>
                  {t('cameras.activeTracksList', 'Live Tracked Subjects')} ({activeTracksList.length})
                </h4>
                {activeTracksList.length === 0 ? (
                  <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)' }}>
                    {t('cameras.noActiveSubjects', 'No confirmed subjects in frame right now.')}
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                    {activeTracksList.slice(0, 8).map((trk, i) => (
                      <div
                        key={`${trk.track_id}-${i}`}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          fontSize: '0.76rem',
                          padding: '6px 8px',
                          backgroundColor: 'var(--bg-body, #090D16)',
                          borderRadius: '6px',
                        }}
                      >
                        <span style={{ fontWeight: 700, color: '#38BDF8' }}>
                          {trk.track_id} · {trk.class_name}
                        </span>
                        <span style={{ color: 'var(--text-muted, #94A3B8)' }}>
                          {Math.round((trk.confidence || 0) * 100)}% · {trk.behavior || 'normal'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Restricted-Zone Events & Recent Camera Alerts */}
              <div
                style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface, #0F172A)',
                  border: '1px solid var(--border-color, #1E293B)',
                  borderRadius: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <h4 style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-main, #F8FAFC)' }}>
                  {t('cameras.zoneEventsTitle', 'Restricted-Zone & Security Events')}
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '180px', overflowY: 'auto' }}>
                  {recentZoneEvents.length === 0 && cameraAlerts.length === 0 ? (
                    <p style={{ margin: 0, fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)' }}>
                      {t('cameras.noRecentZoneEvents', 'No security or zone boundary events triggered yet.')}
                    </p>
                  ) : (
                    <>
                      {recentZoneEvents.slice(0, 5).map((ev, idx) => (
                        <div
                          key={`zv-${idx}`}
                          style={{
                            padding: '6px 8px',
                            borderRadius: '6px',
                            backgroundColor: ev.event_type === 'restricted_area_entry' ? 'rgba(239,68,68,0.12)' : 'var(--bg-body, #090D16)',
                            borderLeft: `3px solid ${ev.event_type === 'restricted_area_entry' ? '#EF4444' : '#38BDF8'}`,
                            fontSize: '0.74rem',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: 'var(--text-main, #F8FAFC)' }}>
                            {ev.event_type === 'restricted_area_entry' ? 'Security Alert: Zone Entry' : 'Zone Exit'} · {ev.zone_name || 'Zone'}
                          </div>
                          <div style={{ color: 'var(--text-muted, #94A3B8)', fontSize: '0.7rem' }}>
                            {ev.explanation || ev.message} · {formatTimeShort(ev.timestamp)}
                          </div>
                        </div>
                      ))}
                      {recentZoneEvents.length === 0 && cameraAlerts.slice(0, 5).map((al) => (
                        <div
                          key={`al-${al.id}`}
                          style={{
                            padding: '6px 8px',
                            borderRadius: '6px',
                            backgroundColor: 'var(--bg-body, #090D16)',
                            borderLeft: `3px solid ${al.severity === 'critical' || al.severity === 'high' ? '#EF4444' : '#F59E0B'}`,
                            fontSize: '0.74rem',
                          }}
                        >
                          <div style={{ fontWeight: 700, color: 'var(--text-main, #F8FAFC)' }}>
                            {al.title || al.event_type}
                          </div>
                          <div style={{ color: 'var(--text-muted, #94A3B8)', fontSize: '0.7rem' }}>
                            {String(al.severity || '').toUpperCase()} · {formatTimeShort(al.detected_at)}
                          </div>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  // =========================================================================
  // MODALS: ADD/EDIT CAMERA (WITH RESTRICTED-ENTRY CONFIG) & DELETE CONFIRM
  // =========================================================================
  const renderCameraModal = () => (
    <Modal
      isOpen={isAddModalOpen}
      onClose={() => setIsAddModalOpen(false)}
      title={editingCamId ? t('cameras.editCameraTitle', 'Edit Camera & Monitoring Policy') : t('cameras.addCameraTitle', 'Register New Camera')}
      maxWidth="580px"
    >
        <form onSubmit={handleAddCameraSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                {t('cameras.nameLabel', 'Camera Name *')}
              </label>
              <input
                required
                type="text"
                value={newCam.name}
                onChange={(e) => setNewCam({ ...newCam, name: e.target.value })}
                placeholder="e.g. Gate-1 Entrance"
                style={{ width: '100%', padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                {t('cameras.locationLabel', 'Location / Area')}
              </label>
              <input
                type="text"
                value={newCam.location}
                onChange={(e) => setNewCam({ ...newCam, location: e.target.value })}
                placeholder="e.g. Server Room"
                style={{ width: '100%', padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                {t('cameras.sourceTypeLabel', 'Source Type')}
              </label>
              <select
                value={newCam.source_type}
                onChange={(e) => setNewCam({ ...newCam, source_type: e.target.value })}
                style={{ width: '100%', padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              >
                <option value="browser">{t('cameras.srcBrowser', 'Browser Webcam (Client)')}</option>
                <option value="webcam">{t('cameras.srcWebcam', 'Local USB / Built-In Webcam (0)')}</option>
                <option value="phone">{t('cameras.srcPhone', 'Phone / IP Camera (HTTP MJPEG)')}</option>
                <option value="rtsp">{t('cameras.srcRtsp', 'RTSP Network Camera')}</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                {t('cameras.sourceLabel', 'Source / Stream URL')}
              </label>
              <input
                type="text"
                value={newCam.source}
                onChange={(e) => setNewCam({ ...newCam, source: e.target.value })}
                placeholder={newCam.source_type === 'webcam' ? '0' : 'http://... or 0'}
                style={{ width: '100%', padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              />
            </div>
          </div>

          {(newCam.source_type === 'rtsp' || newCam.source_type === 'phone') && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <input
                type="text"
                value={newCam.username}
                onChange={(e) => setNewCam({ ...newCam, username: e.target.value })}
                placeholder="Stream username (optional)"
                style={{ padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              />
              <input
                type="password"
                value={newCam.password}
                onChange={(e) => setNewCam({ ...newCam, password: e.target.value })}
                placeholder="Stream password (optional)"
                style={{ padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
              />
            </div>
          )}

          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary, #94A3B8)', marginBottom: '4px' }}>
              {t('cameras.videoQualityLabel', 'Capture & Stream Video Quality')}
            </label>
            <select
              value={newCam.video_quality || 'high'}
              onChange={(e) => setNewCam({ ...newCam, video_quality: e.target.value })}
              style={{ width: '100%', padding: '8px 10px', backgroundColor: 'var(--bg-body, #090D16)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '8px', color: 'var(--text-main, #F8FAFC)' }}
            >
              <option value="standard">Standard (480p — Lowest Bandwidth)</option>
              <option value="high">High HD (720p — Recommended Balanced Clarity & FPS)</option>
              <option value="full">Full Resolution / Source Quality (Native up to 1080p)</option>
            </select>
          </div>

          {/* Restricted-Entry Camera Registration Configuration */}
          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--bg-body, #090D16)',
              border: `1px solid ${newCam.restricted_entry_enabled ? 'rgba(239, 68, 68, 0.45)' : 'var(--border-color, #1E293B)'}`,
              borderRadius: '10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 700, fontSize: '0.86rem', color: 'var(--text-main, #F8FAFC)' }}>
              <input
                type="checkbox"
                checked={newCam.restricted_entry_enabled}
                onChange={(e) => setNewCam({ ...newCam, restricted_entry_enabled: e.target.checked })}
                data-testid="toggle-restricted-entry"
                style={{ width: '16px', height: '16px', accentColor: '#EF4444' }}
              />
              <span>{t('cameras.enableRestrictedEntry', 'Enable Restricted-Entry Monitoring')}</span>
            </label>

            {newCam.restricted_entry_enabled && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', paddingTop: '4px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.74rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                      {t('cameras.entryDirectionLabel', 'Allowed / Trigger Direction')}
                    </label>
                    <select
                      value={newCam.entry_direction}
                      onChange={(e) => setNewCam({ ...newCam, entry_direction: e.target.value })}
                      style={{ width: '100%', padding: '7px 9px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)', fontSize: '0.8rem' }}
                    >
                      <option value="enter">{t('cameras.dirTriggerZoneEntry', 'Trigger on Zone Entry')}</option>
                      <option value="any">{t('cameras.dirAnyPerimeter', 'Any Perimeter Crossing')}</option>
                      <option value="exit">{t('cameras.dirTriggerZoneExit', 'Trigger on Zone Exit')}</option>
                      <option value="left_to_right">{t('cameras.dirLeftToRight', 'Left to Right')}</option>
                      <option value="right_to_left">{t('cameras.dirRightToLeft', 'Right to Left')}</option>
                      <option value="top_to_bottom">{t('cameras.dirTopToBottom', 'Top to Bottom')}</option>
                      <option value="bottom_to_top">{t('cameras.dirBottomToTop', 'Bottom to Top')}</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.74rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                      {t('cameras.alertSeverityLabel', 'Default Alert Severity')}
                    </label>
                    <select
                      value={newCam.alert_severity}
                      onChange={(e) => setNewCam({ ...newCam, alert_severity: e.target.value })}
                      style={{ width: '100%', padding: '7px 9px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)', fontSize: '0.8rem' }}
                    >
                      <option value="critical">{t('severity.critical', 'Critical')}</option>
                      <option value="high">{t('severity.high', 'High')}</option>
                      <option value="medium">{t('severity.medium', 'Medium')}</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                    {t('cameras.scheduleLabel', 'Active Monitoring Schedule')}
                  </label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <select
                      value={newCam.schedule_mode}
                      onChange={(e) => setNewCam({ ...newCam, schedule_mode: e.target.value })}
                      style={{ padding: '6px 9px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)', fontSize: '0.78rem' }}
                    >
                      <option value="always">{t('cameras.schedAlways', 'Always Active (24/7)')}</option>
                      <option value="custom">{t('cameras.schedCustom', 'Custom Time Window')}</option>
                    </select>
                    {newCam.schedule_mode === 'custom' && (
                      <>
                        <input
                          type="time"
                          value={newCam.schedule_start}
                          onChange={(e) => setNewCam({ ...newCam, schedule_start: e.target.value })}
                          style={{ padding: '5px 8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)' }}
                        />
                        <span style={{ color: 'var(--text-muted, #94A3B8)' }}>{t('common.to', 'to')}</span>
                        <input
                          type="time"
                          value={newCam.schedule_end}
                          onChange={(e) => setNewCam({ ...newCam, schedule_end: e.target.value })}
                          style={{ padding: '5px 8px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)' }}
                        />
                      </>
                    )}
                  </div>
                  {newCam.schedule_mode === 'custom' && (
                    <div style={{ display: 'flex', gap: '4px', marginTop: '6px', flexWrap: 'wrap' }}>
                      {DAY_LABELS.map((lbl, idx) => {
                        const checked = newCam.schedule_days.includes(idx);
                        return (
                          <button
                            key={lbl}
                            type="button"
                            onClick={() => {
                              const next = checked
                                ? newCam.schedule_days.filter((d) => d !== idx)
                                : [...newCam.schedule_days, idx].sort();
                              setNewCam({ ...newCam, schedule_days: next.length ? next : [idx] });
                            }}
                            style={{
                              padding: '3px 8px',
                              fontSize: '0.7rem',
                              borderRadius: '4px',
                              border: '1px solid var(--border-color, #1E293B)',
                              cursor: 'pointer',
                              backgroundColor: checked ? '#0891B2' : 'var(--bg-surface, #0F172A)',
                              color: checked ? '#FFFFFF' : 'var(--text-muted, #94A3B8)',
                            }}
                          >
                            {lbl}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.74rem', color: 'var(--text-muted, #94A3B8)', marginBottom: '4px' }}>
                    {t('cameras.recipientsLabel', 'Notification Email Recipients (comma-separated)')}
                  </label>
                  <input
                    type="text"
                    value={newCam.notification_recipients}
                    onChange={(e) => setNewCam({ ...newCam, notification_recipients: e.target.value })}
                    placeholder="security@company.com, ops@company.com"
                    style={{ width: '100%', padding: '7px 9px', backgroundColor: 'var(--bg-surface, #0F172A)', border: '1px solid var(--border-color, #1E293B)', borderRadius: '6px', color: 'var(--text-main, #F8FAFC)', fontSize: '0.8rem' }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '0.76rem', color: 'var(--text-secondary, #CBD5E1)' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={newCam.require_alert}
                      onChange={(e) => setNewCam({ ...newCam, require_alert: e.target.checked })}
                    />
                    <span>{t('cameras.persistAlertEvidence', 'Persist Alert & Evidence')}</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={newCam.suppress_duplicates}
                      onChange={(e) => setNewCam({ ...newCam, suppress_duplicates: e.target.checked })}
                    />
                    <span>Suppress Duplicates ({newCam.cooldown_seconds}s)</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {connectionTestResult && (
            <div
              style={{
                padding: '8px 10px',
                borderRadius: '6px',
                fontSize: '0.78rem',
                backgroundColor: connectionTestResult.success ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                color: connectionTestResult.success ? '#34D399' : '#F87171',
              }}
            >
              {connectionTestResult.message}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                type="button"
                onClick={handleTestModalConnection}
                disabled={isTestingConnection}
                className="btn btn-secondary btn-sm"
              >
                {isTestingConnection ? 'Testing...' : 'Test Connection'}
              </button>
              {newCam.source_type === 'browser' && (
                <button type="button" onClick={requestBrowserCameraPermission} className="btn btn-secondary btn-sm">
                  Request Webcam Access
                </button>
              )}
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" onClick={() => setIsAddModalOpen(false)} className="btn btn-secondary btn-sm">
                {t('common.cancel', 'Cancel')}
              </button>
              <button type="submit" disabled={isSavingCamera} className="btn btn-primary btn-sm">
                {isSavingCamera ? 'Saving...' : editingCamId ? 'Save Changes' : 'Register Camera'}
              </button>
            </div>
          </div>
        </form>
    </Modal>
  );

  return (
    <div style={{ width: '100%' }}>
      {workspaceView === 'management' ? renderCameraManagement() : renderLiveMonitor()}
      {renderCameraModal()}
      <Modal
        isOpen={Boolean(deleteTargetCam)}
        onClose={() => setDeleteTargetCam(null)}
        title={t('cameras.confirmRemoveTitle', 'Remove Camera?')}
        maxWidth="420px"
      >
        {deleteTargetCam && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <p style={{ margin: 0, fontSize: '0.84rem', color: 'var(--text-muted, #94A3B8)' }}>
              Remove "{deleteTargetCam.name}" from active monitoring? Historical recordings and forensic evidence will remain preserved.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" onClick={() => setDeleteTargetCam(null)} className="btn btn-secondary btn-sm">
                {t('common.cancel', 'Cancel')}
              </button>
              <button
                type="button"
                onClick={confirmRemoveCamera}
                className="btn btn-sm"
                style={{ backgroundColor: '#EF4444', color: '#FFFFFF', border: 'none' }}
              >
                {t('common.remove', 'Remove')}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default Cameras;
