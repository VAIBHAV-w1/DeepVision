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


@never_cache
@login_required
def camera_list_view(request):
    """
    Renders camera dashboard list for the authenticated user.
    """
    cameras_qs = Camera.objects.filter(user_id=request.user.id).order_by('id')
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
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    
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
    recordings_count = camera.recordings.filter(user_id=request.user.id).count()
    alerts_count = camera.alerts.filter(user_id=request.user.id).count()
    recent_recordings = list(camera.recordings.filter(user_id=request.user.id).order_by('-id')[:5])
    recent_alerts = list(camera.alerts.filter(user_id=request.user.id).order_by('-id')[:5])

    return render(request, 'pages/cameras/preview.html', {
        'camera': camera,
        'active_mode': active_mode,
        'preview_available': preview_available,
        'engine_reachable': engine_reachable,
        'is_recording': is_camera_recording(camera.id, request.user.id),
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
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    mode_param = request.GET.get('mode', 'tracking').strip().lower()
    canonical_mode = normalize_mode(mode_param)

    # Frame generator from canonical surveillance engine
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=request.user.id,
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
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=request.user.id,
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
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    frame_generator = stream_camera_frames(
        camera_id=camera.id,
        user_id=request.user.id,
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


@never_cache
@login_required
def camera_snapshot_view(request, camera_id):
    """
    Single frame snapshot JPEG endpoint.
    """
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    jpeg_bytes = get_camera_snapshot(camera.id, request.user.id)
    if jpeg_bytes:
        return HttpResponse(jpeg_bytes, content_type="image/jpeg")
    return HttpResponse(status=404)


@never_cache
@login_required
def camera_stats_view(request, camera_id):
    """
    JSON stream telemetry endpoint (FPS, track IDs, latency).
    """
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    stats = get_camera_stats(camera.id, request.user.id)
    return JsonResponse(stats)


@never_cache
@login_required
def camera_warm_view(request, camera_id):
    """
    Pre-warms camera workers on canonical engine.
    """
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    success = warm_camera(camera.id, request.user.id)
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
    """
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    result = start_camera_recording(camera.id, request.user.id)
    return JsonResponse(result)


@require_POST
@login_required
def camera_record_stop_view(request, camera_id):
    """
    Proxies recording stop request to canonical surveillance engine.
    """
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    result = stop_camera_recording(camera.id, request.user.id)
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
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    result = test_existing_camera(camera.id, request.user.id)
    return JsonResponse(result)

