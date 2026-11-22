"""
Native Django Surveillance Camera Health Service.
Tracks camera runtime telemetry, display FPS, AI FPS, inference latency,
active stream counts, and operational health status.
"""

import threading
import datetime
from typing import Dict, Any, List

_health_registry: Dict[int, Dict[str, Any]] = {}
_health_lock = threading.Lock()


def update_camera_health(camera_id: int, status: str = None, stream_active: bool = None,
                          recording_active: bool = None, detection_active: bool = None,
                          tracking_active: bool = None, fps: float = None,
                          last_error: str = None, delta_stream_count: int = 0,
                          ai_fps: float = None, inference_latency_ms: float = None,
                          width: int = None, height: int = None):
    """
    Updates the runtime telemetry for a given camera.
    """
    with _health_lock:
        if camera_id not in _health_registry:
            _health_registry[camera_id] = {
                "camera_id": camera_id,
                "status": "offline",
                "stream_active": False,
                "last_frame_time": None,
                "fps": 0.0,
                "ai_fps": None,
                "inference_latency_ms": None,
                "recording_active": False,
                "detection_active": False,
                "tracking_active": False,
                "last_error": None,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "stream_count": 0,
                "width": None,
                "height": None
            }

        health = _health_registry[camera_id]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if delta_stream_count != 0:
            health["stream_count"] = max(0, health["stream_count"] + delta_stream_count)

        if status is not None:
            health["status"] = status

        if fps is not None:
            health["fps"] = round(fps, 1)
            health["last_frame_time"] = now_iso

        if ai_fps is not None:
            health["ai_fps"] = round(ai_fps, 1)

        if inference_latency_ms is not None:
            health["inference_latency_ms"] = round(inference_latency_ms, 1)

        if width is not None:
            health["width"] = width

        if height is not None:
            health["height"] = height

        if stream_active is not None:
            health["stream_active"] = stream_active
        if recording_active is not None:
            health["recording_active"] = recording_active
        if detection_active is not None:
            health["detection_active"] = detection_active
        if tracking_active is not None:
            health["tracking_active"] = tracking_active
        if last_error is not None:
            health["last_error"] = last_error

        # When stream count drops to 0, keep active only while worker is running and not offline/error
        if health["stream_count"] == 0:
            worker_alive = False
            try:
                from apps.surveillance.camera.registry import get_camera_registry
                worker = get_camera_registry().get_active_worker(camera_id)
                if worker and worker.running:
                    op = worker.get_operational_status() if hasattr(worker, "get_operational_status") else "ONLINE"
                    worker_alive = op in ("ONLINE", "CONNECTING", "RECONNECTING")
            except Exception:
                worker_alive = False

            if not worker_alive:
                health["stream_active"] = False
                health["detection_active"] = False
                health["tracking_active"] = False
                health["fps"] = 0.0
                health["ai_fps"] = None
                health["inference_latency_ms"] = None
                health["status"] = "offline"

        health["updated_at"] = now_iso


def get_live_camera_status(camera_id: int, worker=None) -> Dict[str, Any]:
    """
    Truthful live signal status derived strictly from the active CameraWorker
    and fresh-frame heartbeat (never trusts stale database `cameras.status`).
    """
    if worker is None:
        try:
            from apps.surveillance.camera.registry import get_camera_registry
            worker = get_camera_registry().get_active_worker(camera_id)
        except Exception:
            worker = None

    if worker is None or not getattr(worker, "running", False):
        return {
            "status": "offline",
            "live": False,
            "signal_state": "offline",
            "worker_running": False,
            "frame_age_sec": None,
        }

    op = worker.get_operational_status() if hasattr(worker, "get_operational_status") else "OFFLINE"
    frame_age_sec = worker.get_frame_age_seconds() if hasattr(worker, "get_frame_age_seconds") else None
    mapping = {
        "ONLINE": "online",
        "CONNECTING": "connecting",
        "RECONNECTING": "reconnecting",
        "STALE": "stale",
        "ERROR": "offline",
        "OFFLINE": "offline",
    }
    normalized = mapping.get(op, "offline")
    return {
        "status": normalized,
        "live": normalized == "online",
        "signal_state": str(op).lower(),
        "worker_running": True,
        "frame_age_sec": frame_age_sec,
    }


def get_camera_health(camera_id: int) -> Dict[str, Any]:
    """
    Returns a copy of the health stats synchronized with live worker & fresh-frame state.
    """
    with _health_lock:
        if camera_id in _health_registry:
            health = _health_registry[camera_id].copy()
        else:
            health = {
                "camera_id": camera_id,
                "status": "offline",
                "stream_active": False,
                "last_frame_time": None,
                "fps": 0.0,
                "ai_fps": None,
                "inference_latency_ms": None,
                "recording_active": False,
                "detection_active": False,
                "tracking_active": False,
                "last_error": None,
                "updated_at": None,
                "stream_count": 0,
                "width": None,
                "height": None
            }

    live_info = get_live_camera_status(camera_id)
    health["status"] = live_info["status"]
    health["signal_state"] = live_info["signal_state"]
    health["worker_running"] = live_info["worker_running"]
    health["frame_age_sec"] = live_info["frame_age_sec"]
    if live_info["status"] in ("offline", "connecting"):
        health["fps"] = 0.0
    if live_info["status"] == "offline":
        health["stream_active"] = False
        health["ai_fps"] = None
        health["inference_latency_ms"] = None
        health["detection_active"] = False
        health["tracking_active"] = False

    w = health.get("width")
    h = health.get("height")
    if w and h:
        health["resolution"] = f"{w} × {h}"
    else:
        health["resolution"] = "Native HD"

    if health.get("detection_active") or health.get("tracking_active"):
        if health.get("last_error") and "inference" in str(health.get("last_error")).lower():
            health["ai_state"] = "ERROR"
        elif health.get("inference_latency_ms") is not None and health.get("inference_latency_ms") > 600:
            health["ai_state"] = "DEGRADED"
        elif health.get("ai_fps") is not None and health.get("ai_fps") > 0:
            health["ai_state"] = "RUNNING"
        else:
            health["ai_state"] = "STARTING"
    else:
        health["ai_state"] = "IDLE"

    return health


def get_user_cameras_health(camera_ids: List[int]) -> List[Dict[str, Any]]:
    """Returns a bulk list of health states for a list of camera IDs."""
    return [get_camera_health(cid) for cid in camera_ids]
