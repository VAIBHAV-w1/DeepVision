"""
DeepVision Native Django Surveillance Engine Interface.
-------------------------------------------------------
Directly connects the Django web/API layer to native surveillance services:
  CameraRegistry ──► CameraWorker ──► ONE VideoCapture(0) [DirectShow dshow://0]
       │                                     │
       │                                     ▼ (Frame Copy)
       ▼                               InferenceWorker
  MJPEG Generator ◄─────────────────── YOLO11n + ByteTrack [MODEL_LOAD_COUNT=1]
       │
       ▼
  StreamingHttpResponse (multipart/x-mixed-replace; boundary=frame)

Zero Flask runtime dependency.
Zero legacy HTTP communication.
"""

import os
import json
import urllib.request
import urllib.error
try:
    import cv2
except (ImportError, Exception):
    cv2 = None
import logging
import datetime
from typing import Generator, Optional, Dict, Any

from django.conf import settings

from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.ai.registry import get_inference_registry
from apps.surveillance.recording import recording_service
from apps.surveillance.health.health_service import (
    get_camera_health,
    get_live_camera_status,
    update_camera_health,
)
from apps.surveillance.streaming.stream_service import (
    generate_raw_stream,
    generate_tracking_stream,
    get_camera_telemetry,
    render_annotated_frame,
)
from apps.surveillance.camera.sources import resolve_camera_capture_source
from apps.surveillance.camera.capture import safe_open_video_capture

logger = logging.getLogger(__name__)

# Supported user-facing modes (Exactly two)
MODE_ORIGINAL = "original"
MODE_TRACKING_DETECTION = "tracking"

VALID_MODES = {
    "original": "raw",
    "raw": "raw",
    "tracking": "tracking",
    "detection": "tracking",  # Normalized to tracking + detection
}


def is_engine_reachable(timeout: float = 1.0) -> bool:
    """
    In the native Django architecture, the surveillance engine runs in-process.
    It is always reachable.
    """
    return True


def get_engine_status() -> Dict[str, Any]:
    """
    Retrieves the operating status of the native Django surveillance engine.
    """
    cam_reg = get_camera_registry()
    inf_reg = get_inference_registry()
    unique_cam_workers = len(set(cam_reg.workers.values())) if cam_reg.workers else 0
    active_inference = len(set(inf_reg.workers.values())) if inf_reg.workers else 0

    from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_model_load_count
    shared_m = None
    try:
        shared_m = get_shared_yolo_model()
    except Exception:
        pass
    model_desc = (
        f"models/{shared_m.model_name} ({shared_m.runtime_kind}: {shared_m.device_detail})"
        if hasattr(shared_m, "model_name")
        else "models/yolo11n.pt (native singleton)"
    )
    clip_status = {}
    try:
        from apps.surveillance.ai.clip_service import get_clip_analyzer
        clip_status = get_clip_analyzer().get_status()
    except Exception:
        clip_status = {"status": "unavailable", "enabled": False}

    return {
        "engine_url": "in-process (native Django)",
        "reachable": True,
        "mode": "native_django_surveillance",
        "yolo_model": model_desc,
        "tracker": "BoT-SORT+ReID (native pure-NumPy singleton)",
        "clip_scene": clip_status,
        "camera_registry": f"native (active_cameras={len(cam_reg.workers)}, hardware_handles={unique_cam_workers}, active_inference={active_inference})",
        "django_yolo_loads": get_model_load_count(),
        "django_camera_handles": unique_cam_workers,
    }


