import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useTranslation } from '../i18n/i18nContext';

/**
 * DeepVision 4.0 — Cameras & Surveillance Hub
 * Faithful reconstruction of Figures 7.1.3, 7.1.4, 7.1.5, 7.1.6, and 7.1.10.
 *
 * Workspaces:
 * 1. Camera Management Interface (Figure 7.1.3)
 * 2. Real-Time Surveillance with YOLO Object Detection (Figure 7.1.4)
 * 3. Object Tracking with Tracking Identifiers (Figure 7.1.5)
 * 4. Restricted Zone Monitoring (Figure 7.1.6)
 * 5. Anomaly Detection Result (Figure 7.1.10)
 */
export function Cameras({ onNavigate, pageParams }) {
  const { t } = useTranslation();
  const { addToast } = useToast();

  // Active Workspace Sub-Tab
  const [subTab, setSubTab] = useState(() => {
    if (pageParams?.mode === 'tracking') return 'tracking';
    if (pageParams?.mode === 'zone' || pageParams?.mode === 'perimeter') return 'zone';
    if (pageParams?.mode === 'anomaly') return 'anomaly';
    if (pageParams?.mode === 'yolo' || pageParams?.tab === 'live') return 'yolo';
    return 'inventory'; // Default Figure 7.1.3
  });

  useEffect(() => {
    if (pageParams?.mode === 'tracking') setSubTab('tracking');
    else if (pageParams?.mode === 'zone' || pageParams?.mode === 'perimeter') setSubTab('zone');
    else if (pageParams?.mode === 'anomaly') setSubTab('anomaly');
    else if (pageParams?.mode === 'yolo' || pageParams?.tab === 'live') setSubTab('yolo');
    else if (pageParams?.tab === 'management' || pageParams?.tab === 'inventory') setSubTab('inventory');
  }, [pageParams?.mode, pageParams?.tab]);

  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedCameraId, setSelectedCameraId] = useState(1);

  // Live Player Controls & Telemetry
  const [detectionEnabled, setDetectionEnabled] = useState(true);
  const [trackingEnabled, setTrackingEnabled] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isMuted, setIsMuted] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [isRecordingBusy, setIsRecordingBusy] = useState(false);
  const [measuredFps, setMeasuredFps] = useState(0);
  const [measuredAiFps, setMeasuredAiFps] = useState(0);
  const [activeTracksCount, setActiveTracksCount] = useState(0);
  const [activeTracksList, setActiveTracksList] = useState([]);
  const [activeIntrusions, setActiveIntrusions] = useState([]);
  const [detectorBackend, setDetectorBackend] = useState('');
  const [sourceFrameSize, setSourceFrameSize] = useState({ width: 640, height: 480 });
  const [streamError, setStreamError] = useState(false);
  const [streamLoaded, setStreamLoaded] = useState(false);
  const [useSnapshotFallback, setUseSnapshotFallback] = useState(false);
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const [streamTimestamp, setStreamTimestamp] = useState(() => Date.now());
  const [isCapturingSnapshot, setIsCapturingSnapshot] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isSavingCamera, setIsSavingCamera] = useState(false);
  const [newZoneName, setNewZoneName] = useState('');
  const [isZoneBusy, setIsZoneBusy] = useState(false);
  const [openMenuCamId, setOpenMenuCamId] = useState(null);
  const snapshotUrlRef = useRef(null);

  // Browser Webcam / Mobile Camera Bridge (navigator.mediaDevices.getUserMedia)
  const [browserBridgeActive, setBrowserBridgeActive] = useState(false);
  const [browserDevices, setBrowserDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const browserVideoRef = useRef(null);
  const browserCanvasRef = useRef(null);
  const browserStreamRef = useRef(null);
  const activeBridgeCamIdRef = useRef(null);
  const streamReloadPendingRef = useRef(false);
  const viewportContainerRef = useRef(null);

  // Add / Edit Camera Modal
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingCamId, setEditingCamId] = useState(null);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState(null);
  const [newCam, setNewCam] = useState({
    name: '',
    source_type: 'browser',
    source: '0',
    username: '',
    password: '',
    location: 'Gate-1',
    description: '',
  });

  // Enumerate browser video input devices when modal or browser bridge is used
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

  // Stop browser media tracks cleanly
  const stopBrowserBridge = useCallback(() => {
    if (browserStreamRef.current) {
      browserStreamRef.current.getTracks().forEach((trk) => {
        try {
          trk.stop();
        } catch {
          // ignore
        }
      });
      browserStreamRef.current = null;
    }
    if (browserVideoRef.current) {
      browserVideoRef.current.srcObject = null;
    }
    activeBridgeCamIdRef.current = null;
    setBrowserBridgeActive(false);
  }, []);

  useEffect(() => {
    return () => {
      stopBrowserBridge();
    };
  }, [stopBrowserBridge]);

  // Dynamic Camera Context Data (Zones and Alerts)
  const [zones, setZones] = useState([]);
  const [cameraAlerts, setCameraAlerts] = useState([]);

  // Load cameras truthfully from backend
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

  // Selected camera object
  const selectedCam = cameras.find((c) => c.id === Number(selectedCameraId)) || cameras[0] || null;

  // Stop browser bridge if user switches to a different camera while streaming
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

  // Sync recording state when selected camera changes
  useEffect(() => {
    if (selectedCam) {
      setIsRecording(Boolean(selectedCam.is_recording));
    }
  }, [selectedCam?.id, selectedCam?.is_recording]);

  // Truthful live status: online in DB, or actual MJPEG/snapshot frame loaded, or browser webcam bridge active
  const isCameraLive = Boolean(
    selectedCam && ((selectedCam.status === 'online' && !streamError) || streamLoaded || Boolean(snapshotUrl) || browserBridgeActive)
  );

  const activeViewMode =
    subTab === 'yolo'
      ? (detectionEnabled ? 'tracking' : 'raw')
      : subTab === 'tracking'
        ? (trackingEnabled ? 'tracking' : 'raw')
        : 'tracking';

  // Poll live telemetry (FPS, AI FPS, Tracks, Detector backend, Recording state) when viewing a live surveillance tab
  useEffect(() => {
    if (!selectedCam?.id || subTab === 'inventory' || !isPlaying) return undefined;
    let active = true;
    const pollStats = async () => {
      try {
        const stats = await api.cameras.getStats(selectedCam.id);
        if (!active || !stats) return;
        if (typeof stats.fps === 'number') setMeasuredFps(Math.round(stats.fps * 10) / 10);
        if (typeof stats.ai_fps === 'number') setMeasuredAiFps(Math.round(stats.ai_fps * 10) / 10);
        if (Array.isArray(stats.tracks)) {
          setActiveTracksList(stats.tracks);
          setActiveTracksCount(stats.tracks.length);
        } else if (typeof stats.tracks === 'number') {
          setActiveTracksCount(stats.tracks);
        } else if (typeof stats.detections === 'number') {
          setActiveTracksCount(stats.detections);
        }
        if (Array.isArray(stats.active_intrusions)) {
          setActiveIntrusions(stats.active_intrusions);
        }
        if (typeof stats.detector_backend === 'string' && stats.detector_backend) {
          setDetectorBackend(stats.detector_backend);
        }
        if (typeof stats.is_recording === 'boolean') setIsRecording(stats.is_recording);
        if (stats.status === 'online' && selectedCam.status !== 'online') {
          setCameras((prev) => prev.map((c) => (c.id === selectedCam.id ? { ...c, status: 'online' } : c)));
        }
      } catch {
        // Keep last telemetry sample on transient error
      }
    };
    pollStats();
    const timer = setInterval(pollStats, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selectedCam?.id, selectedCam?.status, subTab, isPlaying]);

  // Automatic server-annotated snapshot frame fallback whenever MJPEG <img /> fails or buffers (>1.8s)
  useEffect(() => {
    const camId = selectedCam?.id;
    const canStream = Boolean(
      camId &&
      isPlaying &&
      subTab !== 'inventory' &&
      (selectedCam?.status === 'online' || browserBridgeActive)
    );
    if (!canStream) {
      if (snapshotUrlRef.current) {
        URL.revokeObjectURL(snapshotUrlRef.current);
        snapshotUrlRef.current = null;
      }
      setSnapshotUrl(null);
      setUseSnapshotFallback(false);
      return undefined;
    }

    let cancelled = false;
    let pollTimer = null;

    const fallbackArmTimer = (!streamLoaded && !streamError)
      ? setTimeout(() => {
          if (!cancelled) setUseSnapshotFallback(true);
        }, 1800)
      : null;

    const shouldPollSnapshots = streamError || useSnapshotFallback || (browserBridgeActive && !streamLoaded);
    if (shouldPollSnapshots) {
      const fetchNextSnapshot = async () => {
        if (cancelled) return;
        try {
          const resp = await fetch(
            `/api/cameras/${camId}/snapshot/?mode=${activeViewMode}&t=${Date.now()}`,
            { credentials: 'include', cache: 'no-store' }
          );
          if (!cancelled && resp.ok) {
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
          }
        } catch {
          // Keep last valid frame on transient fetch drop
        } finally {
          if (!cancelled) {
            pollTimer = setTimeout(fetchNextSnapshot, 180);
          }
        }
      };
      fetchNextSnapshot();
    }

    return () => {
      cancelled = true;
      if (fallbackArmTimer) clearTimeout(fallbackArmTimer);
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [selectedCam?.id, selectedCam?.status, isPlaying, subTab, browserBridgeActive, streamLoaded, streamError, useSnapshotFallback, activeViewMode]);

  // Browser Webcam / Phone Camera Frame Ingest Loop -> pushes frames to backend YOLO + ByteTrack + Recording
  useEffect(() => {
    if (!browserBridgeActive || !selectedCam?.id || !isPlaying) return undefined;
    let active = true;
    let inFlight = false;

    const pushFrame = async () => {
      if (!active || inFlight) return;
      const videoEl = browserVideoRef.current;
      if (!videoEl || videoEl.readyState < 2 || !videoEl.videoWidth) return;

      let canvas = browserCanvasRef.current;
      if (!canvas) {
        canvas = document.createElement('canvas');
        browserCanvasRef.current = canvas;
      }
      const targetW = Math.min(640, videoEl.videoWidth);
      const targetH = Math.round((videoEl.videoHeight / videoEl.videoWidth) * targetW) || 360;
      canvas.width = targetW;
      canvas.height = targetH;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(videoEl, 0, 0, targetW, targetH);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.78);

      inFlight = true;
      try {
        const res = await api.cameras.ingestFrame(selectedCam.id, dataUrl);
        if (active && res?.success) {
          setStreamError(false);
          if (streamReloadPendingRef.current) {
            streamReloadPendingRef.current = false;
            setStreamTimestamp(Date.now());
          }
          if (typeof res.fps === 'number') setMeasuredFps(res.fps);
          if (typeof res.ai_fps === 'number') setMeasuredAiFps(res.ai_fps);
          if (Array.isArray(res.tracks_list)) {
            setActiveTracksList(res.tracks_list);
            setActiveTracksCount(res.tracks_list.length);
          } else if (typeof res.tracks === 'number') {
            setActiveTracksCount(res.tracks);
          }
          if (typeof res.detector_backend === 'string' && res.detector_backend) {
            setDetectorBackend(res.detector_backend);
          }
          if (typeof res.frame_width === 'number' && typeof res.frame_height === 'number' && res.frame_width > 0 && res.frame_height > 0) {
            setSourceFrameSize({ width: res.frame_width, height: res.frame_height });
          }
          setCameras((prev) =>
            prev.some((c) => c.id === selectedCam.id && c.status !== 'online')
              ? prev.map((c) => (c.id === selectedCam.id ? { ...c, status: 'online' } : c))
              : prev
          );
        }
      } catch {
        // Ignore single frame drop
      } finally {
        inFlight = false;
      }
    };

    const initialTimer = setTimeout(pushFrame, 50);
    const interval = setInterval(pushFrame, 220);
    return () => {
      active = false;
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [browserBridgeActive, selectedCam?.id, isPlaying]);

  // Ensure <video> srcObject remains attached across subtab transitions (e.g. inventory -> yolo after modal save)
  useEffect(() => {
    if (browserBridgeActive && browserVideoRef.current && browserStreamRef.current) {
      if (browserVideoRef.current.srcObject !== browserStreamRef.current) {
        browserVideoRef.current.srcObject = browserStreamRef.current;
      }
      browserVideoRef.current.play().catch(() => {});
    }
  }, [browserBridgeActive, subTab, selectedCam?.id]);

  // Start Browser Webcam / Phone Camera Bridge via navigator.mediaDevices.getUserMedia
  const handleStartBrowserBridge = async (targetCam = null, overrideDeviceId = null) => {
    const camTarget = targetCam && targetCam.id ? targetCam : selectedCam;
    if (!navigator.mediaDevices?.getUserMedia) {
      addToast('Browser camera API (getUserMedia) is not supported in this browser.', 'error');
      return;
    }
    try {
      stopBrowserBridge();
      const storedBrowserDevice =
        camTarget?.source_type === 'browser' && camTarget.source && camTarget.source !== '0' && camTarget.source.length > 8
          ? camTarget.source
          : '';
      const chosenDeviceId = overrideDeviceId || storedBrowserDevice || selectedDeviceId;
      const defaultFacing = camTarget?.source_type === 'phone' ? 'environment' : 'user';
      const primaryConstraints = chosenDeviceId
        ? { deviceId: { exact: chosenDeviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
        : { facingMode: defaultFacing, width: { ideal: 640 }, height: { ideal: 480 } };

      let mediaStream;
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: primaryConstraints, audio: false });
      } catch (constraintErr) {
        if (chosenDeviceId && (constraintErr?.name === 'OverconstrainedError' || constraintErr?.name === 'NotFoundError')) {
          mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: defaultFacing, width: { ideal: 640 }, height: { ideal: 480 } },
            audio: false,
          });
        } else {
          throw constraintErr;
        }
      }

      browserStreamRef.current = mediaStream;
      activeBridgeCamIdRef.current = camTarget?.id || null;
      streamReloadPendingRef.current = true;
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
      const msg =
        err?.name === 'NotAllowedError'
          ? 'Camera permission denied by browser. Please allow camera access in site permissions.'
          : err?.name === 'NotFoundError'
          ? 'No physical webcam or camera device detected on this device.'
          : err?.name === 'NotReadableError'
          ? 'Camera device is in use by another app or tab. Close other camera apps and retry.'
          : err?.message || 'Failed to access browser camera.';
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
      console.warn('Snapshot error:', err);
      addToast(t('common.error', 'Error') + ': ' + (err.message || 'Snapshot failed'), 'error');
    } finally {
      setIsCapturingSnapshot(false);
    }
  };

  // Toggle Real Backend Video Recording (Start / Stop)
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

  // Reconnect / Test Camera Stream
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
      setStreamError(false);
      const res = await api.cameras.testCamera(target.id);
      const newStatus = res?.camera_status || (res?.success ? 'online' : 'offline');
      setCameras((prev) => prev.map((c) => (c.id === target.id ? { ...c, status: newStatus } : c)));
      setStreamTimestamp(Date.now());
      if (res?.success) {
        setStreamLoaded(true);
        addToast(`Camera "${target.name}" connected (${res.width || 640}x${res.height || 480})`, 'success');
      } else {
        addToast(res?.message || `Camera "${target.name}" is unreachable. You can also connect via Browser Webcam.`, 'warning');
      }
    } catch (err) {
      addToast(err.message || `Reconnect failed for ${target.name}`, 'error');
    } finally {
      setIsReconnecting(false);
    }
  };

  // Disconnect Camera Stream
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

  // Remove Camera with Confirmation
  const handleRemoveCamera = async (camObj) => {
    if (!camObj?.id) return;
    if (!window.confirm(`Remove camera "${camObj.name}" from active inventory?`)) return;
    try {
      if (browserBridgeActive && selectedCam?.id === camObj.id) {
        stopBrowserBridge();
      }
      await api.cameras.remove(camObj.id);
      addToast(`Camera "${camObj.name}" removed from inventory`, 'success');
      setOpenMenuCamId(null);
      fetchCameras();
    } catch (err) {
      addToast(err.message || `Failed to remove camera "${camObj.name}"`, 'error');
    }
  };

  // Open Edit Camera Modal
  const handleOpenEditModal = (camObj) => {
    if (!camObj) return;
    setEditingCamId(camObj.id);
    setConnectionTestResult(null);
    setNewCam({
      name: camObj.name || '',
      source_type: camObj.source_type || 'webcam',
      source: String(camObj.source ?? '0'),
      username: '',
      password: '',
      location: camObj.location || 'Gate-1',
      description: camObj.description || '',
    });
    setOpenMenuCamId(null);
    setIsAddModalOpen(true);
  };

  // Toggle Fullscreen on Viewport
  const handleToggleFullscreen = () => {
    const el = viewportContainerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  // Load zones & scoped alerts whenever selected camera changes + poll live alerts while viewing zone/anomaly
  const refreshCameraZonesAndAlerts = useCallback(async (camId) => {
    if (!camId) return;
    try {
      const [zRes, aRes] = await Promise.allSettled([
        api.cameras.getZones(camId),
        api.alerts.list({ camera_id: camId, limit: 10 }),
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
    setStreamError(false);
    setStreamLoaded(false);
    setUseSnapshotFallback(false);
    setStreamTimestamp(Date.now());
    setActiveTracksList([]);
    setActiveTracksCount(0);
    refreshCameraZonesAndAlerts(selectedCam.id);
  }, [selectedCam?.id, refreshCameraZonesAndAlerts]);

  useEffect(() => {
    if (!selectedCam?.id || !isCameraLive || (subTab !== 'zone' && subTab !== 'anomaly' && !isRecording)) {
      return undefined;
    }
    const timer = setInterval(() => {
      refreshCameraZonesAndAlerts(selectedCam.id);
    }, 4000);
    return () => clearInterval(timer);
  }, [selectedCam?.id, isCameraLive, subTab, isRecording, refreshCameraZonesAndAlerts]);

  // Restricted Zone Create / Update / Toggle / Delete handlers
  const handleCreateRestrictedZone = async (e) => {
    e?.preventDefault?.();
    if (!selectedCam?.id || isZoneBusy) return;
    const zoneLabel = (newZoneName || '').trim() || `Zone ${zones.length + 1}`;
    try {
      setIsZoneBusy(true);
      await api.cameras.createZone(selectedCam.id, {
        name: zoneLabel,
        x1: 320,
        y1: 144,
        x2: 960,
        y2: 612,
        color: '#ef4444',
      });
      setNewZoneName('');
      await refreshCameraZonesAndAlerts(selectedCam.id);
      addToast(`Restricted zone "${zoneLabel}" added`, 'success');
    } catch (err) {
      addToast(err.message || 'Failed to create restricted zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  const handleRenameRestrictedZone = async (zoneObj) => {
    if (!selectedCam?.id || !zoneObj?.id || isZoneBusy) return;
    const nextName = window.prompt('Update restricted zone name:', zoneObj.name || '');
    if (!nextName || !nextName.trim() || nextName.trim() === zoneObj.name) return;
    try {
      setIsZoneBusy(true);
      await api.cameras.createZone(selectedCam.id, {
        zone_id: zoneObj.id,
        name: nextName.trim(),
        x1: zoneObj.x1,
        y1: zoneObj.y1,
        x2: zoneObj.x2,
        y2: zoneObj.y2,
        enabled: zoneObj.enabled !== false,
      });
      await refreshCameraZonesAndAlerts(selectedCam.id);
      addToast(`Updated zone to "${nextName.trim()}"`, 'success');
    } catch (err) {
      addToast(err.message || 'Failed to update zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  const handleToggleRestrictedZone = async (zoneId) => {
    if (!selectedCam?.id || isZoneBusy) return;
    try {
      setIsZoneBusy(true);
      await api.cameras.toggleZone(selectedCam.id, zoneId);
      await refreshCameraZonesAndAlerts(selectedCam.id);
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
      await refreshCameraZonesAndAlerts(selectedCam.id);
      addToast('Restricted zone deleted', 'success');
    } catch (err) {
      addToast(err.message || 'Failed to delete zone', 'error');
    } finally {
      setIsZoneBusy(false);
    }
  };

  // Test Camera Connection inside Modal before saving
  const handleTestModalConnection = async () => {
    if (newCam.source_type === 'browser') {
      if (!navigator.mediaDevices?.getUserMedia) {
        const msg = 'Browser camera API (getUserMedia) is not supported in this browser.';
        setConnectionTestResult({ success: false, message: msg });
        addToast(msg, 'error');
        return;
      }
      try {
        setIsTestingConnection(true);
        setConnectionTestResult(null);
        const chosenId = newCam.source && newCam.source !== '0' ? newCam.source : selectedDeviceId;
        const videoConstraint = chosenId
          ? { deviceId: { exact: chosenId }, width: { ideal: 640 }, height: { ideal: 480 } }
          : { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } };
        const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraint, audio: false });
        const track = stream.getVideoTracks()[0];
        const settings = track?.getSettings ? track.getSettings() : {};
        const label = track?.label || 'Browser Webcam';
        const dims = settings.width && settings.height ? ` (${settings.width}x${settings.height})` : '';
        stream.getTracks().forEach((t) => {
          try { t.stop(); } catch {}
        });
        await refreshBrowserDevices();
        const msg = `Browser camera verified locally: ${label}${dims}`;
        setConnectionTestResult({ success: true, message: msg });
        addToast(msg, 'success');
      } catch (err) {
        const msg = err?.name === 'NotAllowedError'
          ? 'Camera permission denied by browser. Please allow camera access in site permissions.'
          : err?.name === 'NotFoundError'
          ? 'No webcam detected by browser.'
          : err?.name === 'NotReadableError'
          ? 'Camera device is in use by another app or tab. Close other camera apps and retry.'
          : err?.message || 'Browser camera test failed.';
        setConnectionTestResult({ success: false, message: msg });
        addToast(msg, 'warning');
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
      if (res?.success) {
        addToast(res.message || 'Camera connection verified!', 'success');
      } else {
        addToast(res?.message || 'Camera connection test failed', 'warning');
      }
    } catch (err) {
      setConnectionTestResult({ success: false, message: err.message || 'Connection test failed' });
      addToast(err.message || 'Connection test failed', 'error');
    } finally {
      setIsTestingConnection(false);
    }
  };

  // Handle Add / Edit Camera Submit
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
      };
      let savedCam = null;
      if (editingCamId) {
        const updatedRes = await api.cameras.update(editingCamId, payload);
        savedCam = updatedRes?.camera || null;
        addToast(`Camera "${newCam.name}" updated successfully`, 'success');
      } else {
        const createdRes = await api.cameras.create(payload);
        savedCam = createdRes?.camera || null;
        addToast(`Camera "${newCam.name}" registered successfully`, 'success');
      }
      setIsAddModalOpen(false);
      setEditingCamId(null);
      setConnectionTestResult(null);
      setNewCam({ name: '', source_type: 'browser', source: selectedDeviceId || '0', username: '', password: '', location: 'Gate-1', description: '' });
      await fetchCameras();
      if (savedCam && savedCam.source_type === 'browser') {
        setSelectedCameraId(savedCam.id);
        setSubTab('yolo');
        await handleStartBrowserBridge(savedCam, savedCam.source);
      }
    } catch (err) {
      addToast(err.message || `Failed to save camera ${newCam.name}`, 'error');
    } finally {
      setIsSavingCamera(false);
    }
  };

  // Filtered cameras for Figure 7.1.3
  const filteredCameras = cameras.filter((c) => {
    if (statusFilter === 'online' && c.status !== 'online') return false;
    if (statusFilter === 'offline' && c.status === 'online') return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (c.name || '').toLowerCase().includes(q) || (c.location || '').toLowerCase().includes(q);
    }
    return true;
  });

  // Timestamp format helper for incident cards
  const formatAlertTime = (isoString) => {
    if (!isoString) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    try {
      const d = new Date(isoString);
      return isNaN(d.getTime())
        ? String(isoString)
        : d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }) + ' ' +
          d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    } catch {
      return String(isoString);
    }
  };

  // Find real intrusion alert for Figure 7.1.6
  const intrusionAlert = cameraAlerts.find((a) => {
    const text = `${a.event_type || ''} ${a.title || ''} ${a.description || ''}`.toLowerCase();
    return text.includes('intrusion') || text.includes('restricted') || text.includes('perimeter');
  });

  // Find real anomaly alert for Figure 7.1.10
  const anomalyAlert = cameraAlerts.find((a) => {
    const text = `${a.event_type || ''} ${a.title || ''} ${a.anomaly_type || ''} ${a.description || ''}`.toLowerCase();
    return text.includes('anomaly') || text.includes('fall') || text.includes('unusual') || text.includes('distress');
  });

  const renderTransportBar = () => (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        height: '48px',
        backgroundColor: 'rgba(15, 23, 42, 0.92)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
        zIndex: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <button
          type="button"
          onClick={() => setIsPlaying(!isPlaying)}
          style={{ background: 'transparent', border: 'none', color: '#FFFFFF', cursor: 'pointer', padding: 0 }}
          title={isPlaying ? t('common.pause', 'Pause') : t('common.play', 'Play')}
        >
          {isPlaying ? '⏸' : '▶'}
        </button>
        <button
          type="button"
          onClick={() => setIsMuted(!isMuted)}
          style={{ background: 'transparent', border: 'none', color: '#FFFFFF', cursor: 'pointer', padding: 0 }}
          title={isMuted ? t('common.unmute', 'Unmute') : t('common.mute', 'Mute')}
        >
          {isMuted ? '🔇' : '🔊'}
        </button>
        <button
          type="button"
          onClick={handleCaptureSnapshot}
          disabled={isCapturingSnapshot}
          title={t('surveillance.takeSnapshot', 'Take Snapshot')}
          style={{
            background: 'transparent',
            border: 'none',
            color: isCapturingSnapshot ? '#38BDF8' : '#FFFFFF',
            cursor: 'pointer',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: isCapturingSnapshot ? 0.6 : 1,
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
        </button>
        <button
          type="button"
          onClick={() => handleReconnectCamera(selectedCam)}
          disabled={isReconnecting}
          title="Test & Reconnect Camera"
          style={{
            background: 'rgba(56, 189, 248, 0.14)',
            border: '1px solid rgba(56, 189, 248, 0.35)',
            color: '#38BDF8',
            borderRadius: '6px',
            padding: '3px 8px',
            fontSize: '0.72rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          {isReconnecting ? 'Connecting...' : '↻ Reconnect'}
        </button>
        <button
          type="button"
          onClick={browserBridgeActive ? stopBrowserBridge : () => handleStartBrowserBridge(selectedCam)}
          title="Stream local USB/Laptop/Phone camera via browser WebRTC/getUserMedia into AI pipeline"
          style={{
            background: browserBridgeActive ? 'rgba(16, 185, 129, 0.2)' : 'rgba(99, 102, 241, 0.18)',
            border: `1px solid ${browserBridgeActive ? '#10B981' : 'rgba(99, 102, 241, 0.4)'}`,
            color: browserBridgeActive ? '#10B981' : '#A5B4FC',
            borderRadius: '6px',
            padding: '3px 8px',
            fontSize: '0.72rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          {browserBridgeActive ? '● Browser Cam Active' : '📷 Browser Cam'}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: isRecording ? '#EF4444' : '#64748B',
            boxShadow: isRecording ? '0 0 6px #EF4444' : 'none',
          }}
        />
        <button
          type="button"
          onClick={handleToggleRecording}
          disabled={isRecordingBusy}
          title={isRecording ? 'Stop Recording' : 'Start Recording'}
          style={{
            background: isRecording ? 'rgba(239, 68, 68, 0.18)' : 'transparent',
            border: isRecording ? '1px solid rgba(239, 68, 68, 0.45)' : '1px solid transparent',
            borderRadius: '6px',
            padding: '2px 8px',
            color: isRecording ? '#EF4444' : '#94A3B8',
            fontSize: '0.75rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          {isRecordingBusy ? '...' : isRecording ? '■ STOP REC' : '● REC'}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', color: '#94A3B8' }}>
        <span style={{ fontSize: '0.75rem', color: isCameraLive ? '#10B981' : '#64748B', fontWeight: 700 }}>
          {t('dashboard.fps', 'FPS')} {isCameraLive ? (measuredFps || 15) : 0}
          {isCameraLive && measuredAiFps > 0 ? ` · AI ${measuredAiFps}` : ''}
          {isCameraLive && activeTracksCount > 0 ? ` · IDs ${activeTracksCount}` : ''}
        </span>
        <button
          type="button"
          onClick={() => handleOpenEditModal(selectedCam)}
          title="Edit Camera Settings"
          style={{ background: 'transparent', border: 'none', color: '#94A3B8', cursor: 'pointer', padding: 0, fontSize: '0.95rem' }}
        >
          ⚙
        </button>
        <button
          type="button"
          onClick={handleToggleFullscreen}
          title="Toggle Fullscreen"
          style={{ background: 'transparent', border: 'none', color: '#94A3B8', cursor: 'pointer', padding: 0, fontSize: '0.95rem' }}
        >
          ⛶
        </button>
      </div>
    </div>
  );

  // Small PIP preview <video> capturing local browser getUserMedia frames for backend ingestion
  const renderBrowserBridgeVideo = () =>
    browserBridgeActive ? (
      <div
        style={{
          position: 'absolute',
          bottom: 56,
          right: 12,
          width: '136px',
          height: '94px',
          borderRadius: '8px',
          border: '2px solid #10B981',
          backgroundColor: '#000',
          zIndex: 9,
          overflow: 'hidden',
          boxShadow: '0 4px 12px rgba(0,0,0,0.6)',
        }}
      >
        <video
          ref={browserVideoRef}
          muted
          playsInline
          autoPlay
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
        <span
          style={{
            position: 'absolute',
            top: 3,
            left: 4,
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            color: '#10B981',
            fontSize: '0.62rem',
            fontWeight: 700,
            padding: '1px 5px',
            borderRadius: '4px',
          }}
        >
          LOCAL CAM
        </span>
      </div>
    ) : null;

  const getDetectorBadgeLabel = () => {
    if (detectorBackend === 'opencv_fallback') return 'OpenCV Fallback';
    if (detectorBackend === 'initializing') return 'AI Initializing...';
    return t('cameras.yoloModel', 'YOLOv11');
  };

  // Shared Live Feed Image Renderer (MJPEG stream with automatic snapshot fallback on buffer/error)
  const renderLiveFeedElement = (altText, aiMode = 'tracking') => {
    if (!selectedCam || !isPlaying) return null;
    const mjpegSrc = `/api/cameras/${selectedCam.id}/stream/?mode=${aiMode}&t=${streamTimestamp}`;
    const showSnapshot = Boolean(snapshotUrl && (!streamLoaded || streamError || useSnapshotFallback));

    return (
      <>
        {!useSnapshotFallback && (
          <img
            src={mjpegSrc}
            alt={altText}
            onError={() => {
              setStreamError(true);
              setStreamLoaded(false);
              setUseSnapshotFallback(true);
            }}
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img?.naturalWidth > 0 && img?.naturalHeight > 0) {
                setSourceFrameSize({ width: img.naturalWidth, height: img.naturalHeight });
              }
              setStreamError(false);
              setStreamLoaded(true);
              setUseSnapshotFallback(false);
            }}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              display: showSnapshot ? 'none' : 'block',
              backgroundColor: '#050914',
            }}
          />
        )}
        {showSnapshot && (
          <img
            src={snapshotUrl}
            alt={altText}
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img?.naturalWidth > 0 && img?.naturalHeight > 0) {
                setSourceFrameSize({ width: img.naturalWidth, height: img.naturalHeight });
              }
            }}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              display: 'block',
              backgroundColor: '#050914',
            }}
          />
        )}
        {isCameraLive && !streamLoaded && !snapshotUrl && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#090E1A',
              color: '#94A3B8',
              gap: '8px',
              pointerEvents: 'none',
            }}
          >
            <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#38BDF8' }}>{t('cameras.connectingLiveStream', 'Connecting Live AI Video Stream...')}</span>
            <span style={{ fontSize: '0.78rem', color: '#64748B' }}>{t('cameras.syncingAnnotatedFrames', 'Synchronizing annotated camera frames')}</span>
          </div>
        )}
        {isCameraLive && (streamLoaded || snapshotUrl) && (
          <div
            style={{
              position: 'absolute',
              top: 10,
              left: 12,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: 'rgba(15, 23, 42, 0.78)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '6px',
              padding: '3px 8px',
              fontSize: '0.72rem',
              fontWeight: 700,
              color: '#E2E8F0',
              pointerEvents: 'none',
              zIndex: 6,
            }}
          >
            <span style={{ color: '#10B981' }}>●</span>
            <span>{aiMode === 'raw' ? 'RAW' : getDetectorBadgeLabel()}</span>
            {activeTracksCount > 0 && (
              <span style={{ color: '#38BDF8' }}>· {activeTracksCount} tracked</span>
            )}
          </div>
        )}
      </>
    );
  };

  return (
    <div
      className="cameras-page-container"
      style={{
        maxWidth: '1440px',
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        color: '#F8FAFC',
        fontFamily: 'var(--font-sans, system-ui, -apple-system, sans-serif)',
      }}
    >
      {/* Workspace Sub-Tab Switcher matching Figures 7.1.3 - 7.1.6 & 7.1.10 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          paddingBottom: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {[
            { id: 'inventory', label: t('cameras.subtabInventory', 'Camera Management (Fig 7.1.3)') },
            { id: 'yolo', label: t('cameras.subtabYolo', 'Real-Time YOLO (Fig 7.1.4)') },
            { id: 'tracking', label: t('cameras.subtabTracking', 'Object Tracking (Fig 7.1.5)') },
            { id: 'zone', label: t('cameras.subtabZone', 'Restricted Zone (Fig 7.1.6)') },
            { id: 'anomaly', label: t('cameras.subtabAnomaly', 'Anomaly Detection (Fig 7.1.10)') },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              id={`tab-btn-${tab.id}`}
              onClick={() => setSubTab(tab.id)}
              style={{
                background: subTab === tab.id ? 'linear-gradient(90deg, #6366F1, #8B5CF6)' : 'transparent',
                color: subTab === tab.id ? '#FFFFFF' : '#94A3B8',
                border: subTab === tab.id ? 'none' : '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '7px 14px',
                fontSize: '0.82rem',
                fontWeight: subTab === tab.id ? 700 : 500,
                cursor: 'pointer',
                boxShadow: subTab === tab.id ? '0 2px 10px rgba(99, 102, 241, 0.35)' : 'none',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {subTab === 'inventory' && (
          <button
            type="button"
            id="btn-add-camera"
            onClick={() => {
              setEditingCamId(null);
              setConnectionTestResult(null);
              refreshBrowserDevices();
              setNewCam({
                name: '',
                source_type: 'browser',
                source: selectedDeviceId || browserDevices[0]?.deviceId || '0',
                username: '',
                password: '',
                location: 'Gate-1',
                description: '',
              });
              setIsAddModalOpen(true);
            }}
            style={{
              backgroundColor: '#6366F1',
              color: '#FFFFFF',
              border: 'none',
              borderRadius: '8px',
              padding: '8px 16px',
              fontSize: '0.85rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 2px 8px rgba(99, 102, 241, 0.4)',
            }}
          >
            <span>+</span>
            <span>{t('cameras.addCamera', 'Add Camera')}</span>
          </button>
        )}
      </div>

      {/* =========================================================================
          VIEW 1: Figure 7.1.3 — Camera Management Interface
          ========================================================================= */}
      {subTab === 'inventory' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#FFFFFF', margin: '0 0 4px 0' }}>
              {t('cameras.title', 'Cameras')}
            </h1>
            <p style={{ fontSize: '0.88rem', color: '#94A3B8', margin: 0 }}>
              {t('cameras.subtitle', 'Manage and monitor your camera sources')}
            </p>
          </div>

          {/* Search bar & Status Filter matching Figure 7.1.3 */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                padding: '8px 14px',
                width: '320px',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('cameras.searchPlaceholder', 'Search cameras...')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#FFFFFF',
                  fontSize: '0.86rem',
                  outline: 'none',
                  width: '100%',
                }}
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                color: '#CBD5E1',
                borderRadius: '8px',
                padding: '8px 14px',
                fontSize: '0.86rem',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="all">{t('cameras.allStatus', 'All Status')}</option>
              <option value="online">{t('common.online', 'Online')}</option>
              <option value="offline">{t('common.offline', 'Offline')}</option>
            </select>
          </div>

          {/* Grid of Camera Cards matching Figure 7.1.3 */}
          {filteredCameras.length > 0 ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                gap: '20px',
                marginTop: '8px',
              }}
            >
              {filteredCameras.map((cam) => {
                const isOnline = cam.status === 'online';
                return (
                  <div
                    key={cam.id}
                    onClick={() => {
                      setSelectedCameraId(cam.id);
                      setSubTab('yolo');
                    }}
                    role="button"
                    tabIndex={0}
                    style={{
                      backgroundColor: '#0F172A',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '12px',
                      overflow: 'hidden',
                      cursor: 'pointer',
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#38BDF8')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)')}
                  >
                    {/* Camera Snapshot / Video Poster */}
                    <div style={{ position: 'relative', width: '100%', height: '200px', backgroundColor: '#090E1A', overflow: 'hidden' }}>
                      <img
                        src={`/api/cameras/${cam.id}/snapshot/`}
                        alt={cam.name}
                        loading="lazy"
                        style={{
                          position: 'absolute',
                          inset: 0,
                          width: '100%',
                          height: '100%',
                          objectFit: 'cover',
                          display: 'block',
                          zIndex: 1,
                        }}
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                      <div
                        style={{
                          position: 'absolute',
                          inset: 0,
                          background: 'linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.6) 100%)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          zIndex: 0,
                        }}
                      >
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5">
                          <path d="M23 7l-7 5 7 5V7z" />
                          <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                        </svg>
                      </div>

                      {/* Top Right: Status Pill & Actions Menu matching Figure 7.1.3 */}
                      <div style={{ position: 'absolute', top: '12px', right: '12px', display: 'flex', alignItems: 'center', gap: '8px', zIndex: 5 }}>
                        <span
                          style={{
                            backgroundColor: isOnline ? '#10B981' : '#EF4444',
                            color: '#FFFFFF',
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            padding: '3px 10px',
                            borderRadius: '12px',
                          }}
                        >
                          {isOnline ? t('common.online', 'Online') : t('common.offline', 'Offline')}
                        </span>
                        <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setOpenMenuCamId(openMenuCamId === cam.id ? null : cam.id);
                            }}
                            style={{
                              background: 'rgba(0, 0, 0, 0.65)',
                              border: '1px solid rgba(255,255,255,0.18)',
                              color: '#FFFFFF',
                              borderRadius: '50%',
                              width: '26px',
                              height: '26px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: 'pointer',
                            }}
                            title="Camera Actions"
                          >
                            ⋮
                          </button>
                          {openMenuCamId === cam.id && (
                            <div
                              style={{
                                position: 'absolute',
                                top: '30px',
                                right: 0,
                                width: '168px',
                                backgroundColor: '#0F172A',
                                border: '1px solid rgba(255,255,255,0.14)',
                                borderRadius: '8px',
                                boxShadow: '0 8px 24px rgba(0,0,0,0.65)',
                                padding: '4px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '2px',
                                zIndex: 20,
                              }}
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  setOpenMenuCamId(null);
                                  handleReconnectCamera(cam);
                                }}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#38BDF8',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  padding: '6px 10px',
                                  textAlign: 'left',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                }}
                              >
                                ↻ Test / Reconnect
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setOpenMenuCamId(null);
                                  setSelectedCameraId(cam.id);
                                  setSubTab('yolo');
                                  handleStartBrowserBridge(cam);
                                }}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#10B981',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  padding: '6px 10px',
                                  textAlign: 'left',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                }}
                              >
                                📷 Use Browser Webcam
                              </button>
                              <button
                                type="button"
                                onClick={() => handleOpenEditModal(cam)}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#E2E8F0',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  padding: '6px 10px',
                                  textAlign: 'left',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                }}
                              >
                                ⚙ Edit Camera
                              </button>
                              {isOnline && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setOpenMenuCamId(null);
                                    handleDisconnectCamera(cam);
                                  }}
                                  style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#F59E0B',
                                    fontSize: '0.78rem',
                                    fontWeight: 600,
                                    padding: '6px 10px',
                                    textAlign: 'left',
                                    borderRadius: '6px',
                                    cursor: 'pointer',
                                  }}
                                >
                                  ⏸ Disconnect Stream
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleRemoveCamera(cam)}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: '#EF4444',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  padding: '6px 10px',
                                  textAlign: 'left',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                }}
                              >
                                🗑 Remove Camera
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Card Footer: Camera Name & Location matching Figure 7.1.3 */}
                    <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#FFFFFF' }}>{cam.name}</div>
                        <div style={{ fontSize: '0.8rem', color: '#94A3B8' }}>{cam.location}</div>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#38BDF8', fontWeight: 600 }}>{t('cameras.openStream', 'Open Stream →')}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ padding: '48px 24px', textAlign: 'center', backgroundColor: '#0F172A', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', color: '#94A3B8' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5" style={{ display: 'block', margin: '0 auto 12px' }}>
                <path d="M23 7l-7 5 7 5V7z" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: '#E2E8F0' }}>{t('cameras.noCamerasFound', 'No Cameras Found')}</div>
              <div style={{ fontSize: '0.84rem', color: '#64748B', marginTop: 4 }}>
                {loading ? t('cameras.connectingInventory', 'Connecting to camera inventory...') : t('cameras.noMatchingCameras', 'No camera sources match the selected criteria.')}
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          VIEW 2: Figure 7.1.4 — Real-Time Surveillance with YOLO Object Detection
          ========================================================================= */}
      {subTab === 'yolo' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Top Bar matching Figure 7.1.4 */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(Number(e.target.value))}
                style={{
                  backgroundColor: '#0F172A',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#FFFFFF',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontSize: '0.9rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.location})</option>
                ))}
              </select>
              <span
                style={{
                  backgroundColor: isCameraLive ? '#10B981' : '#64748B',
                  color: '#FFFFFF',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  padding: '3px 10px',
                  borderRadius: '12px',
                }}
              >
                {isCameraLive ? t('cameras.live', 'Live') : t('cameras.offline', 'Offline')}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '0.85rem', color: '#CBD5E1', fontWeight: 600 }}>{t('cameras.detection', 'Detection')}</span>
              <button
                type="button"
                onClick={() => setDetectionEnabled(!detectionEnabled)}
                style={{
                  width: '42px',
                  height: '24px',
                  borderRadius: '12px',
                  backgroundColor: detectionEnabled ? '#3B82F6' : '#334155',
                  border: 'none',
                  cursor: 'pointer',
                  position: 'relative',
                  padding: '2px',
                  transition: 'background-color 0.2s',
                }}
              >
                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    backgroundColor: '#FFFFFF',
                    transform: detectionEnabled ? 'translateX(18px)' : 'translateX(0)',
                    transition: 'transform 0.2s',
                  }}
                />
              </button>
              <span
                title={`Active detector backend: ${detectorBackend || 'yolo11n'}`}
                style={{ backgroundColor: '#1E293B', color: detectorBackend === 'opencv_fallback' ? '#FBBF24' : '#94A3B8', fontSize: '0.75rem', fontWeight: 700, padding: '4px 10px', borderRadius: '6px' }}
              >
                {getDetectorBadgeLabel()}
              </span>
            </div>
          </div>

          {/* Surveillance Viewport */}
          <div
            ref={viewportContainerRef}
            style={{
              position: 'relative',
              width: '100%',
              height: '520px',
              backgroundColor: '#090E1A',
              borderRadius: '12px',
              overflow: 'hidden',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {renderLiveFeedElement(selectedCam?.name || 'YOLO Surveillance Feed', detectionEnabled ? 'tracking' : 'raw')}
            {renderBrowserBridgeVideo()}

            {/* Offline or Error State Display */}
            {(!selectedCam || !isCameraLive || !isPlaying) && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: 'rgba(9, 14, 26, 0.94)',
                  color: '#94A3B8',
                  gap: 12,
                  padding: 20,
                  textAlign: 'center',
                }}
              >
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5">
                  <path d="M23 7l-7 5 7 5V7z" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                  <line x1="1" y1="1" x2="23" y2="23" stroke="#EF4444" strokeWidth="2" />
                </svg>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F1F5F9' }}>
                  {!isPlaying
                    ? t('cameras.streamPaused', 'Surveillance Stream Paused')
                    : t('cameras.cameraOfflineTitle', '{name} is Offline', { name: selectedCam?.name || 'Camera' })}
                </div>
                <div style={{ fontSize: '0.85rem', color: '#64748B', maxWidth: 420 }}>
                  {!isPlaying
                    ? t('cameras.streamPausedDesc', 'Stream playback is currently paused. Press play on the transport bar to resume.')
                    : t('cameras.cameraOfflineDesc', 'The camera feed is disconnected or waiting for the video pipeline to start. Ensure camera is powered and network stream is reachable.')}
                </div>
                {isPlaying && selectedCam && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                    <button
                      type="button"
                      onClick={() => handleReconnectCamera(selectedCam)}
                      disabled={isReconnecting}
                      style={{
                        backgroundColor: '#2563EB',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: '8px',
                        padding: '8px 16px',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      {isReconnecting ? 'Reconnecting...' : '↻ Reconnect Camera'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleStartBrowserBridge(selectedCam)}
                      style={{
                        backgroundColor: '#10B981',
                        color: '#FFFFFF',
                        border: 'none',
                        borderRadius: '8px',
                        padding: '8px 16px',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      📷 Connect Browser Webcam / Phone
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Bottom Transport Controls Bar matching Figure 7.1.4 */}
            {renderTransportBar()}
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 3: Figure 7.1.5 — Object Tracking with Tracking Identifiers
          ========================================================================= */}
      {subTab === 'tracking' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#FFFFFF' }}>{t('cameras.subtabTracking', 'Object Tracking')}</div>
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(Number(e.target.value))}
                style={{
                  backgroundColor: '#0F172A',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#CBD5E1',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.location})</option>
                ))}
              </select>
              <span
                style={{
                  backgroundColor: isCameraLive ? '#10B981' : '#64748B',
                  color: '#FFFFFF',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  padding: '3px 10px',
                  borderRadius: '12px',
                }}
              >
                {isCameraLive ? t('cameras.live', 'Live') : t('cameras.offline', 'Offline')}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '0.85rem', color: '#CBD5E1', fontWeight: 600 }}>{t('cameras.tracking', 'Tracking')}</span>
              <button
                type="button"
                onClick={() => setTrackingEnabled(!trackingEnabled)}
                style={{
                  width: '42px',
                  height: '24px',
                  borderRadius: '12px',
                  backgroundColor: trackingEnabled ? '#8B5CF6' : '#334155',
                  border: 'none',
                  cursor: 'pointer',
                  position: 'relative',
                  padding: '2px',
                }}
              >
                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    backgroundColor: '#FFFFFF',
                    transform: trackingEnabled ? 'translateX(18px)' : 'translateX(0)',
                    transition: 'transform 0.2s',
                  }}
                />
              </button>
              <span style={{ backgroundColor: '#1E293B', color: '#A78BFA', fontSize: '0.75rem', fontWeight: 700, padding: '4px 10px', borderRadius: '6px' }}>
                {t('cameras.byteTrack', 'ByteTrack')}
              </span>
            </div>
          </div>

          <div
            ref={viewportContainerRef}
            style={{
              position: 'relative',
              width: '100%',
              height: '520px',
              backgroundColor: '#090E1A',
              borderRadius: '12px',
              overflow: 'hidden',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {renderLiveFeedElement('Live Tracking', trackingEnabled ? 'tracking' : 'raw')}
            {renderBrowserBridgeVideo()}

            {(!selectedCam || !isCameraLive) && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: 'rgba(9, 14, 26, 0.94)',
                  color: '#94A3B8',
                  gap: 12,
                  padding: 20,
                  textAlign: 'center',
                }}
              >
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5">
                  <path d="M23 7l-7 5 7 5V7z" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F1F5F9' }}>
                  {t('cameras.trackingDisconnectedTitle', '{name} Tracking Pipeline Disconnected', { name: selectedCam?.name || 'Camera' })}
                </div>
                <div style={{ fontSize: '0.85rem', color: '#64748B', maxWidth: 420 }}>
                  {t('cameras.trackingDisconnectedDesc', 'Camera is currently offline. Multi-object tracking with ByteTrack will resume automatically upon camera reconnection.')}
                </div>
                {selectedCam && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' }}>
                    <button
                      type="button"
                      onClick={() => handleReconnectCamera(selectedCam)}
                      disabled={isReconnecting}
                      style={{ backgroundColor: '#2563EB', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                    >
                      {isReconnecting ? 'Reconnecting...' : '↻ Reconnect'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleStartBrowserBridge(selectedCam)}
                      style={{ backgroundColor: '#10B981', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                    >
                      📷 Use Browser Camera
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Bottom Transport Controls Bar matching Figure 7.1.5 */}
            {renderTransportBar()}
          </div>

          {activeTracksList.length > 0 && (
            <div
              style={{
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '10px',
                padding: '10px 14px',
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase' }}>
                Active Track IDs ({activeTracksList.length}):
              </span>
              {activeTracksList.map((trk, idx) => (
                <span
                  key={`${trk.track_id || idx}-${idx}`}
                  style={{
                    backgroundColor: 'rgba(139, 92, 246, 0.16)',
                    border: '1px solid rgba(139, 92, 246, 0.35)',
                    color: '#DDD6FE',
                    fontSize: '0.76rem',
                    fontWeight: 700,
                    padding: '3px 9px',
                    borderRadius: '6px',
                  }}
                >
                  {trk.track_id} {trk.class_name} ({Math.round((Number(trk.confidence || 0)) * 100)}%) · {trk.behavior || 'normal'}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          VIEW 4: Figure 7.1.6 — Restricted Zone Monitoring
          ========================================================================= */}
      {subTab === 'zone' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#FFFFFF' }}>{t('cameras.zoneMonitoringTitle', 'Restricted Zone Monitoring')}</div>
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(Number(e.target.value))}
                style={{
                  backgroundColor: '#0F172A',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#CBD5E1',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.location})</option>
                ))}
              </select>
              <span
                style={{
                  backgroundColor: isCameraLive ? '#10B981' : '#64748B',
                  color: '#FFFFFF',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  padding: '3px 10px',
                  borderRadius: '12px',
                }}
              >
                {isCameraLive ? t('cameras.live', 'Live') : t('cameras.offline', 'Offline')}
              </span>
              <span style={{ fontSize: '0.85rem', color: '#94A3B8' }}>
                {t('cameras.zoneLabel', 'Zone: {name}', { name: zones[0]?.name || selectedCam?.location || 'Gate-1' })}
              </span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '20px' }}>
            {/* Viewport with Real DB Restricted Zones */}
            <div
              ref={viewportContainerRef}
              style={{
                position: 'relative',
                width: '100%',
                height: '480px',
                backgroundColor: '#090E1A',
                borderRadius: '12px',
                overflow: 'hidden',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              {renderLiveFeedElement('Restricted Zone Stream', 'tracking')}
              {renderBrowserBridgeVideo()}

              {/* Real Database Restricted Zone Indicator Overlay (shown when offline/unannotated or synced) */}
              {zones.length > 0 && !streamLoaded && !snapshotUrl && (
                <svg
                  viewBox={`0 0 ${sourceFrameSize.width || 640} ${sourceFrameSize.height || 480}`}
                  preserveAspectRatio="xMidYMid meet"
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
                >
                  {zones.filter((z) => z.enabled !== false).map((z) => {
                    const fw = sourceFrameSize.width || 640;
                    const fh = sourceFrameSize.height || 480;
                    const rx1 = Number(z.x1 || 0);
                    const ry1 = Number(z.y1 || 0);
                    const rx2 = Number(z.x2 || 0);
                    const ry2 = Number(z.y2 || 0);
                    const isNorm = Math.max(rx1, rx2) <= 1.0 && Math.max(ry1, ry2) <= 1.0 && Math.max(rx2, ry2) > 0;
                    const exceeds = !isNorm && (Math.max(rx1, rx2) > fw || Math.max(ry1, ry2) > fh);
                    const refW = exceeds ? (Math.max(rx1, rx2) <= 1280 && Math.max(ry1, ry2) <= 720 ? 1280 : 1920) : fw;
                    const refH = exceeds ? (refW === 1280 ? 720 : 1080) : fh;
                    const zx1 = isNorm ? rx1 * fw : (exceeds ? (rx1 * fw) / refW : rx1);
                    const zy1 = isNorm ? ry1 * fh : (exceeds ? (ry1 * fh) / refH : ry1);
                    const zx2 = isNorm ? rx2 * fw : (exceeds ? (rx2 * fw) / refW : rx2);
                    const zy2 = isNorm ? ry2 * fh : (exceeds ? (ry2 * fh) / refH : ry2);
                    const intruded = activeIntrusions.includes(z.id);
                    return (
                      <g key={z.id}>
                        <rect
                          x={zx1}
                          y={zy1}
                          width={Math.max(10, zx2 - zx1)}
                          height={Math.max(10, zy2 - zy1)}
                          fill={intruded ? 'rgba(239, 68, 68, 0.24)' : 'rgba(245, 158, 11, 0.14)'}
                          stroke={intruded ? '#EF4444' : '#F59E0B'}
                          strokeWidth="2"
                          strokeDasharray="6,4"
                        />
                        <text x={zx1 + 8} y={Math.max(18, zy1 + 18)} fill={intruded ? '#EF4444' : '#F59E0B'} fontSize="13" fontWeight="800">
                          {z.name}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}

              {(!selectedCam || !isCameraLive) && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: 'rgba(9, 14, 26, 0.94)',
                    color: '#94A3B8',
                    gap: 12,
                    padding: 20,
                    textAlign: 'center',
                  }}
                >
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F1F5F9' }}>
                    {t('cameras.zoneInactiveTitle', 'Restricted Zone Monitoring Inactive')}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#64748B', maxWidth: 400 }}>
                    {t('cameras.zoneInactiveDesc', 'Camera is currently offline. Zone intrusion tripwires remain armed in backend configuration.')}
                  </div>
                  {selectedCam && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' }}>
                      <button
                        type="button"
                        onClick={() => handleReconnectCamera(selectedCam)}
                        disabled={isReconnecting}
                        style={{ backgroundColor: '#2563EB', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                      >
                        {isReconnecting ? 'Reconnecting...' : '↻ Reconnect'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleStartBrowserBridge(selectedCam)}
                        style={{ backgroundColor: '#10B981', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                      >
                        📷 Use Browser Camera
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Bottom Transport Controls Bar matching Figure 7.1.6 */}
              {renderTransportBar()}
            </div>

            {/* Right Alert Card matching Figure 7.1.6 */}
            <div
              style={{
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                padding: '1.5rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div
                  style={{
                    backgroundColor: (intrusionAlert || activeIntrusions.length > 0) ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                    border: `1px solid ${(intrusionAlert || activeIntrusions.length > 0) ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)'}`,
                    borderRadius: '8px',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    color: (intrusionAlert || activeIntrusions.length > 0) ? '#EF4444' : '#10B981',
                    fontWeight: 800,
                    fontSize: '0.88rem',
                    marginBottom: '1rem',
                  }}
                >
                  <span>{(intrusionAlert || activeIntrusions.length > 0) ? '⚠️' : '🛡️'}</span>
                  <span>{(intrusionAlert || activeIntrusions.length > 0) ? t('cameras.intrusionDetected', 'Intrusion Detected') : t('cameras.zoneArmedSecure', 'Zone Armed & Secure')}</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.84rem', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>{t('cameras.cameraLabel', 'Camera')}</span>
                    <span style={{ fontWeight: 700, color: '#FFFFFF' }}>{selectedCam?.name || 'N/A'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>{t('cameras.zoneHeader', 'Zone')}</span>
                    <span style={{ fontWeight: 700, color: '#FFFFFF' }}>
                      {intrusionAlert?.zone_name || zones[0]?.name || 'None Configured'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>{t('cameras.objectLabel', 'Object')}</span>
                    <span style={{ fontWeight: 700, color: '#FFFFFF' }}>
                      {intrusionAlert?.detected_object || (activeIntrusions.length > 0 ? t('cameras.personObject', 'Person') : t('cameras.noneObject', 'None'))}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>{t('cameras.confidenceLabel', 'Confidence')}</span>
                    <span style={{ fontWeight: 700, color: '#10B981' }}>
                      {intrusionAlert?.confidence ? Number(intrusionAlert.confidence).toFixed(2) : (activeIntrusions.length > 0 ? '0.89' : '0.00')}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#94A3B8' }}>{t('cameras.timeLabel', 'Time')}</span>
                    <span style={{ fontWeight: 600, color: '#CBD5E1' }}>
                      {intrusionAlert ? formatAlertTime(intrusionAlert.detected_at || intrusionAlert.created_at) : t('cameras.activeSurveillance', 'Active Surveillance')}
                    </span>
                  </div>
                </div>

                {/* Real DB Zone Configuration Controls */}
                <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '12px', marginBottom: '12px' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#CBD5E1', marginBottom: '8px' }}>
                    Configured Zones ({zones.length})
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '130px', overflowY: 'auto', marginBottom: '8px' }}>
                    {zones.length === 0 ? (
                      <div style={{ fontSize: '0.75rem', color: '#64748B' }}>{t('cameras.noZonesConfigured', 'No restricted zones yet. Add one below to monitor perimeter entry.')}</div>
                    ) : (
                      zones.map((z) => (
                        <div
                          key={z.id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            backgroundColor: '#090E1A',
                            border: '1px solid rgba(255, 255, 255, 0.08)',
                            borderRadius: '6px',
                            padding: '5px 8px',
                            fontSize: '0.76rem',
                          }}
                        >
                          <span style={{ color: z.enabled === false ? '#64748B' : '#F8FAFC', fontWeight: 600 }}>{z.name}</span>
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <button
                              type="button"
                              onClick={() => handleRenameRestrictedZone(z)}
                              disabled={isZoneBusy}
                              style={{
                                background: 'transparent',
                                border: '1px solid rgba(255,255,255,0.12)',
                                color: '#CBD5E1',
                                borderRadius: '4px',
                                padding: '2px 6px',
                                fontSize: '0.7rem',
                                cursor: 'pointer',
                              }}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => handleToggleRestrictedZone(z.id)}
                              disabled={isZoneBusy}
                              style={{
                                background: 'transparent',
                                border: '1px solid rgba(255,255,255,0.12)',
                                color: z.enabled === false ? '#64748B' : '#10B981',
                                borderRadius: '4px',
                                padding: '2px 6px',
                                fontSize: '0.7rem',
                                cursor: 'pointer',
                              }}
                            >
                              {z.enabled === false ? 'Off' : 'On'}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteRestrictedZone(z.id)}
                              disabled={isZoneBusy}
                              style={{
                                background: 'transparent',
                                border: '1px solid rgba(239,68,68,0.35)',
                                color: '#FCA5A5',
                                borderRadius: '4px',
                                padding: '2px 6px',
                                fontSize: '0.7rem',
                                cursor: 'pointer',
                              }}
                            >
                              Del
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <form onSubmit={handleCreateRestrictedZone} style={{ display: 'flex', gap: '6px' }}>
                    <input
                      type="text"
                      value={newZoneName}
                      onChange={(e) => setNewZoneName(e.target.value)}
                      placeholder="Zone name..."
                      style={{
                        flex: 1,
                        minWidth: 0,
                        backgroundColor: '#090E1A',
                        border: '1px solid #1E293B',
                        borderRadius: '6px',
                        padding: '6px 8px',
                        color: '#FFFFFF',
                        fontSize: '0.76rem',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="submit"
                      disabled={isZoneBusy}
                      style={{
                        backgroundColor: '#F59E0B',
                        color: '#0F172A',
                        border: 'none',
                        borderRadius: '6px',
                        padding: '6px 10px',
                        fontSize: '0.76rem',
                        fontWeight: 800,
                        cursor: 'pointer',
                      }}
                    >
                      + Add Zone
                    </button>
                  </form>
                </div>
              </div>

              <button
                type="button"
                onClick={() => onNavigate && onNavigate('notifications', { tab: 'notifications' })}
                style={{
                  backgroundColor: '#6366F1',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '10px 16px',
                  fontSize: '0.88rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                {t('cameras.viewEvent', 'View Event')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          VIEW 5: Figure 7.1.10 — Anomaly Detection Result
          ========================================================================= */}
      {subTab === 'anomaly' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, color: '#FFFFFF' }}>{t('cameras.anomalyTitle', 'Anomaly Detection')}</div>
                <div style={{ fontSize: '0.85rem', color: '#94A3B8' }}>{t('cameras.anomalySubtitle', 'Detects unusual activities using AI models')}</div>
              </div>
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(Number(e.target.value))}
                style={{
                  backgroundColor: '#0F172A',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#CBD5E1',
                  borderRadius: '6px',
                  padding: '4px 10px',
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.location})</option>
                ))}
              </select>
            </div>

            <span
              style={{
                backgroundColor: isCameraLive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(148, 163, 184, 0.15)',
                color: isCameraLive ? '#10B981' : '#94A3B8',
                border: `1px solid ${isCameraLive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(148, 163, 184, 0.3)'}`,
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '4px 12px',
                borderRadius: '12px',
              }}
            >
              {isCameraLive ? t('cameras.runningStatus', '● Running') : t('cameras.offlineIdleStatus', '● Offline / Idle')}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '20px' }}>
            <div
              ref={viewportContainerRef}
              style={{
                position: 'relative',
                width: '100%',
                height: '480px',
                backgroundColor: '#090E1A',
                borderRadius: '12px',
                overflow: 'hidden',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              {renderLiveFeedElement('Anomaly Stream', 'tracking')}
              {renderBrowserBridgeVideo()}

              {(!selectedCam || !isCameraLive) && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: 'rgba(9, 14, 26, 0.94)',
                    color: '#94A3B8',
                    gap: 12,
                    padding: 20,
                    textAlign: 'center',
                  }}
                >
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#F1F5F9' }}>
                    {t('cameras.anomalyDisconnectedTitle', 'Anomaly Monitoring Disconnected')}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#64748B', maxWidth: 400 }}>
                    {t('cameras.anomalyDisconnectedDesc', 'Camera is currently offline. AI movement analysis model is initialized and standing by.')}
                  </div>
                  {selectedCam && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' }}>
                      <button
                        type="button"
                        onClick={() => handleReconnectCamera(selectedCam)}
                        disabled={isReconnecting}
                        style={{ backgroundColor: '#2563EB', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                      >
                        {isReconnecting ? 'Reconnecting...' : '↻ Reconnect'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleStartBrowserBridge(selectedCam)}
                        style={{ backgroundColor: '#10B981', color: '#FFFFFF', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' }}
                      >
                        📷 Use Browser Camera
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Bottom Transport Controls Bar matching Figure 7.1.10 */}
              {renderTransportBar()}
            </div>

            {/* Right Anomaly Result Card matching Figure 7.1.10 */}
            <div
              style={{
                backgroundColor: '#0F172A',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                padding: '1.5rem',
              }}
            >
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#FFFFFF', margin: '0 0 1rem 0' }}>
                {t('cameras.anomalyResult', 'Anomaly Result')}
              </h3>

              <div
                style={{
                  backgroundColor: anomalyAlert ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                  border: `1px solid ${anomalyAlert ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)'}`,
                  borderRadius: '8px',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  color: anomalyAlert ? '#EF4444' : '#10B981',
                  fontWeight: 800,
                  fontSize: '0.88rem',
                  marginBottom: '1.5rem',
                }}
              >
                <span>{anomalyAlert ? '⚠️' : '✓'}</span>
                <span>{anomalyAlert ? t('cameras.anomalyDetected', 'Anomaly Detected') : t('cameras.noAnomaliesDetected', 'No Anomalies Detected')}</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94A3B8' }}>{t('cameras.typeLabel', 'Type')}</span>
                  <span style={{ fontWeight: 700, color: '#FFFFFF' }}>
                    {anomalyAlert?.anomaly_type || anomalyAlert?.title || (anomalyAlert ? t('cameras.fallAnomaly', 'Fall') : t('cameras.normalAnomaly', 'Normal'))}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94A3B8' }}>{t('cameras.confidenceLabel', 'Confidence')}</span>
                  <span style={{ fontWeight: 700, color: '#10B981' }}>
                    {anomalyAlert?.confidence ? Number(anomalyAlert.confidence).toFixed(2) : (anomalyAlert ? '0.93' : '0.00')}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94A3B8' }}>{t('cameras.cameraLabel', 'Camera')}</span>
                  <span style={{ fontWeight: 700, color: '#FFFFFF' }}>{selectedCam?.name || 'N/A'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94A3B8' }}>{t('cameras.timeLabel', 'Time')}</span>
                  <span style={{ fontWeight: 600, color: '#CBD5E1' }}>
                    {anomalyAlert ? formatAlertTime(anomalyAlert.detected_at || anomalyAlert.created_at) : t('cameras.liveMonitoringLabel', 'Live Monitoring')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add / Edit Camera Modal */}
      {isAddModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '1rem',
          }}
          onClick={() => setIsAddModalOpen(false)}
        >
          <div
            style={{
              backgroundColor: '#0F172A',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '12px',
              padding: '1.75rem',
              width: '480px',
              maxWidth: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#FFFFFF', margin: '0 0 1.15rem 0' }}>
              {editingCamId ? 'Edit Camera Configuration' : t('cameras.modalAddTitle', 'Add New Camera')}
            </h2>
            <form onSubmit={handleAddCameraSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>{t('cameras.modalCameraName', 'Camera Name')}</label>
                <input
                  type="text"
                  value={newCam.name}
                  onChange={(e) => setNewCam({ ...newCam, name: e.target.value })}
                  placeholder={t('cameras.modalCameraNamePlaceholder', 'e.g. Cam-05 North Gate')}
                  required
                  style={{
                    width: '100%',
                    backgroundColor: '#090E1A',
                    border: '1px solid #1E293B',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    color: '#FFFFFF',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>{t('cameras.modalSourceType', 'Source Type')}</label>
                  <select
                    value={newCam.source_type}
                    onChange={(e) => {
                      const nextType = e.target.value;
                      let nextSource = newCam.source;
                      if (nextType === 'browser') {
                        nextSource = selectedDeviceId || browserDevices[0]?.deviceId || '0';
                        refreshBrowserDevices();
                      } else if (nextType === 'webcam' && !/^\d+$/.test(nextSource)) nextSource = '0';
                      else if (nextType === 'rtsp' && !nextSource.startsWith('rtsp://')) nextSource = 'rtsp://192.168.1.50:554/stream1';
                      else if ((nextType === 'http' || nextType === 'ipcamera' || nextType === 'phone') && !nextSource.startsWith('http')) nextSource = 'http://192.168.1.60:8080/video';
                      setConnectionTestResult(null);
                      setNewCam({ ...newCam, source_type: nextType, source: nextSource });
                    }}
                    style={{
                      width: '100%',
                      backgroundColor: '#090E1A',
                      border: '1px solid #1E293B',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#FFFFFF',
                      outline: 'none',
                    }}
                  >
                    <option value="browser">{t('cameras.modalSourceBrowser', 'Browser Webcam (Laptop / Phone Camera)')}</option>
                    <option value="webcam">{t('cameras.modalSourceWebcam', 'USB / DirectShow Webcam')}</option>
                    <option value="rtsp">{t('cameras.modalSourceRtsp', 'IP Camera / RTSP Stream')}</option>
                    <option value="http">{t('cameras.modalSourceHttp', 'HTTP / MJPEG Stream')}</option>
                    <option value="ipcamera">{t('cameras.modalSourceNetworkIp', 'Network IP Camera')}</option>
                    <option value="phone">{t('cameras.modalSourceMobileIp', 'Mobile IP Webcam (URL Stream)')}</option>
                    <option value="video">{t('cameras.modalSourceLoopback', 'Video Loopback File')}</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>{t('cameras.modalLocation', 'Location / Zone')}</label>
                  <input
                    type="text"
                    value={newCam.location}
                    onChange={(e) => setNewCam({ ...newCam, location: e.target.value })}
                    placeholder={t('cameras.modalLocationPlaceholder', 'e.g. Building B Entrance')}
                    style={{
                      width: '100%',
                      backgroundColor: '#090E1A',
                      border: '1px solid #1E293B',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              {newCam.source_type === 'browser' ? (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px', gap: '8px' }}>
                    <label style={{ fontSize: '0.8rem', color: '#94A3B8' }}>
                      Browser Camera Device (navigator.mediaDevices)
                    </label>
                    <button
                      type="button"
                      onClick={requestBrowserCameraPermission}
                      style={{
                        background: 'rgba(16, 185, 129, 0.15)',
                        border: '1px solid rgba(16, 185, 129, 0.4)',
                        color: '#10B981',
                        borderRadius: '6px',
                        padding: '3px 8px',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Allow Camera / Refresh Devices
                    </button>
                  </div>
                  <select
                    value={newCam.source}
                    onChange={(e) => {
                      setSelectedDeviceId(e.target.value);
                      setNewCam({ ...newCam, source: e.target.value });
                    }}
                    style={{
                      width: '100%',
                      backgroundColor: '#090E1A',
                      border: '1px solid #1E293B',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#FFFFFF',
                      outline: 'none',
                    }}
                  >
                    {browserDevices.length > 0 ? (
                      browserDevices.map((d, idx) => (
                        <option key={d.deviceId || idx} value={d.deviceId || String(idx)}>
                          {d.label || `Browser Camera #${idx + 1} (Grant permission to show model name)`}
                        </option>
                      ))
                    ) : (
                      <option value="0">Default Browser Webcam (Click "Allow Camera" to detect devices)</option>
                    )}
                  </select>
                  <div style={{ marginTop: '6px', fontSize: '0.74rem', color: '#94A3B8' }}>
                    Streams directly from your browser into DeepVision YOLO + ByteTrack + Supabase storage (no server DirectShow required).
                  </div>
                </div>
              ) : (
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>
                    {newCam.source_type === 'webcam'
                      ? t('surveillance.sourceUrl', 'Device Index (0 = Default Webcam, 1 = External USB Camera)')
                      : t('surveillance.sourceUrl', 'Stream URL or Source Path')}
                  </label>
                  <input
                    type="text"
                    value={newCam.source}
                    onChange={(e) => setNewCam({ ...newCam, source: e.target.value })}
                    placeholder={
                      newCam.source_type === 'webcam'
                        ? '0'
                        : newCam.source_type === 'rtsp'
                        ? 'rtsp://192.168.1.50:554/stream1'
                        : 'http://192.168.1.60:8080/video'
                    }
                    required
                    style={{
                      width: '100%',
                      backgroundColor: '#090E1A',
                      border: '1px solid #1E293B',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      color: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                  {browserDevices.length > 0 && (newCam.source_type === 'webcam' || newCam.source_type === 'phone') && (
                    <div style={{ marginTop: '6px', fontSize: '0.75rem', color: '#94A3B8' }}>
                      {t('surveillance.hardwareBridge', 'Detected Browser Video Devices')}:{' '}
                      {browserDevices.map((d, idx) => d.label || `Camera #${idx}`).join(', ')}
                    </div>
                  )}
                </div>
              )}

              {(newCam.source_type === 'rtsp' || newCam.source_type === 'http' || newCam.source_type === 'ipcamera' || newCam.source_type === 'phone') && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>{t('auth.email', 'Stream Username (Optional)')}</label>
                    <input
                      type="text"
                      value={newCam.username}
                      onChange={(e) => setNewCam({ ...newCam, username: e.target.value })}
                      placeholder="admin"
                      autoComplete="off"
                      style={{
                        width: '100%',
                        backgroundColor: '#090E1A',
                        border: '1px solid #1E293B',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        color: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94A3B8', marginBottom: '4px' }}>{t('auth.password', 'Stream Password (Optional)')}</label>
                    <input
                      type="password"
                      value={newCam.password}
                      onChange={(e) => setNewCam({ ...newCam, password: e.target.value })}
                      placeholder="••••••••"
                      autoComplete="new-password"
                      style={{
                        width: '100%',
                        backgroundColor: '#090E1A',
                        border: '1px solid #1E293B',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        color: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                  </div>
                </div>
              )}

              {connectionTestResult && (
                <div
                  style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    backgroundColor: connectionTestResult.success ? 'rgba(16, 185, 129, 0.14)' : 'rgba(239, 68, 68, 0.14)',
                    border: `1px solid ${connectionTestResult.success ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
                    color: connectionTestResult.success ? '#10B981' : '#FCA5A5',
                  }}
                >
                  {connectionTestResult.message || (connectionTestResult.success ? 'Connection verified.' : 'Connection test failed.')}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', marginTop: '0.75rem' }}>
                <button
                  type="button"
                  onClick={handleTestModalConnection}
                  disabled={isTestingConnection}
                  style={{
                    backgroundColor: 'rgba(56, 189, 248, 0.14)',
                    border: '1px solid rgba(56, 189, 248, 0.35)',
                    color: '#38BDF8',
                    padding: '8px 14px',
                    borderRadius: '6px',
                    fontWeight: 700,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                  }}
                >
                  {isTestingConnection ? 'Testing...' : '⚡ Test Connection'}
                </button>

                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(false)}
                    style={{ backgroundColor: 'transparent', border: '1px solid rgba(255, 255, 255, 0.1)', color: '#94A3B8', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer' }}
                  >
                    {t('cameras.modalCancel', 'Cancel')}
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingCamera}
                    style={{
                      backgroundColor: '#2563EB',
                      border: 'none',
                      color: '#FFFFFF',
                      padding: '8px 18px',
                      borderRadius: '6px',
                      fontWeight: 700,
                      cursor: isSavingCamera ? 'wait' : 'pointer',
                      opacity: isSavingCamera ? 0.7 : 1,
                    }}
                  >
                    {isSavingCamera ? 'Saving...' : t('cameras.modalSave', 'Save Camera')}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Cameras;
