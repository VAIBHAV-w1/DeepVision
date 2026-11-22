"""
Django Notifications Views.
Phase 6E: Notifications migration.
Exposes security notification center and unread state management through Django.
Any status updates modify ONLY the existing is_read/read_at columns without schema changes.
"""

import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.paginator import Paginator
from django.db import DatabaseError, InterfaceError, OperationalError, close_old_connections

from apps.accounts.decorators import login_required
from apps.core.api import handle_db_errors
from apps.core.rate_limiter import ratelimit
from apps.notifications.models import Notification, NotificationPreference

logger = logging.getLogger(__name__)


@never_cache
@login_required
def notifications_list_view(request):
    """
    Renders the dedicated Notification Center & Security Inbox.
    """
    user_id = request.user.id
    notifs_qs = Notification.objects.filter(user_id=user_id).select_related('alert', 'alert__camera')

    status_filter = request.GET.get('status', 'all').strip().lower()
    if status_filter == 'unread':
        notifs_qs = notifs_qs.filter(is_read=False)
    elif status_filter == 'read':
        notifs_qs = notifs_qs.filter(is_read=True)

    severity_filter = request.GET.get('severity', '').strip().lower()
    if severity_filter in ('low', 'medium', 'high', 'critical'):
        notifs_qs = notifs_qs.filter(alert__severity=severity_filter)

    date_filter = request.GET.get('date', '').strip().lower()
    if date_filter == 'today':
        notifs_qs = notifs_qs.filter(created_at__date=timezone.localdate())
    elif date_filter == 'yesterday':
        from datetime import timedelta
        notifs_qs = notifs_qs.filter(created_at__date=timezone.localdate() - timedelta(days=1))
    elif date_filter:
        import re
        from datetime import datetime
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_filter):
            try:
                d_val = datetime.strptime(date_filter, '%Y-%m-%d').date()
                notifs_qs = notifs_qs.filter(created_at__date=d_val)
            except Exception:
                pass

    notifs_qs = notifs_qs.order_by('-created_at', '-id')

    page_number = request.GET.get('page', 1)
    paginator = Paginator(notifs_qs, 20)
    page_obj = paginator.get_page(page_number)

    unread_count = Notification.objects.filter(user_id=user_id, is_read=False).count()

    return render(request, 'pages/notifications/index.html', {
        'page_obj': page_obj,
        'notifications': page_obj.object_list,
        'unread_count': unread_count,
        'current_status': status_filter,
        'current_severity': severity_filter,
    })


@require_POST
@login_required
@handle_db_errors
def mark_notification_read_view(request, notification_id):
    """
    POST action marking a single notification as read.
    Modifies ONLY the existing is_read and read_at fields.
    """
    notif = get_object_or_404(Notification, id=notification_id, user_id=request.user.id)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=['is_read', 'read_at'])
        logger.info(f"[NOTIF] User {request.user.id} marked notification {notification_id} as read.")

    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"status": "ok", "success": True, "message": "Notification marked as read"})

    ref = request.META.get('HTTP_REFERER')
    redirect_url = ref if (ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()})) else '/notifications/'
    return redirect(redirect_url)


@require_POST
@login_required
@handle_db_errors
def mark_all_notifications_read_view(request):
    """
    POST action marking all unread notifications for the user as read.
    Modifies ONLY the existing is_read and read_at fields in bulk.
    """
    now = timezone.now()
    count = Notification.objects.filter(user_id=request.user.id, is_read=False).update(
        is_read=True,
        read_at=now
    )
    logger.info(f"[NOTIF] User {request.user.id} marked {count} notifications as read.")

    if request.headers.get('Accept') == 'application/json' or request.content_type == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({"status": "ok", "success": True, "marked_count": count, "message": f"{count} notifications marked as read"})

    ref = request.META.get('HTTP_REFERER')
    redirect_url = ref if (ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()})) else '/notifications/'
    return redirect(redirect_url)


@never_cache
@login_required
@handle_db_errors
def unread_count_api_view(request):
    """
    JSON API returning current unread notifications count for UI badges.
    Self-heals once if a pooled PostgreSQL connection was closed upstream.
    """
    try:
        count = Notification.objects.filter(user_id=request.user.id, is_read=False).count()
    except (OperationalError, InterfaceError):
        close_old_connections()
        count = Notification.objects.filter(user_id=request.user.id, is_read=False).count()
    return JsonResponse({'count': count})