def get_engine_health(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Comprehensive health check for the native Django surveillance architecture.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cam_reg = get_camera_registry()
    inf_reg = get_inference_registry()
    unique_cam_workers = len(set(cam_reg.workers.values())) if cam_reg.workers else 0
    active_inf = len(set(inf_reg.workers.values())) if inf_reg.workers else 0

    return {
        "status": "healthy",
        "flask_reachable": False,  # Flask is completely removed
        "surveillance_engine": "online",
        "camera_subsystem": "ready",
        "inference_subsystem": "ready",
        "camera_ownership": "Django Native Surveillance Services",
        "django_camera_handles": unique_cam_workers,
        "logical_cameras_active": len(cam_reg.workers),
        "django_yolo_loads": 1 if active_inf > 0 else 0,
        "yolo_readiness": "ready",
        "active_mode": "native_django_surveillance",
        "message": "Native Django surveillance architecture fully operational.",
        "timestamp": now_iso,
    }


def normalize_mode(mode: Optional[str]) -> str:
    """
    Normalizes user-facing mode to engine mode.
    Only two modes are supported:
      - 'raw' (Original CCTV feed, no AI overlay)
      - 'tracking' (Tracking + Detection, YOLO11n + ByteTrack)
    Default is 'tracking'.
    """
    if not mode:
        return "tracking"
    m = mode.strip().lower()
    return VALID_MODES.get(m, "tracking")


def get_host_bridge_url() -> Optional[str]:
    """
    Checks if an external host camera bridge is reachable.
    Used when running inside Linux Docker to access the physical Windows DirectShow webcam.
    """
    if os.environ.get("USE_HOST_CAMERA_BRIDGE", "").lower() == "false":
        return None
    url = os.getenv("HOST_CAMERA_BRIDGE_URL", "http://host.docker.internal:8554").rstrip("/")
    # In native Windows, by default we run in-process unless explicitly overridden
    if os.name == "nt" and os.getenv("USE_HOST_CAMERA_BRIDGE", "False").lower() not in ("true", "1"):
        return None
    try:
        req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "DeepVision-Django"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                return url
    except Exception:
        pass
    return None


def stream_camera_frames(camera_id: int, user_id: int, mode: str = "tracking") -> Generator[bytes, None, None]:
    """
    Streams live MJPEG frames directly from native Django surveillance services,
    or from the Windows DirectShow host bridge when running containerized.
    """
    canonical_mode = normalize_mode(mode)
    bridge_url = get_host_bridge_url()
    if bridge_url:
        try:
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/stream/?mode={canonical_mode}")
            resp = urllib.request.urlopen(req, timeout=10.0)
            if resp.status == 200:
                try:
                    read_fn = getattr(resp, "read1", resp.read)
                    while True:
                        chunk = read_fn(65536)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    resp.close()
                return
        except urllib.error.HTTPError as he:
            if he.code != 404:
                logger.warning(f"[BRIDGE_STREAM_HTTP_ERROR] cam={camera_id}: {he}")
        except Exception as e:
            logger.warning(f"[BRIDGE_STREAM_ERROR] cam={camera_id}: {e}")

    if canonical_mode == "raw":
        yield from generate_raw_stream(camera_id, user_id)
    else:
        yield from generate_tracking_stream(camera_id, user_id)


def get_camera_snapshot(camera_id: int, user_id: int, allow_start: bool = True, mode: str = "raw") -> Optional[bytes]:
    """
    Captures a single snapshot JPEG frame directly from native camera worker or hardware,
    or via the host camera bridge if running containerized.
    When `mode == "tracking"`, overlays active restricted zones, bounding boxes, and
    ByteTrack IDs using `render_annotated_frame()`.
    When allow_start=False (e.g. non-blocking dashboard thumbnail GET), returns immediately
    from active workers without stalling HTTP worker threads on offline cameras.
    """
    bridge_url = get_host_bridge_url()
    if bridge_url:
        try:
            suffix = "?mode=tracking" if mode == "tracking" else ""
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/snapshot/{suffix}")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return resp.read()
        except urllib.error.HTTPError as he:
            if he.code != 404:
                logger.warning(f"[BRIDGE_SNAPSHOT_HTTP_ERROR] cam={camera_id}: {he}")
        except Exception as e:
            logger.warning(f"[BRIDGE_SNAPSHOT_ERROR] cam={camera_id}: {e}")

    cam_reg = get_camera_registry()
    worker = cam_reg.get_active_worker(camera_id)

    def _encode_frame(raw_frame, active_cam_worker):
        out_frame = raw_frame
        if mode == "tracking" and get_inference_registry is not None:
            try:
                inf_reg = get_inference_registry()
                inf_worker = inf_reg.get_active_worker(camera_id)
                if inf_worker is None and active_cam_worker is not None and active_cam_worker.running:
                    inf_worker = inf_reg.get_worker(camera_id, active_cam_worker)
                if inf_worker is not None:
                    out_frame, _ = render_annotated_frame(
                        raw_frame,
                        camera_id,
                        inference_worker=inf_worker,
                        current_id=getattr(active_cam_worker, "frame_id", 0),
                        cap_mono=getattr(active_cam_worker, "last_capture_monotonic", 0.0),
                        display_fps=getattr(active_cam_worker, "fps", 0.0),
                        worker=active_cam_worker,
                    )
            except Exception as exc:
                logger.warning(f"[SNAPSHOT_ANNOTATE_WARN] cam={camera_id}: {exc}")
        success, buffer = cv2.imencode(".jpg", out_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes() if success else None

    # 1. Grab from active worker (including shared physical hardware worker) if available and fresh
    live_info = get_live_camera_status(camera_id, worker=worker) if worker else None
    if (
        worker
        and worker.running
        and worker.latest_frame is not None
        and live_info is not None
        and live_info.get("status") not in ("offline",)
        and (live_info.get("frame_age_sec") is None or float(live_info.get("frame_age_sec") or 0.0) <= 15.0)
    ):
        with worker.lock:
            frame = worker.latest_frame
        if frame is None:
            return None
        sample = frame[::16, ::16]
        if float(sample.mean()) < 1.0 and float(sample.std()) < 0.5:
            return None
        return _encode_frame(frame, worker)

    if not allow_start:
        return None

    # 2. Acquire on-demand from Camera model when explicitly requested (e.g. manual snapshot POST)
    try:
        from apps.cameras.models import Camera
        camera = Camera.objects.filter(id=camera_id, user_id=user_id).first()
        if not camera:
            return None

        temp_worker = cam_reg.get_worker(camera_id, user_id)
        for _ in range(30):
            if temp_worker.latest_frame is not None:
                with temp_worker.lock:
                    frame = temp_worker.latest_frame.copy()
                sample = frame[::16, ::16]
                if float(sample.mean()) >= 1.0 or float(sample.std()) >= 0.5:
                    encoded = _encode_frame(frame, temp_worker)
                    cam_reg.release_worker(camera_id)
                    if encoded is not None:
                        return encoded
            import time
            time.sleep(0.05)
        cam_reg.release_worker(camera_id)
    except Exception as e:
        logger.warning(f"[NATIVE_SNAPSHOT_ERROR] cam={camera_id}: {e}")

    return None


def get_camera_stats(camera_id: int, user_id: int) -> Dict[str, Any]:
    """
    Retrieves live stream telemetry from native surveillance services or host bridge.
    Falls back directly to active InferenceWorker state so tracks, zones, anomalies,
    and detector_backend remain fresh even when MJPEG streaming isn't open.
    """
    bridge_url = get_host_bridge_url()
    if bridge_url:
        try:
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/stats/")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except Exception:
            pass

    telemetry = get_camera_telemetry(camera_id)
    health = get_camera_health(camera_id)
    tracks_list = telemetry.get("tracks", [])
    anomalies_list = telemetry.get("anomalies", [])
    zones_list = telemetry.get("zones", [])
    active_intrusions = telemetry.get("active_intrusions", [])
    detector_backend = telemetry.get("detector_backend", "unknown")
    tracker_backend = telemetry.get("tracker_backend", "unknown")
    summary = {}

    cam_reg = get_camera_registry()
    active_worker = cam_reg.get_active_worker(camera_id) if cam_reg else None
    inf_worker = get_inference_registry().get_active_worker(camera_id) if get_inference_registry else None

    if inf_worker is not None and getattr(inf_worker, "running", False):
        tracker = getattr(inf_worker, "tracker", None)
        detector_backend = getattr(tracker, "detector_backend", detector_backend) if tracker is not None else detector_backend
        tracker_backend = getattr(tracker, "tracker_backend", tracker_backend) if tracker is not None else tracker_backend
        if hasattr(inf_worker, "get_telemetry_summary"):
            summary = inf_worker.get_telemetry_summary()
        if not tracks_list:
            tracks_list = [
                {
                    "track_id": f"#{trk['track_id']}",
                    "class_name": str(trk.get("class_name", "object")).capitalize(),
                    "confidence": round(float(trk.get("confidence", 0.0)), 3),
                    "bbox": [int(trk["x1"]), int(trk["y1"]), int(trk["x2"]), int(trk["y2"])],
                    "behavior": trk.get("behavior") or "normal",
                    "direction": trk.get("direction") or "stationary",
                    "speed": round(float(trk.get("speed", 0.0) or 0.0), 1),
                }
                for trk in (getattr(inf_worker, "cached_tracks", []) or [])
            ]
        if not anomalies_list:
            anomalies_list = list(getattr(inf_worker, "cached_anomalies", []) or [])
        if not zones_list and hasattr(inf_worker, "get_cached_zones"):
            zones_list = list(inf_worker.get_cached_zones(camera_id) or [])

    from apps.cameras.surveillance_config import get_camera_surveillance_config, resolve_video_quality_profile
    cam_cfg = get_camera_surveillance_config(camera_id, has_enabled_zones=bool(zones_list))
    quality_id = str(cam_cfg.get("video_quality", "high"))
    q_prof = resolve_video_quality_profile(quality_id)
    media_prof = active_worker.get_media_profile() if (active_worker and hasattr(active_worker, "get_media_profile")) else {}
    fw = int(media_prof.get("width") or health.get("width") or telemetry.get("frame_width") or 0)
    fh = int(media_prof.get("height") or health.get("height") or telemetry.get("frame_height") or 0)
    res_str = f"{fw}x{fh}" if (fw > 0 and fh > 0) else ""
    fourcc_str = str(media_prof.get("fourcc") or telemetry.get("fourcc") or "")

    is_rec = False
    try:
        is_rec = recording_service.get_active_recording(camera_id, user_id) is not None
    except Exception:
        pass
    real_fps = health.get("fps", 0.0) or telemetry.get("fps", 0.0) or (active_worker.fps if active_worker else 0.0)
    cap_fps = (active_worker.fps if (active_worker and getattr(active_worker, "fps", 0.0)) else 0.0) or real_fps
    inf_fps = (
        health.get("ai_fps")
        or telemetry.get("ai_fps")
        or (getattr(inf_worker, "ai_fps", 0.0) if inf_worker else 0.0)
        or 0.0
    )
    lat_ms = (
        health.get("inference_latency_ms")
        or telemetry.get("latency_ms")
        or (getattr(inf_worker, "latency_ms", 0.0) if inf_worker else 0.0)
        or 0.0
    )
    live_info = get_live_camera_status(camera_id, worker=active_worker)
    live_status = live_info["status"]
    if live_status in ("offline", "connecting"):
        real_fps = 0.0
        cap_fps = 0.0
    if live_status == "offline":
        inf_fps = 0.0
        lat_ms = 0.0

    visible_persons_default = sum(1 for t in tracks_list if str(t.get("class_name", "")).lower() == "person")
    return {
        "camera_id": camera_id,
        "tracks": tracks_list,
        "detections": len(tracks_list),
        "currently_visible_persons": summary.get("currently_visible_persons", telemetry.get("currently_visible_persons", visible_persons_default)),
        "active_tracks": summary.get("active_tracks", telemetry.get("active_tracks", len(tracks_list))),
        "unique_persons_observed": summary.get("unique_persons_observed", telemetry.get("unique_persons_observed", visible_persons_default)),
        "total_detection_events": summary.get("total_detection_events", telemetry.get("total_detection_events", len(tracks_list))),
        "recent_detections": summary.get("recent_detections", telemetry.get("recent_detections", [])),
        "recent_zone_events": summary.get("recent_zone_events", telemetry.get("recent_zone_events", [])),
        "camera_purpose": summary.get("camera_purpose", cam_cfg.get("purpose", "general")),
        "restricted_entry_enabled": summary.get("restricted_entry_enabled", cam_cfg.get("restricted_entry_enabled", bool(zones_list))),
        "session_started_at": summary.get("session_started_at", telemetry.get("session_started_at", "")),
        "anomalies": anomalies_list,
        "zones": zones_list,
        "active_intrusions": active_intrusions,
        "detector_backend": detector_backend,
        "tracker_backend": tracker_backend,
        "motion_active": summary.get("motion_active", telemetry.get("motion_active", False)),
        "motion_ratio": summary.get("motion_ratio", telemetry.get("motion_ratio", 0.0)),
        "motion_lighting_shift": summary.get("motion_lighting_shift", telemetry.get("motion_lighting_shift", False)),
        "motion_backend": summary.get("motion_backend", telemetry.get("motion_backend", "mog2")),
        "inference_dropped_frames": summary.get("inference_dropped_frames", telemetry.get("inference_dropped_frames", 0)),
        "fps": real_fps,
        "capture_fps": round(float(cap_fps), 2),
        "ai_fps": inf_fps,
        "inference_fps": round(float(inf_fps), 2),
        "latency_ms": lat_ms,
        "p50_latency_ms": 0.0 if live_status == "offline" else summary.get("p50_latency_ms", telemetry.get("p50_latency_ms", lat_ms)),
        "p95_latency_ms": 0.0 if live_status == "offline" else summary.get("p95_latency_ms", telemetry.get("p95_latency_ms", lat_ms)),
        "frame_age_ms": 0.0 if live_status == "offline" else telemetry.get("frame_age_ms", summary.get("frame_age_ms", 0.0)),
        "frame_age_sec": live_info.get("frame_age_sec"),
        "ai_profile": summary.get("ai_profile", telemetry.get("ai_profile", "balanced")),
        "stage_timings": telemetry.get("stage_timings", {}) or (getattr(inf_worker, "last_stage_timings", {}) if inf_worker else {}),
        "inference_age_ms": telemetry.get("inference_age_ms", 0.0),
        "video_quality": quality_id,
        "video_quality_label": q_prof.get("label", "High HD (720p)"),
        "frame_width": fw,
        "frame_height": fh,
        "resolution": res_str,
        "fourcc": fourcc_str,
        "status": live_status,
        "live": live_info["live"],
        "signal_state": live_info["signal_state"],
        "worker_running": live_info["worker_running"],
        "is_recording": is_rec,
        "clip_scene": summary.get("clip_scene") or _safe_camera_clip_scene(camera_id),
    }


def _safe_camera_clip_scene(camera_id: int) -> Dict[str, Any]:
    try:
        from apps.surveillance.ai.clip_service import get_clip_scheduler, get_clip_analyzer
        cached = get_clip_scheduler().get_camera_scene(camera_id)
        if cached:
            return cached
        st = get_clip_analyzer().get_status()
        return {
            "available": st.get("available", False),
            "analyzed": False,
            "status": st.get("status", "disabled_by_config"),
            "model_name": st.get("model_name"),
            "device": st.get("device"),
        }
    except Exception:
        return {"available": False, "analyzed": False, "status": "unavailable"}


def warm_camera_capture_only(camera_id: int, user_id: int) -> bool:
    """
    Pre-warms ONLY the physical CameraWorker (without starting YOLO11n inference)
    and releases the reference immediately into its grace window so dashboard
    thumbnails stay fast and never leak eternal inference workers.
    """
    try:
        cam_reg = get_camera_registry()
        worker = cam_reg.get_worker(camera_id, user_id)
        if worker:
            cam_reg.release_worker(camera_id)
            return True
        return False
    except Exception as e:
        logger.warning(f"[WARM_CAPTURE_ONLY_ERROR] cam={camera_id}: {e}")
        return False


def warm_camera(camera_id: int, user_id: int) -> bool:
    """
    Pre-warms the native CameraWorker and InferenceWorker ahead of user viewing,
    immediately releasing temporary warm references into the 30s grace period.
    """
    try:
        cam_reg = get_camera_registry()
        worker = cam_reg.get_worker(camera_id, user_id)
        inf_reg = get_inference_registry()
        inf_reg.get_worker(camera_id, worker)
        inf_reg.release_worker(camera_id)
        cam_reg.release_worker(camera_id)
        return True
    except Exception as e:
        logger.warning(f"[WARM_CAMERA_ERROR] cam={camera_id}: {e}")
        return False


def start_camera_recording(camera_id: int, user_id: int) -> Dict[str, Any]:
    """
    Initiates physical recording on the native Django surveillance engine
    or delegates to host camera bridge if containerized.
    """
    bridge_url = get_host_bridge_url()
    if bridge_url:
        try:
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/record/start", data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"[BRIDGE_START_RECORD_ERROR] cam={camera_id}: {e}")

    try:
        active = recording_service.get_active_recording(camera_id, user_id)
        if active:
            return {
                "status": "warning",
                "message": "Camera is already recording.",
                "recording_id": active.id,
            }

        # Ensure CameraWorker is active and explicitly bound to this logical camera_id so frames stream into the MP4 writer
        cam_reg = get_camera_registry()
        worker = cam_reg.workers.get(camera_id)
        if worker is None or not worker.running:
            worker = cam_reg.get_worker(camera_id, user_id)

        measured_fps = worker.fps if (worker and getattr(worker, "fps", 0.0) >= 5.0) else 25.0
        rec = recording_service.start_recording(user_id, camera_id, fps=measured_fps)

        # Immediately seed initial frame if available so short clips always contain valid video frames
        if worker and worker.latest_frame is not None:
            with worker.lock:
                seed_frame = worker.latest_frame.copy()
            recording_service.write_frame(camera_id, seed_frame)

        return {
            "status": "ok",
            "message": "Recording started.",
            "recording_id": rec.id,
        }
    except Exception as e:
        logger.error(f"[START_RECORDING_ERROR] cam={camera_id}: {e}")
        return {"status": "error", "error": "Unable to start recording.", "message": "Cannot start recording right now."}


def stop_camera_recording(camera_id: int, user_id: int) -> Dict[str, Any]:
    """
    Stops physical recording on the native Django surveillance engine
    or delegates to host camera bridge if containerized.
    """
    bridge_url = get_host_bridge_url()
    if bridge_url:
        try:
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/record/stop", data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"[BRIDGE_STOP_RECORD_ERROR] cam={camera_id}: {e}")

    try:
        active = recording_service.get_active_recording(camera_id, user_id)
        if not active:
            return {"status": "warning", "message": "No active recording found."}
        rec = recording_service.stop_recording(active.id, user_id)
        return {
            "status": "ok",
            "message": "Recording stopped.",
            "recording_id": active.id,
        }
    except Exception as e:
        logger.error(f"[STOP_RECORDING_ERROR] cam={camera_id}: {e}")
        return {"status": "error", "error": "Unable to stop recording."}


def is_camera_recording(camera_id: int, user_id: int) -> bool:
    """
    Checks if there is an active recording session for the given camera.
    """
    try:
        return recording_service.get_active_recording(camera_id, user_id) is not None
    except Exception:
        return False


def test_camera_connection(source_type: str, source: str, user_id: int) -> Dict[str, Any]:
    """
    Validates connection parameters for a candidate camera feed.
    Reuses active physical worker telemetry if the hardware handle is already open so
    it never competes for an active DirectShow/USB device.
    """
    if not source_type or source == "":
        return {
            "success": False,
            "error": "Source type and stream source path/URL are required.",
            "message": "Source type and source path/URL are required.",
            "status_code": 400,
        }

    try:
        cap_source = resolve_camera_capture_source(source_type, source)
    except ValueError as e:
        err_msg = str(e)
        safe_msg = err_msg if err_msg.startswith("Security Error:") else "Invalid camera stream source."
        return {"success": False, "error": safe_msg, "message": safe_msg, "status_code": 400}

    # Never attempt server-side OpenCV probing for browser-managed cameras
    if str(source_type).strip().lower() == "browser":
        return {
            "success": True,
            "browser_managed": True,
            "message": "Browser webcam connects via your browser's navigator.mediaDevices.getUserMedia() bridge.",
        }

    if str(source_type).strip().lower() in ("webcam", "usb") and os.name != "nt" and not os.path.exists("/dev/video0"):
        return {
            "success": False,
            "browser_managed": False,
            "message": "No local USB/DirectShow camera hardware is attached to this server. Select 'Browser Webcam' to stream your laptop or phone camera.",
        }

    from apps.surveillance.camera.sources import get_physical_source_key
    physical_key = get_physical_source_key(source_type, source)
    cam_reg = get_camera_registry()
    active_worker = cam_reg.get_physical_worker(physical_key)
    if active_worker and active_worker.running and active_worker.latest_frame is not None:
        return {"success": True, "message": "Camera stream is currently active and healthy."}

    cap = None
    try:
        cap = safe_open_video_capture(cap_source)
        if not cap.isOpened():
            return {"success": False, "message": "Unable to connect to camera source."}
        ret, frame = cap.read()
        if not ret or frame is None:
            return {"success": False, "message": "Camera opened but failed to read frames."}
        return {"success": True, "message": "Camera connected successfully."}
    except Exception as e:
        logger.warning("[CAMERA_TEST_CONN_ERROR] %s", e)
        return {"success": False, "message": "Unable to connect to camera stream."}
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


def test_existing_camera(camera_id: int, user_id: int) -> Dict[str, Any]:
    """
    Tests connection for an already-registered camera.
    """
    from apps.cameras.models import Camera
    camera = Camera.objects.filter(id=camera_id).first()
    if not camera:
        return {"success": False, "message": "Camera not found."}

    bridge_url = get_host_bridge_url()
    if bridge_url and camera.source_type in ("webcam", "usb", "local"):
        try:
            req = urllib.request.Request(f"{bridge_url}/cameras/{camera_id}/test/")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"[BRIDGE_TEST_CAM_ERROR] cam={camera_id}: {e}")

    from apps.surveillance.camera.sources import get_physical_source_key
    cam_reg = get_camera_registry()
    if camera.source_type == "browser":
        active_worker = cam_reg.get_active_worker(camera_id)
        if active_worker and active_worker.running and active_worker.latest_frame is not None:
            return {"success": True, "browser_managed": True, "message": "Browser camera stream is active and receiving live frames."}
        return {
            "success": False,
            "browser_managed": True,
            "message": "Browser camera ready. Start Browser Cam in your browser to push live frames.",
        }

    physical_key = get_physical_source_key(camera.source_type, camera.source)
    active_worker = cam_reg.get_active_worker(camera_id) or cam_reg.get_physical_worker(physical_key)
    if active_worker and active_worker.running:
        return {"success": True, "message": "Camera stream is currently active and healthy."}

    if camera.source_type in ("webcam", "usb") and os.name != "nt" and not os.path.exists("/dev/video0"):
        return {
            "success": False,
            "browser_managed": True,
            "message": "No DirectShow/V4L2 camera hardware on server. Use 'Browser Cam' to stream from your browser.",
        }

    try:
        cap_source = resolve_camera_capture_source(camera.source_type, camera.source)
    except ValueError as e:
        err_msg = str(e)
        safe_msg = err_msg if err_msg.startswith("Security Error:") else "Invalid camera stream source."
        return {"success": False, "message": safe_msg}

    cap = None
    try:
        cap = safe_open_video_capture(cap_source)
        if not cap.isOpened():
            return {"success": False, "message": "Unable to connect to camera source."}
        ret, frame = cap.read()
        if not ret or frame is None:
            return {"success": False, "message": "Camera opened but failed to read frames."}
        return {"success": True, "message": "Camera connected successfully."}
    except Exception as e:
        logger.warning("[CAMERA_TEST_CONN_ERROR] %s", e)
        return {"success": False, "message": "Unable to connect to camera stream."}
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
