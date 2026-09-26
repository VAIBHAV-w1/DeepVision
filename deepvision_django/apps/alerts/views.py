"""
Django Alerts & Incident Cases Views.
Phase 6C & 6D: Alerts and Incident Cases migration.
Exposes existing alerts, forensic incident cases, and investigation notes through Django
without altering database schema or duplicating the surveillance alert-generation engine.
"""

import logging
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404, JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.decorators import login_required
from apps.alerts.models import Alert, IncidentCase, IncidentNote
from apps.cameras.models import Camera

logger = logging.getLogger(__name__)


# =========================================================================
# PHASE 6C: ALERTS VIEWS
# =========================================================================

@never_cache
@login_required
def alerts_list_view(request):
    """
    Renders the central Alerts Management & Incident Inbox.
    """
    user_id = request.user.id
    alerts_qs = Alert.objects.filter(user_id=user_id).select_related('camera')

    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter in ('new', 'acknowledged', 'resolved'):
        alerts_qs = alerts_qs.filter(status=status_filter)

    severity_filter = request.GET.get('severity', '').strip().lower()
    if severity_filter in ('low', 'medium', 'high', 'critical'):
        alerts_qs = alerts_qs.filter(severity=severity_filter)

    event_type_filter = request.GET.get('event_type', '').strip().lower()
    if event_type_filter:
        alerts_qs = alerts_qs.filter(event_type__iexact=event_type_filter)

    camera_id = request.GET.get('camera_id', '').strip() or request.GET.get('camera', '').strip()
    if camera_id and camera_id.isdigit():
        alerts_qs = alerts_qs.filter(camera_id=int(camera_id))

    search_query = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()
    if search_query:
        alerts_qs = alerts_qs.filter(
            Q(title__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(event_type__icontains=search_query) |
            Q(camera__name__icontains=search_query)
        )

    alerts_qs = alerts_qs.order_by('-detected_at', '-id')

    # Metrics (unfiltered user totals)
    user_all_alerts = Alert.objects.filter(user_id=user_id)
    total_count = user_all_alerts.count()
    new_count = user_all_alerts.filter(status='new').count()
    active_high_count = user_all_alerts.filter(status='new', severity__in=['high', 'critical']).count()
    resolved_count = user_all_alerts.filter(status='resolved').count()

    # Pagination: 20 alerts per page
    page_number = request.GET.get('page', 1)
    paginator = Paginator(alerts_qs, 20)
    page_obj = paginator.get_page(page_number)

    user_cameras = Camera.objects.filter(user_id=user_id).order_by('name')

    return render(request, 'pages/alerts/index.html', {
        'page_obj': page_obj,
        'alerts': page_obj.object_list,
        'total_count': total_count,
        'new_count': new_count,
        'active_high_count': active_high_count,
        'resolved_count': resolved_count,
        'cameras': user_cameras,
        'current_status': status_filter,
        'current_severity': severity_filter,
        'current_event_type': event_type_filter,
        'current_camera_id': camera_id,
        'current_search': search_query,
    })


@never_cache
@login_required
def alert_detail_view(request, alert_id):
    """
    Renders detailed forensic investigation console for a single alert.
    """
    alert = get_object_or_404(
        Alert.objects.select_related('camera'),
        id=alert_id,
        user_id=request.user.id
    )

    # Preload related evidence items and notes
    evidence_items = list(alert.evidence_items.all().order_by('-captured_at'))
    notes = list(alert.incident_notes.all().order_by('-created_at'))
    incident_case = alert.incident_cases.first()

    return render(request, 'pages/alerts/detail.html', {
        'alert': alert,
        'camera': alert.camera,
        'camera_name': alert.camera.name if alert.camera else 'Channel 01',
        'evidence_items': evidence_items,
        'notes': notes,
        'incident_case': incident_case,
    })


@require_POST
@login_required
def alert_acknowledge_view(request, alert_id):
    """
    Transitions an alert from 'new' to 'acknowledged'.
    Modifies only existing SQLite columns.
    """
    alert = get_object_or_404(Alert, id=alert_id, user_id=request.user.id)
    if alert.status == 'new':
        alert.status = 'acknowledged'
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=['status', 'acknowledged_at'])
        msg = f"Alert #{alert.id} acknowledged."
        messages.success(request, msg)
        logger.info(f"[ALERTS] User {request.user.id} acknowledged alert {alert_id}.")
    else:
        msg = f"Alert #{alert.id} cannot be acknowledged from status '{alert.status}'."
        messages.warning(request, msg)

    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"status": "ok", "success": True, "alert_status": alert.status, "message": msg})
    return redirect(request.META.get('HTTP_REFERER') or f'/alerts/{alert_id}/')