@never_cache
@login_required
@handle_db_errors
def api_notifications_list_view(request):
    """
    JSON API for notifications center (paginated, with timestamps, camera attribution, and unread counts).
    """
    user_id = request.user.id
    base_qs = Notification.objects.filter(user_id=user_id)
    unread_count = base_qs.filter(is_read=False).count()
    total_all = base_qs.count()

    notifs_qs = base_qs.select_related('alert', 'alert__camera')
    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter == 'unread':
        notifs_qs = notifs_qs.filter(is_read=False)
    elif status_filter == 'read':
        notifs_qs = notifs_qs.filter(is_read=True)

    severity_filter = request.GET.get('severity', '').strip().lower()
    if severity_filter in ('low', 'medium', 'high', 'critical'):
        notifs_qs = notifs_qs.filter(alert__severity=severity_filter)

    date_filter = request.GET.get('date', '').strip().lower()
    if date_filter == 'today':
        notifs_qs = notifs_qs.filter(created_at__date=timezone.localdate())
    elif date_filter == 'yesterday':
        from datetime import timedelta
        notifs_qs = notifs_qs.filter(created_at__date=timezone.localdate() - timedelta(days=1))
    elif date_filter:
        import re
        from datetime import datetime
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_filter):
            try:
                d_val = datetime.strptime(date_filter, '%Y-%m-%d').date()
                notifs_qs = notifs_qs.filter(created_at__date=d_val)
            except Exception:
                pass

    try:
        per_page = max(1, min(100, int(request.GET.get('per_page', 30))))
    except (ValueError, TypeError):
        per_page = 30
    try:
        page_number = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page_number = 1

    paginator = Paginator(notifs_qs.order_by('-created_at', '-id'), per_page)
    page_obj = paginator.get_page(page_number)

    data = []
    for n in page_obj.object_list:
        al = n.alert
        cam = al.camera if al else None
        cam_name = cam.name if cam else (f"Camera 0{al.camera_id}" if (al and al.camera_id) else "System")
        title = al.title if (al and al.title) else (al.event_type if (al and al.event_type) else "Security Notification")
        message = al.message if (al and al.message) else f"Security event #{n.id}"
        ts_dt = n.created_at or (al.detected_at if al else None)
        created_iso = ts_dt.isoformat() if ts_dt else ""
        data.append({
            'id': n.id,
            'alert_id': al.id if al else None,
            'title': title,
            'message': message,
            'is_read': n.is_read,
            'created_at': created_iso,
            'read_at': n.read_at.isoformat() if n.read_at else None,
            'camera_id': al.camera_id if al else None,
            'camera_name': cam_name,
            'severity': al.severity if al else 'medium',
            'alert': {
                'id': al.id,
                'title': al.title or title,
                'message': al.message or message,
                'camera_id': al.camera_id,
                'camera_name': cam_name,
                'event_type': al.event_type,
                'severity': al.severity,
                'detected_at': al.detected_at.isoformat() if al.detected_at else created_iso,
            } if al else None
        })
    return JsonResponse({
        'notifications': data,
        'count': len(data),
        'total_count': paginator.count,
        'total_all': total_all,
        'unread_count': unread_count,
        'num_pages': paginator.num_pages,
        'current_page': page_obj.number,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
    })


_PREF_BOOL_FIELDS = (
    'enabled',
    'notify_critical',
    'notify_high',
    'notify_medium',
    'notify_low',
    'notify_loitering',
    'notify_restricted_entry',
    'notify_unusual_movement',
    'notify_abandoned_object',
    'notify_recording_events',
    'notify_system_events',
)


