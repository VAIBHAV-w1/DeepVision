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
            return JsonResponse({"success": False, "error": f"Filesystem write failed: {e}"}, status=500)

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
        except Exception as e:
            logger.error(f"[SNAPSHOT_DB_ERROR] Failed creating Evidence metadata: {e}")
            return JsonResponse({"success": False, "error": f"Database recording failed: {e}"}, status=500)

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

    if camera.status == "offline":
        return HttpResponse(_get_offline_snapshot_bytes(), content_type="image/jpeg")

    # Fast preview thumbnail lookup; online local webcams warm capture-only (zero YOLO threads), offline LAN cameras never block
    allow_sync_start = (camera.source_type in ("webcam", "usb") and camera.status != "offline")
    jpeg_bytes = get_camera_snapshot(camera.id, camera.user_id, allow_start=allow_sync_start)
    if jpeg_bytes:
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")
    if camera.source_type in ("webcam", "usb"):
        import threading
        from apps.ai.engine import warm_camera_capture_only
        threading.Thread(target=warm_camera_capture_only, args=(camera.id, camera.user_id), daemon=True).start()
    return HttpResponse(_get_offline_snapshot_bytes(), content_type="image/jpeg")


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
    Pre-warms camera workers on canonical engine.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    success = warm_camera(camera.id, camera.user_id)
    return JsonResponse({"status": "ok", "warmed": success})


@never_cache
@login_required
def surveillance_health_api_view(request):
    """
    Phase 8: Boundary Health & Diagnostics API.
    Exposes observable, sanitized status of the canonical surveillance engine.
    Strictly protected by authentication; never leaks internal paths or secrets.
    """
    health = get_engine_health(user_id=request.user.id)
    status_code = 200 if health.get("status") in ("healthy", "degraded") else 503
    return JsonResponse(health, status=status_code)


@require_POST
@login_required
def camera_record_start_view(request, camera_id):
    """
    Proxies recording start request to canonical surveillance engine.
    Strictly enforces authorization: any user authorized to access this camera can record.
    """
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
    Strictly enforces authorization: any user authorized to access this camera can stop recording.
    """
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
    """
    data = {}
    if request.body:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            data = {}
    source_type = data.get("source_type", "") or request.POST.get("source_type", "")
    source = (
        data.get("source", "")
        or data.get("source_value", "")
        or request.POST.get("source", "")
        or request.POST.get("source_value", "")
    )
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
    camera = get_user_camera_or_404(request.user, camera_id)
    result = test_existing_camera(camera.id, camera.user_id)
    new_status = "online" if result.get("success") else "offline"
    if camera.status != new_status:
        camera.status = new_status
        camera.updated_at = timezone.now()
        camera.save(update_fields=["status", "updated_at"])
    result["camera_status"] = new_status
    return JsonResponse(result)

