"""
DeepVision REST/JSON API Layer.
Provides centralized, strongly typed JSON endpoints for the React frontend:
- Auth (session-based, CSRF protected, PBKDF2 hashing with scrypt backward compatibility)
- Dashboard (real SQLite statistics)
- Cameras (list, detail, stream telemetry, test, recording triggers)
- Recordings (list, detail, HTTP 206 range stream URL metadata)
- Evidence (vault list, detail)
- Alerts & Cases (list, detail, state transitions, investigation notes)
- Notifications (real-time unread count, list, mark read)
- Assistant (grounded SOC domain assistant)
"""

import json
import logging
import re
from datetime import datetime, timezone as dt_timezone
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.accounts.decorators import login_required
from apps.accounts.models import User
from apps.accounts.email_service import send_verification_email, send_password_reset_email
from apps.accounts.views import validate_signup_inputs, validate_password_strength, EMAIL_REGEX
from apps.cameras.models import Camera
from apps.recordings.models import Recording
from apps.evidence.models import Evidence
from apps.alerts.models import Alert, IncidentCase, IncidentNote
from apps.alerts.incident_service import get_incident_context
from apps.notifications.models import Notification
from apps.ai.engine import (
    get_engine_status,
    get_engine_health,
    is_engine_reachable,
    is_camera_recording,
    get_camera_stats,
    test_camera_connection,
    test_existing_camera,
    warm_camera,
    start_camera_recording,
    stop_camera_recording,
)
from apps.core.media_service import safe_resolve_recording, safe_resolve_evidence

logger = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    if not size_bytes or size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def _parse_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except Exception:
        return {}


# =========================================================================
# AUTHENTICATION APIS
# =========================================================================

@ensure_csrf_cookie
@require_GET
def api_csrf(request):
    """Returns current CSRF token and sets the cookie."""
    token = get_token(request)
    return JsonResponse({"csrfToken": token})


@never_cache
@require_GET
def api_me(request):
    """Returns current authenticated session user state."""
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return JsonResponse({
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
            }
        })
    return JsonResponse({"authenticated": False, "user": None})


