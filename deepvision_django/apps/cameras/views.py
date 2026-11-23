"""
Django Camera Views & Streaming Endpoints.
Phase 5: Django Camera + AI Integration Layer.
Connects Django to the canonical DeepVision surveillance engine without
instantiating duplicate CameraWorker or YOLO11n models.
"""

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse, Http404
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import login_required
from apps.core.audit import log_audit
from apps.cameras.models import Camera, CameraGroup, SurveillancePreset
from apps.ai.engine import (
    stream_camera_frames,
    get_camera_snapshot,
    get_camera_stats,
    warm_camera,
    get_engine_status,
    get_engine_health,
    is_engine_reachable,
    normalize_mode,
    start_camera_recording,
    stop_camera_recording,
    is_camera_recording,
    test_camera_connection,
    test_existing_camera,
    MODE_ORIGINAL,
    MODE_TRACKING_DETECTION
)

logger = logging.getLogger(__name__)


def _is_viewer_role(user) -> bool:
    return getattr(user, "role", "") == "viewer" and not getattr(user, "is_superuser", False)


def _get_writable_camera_or_403(user, camera_id):
    if _is_viewer_role(user):
        return None, JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    try:
        return get_user_camera_or_404(user, camera_id, require_write=True), None
    except PermissionDenied as exc:
        return None, JsonResponse({"success": False, "error": str(exc)}, status=403)


