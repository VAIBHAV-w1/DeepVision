"""
Django Recordings Views.
Phase 6A: Recordings migration.
Exposes existing surveillance recordings through Django without modifying database schema
or regenerating/moving/re-encoding existing MP4 files.
"""

import logging
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.views.decorators.cache import never_cache
from django.db.models import Q

from apps.accounts.decorators import login_required
from apps.recordings.models import Recording
from apps.alerts.models import Alert
from apps.cameras.models import Camera
from apps.core.media_service import safe_resolve_recording, serve_file_with_ranges

logger = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    """Formats file size in bytes to human-readable string."""
    if not size_bytes or size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


@never_cache
@login_required
def recordings_list_view(request):
    """
    Renders the central Recordings library for the authenticated user.
    """
    user_id = request.user.id
    recordings_qs = Recording.objects.filter(user_id=user_id).select_related('camera')

    camera_id = request.GET.get('camera_id', '').strip() or request.GET.get('camera', '').strip()
    if camera_id and camera_id.isdigit():
        recordings_qs = recordings_qs.filter(camera_id=int(camera_id))

    search_query = request.GET.get('q', '').strip()
    if search_query:
        recordings_qs = recordings_qs.filter(
            Q(filename__icontains=search_query) | Q(camera__name__icontains=search_query)
        )

    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter in ('completed', 'recording', 'stopped'):
        recordings_qs = recordings_qs.filter(status=status_filter)

    recordings = list(recordings_qs.order_by('-started_at', '-id')[:100])

    # Pre-check physical file availability
    items = []
    total_size = 0
    for r in recordings:
        full_path = safe_resolve_recording(r.file_path)
        file_exists = full_path is not None
        if file_exists:
            total_size += r.file_size
        items.append({
            'recording': r,
            'file_exists': file_exists,
            'formatted_size': _format_size(r.file_size),
        })

    user_cameras = Camera.objects.filter(user_id=user_id).order_by('name')

    return render(request, 'pages/recordings/index.html', {
        'items': items,
        'recordings': recordings,
        'cameras': user_cameras,
        'retention_days': 7,
        'storage_stats': {
            'total_size_bytes': total_size,
            'formatted_size': _format_size(total_size),
            'total_count': len(items)
        },
        'current_camera_id': camera_id,
        'search_query': search_query,
    })


@never_cache
@login_required
def recording_detail_view(request, recording_id):
    """
    Shows detail page for an existing recording with synchronized security events.
    """
    recording = get_object_or_404(Recording.objects.select_related('camera'), id=recording_id, user_id=request.user.id)
    
    full_path = safe_resolve_recording(recording.file_path)
    file_exists = full_path is not None

    # Retrieve synchronized security events (Alerts for this camera during the recording timeframe)
    timeline_events = []
    if recording.started_at:
        events_qs = Alert.objects.filter(
            user_id=request.user.id,
            camera_id=recording.camera_id,
            detected_at__gte=recording.started_at
        )
        if recording.ended_at:
            events_qs = events_qs.filter(detected_at__lte=recording.ended_at)
        timeline_events = list(events_qs.order_by('detected_at'))

    return render(request, 'pages/recordings/detail.html', {
        'recording': recording,
        'file_exists': file_exists,
        'formatted_size': _format_size(recording.file_size),
        'timeline_events': timeline_events,
    })


@never_cache
@login_required
def view_recording_media_view(request, recording_id):
    """
    Serves the existing MP4 recording file supporting HTTP Range requests
    for inline HTML5 video playback and seeking.
    """
    recording = get_object_or_404(Recording, id=recording_id, user_id=request.user.id)
    full_path = safe_resolve_recording(recording.file_path)
    if not full_path:
        raise Http404("Recording file not found on disk.")

    return serve_file_with_ranges(
        request=request,
        full_path=full_path,
        content_type="video/mp4",
        as_attachment=False
    )


@never_cache
@login_required
def download_recording_view(request, recording_id):
    """
    Serves the existing recording file as a download attachment.
    """
    recording = get_object_or_404(Recording, id=recording_id, user_id=request.user.id)
    full_path = safe_resolve_recording(recording.file_path)
    if not full_path:
        raise Http404("Recording file not found on disk.")

    return serve_file_with_ranges(
        request=request,
        full_path=full_path,
        content_type="video/mp4",
        as_attachment=True,
        download_name=recording.filename
    )