@require_POST
@login_required
def alert_resolve_view(request, alert_id):
    """
    Transitions an alert from 'new' or 'acknowledged' to 'resolved'.
    Modifies only existing SQLite columns.
    """
    alert = get_object_or_404(Alert, id=alert_id, user_id=request.user.id)
    if alert.status in ('new', 'acknowledged'):
        alert.status = 'resolved'
        alert.resolved_at = timezone.now()
        alert.save(update_fields=['status', 'resolved_at'])
        msg = f"Alert #{alert.id} marked as resolved."
        messages.success(request, msg)
        logger.info(f"[ALERTS] User {request.user.id} resolved alert {alert_id}.")
    else:
        msg = f"Alert #{alert.id} is already in status '{alert.status}'."
        messages.warning(request, msg)

    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"status": "ok", "success": True, "alert_status": alert.status, "message": msg})
    return redirect(request.META.get('HTTP_REFERER') or f'/alerts/{alert_id}/')


# =========================================================================
# PHASE 6D: INCIDENT CASES VIEWS
# =========================================================================

@never_cache
@login_required
def cases_list_view(request):
    """
    Renders the forensic Incident Cases registry.
    """
    user_id = request.user.id
    cases_qs = IncidentCase.objects.filter(user_id=user_id).select_related('alert', 'alert__camera')

    status_filter = request.GET.get('status', '').strip().upper()
    if status_filter in ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED'):
        cases_qs = cases_qs.filter(status=status_filter)

    priority_filter = request.GET.get('priority', '').strip().upper()
    if priority_filter in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'):
        cases_qs = cases_qs.filter(priority=priority_filter)

    search_query = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()
    if search_query:
        cases_qs = cases_qs.filter(
            Q(case_number__icontains=search_query) |
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    cases_qs = cases_qs.order_by('-created_at', '-id')

    page_number = request.GET.get('page', 1)
    paginator = Paginator(cases_qs, 20)
    page_obj = paginator.get_page(page_number)

    total_count = IncidentCase.objects.filter(user_id=user_id).count()

    return render(request, 'pages/cases/index.html', {
        'page_obj': page_obj,
        'cases': page_obj.object_list,
        'total_count': total_count,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'search_query': search_query,
    })


@never_cache
@login_required
def case_detail_view(request, case_id):
    """
    Renders the complete forensic investigation workspace for an Incident Case.
    """
    case = get_object_or_404(
        IncidentCase.objects.select_related('alert', 'alert__camera'),
        id=case_id,
        user_id=request.user.id
    )

    alert = case.alert
    notes = list(alert.incident_notes.all().order_by('-created_at')) if alert else []
    evidence_items = list(alert.evidence_items.all().order_by('-captured_at')) if alert else []

    # Assemble chronological timeline
    timeline = []
    if alert:
        if alert.detected_at:
            timeline.append({'time': alert.detected_at, 'label': 'Alert Detected by AI Engine', 'color': 'danger'})
        if alert.created_at:
            timeline.append({'time': alert.created_at, 'label': 'Alert Recorded in System', 'color': 'primary'})
        if alert.acknowledged_at:
            timeline.append({'time': alert.acknowledged_at, 'label': 'Alert Acknowledged by Investigator', 'color': 'warning'})
        if alert.resolved_at:
            timeline.append({'time': alert.resolved_at, 'label': 'Alert Resolved', 'color': 'success'})

        for ev in evidence_items:
            if ev.captured_at:
                timeline.append({'time': ev.captured_at, 'label': f'Evidence Captured ({ev.evidence_type})', 'color': 'info'})

        for note in notes:
            timeline.append({'time': note.created_at, 'label': 'Investigation Note Added', 'color': 'info'})

    if case.created_at:
        timeline.append({'time': case.created_at, 'label': f'Incident Case #{case.case_number} Created', 'color': 'primary'})
    if case.closed_at:
        timeline.append({'time': case.closed_at, 'label': 'Incident Case Closed', 'color': 'secondary'})

    timeline.sort(key=lambda x: x['time'])

    return render(request, 'pages/cases/detail.html', {
        'case': case,
        'alert': alert,
        'notes': notes,
        'evidence_items': evidence_items,
        'timeline': timeline,
    })