@require_POST
def api_login(request):
    """Session login supporting JSON payload."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()
    password = data.get("password", "") or request.POST.get("password", "")

    if not email or not password:
        return JsonResponse({"success": False, "error": "Email and password are required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user or not user.check_password(password):
        return JsonResponse({"success": False, "error": "Invalid email or password."}, status=401)

    if not user.is_email_verified:
        request.session["signup_email"] = user.email
        return JsonResponse({
            "success": False,
            "error": "Please verify your email before logging in.",
            "needs_verification": True,
            "email": user.email
        }, status=403)

    if not user.is_active:
        return JsonResponse({"success": False, "error": "Your account is currently inactive."}, status=403)

    request.session.flush()
    request.session["user_id"] = user.id

    return JsonResponse({
        "success": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }
    })


@require_POST
def api_signup(request):
    """Creates user using PBKDF2 hashing and sends 6-digit OTP."""
    data = _parse_body(request)
    full_name = data.get("full_name", "").strip() or request.POST.get("full_name", "").strip()
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()
    password = data.get("password", "") or request.POST.get("password", "")
    confirm_password = data.get("confirm_password", "") or request.POST.get("confirm_password", "")

    err = validate_signup_inputs(full_name, email, password, confirm_password)
    if err:
        return JsonResponse({"success": False, "error": err}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"success": False, "error": "An account with this email already exists."}, status=400)

    try:
        new_user = User(
            full_name=full_name,
            email=email,
            role="user",
            is_email_verified=False,
            is_active=True,
        )
        new_user.set_password(password)  # Uses Django PBKDF2
        otp = new_user.generate_otp()
        new_user.save()

        try:
            sent = send_verification_email(email, otp, full_name)
            if not sent:
                logger.warning(f"[AUTH] Verification email was not dispatched for {email}")
        except Exception as e:
            logger.error(f"[AUTH] Failed to send verification email to {email}: {e}")

        request.session["signup_email"] = email
        return JsonResponse({
            "success": True,
            "message": "Account created successfully. A verification code has been sent to your email.",
            "email": email
        })
    except Exception as e:
        logger.error(f"[AUTH] Signup failed: {e}")
        return JsonResponse({"success": False, "error": "An error occurred while creating your account."}, status=500)


@require_POST
def api_verify_otp(request):
    """Validates 6-digit email verification OTP."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.session.get("signup_email", "")
    otp = data.get("otp", "").strip() or request.POST.get("otp", "").strip()

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and verification code are required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Account not found."}, status=404)

    success, err_msg = user.verify_otp(otp)
    if not success:
        user.save(update_fields=["email_otp_attempts"])
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    user.save(update_fields=["is_email_verified", "email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
    request.session.flush()
    request.session["user_id"] = user.id

    return JsonResponse({
        "success": True,
        "message": "Email verified successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }
    })


@require_POST
def api_resend_otp(request):
    """Resends email verification OTP."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.session.get("signup_email", "")

    if not email:
        return JsonResponse({"success": False, "error": "Email is required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Account not found."}, status=404)

    if user.is_email_verified:
        return JsonResponse({"success": False, "error": "Email is already verified."}, status=400)

    otp = user.generate_otp()
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    try:
        sent = send_verification_email(user.email, otp, user.full_name)
        if not sent:
            logger.warning(f"[AUTH] Resend verification email was not dispatched for {user.email}")
    except Exception as e:
        logger.error(f"[AUTH] Failed to resend verification email to {user.email}: {e}")

    return JsonResponse({"success": True, "message": "A new verification code has been sent."})


@require_POST
def api_forgot_password(request):
    """Initiates password reset flow."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"success": False, "error": "Email address is required."}, status=400)

    user = User.objects.filter(email=email).first()
    if user:
        otp = user.generate_reset_otp()
        user.save(update_fields=["password_reset_otp_hash", "password_reset_otp_expires_at", "password_reset_otp_sent_at", "password_reset_otp_attempts"])
        try:
            sent = send_password_reset_email(user.email, otp, user.full_name)
            if not sent:
                logger.warning(f"[AUTH] Password reset email was not dispatched for {user.email}")
        except Exception as e:
            logger.error(f"[AUTH] Failed to send reset email to {user.email}: {e}")

    # Constant message prevents account enumeration
    return JsonResponse({"success": True, "message": "If an account exists with this email, a reset code has been sent."})



@require_POST
def api_reset_password(request):
    """Verifies OTP and resets password using PBKDF2."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()
    otp = data.get("otp", "").strip() or request.POST.get("otp", "").strip()
    new_password = data.get("new_password", "") or request.POST.get("new_password", "")
    confirm_password = data.get("confirm_password", "") or request.POST.get("confirm_password", "")

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and reset code are required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Invalid reset code or email."}, status=400)

    success, err_msg = user.verify_reset_otp(otp)
    if not success:
        user.save(update_fields=["password_reset_otp_attempts"])
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    err = validate_password_strength(new_password)
    if err:
        return JsonResponse({"success": False, "error": err}, status=400)

    if new_password != confirm_password:
        return JsonResponse({"success": False, "error": "Passwords do not match."}, status=400)

    user.set_password(new_password)  # PBKDF2
    user.clear_reset_otp()
    user.save(update_fields=["password_hash", "password_reset_otp_hash", "password_reset_otp_expires_at", "password_reset_otp_attempts", "password_reset_otp_sent_at"])

    return JsonResponse({"success": True, "message": "Password successfully reset. You may now log in."})


@require_POST
def api_logout(request):
    """Flushes session."""
    request.session.flush()
    return JsonResponse({"success": True, "message": "Logged out successfully."})


# =========================================================================
# DASHBOARD APIS
# =========================================================================

@never_cache
@login_required
def api_dashboard_stats(request):
    """Returns SOC dashboard real metrics and recent activities."""
    user_id = request.user.id
    user_cameras = list(Camera.objects.filter(user_id=user_id).order_by('id'))
    total_cameras = len(user_cameras)
    online_cameras = sum(1 for c in user_cameras if c.status == 'online')
    active_cameras = sum(1 for c in user_cameras if c.is_active)

    new_alerts_count = Alert.objects.filter(user_id=user_id, status__in=['new', 'unresolved', 'active', 'OPEN']).count()
    high_critical_count = Alert.objects.filter(user_id=user_id, severity__in=['high', 'critical', 'HIGH', 'CRITICAL']).count()
    total_recordings = Recording.objects.filter(user_id=user_id).count()
    total_evidence = Evidence.objects.filter(user_id=user_id).count()
    total_cases = IncidentCase.objects.filter(user_id=user_id).count()
    unread_notifications = Notification.objects.filter(user_id=user_id, is_read=False).count()

    recent_alerts_qs = Alert.objects.filter(user_id=user_id).select_related('camera').order_by('-detected_at', '-id')[:5]
    recent_alerts = []
    for a in recent_alerts_qs:
        recent_alerts.append({
            "id": a.id,
            "title": a.title or a.event_type or "Security Alert",
            "message": a.message or "",
            "severity": a.severity or "medium",
            "status": a.status or "new",
            "detected_at": a.detected_at.isoformat() if a.detected_at else "",
            "camera_name": a.camera.name if a.camera else "Channel 01",
            "camera_id": a.camera_id,
        })

    recent_recordings_qs = Recording.objects.filter(user_id=user_id).select_related('camera').order_by('-started_at', '-id')[:4]
    recent_recordings = []
    for r in recent_recordings_qs:
        recent_recordings.append({
            "id": r.id,
            "filename": r.filename,
            "camera_name": r.camera.name if r.camera else "Channel 01",
            "camera_id": r.camera_id,
            "duration_seconds": r.duration_seconds or 0,
            "file_size": r.file_size or 0,
            "formatted_size": _format_size(r.file_size),
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "status": r.status or "completed",
        })

    cameras_data = []
    for c in user_cameras:
        cameras_data.append({
            "id": c.id,
            "name": c.name,
            "location": c.location or "Default Zone",
            "source_type": c.source_type,
            "status": c.status,
            "is_active": c.is_active,
            "is_recording": is_camera_recording(c.id, user_id),
        })

    engine_reachable = is_engine_reachable(timeout=0.5)

    return JsonResponse({
        "total_cameras": total_cameras,
        "online_cameras": online_cameras,
        "active_cameras": active_cameras,
        "new_alerts_count": new_alerts_count,
        "high_critical_count": high_critical_count,
        "total_recordings": total_recordings,
        "total_evidence": total_evidence,
        "total_cases": total_cases,
        "unread_notifications": unread_notifications,
        "recent_alerts": recent_alerts,
        "recent_recordings": recent_recordings,
        "cameras": cameras_data,
        "engine_reachable": engine_reachable,
    })


# =========================================================================
# CAMERAS APIS
# =========================================================================

@never_cache
@login_required
def api_cameras_list(request):
    """Returns cameras list for authenticated user with operational status."""
    user_id = request.user.id
    cameras_qs = Camera.objects.filter(user_id=user_id).order_by('id')
    status_filter = request.GET.get('status', 'all').strip().lower()
    if status_filter in ('online', 'offline'):
        cameras_qs = cameras_qs.filter(status=status_filter)

    cameras = []
    for c in cameras_qs:
        cameras.append({
            "id": c.id,
            "name": c.name,
            "source_type": c.source_type,
            "source": c.source,
            "location": c.location or "Default Zone",
            "status": c.status,
            "is_active": c.is_active,
            "is_recording": is_camera_recording(c.id, user_id),
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })

    engine_status = get_engine_status()
    engine_reachable = is_engine_reachable(timeout=0.5)

    return JsonResponse({
        "cameras": cameras,
        "engine_status": engine_status,
        "engine_reachable": engine_reachable,
        "total": len(cameras),
    })


@never_cache
@login_required
def api_camera_detail(request, camera_id):
    """Returns single camera metadata and runtime state."""
    camera = get_object_or_404(Camera, id=camera_id, user_id=request.user.id)
    engine_reachable = is_engine_reachable(timeout=0.5)
    is_recording = is_camera_recording(camera.id, request.user.id)
    recordings_count = camera.recordings.filter(user_id=request.user.id).count()
    alerts_count = camera.alerts.filter(user_id=request.user.id).count()

    recent_recordings = []
    for r in camera.recordings.filter(user_id=request.user.id).order_by('-started_at', '-id')[:5]:
        recent_recordings.append({
            "id": r.id,
            "filename": r.filename,
            "duration_seconds": r.duration_seconds,
            "file_size": r.file_size,
            "formatted_size": _format_size(r.file_size),
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "status": r.status,
        })

    recent_alerts = []
    for a in camera.alerts.filter(user_id=request.user.id).order_by('-detected_at', '-id')[:5]:
        recent_alerts.append({
            "id": a.id,
            "title": a.title or a.event_type or "Security Alert",
            "severity": a.severity,
            "status": a.status,
            "detected_at": a.detected_at.isoformat() if a.detected_at else "",
        })

    return JsonResponse({
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "source_type": camera.source_type,
            "source": camera.source,
            "location": camera.location,
            "status": camera.status,
            "is_active": camera.is_active,
            "created_at": camera.created_at.isoformat() if camera.created_at else "",
        },
        "is_recording": is_recording,
        "engine_reachable": engine_reachable,
        "recordings_count": recordings_count,
        "alerts_count": alerts_count,
        "recent_recordings": recent_recordings,
        "recent_alerts": recent_alerts,
    })


# =========================================================================
# RECORDINGS APIS
# =========================================================================

@never_cache
@login_required
def api_recordings_list(request):
    """Returns paginated recordings with filter criteria."""
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

    type_filter = request.GET.get('type', '').strip().lower()
    if type_filter == 'anomaly':
        recordings_qs = recordings_qs.filter(filename__icontains='ANOMALY')
    elif type_filter in ('continuous', 'normal'):
        recordings_qs = recordings_qs.exclude(filename__icontains='ANOMALY')

    recordings_qs = recordings_qs.order_by('-started_at', '-id')
    page_number = int(request.GET.get('page', 1) or 1)
    per_page = int(request.GET.get('per_page', 24) or 24)
    paginator = Paginator(recordings_qs, per_page)
    page_obj = paginator.get_page(page_number)

    items = []
    total_size = 0
    for r in page_obj:
        full_path = safe_resolve_recording(r.file_path)
        file_exists = full_path is not None
        if file_exists:
            total_size += (r.file_size or 0)
        items.append({
            "id": r.id,
            "filename": r.filename,
            "camera_id": r.camera_id,
            "camera_name": r.camera.name if r.camera else "Channel 01",
            "duration_seconds": r.duration_seconds or 0,
            "file_size": r.file_size or 0,
            "formatted_size": _format_size(r.file_size),
            "file_exists": file_exists,
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "ended_at": r.ended_at.isoformat() if r.ended_at else "",
            "status": r.status or "completed",
            "stream_url": f"/recordings/{r.id}/view/",
            "download_url": f"/recordings/{r.id}/download/",
        })

    user_cameras = [{"id": c.id, "name": c.name} for c in Camera.objects.filter(user_id=user_id).order_by('name')]

    return JsonResponse({
        "recordings": items,
        "total_count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "cameras": user_cameras,
        "total_size": total_size,
        "formatted_total_size": _format_size(total_size),
    })


@never_cache
@login_required
def api_recording_detail(request, recording_id):
    """Returns single recording metadata and events."""
    recording = get_object_or_404(Recording.objects.select_related('camera'), id=recording_id, user_id=request.user.id)
    full_path = safe_resolve_recording(recording.file_path)

    events = []
    if recording.camera and recording.started_at:
        events_qs = Alert.objects.filter(
            camera_id=recording.camera_id,
            user_id=request.user.id,
            detected_at__gte=recording.started_at
        )
        if recording.ended_at:
            events_qs = events_qs.filter(detected_at__lte=recording.ended_at)
        for e in events_qs.order_by('detected_at')[:20]:
            events.append({
                "id": e.id,
                "title": e.title or e.event_type,
                "severity": e.severity,
                "detected_at": e.detected_at.isoformat() if e.detected_at else "",
            })

    return JsonResponse({
        "recording": {
            "id": recording.id,
            "filename": recording.filename,
            "camera_id": recording.camera_id,
            "camera_name": recording.camera.name if recording.camera else "Channel 01",
            "duration_seconds": recording.duration_seconds or 0,
            "file_size": recording.file_size or 0,
            "formatted_size": _format_size(recording.file_size),
            "file_exists": full_path is not None,
            "started_at": recording.started_at.isoformat() if recording.started_at else "",
            "ended_at": recording.ended_at.isoformat() if recording.ended_at else "",
            "status": recording.status or "completed",
            "stream_url": f"/recordings/{recording.id}/view/",
            "download_url": f"/recordings/{recording.id}/download/",
        },
        "events": events,
    })


# =========================================================================
# EVIDENCE APIS
# =========================================================================

@never_cache
@login_required
def api_evidence_list(request):
    """Returns forensic evidence vault assets."""
    user_id = request.user.id
    evidence_qs = Evidence.objects.filter(user_id=user_id).select_related('camera', 'alert')

    ev_type = request.GET.get('type', '').strip().lower()
    if ev_type in ('snapshot', 'video'):
        evidence_qs = evidence_qs.filter(evidence_type=ev_type)

    camera_id = request.GET.get('camera_id', '').strip()
    if camera_id and camera_id.isdigit():
        evidence_qs = evidence_qs.filter(camera_id=int(camera_id))

    alert_id = request.GET.get('alert_id', '').strip()
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
    page_number = int(request.GET.get('page', 1) or 1)
    per_page = int(request.GET.get('per_page', 18) or 18)
    paginator = Paginator(evidence_qs, per_page)
    page_obj = paginator.get_page(page_number)

    items = []
    for ev in page_obj:
        full_path = safe_resolve_evidence(ev.file_path)
        items.append({
            "id": ev.id,
            "file_name": ev.file_name,
            "evidence_type": ev.evidence_type,
            "mime_type": ev.mime_type,
            "file_size": ev.file_size,
            "formatted_size": _format_size(ev.file_size),
            "file_available": full_path is not None,
            "captured_at": ev.captured_at.isoformat() if ev.captured_at else "",
            "camera_id": ev.camera_id,
            "camera_name": ev.camera.name if ev.camera else "Channel 01",
            "alert_id": ev.alert_id,
            "alert_title": ev.alert.title if ev.alert else None,
            "preview_url": f"/evidence/{ev.id}/preview/",
            "download_url": f"/evidence/{ev.id}/download/",
        })

    user_cameras = [{"id": c.id, "name": c.name} for c in Camera.objects.filter(user_id=user_id).order_by('name')]

    return JsonResponse({
        "evidence": items,
        "total_count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "cameras": user_cameras,
    })


@never_cache
@login_required
def api_evidence_detail(request, evidence_id):
    """Returns single evidence metadata."""
    ev = get_object_or_404(Evidence.objects.select_related('camera', 'alert'), id=evidence_id, user_id=request.user.id)
    full_path = safe_resolve_evidence(ev.file_path)

    return JsonResponse({
        "evidence": {
            "id": ev.id,
            "file_name": ev.file_name,
            "evidence_type": ev.evidence_type,
            "mime_type": ev.mime_type,
            "file_size": ev.file_size,
            "formatted_size": _format_size(ev.file_size),
            "file_available": full_path is not None,
            "captured_at": ev.captured_at.isoformat() if ev.captured_at else "",
            "camera_id": ev.camera_id,
            "camera_name": ev.camera.name if ev.camera else "Channel 01",
            "alert_id": ev.alert_id,
            "alert_title": ev.alert.title if ev.alert else None,
            "preview_url": f"/evidence/{ev.id}/preview/",
            "download_url": f"/evidence/{ev.id}/download/",
        }
    })


# =========================================================================
# ALERTS & CASES APIS
# =========================================================================

@never_cache
@login_required
def api_alerts_list(request):
    """Returns alerts inbox with severity/status filters, media flags, case association, and metrics."""
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

    camera_id = request.GET.get('camera_id', '').strip()
    if camera_id and camera_id.isdigit():
        alerts_qs = alerts_qs.filter(camera_id=int(camera_id))

    # Media / Case Flags filtering
    has_video_filter = request.GET.get('has_video', '').strip().lower()
    if has_video_filter in ('true', '1', 'yes'):
        alerts_qs = alerts_qs.filter(evidence_items__evidence_type='video').distinct()

    has_snapshot_filter = request.GET.get('has_snapshot', '').strip().lower()
    if has_snapshot_filter in ('true', '1', 'yes'):
        alerts_qs = alerts_qs.filter(evidence_items__evidence_type='snapshot').distinct()

    has_evidence_filter = request.GET.get('has_evidence', '').strip().lower()
    if has_evidence_filter in ('true', '1', 'yes'):
        alerts_qs = alerts_qs.filter(evidence_items__isnull=False).distinct()

    has_case_filter = request.GET.get('has_case', '').strip().lower()
    if has_case_filter in ('true', '1', 'yes'):
        alerts_qs = alerts_qs.filter(incident_cases__isnull=False).distinct()
    elif has_case_filter in ('false', '0', 'no'):
        alerts_qs = alerts_qs.filter(incident_cases__isnull=True).distinct()

    has_audio_filter = request.GET.get('has_audio', '').strip().lower()
    if has_audio_filter in ('true', '1', 'yes'):
        # Video-only capture sources currently have no audio tracks
        alerts_qs = alerts_qs.none()

    search_query = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()
    if search_query:
        search_filter = (
            Q(title__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(event_type__icontains=search_query) |
            Q(camera__name__icontains=search_query) |
            Q(incident_cases__case_number__icontains=search_query)
        )
        if search_query.isdigit():
            search_filter |= Q(id=int(search_query))
        alerts_qs = alerts_qs.filter(search_filter).distinct()

    alerts_qs = alerts_qs.order_by('-detected_at', '-id').prefetch_related('evidence_items', 'incident_cases')
    page_number = int(request.GET.get('page', 1) or 1)
    per_page = int(request.GET.get('per_page', 20) or 20)
    paginator = Paginator(alerts_qs, per_page)
    page_obj = paginator.get_page(page_number)

    items = []
    for a in page_obj:
        ev_list = list(a.evidence_items.all())
        cases_list = list(a.incident_cases.all())

        video_ev = next((ev for ev in ev_list if ev.evidence_type == 'video'), None)
        snapshot_ev = next((ev for ev in ev_list if ev.evidence_type == 'snapshot'), None)
        case_obj = cases_list[0] if cases_list else None

        items.append({
            "id": a.id,
            "title": a.title or a.event_type or "Security Alert",
            "message": a.message or "",
            "event_type": a.event_type or "motion",
            "severity": a.severity or "medium",
            "status": a.status or "new",
            "confidence": a.confidence,
            "location": a.location or (a.camera.location if a.camera else "Default Zone"),
            "camera_id": a.camera_id,
            "camera_name": a.camera.name if a.camera else "Channel 01",
            "detected_at": a.detected_at.isoformat() if a.detected_at else "",
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else "",
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else "",
            "has_video": video_ev is not None,
            "video_ev_id": video_ev.id if video_ev else None,
            "has_snapshot": snapshot_ev is not None,
            "snapshot_ev_id": snapshot_ev.id if snapshot_ev else None,
            "has_audio": False,
            "audio_status": "unavailable",
            "audio_reason": "DirectShow video-only source (no multiplexed audio track)",
            "has_case": case_obj is not None,
            "case_id": case_obj.id if case_obj else None,
            "case_number": case_obj.case_number if case_obj else None,
            "case_status": case_obj.status if case_obj else None,
            "case_priority": case_obj.priority if case_obj else None,
            "evidence_count": len(ev_list),
        })

    user_all = Alert.objects.filter(user_id=user_id)
    total_count = user_all.count()
    new_count = user_all.filter(status='new').count()
    active_high_count = user_all.filter(status='new', severity__in=['high', 'critical']).count()
    resolved_count = user_all.filter(status='resolved').count()
    with_video_count = user_all.filter(evidence_items__evidence_type='video').distinct().count()
    with_case_count = user_all.filter(incident_cases__isnull=False).distinct().count()
    user_cameras = [{"id": c.id, "name": c.name} for c in Camera.objects.filter(user_id=user_id).order_by('name')]

    return JsonResponse({
        "alerts": items,
        "total_count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "metrics": {
            "total_count": total_count,
            "new_count": new_count,
            "active_high_count": active_high_count,
            "resolved_count": resolved_count,
            "with_video_count": with_video_count,
            "with_case_count": with_case_count,
            "with_audio_count": 0,
        },
        "cameras": user_cameras,
    })


@never_cache
@login_required
def api_alert_detail(request, alert_id):
    """Returns single alert detail with strictly scoped canonical incident forensic payload."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse(context)


@never_cache
@login_required
def api_alert_incident_context(request, alert_id):
    """Canonical endpoint returning full strictly scoped incident context."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse(context)


@never_cache
@login_required
def api_alert_scoped_evidence(request, alert_id):
    """Returns ONLY evidence assets strictly belonging to this incident."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse({
        "alert_id": alert_id,
        "evidence": context.get("evidence_items", []),
        "total": len(context.get("evidence_items", [])),
    })


