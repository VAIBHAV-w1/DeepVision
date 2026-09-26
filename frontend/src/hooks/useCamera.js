import { useState, useEffect, useCallback, useRef } from 'react';
import { cameraService } from '../services/camera';
import { STREAM_MODES } from '../utils/constants';

export function useCamera(cameraId) {
  const [camera, setCamera] = useState(null);
  const [mode, setMode] = useState(STREAM_MODES.TRACKING_DETECTION); // Default: tracking
  const [isRecording, setIsRecording] = useState(false);
  const [stats, setStats] = useState({ fps: 0, detections: 0, latency_ms: 0, tracks: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const statsTimerRef = useRef(null);

  const fetchCamera = useCallback(async () => {
    if (!cameraId) return;
    try {
      setLoading(true);
      const data = await cameraService.get(cameraId);
      if (data && data.camera) {
        setCamera(data.camera);
        setIsRecording(!!data.is_recording);
      }
      setError(null);
    } catch (e) {
      setError(e.message || 'Failed to load camera details');
    } finally {
      setLoading(false);
    }
  }, [cameraId]);

  const fetchStats = useCallback(async () => {
    if (!cameraId) return;
    try {
      const data = await cameraService.getStats(cameraId);
      if (data) {
        setStats(data);
        if (typeof data.is_recording === 'boolean') {
          setIsRecording(data.is_recording);
        }
      }
    } catch (e) {
      // Telemetry error is silent during stream
    }
  }, [cameraId]);

  useEffect(() => {
    fetchCamera();
  }, [fetchCamera]);

  useEffect(() => {
    if (!cameraId) return;
    statsTimerRef.current = setInterval(fetchStats, 2000);
    return () => {
      if (statsTimerRef.current) clearInterval(statsTimerRef.current);
    };
  }, [cameraId, fetchStats]);

  const toggleMode = (newMode) => {
    if (newMode === STREAM_MODES.ORIGINAL || newMode === STREAM_MODES.TRACKING_DETECTION) {
      setMode(newMode);
    }
  };

  const startRecording = async () => {
    try {
      const res = await cameraService.startRecording(cameraId);
      if (res && (res.status === 'recording_started' || res.status === 'ok')) {
        setIsRecording(true);
        return { success: true, message: res.message || 'Recording started' };
      }
      return { success: false, message: res?.message || res?.error || 'Failed to start recording' };
    } catch (e) {
      return { success: false, message: e.message };
    }
  };

  const stopRecording = async () => {
    try {
      const res = await cameraService.stopRecording(cameraId);
      if (res && (res.status === 'recording_stopped' || res.status === 'ok')) {
        setIsRecording(false);
        return { success: true, message: 'Recording saved' };
      }
      return { success: false, message: res?.error || 'Failed to stop recording' };
    } catch (e) {
      return { success: false, message: e.message };
    }
  };

  const takeSnapshot = () => {
    const url = cameraService.getSnapshotUrl(cameraId);
    window.open(url, '_blank');
  };

  return {
    camera,
    mode,
    isRecording,
    stats,
    loading,
    error,
    toggleMode,
    startRecording,
    stopRecording,
    takeSnapshot,
    refreshCamera: fetchCamera,
    streamUrl: cameraService.getStreamUrl(cameraId, mode),
  };
}

export default useCamera;
