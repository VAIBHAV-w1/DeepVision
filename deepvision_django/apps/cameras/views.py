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
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import login_required
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
    Returns queryset of cameras accessible to user:
    - Admin/Supervisor: all cameras.
    - User with assigned cameras: user's cameras.
    - User without assigned cameras: all online or registered cameras.
    """
    if getattr(user, 'role', '') in ('admin', 'supervisor') or getattr(user, 'is_superuser', False):
        return Camera.objects.all().order_by('id')
    qs = Camera.objects.filter(user_id=user.id).order_by('id')
    if not qs.exists():
        qs = Camera.objects.filter(status='online').order_by('id')
        if not qs.exists():
            qs = Camera.objects.all().order_by('id')
    return qs


def get_user_camera_or_404(user, camera_id):
    """
    Safely resolves camera object with role-based and fallback permissions:
    1. If user is admin/supervisor (staff), can access any camera.
    2. If camera is owned by user, access granted.
    3. If user has no cameras assigned, or camera is an active physical/webcam stream, allow access.
    """
    if getattr(user, 'role', '') in ('admin', 'supervisor') or getattr(user, 'is_superuser', False):
        return get_object_or_404(Camera, id=camera_id)
    try:
        return Camera.objects.get(id=camera_id, user_id=user.id)
    except Camera.DoesNotExist:
        if not Camera.objects.filter(user_id=user.id).exists() or Camera.objects.filter(id=camera_id, source_type='webcam').exists():
            return get_object_or_404(Camera, id=camera_id)
        raise Http404("Camera not found")


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
    Single frame snapshot JPEG endpoint.
    Returns live captured frame or standard diagnostic offline placeholder.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    jpeg_bytes = get_camera_snapshot(camera.id, camera.user_id)
    if jpeg_bytes:
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")
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
    Strictly enforces authorization: only owner or admin can initiate recording.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    if getattr(request.user, 'role', '') not in ('admin', 'supervisor') and camera.user_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Permission denied. Only camera owner or admin can record."}, status=403)
    result = start_camera_recording(camera.id, camera.user_id)
    return JsonResponse(result)


@require_POST
@login_required
def camera_record_stop_view(request, camera_id):
    """
    Proxies recording stop request to canonical surveillance engine.
    Strictly enforces authorization: only owner or admin can stop recording.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    if getattr(request.user, 'role', '') not in ('admin', 'supervisor') and camera.user_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Permission denied. Only camera owner or admin can control recording."}, status=403)
    result = stop_camera_recording(camera.id, camera.user_id)
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
    source = data.get("source", "") or request.POST.get("source", "")
    result = test_camera_connection(source_type, source, request.user.id)
    return JsonResponse(result)


@require_POST
@login_required
def camera_test_view(request, camera_id):
    """
    Tests existing registered camera via canonical surveillance engine.
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    if getattr(request.user, 'role', '') not in ('admin', 'supervisor') and camera.user_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Permission denied."}, status=403)
    result = test_existing_camera(camera.id, camera.user_id)
    return JsonResponse(result)