def get_accessible_cameras_qs(user):
    """
    Returns queryset of active cameras accessible to user:
    - Admin/Supervisor/Operator: all active SOC cameras.
    - Standard user: strictly their own personal cameras plus shared facility staff cameras
      (never another standard user's private cameras).
    """
    from django.db.models import Q
    base_qs = Camera.objects.filter(is_active=True)
    is_staff_role = getattr(user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(user, 'is_superuser', False)
    if is_staff_role:
        return base_qs.order_by('id')

    return base_qs.filter(
        Q(user_id=user.id) | Q(user__role__in=('admin', 'supervisor', 'operator'))
    ).order_by('id')


def get_user_camera_or_404(user, camera_id, require_write=False):
    """
    Safely resolves camera object with strict RBAC and multi-tenant BOLA/IDOR enforcement:
    - Write mutations (require_write=True): privileged staff or the personal owner of the camera (403 otherwise).
    - Read/stream/record access: strictly scoped to get_accessible_cameras_qs(user) (404 otherwise).
    """
    is_staff_role = getattr(user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(user, 'is_superuser', False)
    camera = get_object_or_404(Camera, id=camera_id)

    if require_write:
        if _is_viewer_role(user):
            raise PermissionDenied("Viewer accounts have read-only access.")
        if camera.user_id == user.id or is_staff_role:
            return camera
        raise PermissionDenied("Insufficient privileges to modify this camera or its security zones.")

    if camera.user_id == user.id:
        return camera
    if get_accessible_cameras_qs(user).filter(id=camera_id).exists():
        return camera
    raise Http404("Camera not found.")


@never_cache
@login_required
def camera_list_view(request):
    """
    Renders camera dashboard list for the authenticated user.
    """
    cameras_qs = get_accessible_cameras_qs(request.user)
    status_filter = request.GET.get('status', 'all').strip().lower()
    if status_filter in ('online', 'offline'):
        cameras_qs = cameras_qs.filter(status=status_filter)
        
    cameras = list(cameras_qs)
    engine_status = get_engine_status()

    return render(request, 'pages/cameras/index.html', {
        'cameras': cameras,
        'engine_status': engine_status,
        'active_filter': status_filter,
    })


@never_cache
@login_required
def camera_preview_view(request, camera_id):
    """
    Renders the live surveillance preview UI for a specific camera.
    User-facing modes: Exactly TWO modes:
      1. ORIGINAL (plain raw CCTV frame, no YOLO/tracking overlay)
      2. TRACKING + DETECTION (YOLO11n + ByteTrack overlay - DEFAULT)
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    
    # Mode selection: 'raw'/'original' vs 'tracking' (Default)
    mode_param = request.GET.get('mode', 'tracking').strip().lower()
    if mode_param in ('raw', 'original'):
        active_mode = 'raw'
    else:
        active_mode = 'tracking'

    # Check canonical engine reachability
    engine_reachable = is_engine_reachable(timeout=1.0)
    preview_available = engine_reachable and (camera.status == 'online' or camera.is_active)

    # Fetch related camera assets
    recordings_count = camera.recordings.filter(user_id=camera.user_id).count()
    alerts_count = camera.alerts.filter(user_id=camera.user_id).count()
    recent_recordings = list(camera.recordings.filter(user_id=camera.user_id).order_by('-id')[:5])
    recent_alerts = list(camera.alerts.filter(user_id=camera.user_id).order_by('-id')[:5])

    return render(request, 'pages/cameras/preview.html', {
        'camera': camera,
        'active_mode': active_mode,
        'preview_available': preview_available,
        'engine_reachable': engine_reachable,
        'is_recording': is_camera_recording(camera.id, camera.user_id),
        'recordings_count': recordings_count,
        'alerts_count': alerts_count,
        'recent_recordings': recent_recordings,
        'recent_alerts': recent_alerts,
    })


@never_cache
@login_required
def camera_stream_view(request, camera_id):
    """
    MJPEG streaming endpoint serving real-time encoded frames.
    Yields multipart/x-mixed-replace chunks from canonical surveillance engine.
    Supports ?mode=tracking (Default) and ?mode=raw / ?mode=original.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    mode_param = request.GET.get('mode', 'tracking').strip().lower()
    canonical_mode = normalize_mode(mode_param)

    # Frame generator from canonical surveillance engine
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=camera.user_id,
        mode=canonical_mode
    )

    response = StreamingHttpResponse(
        frame_generator,
        content_type="multipart/x-mixed-replace; boundary=frame"
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Accel-Buffering"] = "no"
    return response


@never_cache
@login_required
def camera_stream_tracking_view(request, camera_id):
    """
    Direct endpoint for Tracking + Detection MJPEG stream.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=camera.user_id,
        mode='tracking'
    )
    response = StreamingHttpResponse(
        frame_generator,
        content_type="multipart/x-mixed-replace; boundary=frame"
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Accel-Buffering"] = "no"
    return response


@never_cache
@login_required
def camera_stream_original_view(request, camera_id):
    """
    Direct endpoint for Original (Raw CCTV) MJPEG stream.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=camera.user_id,
        mode='raw'
    )
    response = StreamingHttpResponse(
        frame_generator,
        content_type="multipart/x-mixed-replace; boundary=frame"
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Accel-Buffering"] = "no"
    return response


_OFFLINE_SNAPSHOT_BYTES = None

def _get_offline_snapshot_bytes():
    global _OFFLINE_SNAPSHOT_BYTES
    if _OFFLINE_SNAPSHOT_BYTES is None:
        try:
            import cv2, numpy as np
            ph = np.zeros((360, 640, 3), dtype=np.uint8)
            ph[:] = (20, 24, 33)
            cv2.putText(ph, "SIGNAL OFFLINE", (210, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (120, 140, 160), 2)
            cv2.putText(ph, "Standby for camera signal reacquisition", (150, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 105, 120), 1)
            _, buf = cv2.imencode(".jpg", ph, [cv2.IMWRITE_JPEG_QUALITY, 80])
            _OFFLINE_SNAPSHOT_BYTES = buf.tobytes()
        except Exception:
            _OFFLINE_SNAPSHOT_BYTES = b""
    return _OFFLINE_SNAPSHOT_BYTES


@never_cache
@login_required
def camera_snapshot_view(request, camera_id):
    """
    Single frame snapshot JPEG endpoint (GET) or persistent Evidence capture (POST).
    """
    import os
    import datetime
    from django.utils import timezone
    from apps.core.media_service import EVIDENCE_DIR

    camera = get_user_camera_or_404(request.user, camera_id)

    if request.method == "POST":
        if _is_viewer_role(request.user):
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        jpeg_bytes = get_camera_snapshot(camera.id, camera.user_id)
        if not jpeg_bytes:
            return JsonResponse({
                "success": False,
                "error": "Failed to capture frame from camera. Camera may be initializing or offline."
            }, status=503)

        now = timezone.now()
        date_str = now.strftime("%Y-%m-%d")
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        target_dir = os.path.normpath(os.path.join(EVIDENCE_DIR, f"camera_{camera.id}", date_str))
        os.makedirs(target_dir, exist_ok=True)
        filename = f"manual_snap_{camera.id}_{ts_str}.jpg"
        abs_path = os.path.join(target_dir, filename)
        rel_path = f"camera_{camera.id}/{date_str}/{filename}"

        try:
            with open(abs_path, "wb") as f:
                f.write(jpeg_bytes)
        except Exception as e:
            logger.error(f"[SNAPSHOT_SAVE_ERROR] Failed writing snapshot to disk: {e}")
            return JsonResponse({"success": False, "error": "Failed to save snapshot file."}, status=500)

        from apps.alerts.models import Alert
        from apps.evidence.models import Evidence

        try:
            alert = Alert.objects.create(
                user_id=request.user.id,
                camera=camera,
                event_type="MANUAL_SNAPSHOT",
                title=f"Manual Snapshot - {camera.name}",
                message=f"Operator captured forensic snapshot from {camera.name}.",
                severity="low",
                status="resolved",
                detected_at=now,
                created_at=now,
                updated_at=now,
                response_state="RESOLVED",
            )

            evidence = Evidence.objects.create(
                alert=alert,
                user_id=request.user.id,
                camera=camera,
                evidence_type="snapshot",
                file_path=rel_path,
                file_name=filename,
                mime_type="image/jpeg",
                file_size=len(jpeg_bytes),
                captured_at=now,
                created_at=now,
            )
            try:
                from apps.core.storage_service import schedule_evidence_upload
                schedule_evidence_upload(evidence.id)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"[SNAPSHOT_DB_ERROR] Failed creating Evidence metadata: {e}")
            return JsonResponse({"success": False, "error": "Failed to record snapshot metadata."}, status=500)

        log_audit(
            request,
            action="MANUAL_SNAPSHOT_CAPTURED",
            resource_type="evidence",
            resource_id=evidence.id,
            description=f"Captured manual snapshot {filename} on camera #{camera.id}.",
        )
        return JsonResponse({
            "success": True,
            "evidence_id": evidence.id,
            "alert_id": alert.id,
            "file_name": filename,
            "preview_url": f"/evidence/{evidence.id}/preview/",
            "message": f"Snapshot #{evidence.id} captured and saved to Evidence Vault."
        })

    mode = request.GET.get("mode", "raw").strip().lower()
    if mode not in ("raw", "tracking"):
        mode = "raw"

    from apps.surveillance.camera.registry import get_camera_registry
    from apps.surveillance.health.health_service import get_live_camera_status
    active_worker = get_camera_registry().get_active_worker(camera.id)
    live_info = get_live_camera_status(camera.id, worker=active_worker)
    allow_placeholder = request.GET.get("placeholder") == "1"

    def _offline_snap_response():
        status_code = 200 if allow_placeholder else 503
        resp = HttpResponse(_get_offline_snapshot_bytes(), content_type="image/jpeg", status=status_code)
        resp["X-DeepVision-Signal"] = "offline"
        resp["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return resp

    if not (active_worker and active_worker.running and active_worker.latest_frame is not None and live_info["status"] != "offline"):
        if camera.status == "offline":
            return _offline_snap_response()

    # Fast preview thumbnail lookup; only warm local OpenCV capture when physical video hardware exists
    has_local_capture = (os.name == "nt") or os.path.exists("/dev/video0")
    allow_sync_start = (
        camera.source_type in ("webcam", "usb")
        and camera.status != "offline"
        and has_local_capture
    )
    jpeg_bytes = get_camera_snapshot(camera.id, camera.user_id, allow_start=allow_sync_start, mode=mode)
    if jpeg_bytes:
        resp = HttpResponse(jpeg_bytes, content_type="image/jpeg")
        resp["X-DeepVision-Signal"] = "live"
        resp["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return resp
    if has_local_capture and camera.source_type in ("webcam", "usb"):
        import threading
        from apps.ai.engine import warm_camera_capture_only
        threading.Thread(target=warm_camera_capture_only, args=(camera.id, camera.user_id), daemon=True).start()
    return _offline_snap_response()


@never_cache
@login_required
def camera_stats_view(request, camera_id):
    """
    JSON stream telemetry endpoint (FPS, track IDs, latency).
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    stats = get_camera_stats(camera.id, camera.user_id)
    return JsonResponse(stats)


@never_cache
@login_required
def camera_warm_view(request, camera_id):
    """
    Pre-warms camera workers on canonical engine and returns live status.
    Supports capture_only=1 to warm only CameraWorker without starting AI inference.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    capture_only = str(request.GET.get("capture_only", "") or request.POST.get("capture_only", "")).strip().lower() in ("1", "true", "yes")
    if capture_only:
        from apps.ai.engine import warm_camera_capture_only
        success = warm_camera_capture_only(camera.id, camera.user_id)
    else:
        success = warm_camera(camera.id, camera.user_id)
    from apps.surveillance.health.health_service import get_live_camera_status
    live_info = get_live_camera_status(camera.id)
    if success and live_info.get("status") == "online" and camera.status != "online":
        from django.utils import timezone
        camera.status = "online"
        camera.updated_at = timezone.now()
        camera.save(update_fields=["status", "updated_at"])
    return JsonResponse({
        "status": "ok",
        "warmed": bool(success),
        "camera_status": live_info.get("status", "offline"),
        "live": bool(live_info.get("live", False)),
    })


@never_cache
@login_required
def surveillance_health_api_view(request):
    """
    Phase 8: Boundary Health & Diagnostics API.
    Exposes observable, sanitized status of the canonical surveillance engine and storage posture.
    Strictly protected by authentication; never leaks internal paths or secrets.
    """
    from apps.core.storage_service import get_storage_health

    health = dict(get_engine_health(user_id=request.user.id) or {})
    health["storage"] = get_storage_health()
    status_code = 200 if health.get("status") in ("healthy", "degraded") else 503
    return JsonResponse(health, status=status_code)


@require_POST
@login_required
def camera_record_start_view(request, camera_id):
    """
    Proxies recording start request to canonical surveillance engine.
    Strictly enforces authorization: non-viewer users authorized to access this camera can record.
    """
    if _is_viewer_role(request.user):
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    camera = get_user_camera_or_404(request.user, camera_id)
    result = start_camera_recording(camera.id, request.user.id)
    if isinstance(result, dict) and "success" not in result:
        result["success"] = result.get("status") in ("ok", "warning")
    if isinstance(result, dict) and result.get("success"):
        log_audit(
            request,
            action="RECORDING_STARTED",
            resource_type="recording",
            resource_id=result.get("recording_id"),
            description=f"Started clip recording on camera #{camera.id} ({camera.name}).",
        )
    return JsonResponse(result)


@require_POST
@login_required
def camera_record_stop_view(request, camera_id):
    """
    Proxies recording stop request to canonical surveillance engine.
    Strictly enforces authorization: non-viewer users authorized to access this camera can stop recording.
    """
    if _is_viewer_role(request.user):
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    camera = get_user_camera_or_404(request.user, camera_id)
    result = stop_camera_recording(camera.id, request.user.id)
    if isinstance(result, dict) and "success" not in result:
        result["success"] = result.get("status") in ("ok", "warning")
    if isinstance(result, dict) and result.get("success"):
        log_audit(
            request,
            action="RECORDING_STOPPED",
            resource_type="recording",
            resource_id=result.get("recording_id"),
            description=f"Stopped clip recording on camera #{camera.id} ({camera.name}).",
        )
    return JsonResponse(result)


@require_POST
@login_required
def camera_test_connection_view(request):
    """
    Tests camera connection parameters via canonical surveillance engine.
    Supports optional username/password credentials for RTSP/HTTP cameras.
    """
    if _is_viewer_role(request.user):
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    data = {}
    if request.body:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            data = {}
    source_type = data.get("source_type", "") or request.POST.get("source_type", "")
    if str(source_type).strip().lower() == "stream":
        source_type = "http"
    source = (
        data.get("source", "")
        or data.get("source_value", "")
        or request.POST.get("source", "")
        or request.POST.get("source_value", "")
    )
    username = str(data.get("username", "") or request.POST.get("username", "")).strip()
    password = str(data.get("password", "") or request.POST.get("password", "")).strip()
    if username or password:
        from apps.core.api import _inject_url_credentials
        source = _inject_url_credentials(str(source or ""), username, password)
    result = dict(test_camera_connection(source_type, source, request.user.id))
    http_status = int(result.pop("status_code", 200))
    return JsonResponse(result, status=http_status)


@require_POST
@login_required
def camera_test_view(request, camera_id):
    """
    Tests existing registered camera via canonical surveillance engine and updates its operational status.
    """
    from django.utils import timezone
    camera, err_resp = _get_writable_camera_or_403(request.user, camera_id)
    if err_resp is not None:
        return err_resp
    result = test_existing_camera(camera.id, camera.user_id)
    new_status = "online" if result.get("success") else "offline"
    if camera.status != new_status:
        camera.status = new_status
        camera.updated_at = timezone.now()
        camera.save(update_fields=["status", "updated_at"])
    result["camera_status"] = new_status
    return JsonResponse(result)


import collections
import time

_INGEST_RATE_BUCKETS = {}  # (user_id, camera_id) -> deque of monotonic timestamps
_INGEST_RATE_LOCK = None


def _check_ingest_rate_limit(user_id, camera_id, max_fps=15, window_sec=1.0):
    global _INGEST_RATE_LOCK
    if _INGEST_RATE_LOCK is None:
        import threading
        _INGEST_RATE_LOCK = threading.Lock()
    now = time.monotonic()
    key = (int(user_id), int(camera_id))
    with _INGEST_RATE_LOCK:
        dq = _INGEST_RATE_BUCKETS.get(key)
        if dq is None:
            dq = collections.deque(maxlen=max_fps * 2)
            _INGEST_RATE_BUCKETS[key] = dq
        cutoff = now - window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_fps:
            return True
        dq.append(now)
        return False


@require_POST
@login_required
def camera_ingest_frame_view(request, camera_id):
    """
    Accepts a live JPEG frame pushed from the authenticated user's browser (navigator.mediaDevices.getUserMedia)
    and feeds it directly into the CameraWorker + InferenceWorker + RecordingService pipeline.
    Enables real webcam & mobile phone camera AI surveillance and recording on both local and cloud-hosted servers.
    Enforces payload size limits (1.5 MB), resolution bounds (1920x1080), and per-camera rate limits (15 FPS).
    """
    import base64
    try:
        import cv2
        import numpy as np
    except Exception:
        return JsonResponse({"success": False, "error": "OpenCV/NumPy unavailable."}, status=503)

    from django.utils import timezone
    from apps.surveillance.camera.registry import get_camera_registry
    from apps.surveillance.ai.registry import get_inference_registry

    camera, err_resp = _get_writable_camera_or_403(request.user, camera_id)
    if err_resp is not None:
        return err_resp

    if _check_ingest_rate_limit(request.user.id, camera.id, max_fps=30, window_sec=1.0):
        resp = JsonResponse(
            {"success": False, "error": "Frame ingestion rate limit exceeded (max 30 FPS per camera)."},
            status=429,
        )
        resp["Retry-After"] = "1"
        return resp

    raw_bytes = None

    if request.FILES and "frame" in request.FILES:
        raw_bytes = request.FILES["frame"].read()
    elif request.content_type and "image/" in request.content_type.lower():
        raw_bytes = request.body
    elif request.body:
        if len(request.body) > 2 * 1024 * 1024:
            return JsonResponse({"success": False, "error": "Frame payload exceeds maximum size (1.5MB)."}, status=413)
        try:
            payload = json.loads(request.body.decode("utf-8"))
            b64_str = str(payload.get("frame") or payload.get("image") or "")
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            if b64_str:
                raw_bytes = base64.b64decode(b64_str)
        except Exception:
            raw_bytes = request.body

    if not raw_bytes or len(raw_bytes) < 64:
        return JsonResponse({"success": False, "error": "Empty or invalid frame payload."}, status=400)
    if len(raw_bytes) > 1536 * 1024:
        return JsonResponse({"success": False, "error": "Frame payload exceeds maximum size (1.5MB)."}, status=413)

    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None or frame.size == 0:
        return JsonResponse({"success": False, "error": "Unable to decode JPEG/PNG image frame."}, status=400)

    fh, fw = frame.shape[:2]
    if fw > 1920 or fh > 1080:
        return JsonResponse({"success": False, "error": f"Frame dimensions ({fw}x{fh}) exceed maximum allowed (1920x1080)."}, status=413)

    seq_raw = request.GET.get("seq") or request.headers.get("X-Frame-Seq")
    seq_out = None
    if seq_raw is not None and str(seq_raw).strip() != "":
        try:
            seq_out = int(seq_raw)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "Invalid frame sequence number."}, status=400)
        if seq_out < 0:
            return JsonResponse({"success": False, "error": "Frame sequence number must be non-negative."}, status=400)

    cam_reg = get_camera_registry()
    worker = cam_reg.get_or_create_browser_worker(camera.id, camera.user_id)
    accepted = worker.ingest_external_frame(frame, seq=seq_out)
    received_at_iso = timezone.now().isoformat()
    if not accepted:
        from apps.surveillance.health.health_service import get_live_camera_status
        live_info = get_live_camera_status(camera.id, worker=worker)
        return JsonResponse({
            "success": True,
            "accepted": False,
            "stale_sequence": True,
            "seq": seq_out,
            "latest_seq": worker.last_ingest_seq,
            "received_at": received_at_iso,
            "camera_id": camera.id,
            "frame_id": worker.frame_id,
            "fps": worker.fps,
            "camera_status": live_info["status"],
            "live": live_info["live"],
            "signal_state": live_info["signal_state"],
        })

    if camera.status != "online":
        camera.status = "online"
        camera.updated_at = timezone.now()
        camera.save(update_fields=["status", "updated_at"])

    # Ensure InferenceWorker is running and bound so YOLO/Tracking/Anomaly detection runs on browser frames
    inf_worker = None
    try:
        inf_reg = get_inference_registry()
        inf_worker = inf_reg.ensure_worker(camera.id, worker)
    except Exception:
        pass

    tracks_list = []
    anomalies_list = []
    zones_list = []
    detector_backend = "inactive"
    tracker_backend = "inactive"
    summary = {}
    if inf_worker is not None:
        raw_tracks = getattr(inf_worker, "cached_tracks", []) or []
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
            for trk in raw_tracks
        ]
        anomalies_list = list(getattr(inf_worker, "cached_anomalies", []) or [])
        if hasattr(inf_worker, "get_cached_zones"):
            zones_list = list(inf_worker.get_cached_zones(camera.id) or [])
        tracker = getattr(inf_worker, "tracker", None)
        detector_backend = getattr(tracker, "detector_backend", "unknown") if tracker is not None else "unknown"
        tracker_backend = getattr(tracker, "tracker_backend", "unknown") if tracker is not None else "unknown"
        if hasattr(inf_worker, "get_telemetry_summary"):
            summary = inf_worker.get_telemetry_summary()

    try:
        from apps.surveillance.health.health_service import update_camera_health
        update_camera_health(
            camera.id,
            status="online",
            fps=round(float(getattr(worker, "fps", 0.0) or 0.0), 1),
            ai_fps=round(float(getattr(inf_worker, "ai_fps", 0.0) or 0.0), 1) if inf_worker else 0.0,
            inference_latency_ms=round(float(getattr(inf_worker, "latency_ms", 0.0) or 0.0), 2) if inf_worker else 0.0,
            stream_active=True,
            detection_active=bool(inf_worker and getattr(inf_worker, "running", False)),
            tracking_active=bool(inf_worker and getattr(inf_worker, "running", False)),
        )
    except Exception:
        pass

    visible_persons_default = sum(1 for t in tracks_list if str(t.get("class_name", "")).lower() == "person")
    from apps.surveillance.health.health_service import get_live_camera_status
    live_info = get_live_camera_status(camera.id, worker=worker)
    return JsonResponse({
        "success": True,
        "accepted": True,
        "seq": seq_out,
        "received_at": received_at_iso,
        "camera_id": camera.id,
        "frame_id": worker.frame_id,
        "fps": worker.fps,
        "ai_fps": getattr(inf_worker, "ai_fps", 0.0) if inf_worker else 0.0,
        "latency_ms": round(float(getattr(inf_worker, "latency_ms", 0.0) or 0.0), 2) if inf_worker else 0.0,
        "p50_latency_ms": summary.get("p50_latency_ms", round(float(getattr(inf_worker, "latency_ms", 0.0) or 0.0), 2) if inf_worker else 0.0),
        "p95_latency_ms": summary.get("p95_latency_ms", round(float(getattr(inf_worker, "latency_ms", 0.0) or 0.0), 2) if inf_worker else 0.0),
        "frame_age_ms": summary.get("frame_age_ms", 0.0),
        "frame_age_sec": live_info.get("frame_age_sec"),
        "ai_profile": summary.get("ai_profile", "balanced"),
        "stage_timings": dict(getattr(inf_worker, "last_stage_timings", {}) or {}) if inf_worker else {},
        "tracks": len(tracks_list),
        "tracks_list": tracks_list,
        "currently_visible_persons": summary.get("currently_visible_persons", visible_persons_default),
        "active_tracks": summary.get("active_tracks", len(tracks_list)),
        "unique_persons_observed": summary.get("unique_persons_observed", visible_persons_default),
        "total_detection_events": summary.get("total_detection_events", len(tracks_list)),
        "recent_detections": summary.get("recent_detections", []),
        "recent_zone_events": summary.get("recent_zone_events", []),
        "camera_purpose": summary.get("camera_purpose", "general"),
        "restricted_entry_enabled": summary.get("restricted_entry_enabled", bool(zones_list)),
        "anomalies": len(anomalies_list),
        "anomalies_list": anomalies_list,
        "zones": zones_list,
        "inference_active": bool(inf_worker and getattr(inf_worker, "running", False)),
        "detector_backend": detector_backend,
        "tracker_backend": tracker_backend,
        "frame_width": fw,
        "frame_height": fh,
        "camera_status": live_info["status"],
        "live": live_info["live"],
        "signal_state": live_info["signal_state"],
    })


@require_POST
@login_required
def camera_disconnect_view(request, camera_id):
    """
    Cleanly disconnects a camera worker, stops any active recording, releases capture handles,
    and transitions camera status to offline.
    """
    from django.utils import timezone
    from apps.surveillance.camera.registry import get_camera_registry

    camera, err_resp = _get_writable_camera_or_403(request.user, camera_id)
    if err_resp is not None:
        return err_resp
    if is_camera_recording(camera.id, camera.user_id):
        try:
            stop_camera_recording(camera.id, camera.user_id)
        except Exception:
            pass

    try:
        get_camera_registry().remove_camera(camera.id)
    except Exception:
        pass

    try:
        from apps.surveillance.ai.registry import get_inference_registry
        from apps.surveillance.ai.reid import registry as reid_registry
        from apps.surveillance.streaming.stream_service import clear_camera_telemetry
        get_inference_registry().remove_worker(camera.id)
        reid_registry.clear_camera(camera.id)
        clear_camera_telemetry(camera.id)
    except Exception:
        pass

    if camera.status != "offline":
        camera.status = "offline"
        camera.updated_at = timezone.now()
        camera.save(update_fields=["status", "updated_at"])

    try:
        from apps.surveillance.health.health_service import update_camera_health
        update_camera_health(
            camera.id,
            status="offline",
            fps=0.0,
            ai_fps=0.0,
            inference_latency_ms=0.0,
            stream_active=False,
            detection_active=False,
            tracking_active=False,
        )
    except Exception:
        pass

    log_audit(
        request,
        action="CAMERA_DISCONNECTED",
        resource_type="camera",
        resource_id=camera.id,
        description=f"Disconnected camera #{camera.id} ({camera.name}).",
    )
    return JsonResponse({
        "success": True,
        "camera_id": camera.id,
        "camera_status": "offline",
        "message": f"Camera '{camera.name}' disconnected.",
    })

