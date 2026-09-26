"""
Django Notifications Views.
Phase 6E: Notifications migration.
Exposes security notification center and unread state management through Django.
Any status updates modify ONLY the existing is_read/read_at columns without schema changes.
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.core.paginator import Paginator

from apps.accounts.decorators import login_required
from apps.notifications.models import Notification

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

    redirect_url = request.META.get('HTTP_REFERER') or '/notifications/'
    return redirect(redirect_url)


@require_POST
@login_required
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

    redirect_url = request.META.get('HTTP_REFERER') or '/notifications/'
    return redirect(redirect_url)


@never_cache
@login_required
def unread_count_api_view(request):
    """
    JSON API returning current unread notifications count for UI badges.
    """
    count = Notification.objects.filter(user_id=request.user.id, is_read=False).count()
    return JsonResponse({'count': count})


@never_cache
@login_required
def api_notifications_list_view(request):
    """
    JSON API for notifications polling in app.js toasts.
    """
    user_id = request.user.id
    notifs_qs = Notification.objects.filter(user_id=user_id).select_related('alert', 'alert__camera')
    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter == 'unread':
        notifs_qs = notifs_qs.filter(is_read=False)
    try:
        per_page = int(request.GET.get('per_page', 5))
    except (ValueError, TypeError):
        per_page = 5
    notifs = list(notifs_qs.order_by('-created_at', '-id')[:per_page])
    data = []
    for n in notifs:
        title = n.alert.title if (n.alert and n.alert.title) else (n.alert.event_type if (n.alert and n.alert.event_type) else "Security Notification")
        message = n.alert.message if (n.alert and n.alert.message) else f"Security event #{n.id}"
        data.append({
            'id': n.id,
            'title': title,
            'message': message,
            'is_read': n.is_read,
            'alert': {
                'id': n.alert.id if n.alert else None,
                'title': n.alert.title if (n.alert and n.alert.title) else title,
                'message': n.alert.message if (n.alert and n.alert.message) else message,
                'camera_id': n.alert.camera_id if n.alert else None,
                'event_type': n.alert.event_type if n.alert else None,
                'severity': n.alert.severity if n.alert else None,
            } if n.alert else None
        })
    return JsonResponse({'notifications': data, 'count': len(data)})