def _serialize_pref(pref_obj, user_email=""):
    return {
        'enabled': bool(pref_obj.enabled) if pref_obj else True,
        'notify_critical': bool(pref_obj.notify_critical) if pref_obj else True,
        'notify_high': bool(pref_obj.notify_high) if pref_obj else True,
        'notify_medium': bool(pref_obj.notify_medium) if pref_obj else False,
        'notify_low': bool(pref_obj.notify_low) if pref_obj else False,
        'notify_loitering': bool(pref_obj.notify_loitering) if pref_obj else True,
        'notify_restricted_entry': bool(pref_obj.notify_restricted_entry) if pref_obj else True,
        'notify_unusual_movement': bool(pref_obj.notify_unusual_movement) if pref_obj else True,
        'notify_abandoned_object': bool(pref_obj.notify_abandoned_object) if pref_obj else True,
        'notify_recording_events': bool(pref_obj.notify_recording_events) if pref_obj else False,
        'notify_system_events': bool(pref_obj.notify_system_events) if pref_obj else True,
        'email': user_email or "",
    }


@require_http_methods(['GET', 'POST', 'PUT'])
@never_cache
@login_required
@handle_db_errors
def api_notification_preferences_view(request):
    """GET/POST per-user alert and email notification preferences stored in `notification_preferences`."""
    user = request.user
    pref = NotificationPreference.objects.filter(user_id=user.id).first()

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'preferences': _serialize_pref(pref, getattr(user, 'email', '')),
        })

    if getattr(user, 'role', '') == 'viewer' and not getattr(user, 'is_superuser', False):
        return JsonResponse({'success': False, 'error': 'Viewer accounts have read-only access.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload.'}, status=400)

    now = timezone.now()
    if pref is None:
        defaults = {field: bool(payload.get(field, field not in ('notify_medium', 'notify_low', 'notify_recording_events'))) for field in _PREF_BOOL_FIELDS}
        pref = NotificationPreference.objects.create(
            user_id=user.id,
            created_at=now,
            updated_at=now,
            **defaults,
        )
    else:
        for field in _PREF_BOOL_FIELDS:
            if field in payload:
                setattr(pref, field, bool(payload[field]))
        pref.updated_at = now
        pref.save()

    return JsonResponse({
        'success': True,
        'message': 'Notification preferences saved.',
        'preferences': _serialize_pref(pref, getattr(user, 'email', '')),
    })


@never_cache
@login_required
@handle_db_errors
def api_notification_delivery_status_view(request):
    """Returns sanitized email delivery summary & recent audit records plus SMTP configuration status."""
    from django.conf import settings
    from apps.accounts.email_service import get_email_runtime_status
    from apps.notifications.delivery_service import get_delivery_records

    try:
        limit = int(request.GET.get('limit', 30))
    except (TypeError, ValueError):
        limit = 30
    data = get_delivery_records(user_id=request.user.id, limit=limit)
    smtp_configured = bool(
        getattr(settings, 'EMAIL_HOST', '')
        and getattr(settings, 'EMAIL_HOST_USER', '')
        and getattr(settings, 'EMAIL_HOST_PASSWORD', '')
        and getattr(settings, 'DEFAULT_FROM_EMAIL', '')
    )
    return JsonResponse({
        'success': True,
        'smtp_configured': smtp_configured,
        'runtime': get_email_runtime_status(),
        **data,
    })


@require_POST
@never_cache
@login_required
@ratelimit(scope="test_email", limit=5, window=300)
@handle_db_errors
def api_notification_test_email_view(request):
    """Triggers a controlled test email to the user or provided email and returns explicit delivery status."""
    from apps.accounts.email_service import get_email_runtime_status, send_test_email
    from apps.cameras.surveillance_config import normalize_recipients

    if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'success': False, 'error': 'Viewer accounts have read-only access.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        payload = {}
    is_staff = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)
    req_emails = normalize_recipients(payload.get('recipient') or payload.get('email')) if is_staff else []
    target_email = req_emails[0] if req_emails else getattr(request.user, 'email', '')
    if not target_email:
        return JsonResponse({'success': False, 'error': 'No valid recipient email address available.'}, status=400)

    ok = send_test_email(target_email, full_name=getattr(request.user, 'full_name', None), user_id=request.user.id)
    rt = get_email_runtime_status()
    return JsonResponse({
        'success': bool(ok),
        'status': 'sent' if ok else 'failed',
        'provider': rt.get('last_provider'),
        'error_code': rt.get('last_error_code'),
        'message': (
            f"Test email accepted by {rt.get('last_provider') or 'email'} provider."
            if ok
            else f"Email delivery failed ({rt.get('last_error_code') or 'provider error'})."
        ),
    }, status=200 if ok else 502)