@never_cache
@login_required
def api_alert_scoped_recordings(request, alert_id):
    """Returns ONLY recordings strictly belonging to this incident."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    rec = context.get("primary_media", {}).get("recording")
    recordings = [rec] if rec else []
    return JsonResponse({
        "alert_id": alert_id,
        "recordings": recordings,
        "total": len(recordings),
    })


@never_cache
@login_required
def api_alert_scoped_case(request, alert_id):
    """Returns ONLY the forensic case strictly belonging to this incident."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse({
        "alert_id": alert_id,
        "case": context.get("incident_case"),
    })


@never_cache
@login_required
def api_alert_scoped_notifications(request, alert_id):
    """Returns ONLY notifications strictly belonging to this incident."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse({
        "alert_id": alert_id,
        "notifications": context.get("notifications", []),
        "total": len(context.get("notifications", [])),
    })


@never_cache
@login_required
def api_alert_scoped_timeline(request, alert_id):
    """Returns ONLY chronological timeline milestones strictly belonging to this incident."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    return JsonResponse({
        "alert_id": alert_id,
        "timeline": context.get("timeline", []),
        "total": len(context.get("timeline", [])),
    })


@require_POST
@login_required
def api_alert_create_case(request, alert_id):
    """Creates a forensic case directly linked to an alert."""
    import uuid
    alert = get_object_or_404(Alert, id=alert_id, user_id=request.user.id)
    existing_case = alert.incident_cases.first()
    if existing_case:
        return JsonResponse({
            "success": True,
            "created": False,
            "case": {
                "id": existing_case.id,
                "case_number": existing_case.case_number,
                "title": existing_case.title,
                "status": existing_case.status,
                "priority": existing_case.priority,
            }
        })

    data = _parse_body(request)
    title = data.get("title", "").strip() or f"Case: {alert.title}"
    description = data.get("description", "").strip() or f"Operator forensic investigation for {alert.severity.upper()} alert #{alert.id} ({alert.event_type})."
    priority = (data.get("priority", "").strip().upper() or 
                ("CRITICAL" if alert.severity == "critical" else "HIGH" if alert.severity == "high" else "MEDIUM"))

    date_str = datetime.now().strftime("%Y%m%d")
    case_number = f"CASE-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    case = IncidentCase.objects.create(
        case_number=case_number,
        user=request.user,
        alert=alert,
        title=title,
        description=description,
        priority=priority,
        status="open",
        assigned_to=request.user.full_name or request.user.email,
    )

    return JsonResponse({
        "success": True,
        "created": True,
        "case": {
            "id": case.id,
            "case_number": case.case_number,
            "title": case.title,
            "description": case.description,
            "priority": case.priority,
            "status": case.status,
            "assigned_to": case.assigned_to,
            "created_at": case.created_at.isoformat() if case.created_at else timezone.now().isoformat(),
        }
    })


