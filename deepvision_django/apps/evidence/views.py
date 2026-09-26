"""
Django Evidence Views.
Phase 6B: Evidence migration.
Exposes existing forensic evidence assets (snapshots, video clips) through Django
without moving, renaming, converting, or modifying existing media files.
"""

import logging
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.decorators import login_required
from apps.evidence.models import Evidence
from apps.cameras.models import Camera
from apps.core.media_service import safe_resolve_evidence, serve_file_with_ranges

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
def evidence_list_view(request):
    """
    Renders the forensic Evidence Investigation Vault for the authenticated user.
    """
    user_id = request.user.id
    evidence_qs = Evidence.objects.filter(user_id=user_id).select_related('camera', 'alert')

    evidence_type = request.GET.get('type', '').strip().lower()
    if evidence_type in ('snapshot', 'video'):
        evidence_qs = evidence_qs.filter(evidence_type=evidence_type)

    camera_id = request.GET.get('camera_id', '').strip() or request.GET.get('camera', '').strip()
    if camera_id and camera_id.isdigit():
        evidence_qs = evidence_qs.filter(camera_id=int(camera_id))

    alert_id = request.GET.get('alert_id', '').strip() or request.GET.get('alert', '').strip()
    if alert_id and alert_id.isdigit():
        evidence_qs = evidence_qs.filter(alert_id=int(alert_id))

    search_query = request.GET.get('q', '').strip()
    if search_query:
        evidence_qs = evidence_qs.filter(
            Q(file_name__icontains=search_query) |
            Q(alert__title__icontains=search_query) |
            Q(camera__name__icontains=search_query)
        )

    evidence_qs = evidence_qs.order_by('-captured_at', '-id')

    # Pagination: 18 items per page
    page_number = request.GET.get('page', 1)
    paginator = Paginator(evidence_qs, 18)
    page_obj = paginator.get_page(page_number)

    # Pre-check physical file availability for the active page
    items = []
    for ev in page_obj:
        full_path = safe_resolve_evidence(ev.file_path)
        items.append({
            'evidence': ev,
            'file_available': full_path is not None,
            'formatted_size': _format_size(ev.file_size),
        })

    # Summary statistics for user
    total_count = Evidence.objects.filter(user_id=user_id).count()
    snapshots_count = Evidence.objects.filter(user_id=user_id, evidence_type='snapshot').count()
    videos_count = Evidence.objects.filter(user_id=user_id, evidence_type='video').count()
    user_cameras = Camera.objects.filter(user_id=user_id).order_by('name')

    return render(request, 'pages/evidence/index.html', {
        'items': items,
        'page_obj': page_obj,
        'cameras': user_cameras,
        'stats': {
            'total_count': total_count,
            'snapshots_count': snapshots_count,
            'videos_count': videos_count,
        },
        'current_type': evidence_type or 'all',
        'current_camera_id': camera_id,
        'current_alert_id': alert_id,
        'search_query': search_query,
    })


@never_cache
@login_required
def evidence_detail_view(request, evidence_id):
    """
    Renders detailed forensic view for a specific evidence asset.
    """
    evidence = get_object_or_404(
        Evidence.objects.select_related('alert', 'camera'),
        id=evidence_id,
        user_id=request.user.id
    )

    full_path = safe_resolve_evidence(evidence.file_path)
    file_exists = full_path is not None

    return render(request, 'pages/evidence/detail.html', {
        'evidence': evidence,
        'file_exists': file_exists,
        'formatted_size': _format_size(evidence.file_size),
    })


@never_cache
@login_required
def preview_evidence_media_view(request, evidence_id):
    """
    Serves the existing evidence asset inline.
    Supports HTTP Range requests for video clips and standard binary response for snapshots.
    """
    evidence = get_object_or_404(Evidence, id=evidence_id, user_id=request.user.id)
    full_path = safe_resolve_evidence(evidence.file_path)
    if not full_path:
        raise Http404("Evidence file not found on disk.")

    mime_type = evidence.mime_type
    if not mime_type:
        mime_type = "image/jpeg" if evidence.evidence_type == "snapshot" else "video/mp4"

    return serve_file_with_ranges(
        request=request,
        full_path=full_path,
        content_type=mime_type,
        as_attachment=False
    )


@never_cache
@login_required
def download_evidence_view(request, evidence_id):
    """
    Serves the existing evidence asset as a download attachment.
    """
    evidence = get_object_or_404(Evidence, id=evidence_id, user_id=request.user.id)
    full_path = safe_resolve_evidence(evidence.file_path)
    if not full_path:
        raise Http404("Evidence file not found on disk.")

    mime_type = evidence.mime_type or "application/octet-stream"

    return serve_file_with_ranges(
        request=request,
        full_path=full_path,
        content_type=mime_type,
        as_attachment=True,
        download_name=evidence.file_name
    )