@require_POST
@login_required
def api_alert_add_note(request, alert_id):
    """Appends an investigator note directly to an alert."""
    alert = get_object_or_404(Alert, id=alert_id, user_id=request.user.id)
    data = _parse_body(request)
    note_text = data.get("note", "").strip() or request.POST.get("note", "").strip()

    if not note_text:
        return JsonResponse({"success": False, "error": "Note text is required."}, status=400)

    note = IncidentNote.objects.create(
        alert=alert,
        user=request.user,
        body=note_text,
    )

    return JsonResponse({
        "success": True,
        "note": {
            "id": note.id,
            "note": note.body,
            "author_name": request.user.full_name or request.user.email,
            "created_at": note.created_at.isoformat() if note.created_at else timezone.now().isoformat(),
        }
    })


@never_cache
@login_required
def api_cases_list(request):
    """Returns incident cases list."""
    user_id = request.user.id
    cases_qs = IncidentCase.objects.filter(user_id=user_id).select_related('alert', 'alert__camera').order_by('-created_at')

    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter:
        if status_filter == 'investigating':
            status_filter = 'in_progress'
        cases_qs = cases_qs.filter(status__iexact=status_filter)

    priority_filter = request.GET.get('priority', '').strip().lower()
    if priority_filter:
        cases_qs = cases_qs.filter(priority__iexact=priority_filter)

    alert_id = request.GET.get('alert_id', '').strip()
    if alert_id and alert_id.isdigit():
        cases_qs = cases_qs.filter(alert_id=int(alert_id))

    search_query = request.GET.get('search', '').strip() or request.GET.get('q', '').strip()
    if search_query:
        cases_qs = cases_qs.filter(
            Q(title__icontains=search_query) |
            Q(case_number__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    items = []
    for c in cases_qs:
        items.append({
            "id": c.id,
            "case_number": c.case_number,
            "title": c.title,
            "description": c.description or "",
            "priority": c.priority or "medium",
            "status": c.status or "open",
            "alert_id": c.alert_id,
            "alert_title": c.alert.title if c.alert else "",
            "camera_name": c.alert.camera.name if (c.alert and c.alert.camera) else "Channel 01",
            "created_at": c.created_at.isoformat() if c.created_at else "",
            "closed_at": c.closed_at.isoformat() if c.closed_at else "",
        })

    return JsonResponse({"cases": items, "total": len(items)})


@never_cache
@login_required
def api_case_detail(request, case_id):
    """Returns single case details with forensic timeline notes."""
    case = get_object_or_404(IncidentCase.objects.select_related('alert', 'alert__camera'), id=case_id, user_id=request.user.id)
    notes = []
    if case.alert:
        for n in case.alert.incident_notes.all().select_related('user').order_by('created_at'):
            notes.append({
                "id": n.id,
                "note": n.body,
                "author_id": n.user_id,
                "author_name": n.user.full_name if n.user else "Investigator",
                "created_at": n.created_at.isoformat() if n.created_at else "",
            })

    return JsonResponse({
        "case": {
            "id": case.id,
            "case_number": case.case_number,
            "title": case.title,
            "description": case.description or "",
            "priority": case.priority,
            "status": case.status,
            "alert_id": case.alert_id,
            "alert_title": case.alert.title if case.alert else "",
            "camera_name": case.alert.camera.name if (case.alert and case.alert.camera) else "Channel 01",
            "created_at": case.created_at.isoformat() if case.created_at else "",
            "closed_at": case.closed_at.isoformat() if case.closed_at else "",
        },
        "notes": notes,
    })


@require_POST
@login_required
def api_case_add_note(request, case_id):
    """Appends note to case's alert."""
    case = get_object_or_404(IncidentCase, id=case_id, user_id=request.user.id)
    data = _parse_body(request)
    note_text = data.get("note", "").strip() or request.POST.get("note", "").strip()

    if not note_text:
        return JsonResponse({"success": False, "error": "Note text is required."}, status=400)

    if not case.alert:
        return JsonResponse({"success": False, "error": "This case has no associated alert to attach notes to."}, status=400)

    note = IncidentNote.objects.create(
        alert=case.alert,
        user=request.user,
        body=note_text,
    )

    return JsonResponse({
        "success": True,
        "note": {
            "id": note.id,
            "note": note.body,
            "author_name": request.user.full_name,
            "created_at": note.created_at.isoformat() if note.created_at else timezone.now().isoformat(),
        }
    })

