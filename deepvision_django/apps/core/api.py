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

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone as dt_timezone
from functools import wraps
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.core.exceptions import PermissionDenied
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.db import DatabaseError, OperationalError, InterfaceError, connection, close_old_connections
from django.utils import timezone

from apps.accounts.decorators import login_required
from apps.accounts.middleware import compute_session_password_fingerprint
from apps.accounts.models import User
from apps.accounts.email_service import send_verification_email, send_password_reset_email, send_login_otp_email
from apps.accounts.views import validate_signup_inputs, validate_password_strength, EMAIL_REGEX
from apps.cameras.models import Camera
from apps.recordings.models import Recording
from apps.evidence.models import Evidence
from apps.alerts.models import Alert, IncidentCase, IncidentNote, IncidentPolicy, IncidentPlaybook
from apps.alerts.incident_service import get_incident_context
from apps.alerts.soc_triage import analyze_incident, sanitize_untrusted_text
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
from apps.cameras.views import get_accessible_cameras_qs, get_user_camera_or_404
from apps.core.media_service import safe_resolve_recording, safe_resolve_evidence
from apps.core.storage_service import (
    delete_stored_media,
    get_storage_health,
    media_exists,
    parse_storage_uri,
    resolve_local_staged_evidence,
    resolve_local_staged_recording,
    upload_recording_by_id,
)
from apps.core.rate_limiter import ratelimit
from apps.core.models import AuditLog
from apps.core.audit import log_audit

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
        parsed = json.loads(request.body.decode('utf-8'))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_bounded_int(raw_val, default: int, min_val: int = 1, max_val: int = 100) -> int:
    try:
        val = int(raw_val)
    except (TypeError, ValueError):
        return default
    return max(min_val, min(max_val, val))


def _apply_date_filter(qs, request, date_field='created_at'):
    """
    Applies explicit date filtering to a QuerySet:
    - date='today' -> current local date
    - date='yesterday' -> previous date
    - date='YYYY-MM-DD' -> exact date match
    - date_from='YYYY-MM-DD' and/or date_to='YYYY-MM-DD' -> date range
    """
    date_val = request.GET.get('date', '').strip().lower()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    today = timezone.localdate()
    if date_val == 'today':
        return qs.filter(**{f"{date_field}__date": today})
    elif date_val == 'yesterday':
        from datetime import timedelta
        return qs.filter(**{f"{date_field}__date": today - timedelta(days=1)})
    elif date_val and re.match(r'^\d{4}-\d{2}-\d{2}$', date_val):
        try:
            d_obj = datetime.strptime(date_val, '%Y-%m-%d').date()
            return qs.filter(**{f"{date_field}__date": d_obj})
        except Exception:
            pass

    if date_from and re.match(r'^\d{4}-\d{2}-\d{2}$', date_from):
        try:
            d_f = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(**{f"{date_field}__date__gte": d_f})
        except Exception:
            pass
    if date_to and re.match(r'^\d{4}-\d{2}-\d{2}$', date_to):
        try:
            d_t = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(**{f"{date_field}__date__lte": d_t})
        except Exception:
            pass

    return qs


def handle_db_errors(view_func):
    """
    Decorator ensuring database connection drops, timeouts,
    or schema errors self-heal once via close_old_connections() and otherwise
    return a structured HTTP 503 response instead of unhandled 500s.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except (OperationalError, InterfaceError) as first_err:
            try:
                close_old_connections()
                return view_func(request, *args, **kwargs)
            except (OperationalError, InterfaceError, DatabaseError) as db_err:
                logger.error(f"[DB_ERROR] {view_func.__name__}: {type(db_err).__name__}: {db_err} (initial={type(first_err).__name__})")
                return JsonResponse({
                    "success": False,
                    "error": "Database service is temporarily unavailable. Please try again later.",
                    "code": "DATABASE_UNAVAILABLE",
                    "detail": "Connection to the database cluster timed out or failed. Please retry in a few moments."
                }, status=503)
        except DatabaseError as db_err:
            logger.error(f"[DB_ERROR] {view_func.__name__}: {type(db_err).__name__}: {db_err}")
            return JsonResponse({
                "success": False,
                "error": "Database service is temporarily unavailable. Please try again later.",
                "code": "DATABASE_UNAVAILABLE",
                "detail": "Connection to the database cluster timed out or failed. Please retry in a few moments."
            }, status=503)
    return _wrapped


# =========================================================================
# AUTHENTICATION APIS
# =========================================================================

@ensure_csrf_cookie
@require_GET
def api_csrf(request):
    """Returns current CSRF token and sets the cookie."""
    token = get_token(request)
    return JsonResponse({"csrfToken": token})


@ensure_csrf_cookie
@never_cache
@require_GET
def api_me(request):
    """Returns current authenticated session user state and ensures CSRF token availability."""
    csrf_token = get_token(request)
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return JsonResponse({
            "authenticated": True,
            "csrfToken": csrf_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
            }
        })
    return JsonResponse({"authenticated": False, "user": None, "csrfToken": csrf_token})


@require_POST
@ratelimit(scope="login", limit=10, window=60, key_field="email")
@handle_db_errors
def api_login(request):
    """
    Step 1 of Login: Validates username/email and password.
    Every login MUST require a fresh, single-use Login OTP sent to registered email.
    Does NOT establish authenticated session until Login OTP is verified.
    """
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()
    password = data.get("password", "") or request.POST.get("password", "")

    if not email or not password:
        return JsonResponse({"success": False, "error": "Email and password are required."}, status=400)

    try:
        user = User.objects.filter(email=email).first()
    except Exception as db_err:
        logger.error(f"Database error in api_login: {db_err}")
        return JsonResponse({"success": False, "error": "Database service is not ready. Please verify database connection."}, status=503)

    if not user or not user.check_password(password):
        log_audit(request, "AUTH_LOGIN_FAILED", "auth", resource_id=email, description="Invalid email or password.")
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
        return JsonResponse({"success": False, "error": "Your account is currently inactive. Please contact an administrator."}, status=403)

    # Flush session fixation state
    request.session.flush()

    # Generate fresh single-use Login OTP (purpose="login")
    otp = user.generate_otp(purpose="login")
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    try:
        sent = send_login_otp_email(user.email, otp, user.full_name)
        if not sent:
            logger.warning("[AUTH] Sign-in verification email delivery failed for user_id=%s", user.id)
            user.email_otp_hash = None
            user.email_otp_expires_at = None
            user.email_otp_sent_at = None
            user.email_otp_attempts = 0
            user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])
            return JsonResponse({
                "success": False,
                "code": "EMAIL_DELIVERY_UNAVAILABLE",
                "error": "Could not deliver a sign-in code. Please try again later.",
                "detail": "Credentials verified against PostgreSQL, but the outbound email service (SMTP) is not configured or unreachable."
            }, status=503)
    except Exception:
        logger.warning("[AUTH] Sign-in verification email delivery failed for user_id=%s", user.id)
        user.email_otp_hash = None
        user.email_otp_expires_at = None
        user.email_otp_sent_at = None
        user.email_otp_attempts = 0
        user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])
        return JsonResponse({
            "success": False,
            "code": "EMAIL_DELIVERY_UNAVAILABLE",
            "error": "Could not deliver a sign-in code. Please try again later.",
            "detail": "Credentials verified against PostgreSQL, but the outbound email service (SMTP) is not configured or unreachable."
        }, status=503)

    # Set pending login state in signed session (USER IS NOT AUTHENTICATED YET)
    request.session["pending_login_user_id"] = user.id
    request.session["pending_login_email"] = user.email
    log_audit(request, "AUTH_LOGIN_OTP_SENT", "auth", resource_id=user.id, description=f"Login OTP issued for {user.email}.", user=user)

    return JsonResponse({
        "success": True,
        "requires_otp": True,
        "email": user.email,
        "message": "A 6-digit verification code has been sent to your email."
    })


@require_POST
@ratelimit(scope="verify_login_otp", limit=10, window=60, key_field="email")
@handle_db_errors
def api_verify_login_otp(request):
    """
    Step 2 of Login: Validates the 6-digit Login OTP.
    Only upon successful OTP validation is the authenticated Django session established.
    """
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.session.get("pending_login_email", "")
    otp = data.get("otp", "").strip() or request.POST.get("otp", "").strip()

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and verification code are required."}, status=400)

    user = User.objects.filter(email=email).first()
    pending_uid = request.session.get("pending_login_user_id")

    if not user or not pending_uid or int(pending_uid) != int(user.id):
        return JsonResponse({"success": False, "error": "Invalid or expired login session. Please sign in again."}, status=401)

    success, err_msg = user.verify_otp(otp, purpose="login")
    if not success:
        user.save(update_fields=["email_otp_attempts"])
        log_audit(request, "AUTH_OTP_FAILED", "auth", resource_id=user.id, description=f"Invalid login OTP attempt for {user.email}.", user=user)
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])

    # OTP verified! Establish the authenticated Django session now
    request.session.flush()
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    request.session["pw_fp"] = compute_session_password_fingerprint(user.password_hash)
    log_audit(request, "AUTH_LOGIN_SUCCESS", "auth", resource_id=user.id, description=f"Authenticated session established for {user.email}.", user=user)

    return JsonResponse({
        "success": True,
        "message": "Authentication successful.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }
    })


@require_POST
@ratelimit(scope="resend_login_otp", limit=4, window=120, key_field="email")
@handle_db_errors
def api_resend_login_otp(request):
    """Resends single-use 6-digit Login OTP for pending login session."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.session.get("pending_login_email", "")

    if not email:
        return JsonResponse({"success": False, "error": "Email is required."}, status=400)

    user = User.objects.filter(email=email).first()
    pending_uid = request.session.get("pending_login_user_id")
    if not user or not pending_uid or int(pending_uid) != int(user.id):
        return JsonResponse({"success": False, "error": "Invalid or expired login session. Please sign in again."}, status=401)

    # Enforce 60-second cooldown
    now = timezone.now()
    sent_at = user.email_otp_sent_at
    if sent_at:
        if timezone.is_naive(sent_at):
            sent_at = timezone.make_aware(sent_at, dt_timezone.utc)
        elapsed = (now - sent_at).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed)
            return JsonResponse({
                "success": False,
                "error": f"Please wait {remaining} seconds before requesting a new verification code.",
                "cooldown": remaining
            }, status=429)

    otp = user.generate_otp(purpose="login")
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    try:
        sent = send_login_otp_email(user.email, otp, user.full_name)
        if not sent:
            logger.warning("[AUTH] Resent sign-in code delivery failed for user_id=%s", user.id)
            user.email_otp_hash = None
            user.email_otp_expires_at = None
            user.email_otp_sent_at = None
            user.email_otp_attempts = 0
            user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])
            return JsonResponse({"success": False, "error": "Could not deliver a sign-in code. Please try again later."}, status=503)
    except Exception:
        logger.warning("[AUTH] Resent sign-in code delivery failed for user_id=%s", user.id)
        return JsonResponse({"success": False, "error": "Could not deliver a sign-in code. Please try again later."}, status=503)

    return JsonResponse({"success": True, "message": "A new sign-in verification code has been sent."})


@require_POST
def api_demo_session(request):
    """Legacy demo-login route is intentionally disabled in every environment."""
    return JsonResponse({
        "success": False,
        "error": "Demo sessions are disabled. Sign in with a registered account."
    }, status=410)


@require_POST
@ratelimit(scope="signup", limit=6, window=60, key_field="email")
@handle_db_errors
def api_signup(request):
    """Creates user in pending/unverified state and sends 6-digit Signup OTP."""
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
        otp = new_user.generate_otp(purpose="signup")
        new_user.save()
        request.session["signup_email"] = email

        email_sent = False
        try:
            email_sent = send_verification_email(email, otp, full_name)
            if not email_sent:
                logger.warning("[AUTH] Verification email delivery failed for user_id=%s", new_user.id)
                new_user.email_otp_sent_at = None
                new_user.save(update_fields=["email_otp_sent_at"])
        except Exception:
            logger.warning("[AUTH] Verification email delivery failed for user_id=%s", new_user.id)
            new_user.email_otp_sent_at = None
            new_user.save(update_fields=["email_otp_sent_at"])

        log_audit(request, "AUTH_SIGNUP", "user", resource_id=new_user.id, description=f"New account registered ({email}).", user=new_user)
        return JsonResponse({
            "success": True,
            "email_sent": email_sent,
            "message": "Account created. A verification code has been sent to your email." if email_sent else "Account created, but the verification email could not be delivered. You can retry from the verification screen.",
            "email": email
        }, status=201)
    except Exception as e:
        logger.error(f"[AUTH] Signup failed: {e}")
        return JsonResponse({"success": False, "error": "An error occurred while creating your account."}, status=500)


@require_POST
@ratelimit(scope="verify_otp", limit=10, window=60, key_field="email")
@handle_db_errors
def api_verify_otp(request):
    """
    Validates 6-digit email verification OTP for newly registered accounts.
    Marks account as verified. Does NOT automatically log the user in; redirects to Login.
    If requested with purpose='login', delegates to login OTP validation.
    """
    data = _parse_body(request)
    purpose = data.get("purpose", "").strip().lower()
    if purpose == "login" or (not request.session.get("signup_email") and request.session.get("pending_login_email")):
        return api_verify_login_otp(request)

    email = data.get("email", "").strip().lower() or request.session.get("signup_email", "")
    otp = data.get("otp", "").strip() or request.POST.get("otp", "").strip()

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and verification code are required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Account not found."}, status=404)

    success, err_msg = user.verify_otp(otp, purpose="signup")
    if not success:
        user.save(update_fields=["email_otp_attempts"])
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    user.save(update_fields=["is_email_verified", "email_otp_hash", "email_otp_expires_at", "email_otp_attempts"])
    
    # Flush session. DO NOT log in automatically!
    request.session.flush()

    return JsonResponse({
        "success": True,
        "verified": True,
        "message": "Email verified successfully. Please sign in with your credentials.",
        "email": user.email
    })


@require_POST
@ratelimit(scope="resend_otp", limit=4, window=120, key_field="email")
@handle_db_errors
def api_resend_otp(request):
    """Resends email verification OTP for signup."""
    data = _parse_body(request)
    purpose = data.get("purpose", "").strip().lower()
    if purpose == "login" or (not request.session.get("signup_email") and request.session.get("pending_login_email")):
        return api_resend_login_otp(request)

    email = data.get("email", "").strip().lower() or request.session.get("signup_email", "")

    if not email:
        return JsonResponse({"success": False, "error": "Email is required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Account not found."}, status=404)

    if user.is_email_verified:
        return JsonResponse({"success": False, "error": "Email is already verified."}, status=400)

    # Enforce 60-second cooldown
    now = timezone.now()
    sent_at = user.email_otp_sent_at
    if sent_at:
        if timezone.is_naive(sent_at):
            sent_at = timezone.make_aware(sent_at, dt_timezone.utc)
        elapsed = (now - sent_at).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed)
            return JsonResponse({
                "success": False,
                "error": f"Please wait {remaining} seconds before requesting a new verification code.",
                "cooldown": remaining
            }, status=429)

    otp = user.generate_otp(purpose="signup")
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    try:
        sent = send_verification_email(user.email, otp, user.full_name)
        if not sent:
            logger.warning("[AUTH] Resent verification code delivery failed for user_id=%s", user.id)
            user.email_otp_sent_at = None
            user.save(update_fields=["email_otp_sent_at"])
            return JsonResponse({"success": False, "error": "Could not deliver a verification code. Please try again later."}, status=503)
    except Exception:
        logger.warning("[AUTH] Resent verification code delivery failed for user_id=%s", user.id)
        user.email_otp_sent_at = None
        user.save(update_fields=["email_otp_sent_at"])
        return JsonResponse({"success": False, "error": "Could not deliver a verification code. Please try again later."}, status=503)

    return JsonResponse({"success": True, "message": "A new verification code has been sent."})


@require_POST
@ratelimit(scope="forgot_password", limit=5, window=120, key_field="email")
@handle_db_errors
def api_forgot_password(request):
    """Initiates password reset flow."""
    data = _parse_body(request)
    email = data.get("email", "").strip().lower() or request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"success": False, "error": "Email address is required."}, status=400)

    user = User.objects.filter(email=email).first()
    if user:
        now = timezone.now()
        sent_at = user.password_reset_otp_sent_at
        if sent_at:
            if timezone.is_naive(sent_at):
                sent_at = timezone.make_aware(sent_at, dt_timezone.utc)
            elapsed = (now - sent_at).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                return JsonResponse({
                    "success": False,
                    "error": f"Please wait {remaining} seconds before requesting a new recovery code.",
                    "cooldown": remaining
                }, status=429)

        otp = user.generate_reset_otp()
        user.save(update_fields=["password_reset_otp_hash", "password_reset_otp_expires_at", "password_reset_otp_sent_at", "password_reset_otp_attempts"])
        try:
            sent = send_password_reset_email(user.email, otp, user.full_name)
            if not sent:
                logger.warning("[AUTH] Password reset email delivery failed for user_id=%s", user.id)
                user.password_reset_otp_sent_at = None
                user.save(update_fields=["password_reset_otp_sent_at"])
        except Exception:
            logger.warning("[AUTH] Password reset email delivery failed for user_id=%s", user.id)
            user.password_reset_otp_sent_at = None
            user.save(update_fields=["password_reset_otp_sent_at"])

    # Constant message prevents account enumeration
    return JsonResponse({"success": True, "message": "If an account exists with this email, a reset code will be sent when delivery is available."})



@require_POST
@ratelimit(scope="verify_reset_otp", limit=10, window=60, key_field="email")
@handle_db_errors
def api_verify_reset_otp(request):
    """
    Verifies password reset OTP without altering password yet.
    Allows frontend to confirm code validity before user sets new password.
    """
    data = _parse_body(request)
    email = (data.get("email", "") or request.POST.get("email", "")).strip().lower()
    otp = (data.get("otp", "") or data.get("reset_code", "") or data.get("code", "") or request.POST.get("otp", "") or request.POST.get("reset_code", "")).strip()

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and reset code are required."}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({"success": False, "error": "Invalid reset code or email."}, status=400)

    success, err_msg = user.verify_reset_otp(otp)
    if not success:
        user.save(update_fields=["password_reset_otp_attempts"])
        return JsonResponse({"success": False, "error": err_msg}, status=400)

    return JsonResponse({"success": True, "message": "Verification code confirmed."})


@require_POST
@ratelimit(scope="reset_password", limit=6, window=60, key_field="email")
@handle_db_errors
def api_reset_password(request):
    """Verifies OTP and resets password using PBKDF2."""
    data = _parse_body(request)
    email = (data.get("email", "") or request.POST.get("email", "")).strip().lower()
    otp = (data.get("otp", "") or data.get("reset_code", "") or data.get("code", "") or request.POST.get("otp", "") or request.POST.get("reset_code", "")).strip()
    new_password = data.get("new_password", "") or data.get("newPassword", "") or request.POST.get("new_password", "") or request.POST.get("password", "")
    confirm_password = data.get("confirm_password", "") or data.get("confirmPassword", "") or request.POST.get("confirm_password", "")

    if not email or not otp:
        return JsonResponse({"success": False, "error": "Email and reset code are required."}, status=400)

    if not new_password or not confirm_password:
        return JsonResponse({"success": False, "error": "New password and confirmation are required."}, status=400)

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
    log_audit(request, "AUTH_PASSWORD_RESET", "user", resource_id=user.id, description=f"Password reset completed for {user.email}.", user=user)

    return JsonResponse({"success": True, "message": "Password successfully reset. You may now log in."})


@require_POST
def api_logout(request):
    """Flushes session."""
    log_audit(request, "AUTH_LOGOUT", "auth", description="User signed out.")
    request.session.flush()
    return JsonResponse({"success": True, "message": "Logged out successfully."})


# =========================================================================
# DASHBOARD APIS
# =========================================================================

_DASHBOARD_STATS_CACHE = {}

@never_cache
@login_required
@handle_db_errors
def api_dashboard_stats(request):
    """Returns SOC dashboard real metrics and recent activities."""
    user_id = request.user.id
    is_privileged = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)
    cache_key = (user_id, is_privileged)
    now = time.time()
    cached = _DASHBOARD_STATS_CACHE.get(cache_key)
    if cached and (now - cached['time']) < 2.0:
        return JsonResponse(cached['data'])

    import datetime
    from django.utils import timezone
    try:
        import psutil
        cpu_usage = int(round(psutil.cpu_percent(interval=0.05)))
        mem_usage = int(round(psutil.virtual_memory().percent))
        disk_usage = int(round(psutil.disk_usage('/').percent))
    except Exception:
        cpu_usage, mem_usage, disk_usage = 0, 0, 0

    twenty_four_hours_ago = timezone.now() - datetime.timedelta(hours=24)
    one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
    events_24h = Alert.objects.filter(user_id=user_id, detected_at__gte=twenty_four_hours_ago).count()
    alerts_last_1h = Alert.objects.filter(user_id=user_id, detected_at__gte=one_hour_ago).count()

    from apps.surveillance.health.health_service import get_live_camera_status, get_user_cameras_health
    user_cameras = list(get_accessible_cameras_qs(request.user))
    total_cameras = len(user_cameras)
    live_statuses = {c.id: get_live_camera_status(c.id) for c in user_cameras}
    online_cameras = sum(1 for c in user_cameras if live_statuses[c.id]["status"] == 'online')
    active_cameras = sum(1 for c in user_cameras if c.is_active)

    alert_counts = Alert.objects.filter(user_id=user_id).aggregate(
        new_alerts=Count('id', filter=Q(status__in=['new', 'unresolved', 'active', 'OPEN'])),
        high_critical=Count('id', filter=Q(severity__in=['high', 'critical', 'HIGH', 'CRITICAL']))
    )
    new_alerts_count = alert_counts['new_alerts'] or 0
    high_critical_count = alert_counts['high_critical'] or 0
    total_recordings = Recording.objects.filter(user_id=user_id).count()
    total_evidence = Evidence.objects.filter(user_id=user_id).count()
    total_cases = IncidentCase.objects.filter(user_id=user_id).count()
    open_cases = IncidentCase.objects.filter(user_id=user_id).exclude(status__iexact='closed').exclude(status__iexact='resolved').count()
    active_policies = IncidentPolicy.objects.filter(user_id=user_id, enabled=True).count()
    active_playbooks = IncidentPlaybook.objects.filter(user_id=user_id, enabled=True).count()
    unread_notifications = Notification.objects.filter(user_id=user_id, is_read=False).count()
    recent_alerts_qs = Alert.objects.filter(user_id=user_id).select_related('camera').only(
        'id', 'title', 'event_type', 'severity', 'status', 'camera_id', 'camera__name', 'detected_at'
    ).order_by('-detected_at', '-id')[:5]
    recent_recordings_qs = Recording.objects.filter(user_id=user_id).select_related('camera').only(
        'id', 'filename', 'camera_id', 'camera__name', 'duration_seconds', 'file_size', 'started_at', 'status'
    ).order_by('-started_at', '-id')[:4]

    recent_alerts = []
    for a in recent_alerts_qs:
        recent_alerts.append({
            "id": a.id,
            "title": a.title,
            "alert_type": a.event_type,
            "severity": a.severity,
            "status": a.status,
            "camera_name": a.camera.name if a.camera else "Channel 01",
            "camera_id": a.camera_id,
            "detected_at": a.detected_at.isoformat() if a.detected_at else "",
        })

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

    cam_ids = [c.id for c in user_cameras]
    active_recording_cam_ids = set(Recording.objects.filter(camera_id__in=cam_ids, status='recording').values_list('camera_id', flat=True))
    cameras_data = []
    for c in user_cameras:
        linfo = live_statuses.get(c.id, {"status": "offline", "live": False, "signal_state": "offline"})
        cameras_data.append({
            "id": c.id,
            "name": c.name,
            "location": c.location or "Default Zone",
            "source_type": c.source_type,
            "status": linfo["status"],
            "live": linfo["live"],
            "signal_state": linfo["signal_state"],
            "is_active": c.is_active,
            "is_recording": c.id in active_recording_cam_ids,
        })

    engine_reachable = is_engine_reachable(timeout=0.5)
    db_backend = getattr(connection, 'vendor', 'unknown')

    cam_healths = get_user_cameras_health(cam_ids) if cam_ids else []
    active_fps_vals = [float(h.get("fps") or 0.0) for h in cam_healths if float(h.get("fps") or 0.0) > 0.0]
    live_avg_fps = round(sum(active_fps_vals) / len(active_fps_vals), 1) if active_fps_vals else 0.0

    payload = {
        "total_cameras": total_cameras,
        "online_cameras": online_cameras,
        "offline_cameras": max(0, total_cameras - online_cameras),
        "active_cameras": active_cameras,
        "events_24h": events_24h,
        "new_alerts_count": new_alerts_count,
        "high_critical_count": high_critical_count,
        "total_recordings": total_recordings,
        "total_evidence": total_evidence,
        "total_cases": total_cases,
        "open_cases": open_cases,
        "alerts_last_1h": alerts_last_1h,
        "cameras_recording": len(active_recording_cam_ids),
        "active_policies": active_policies,
        "active_playbooks": active_playbooks,
        "unread_notifications": unread_notifications,
        "recent_alerts": recent_alerts,
        "recent_recordings": recent_recordings,
        "cameras": cameras_data,
        "system_health": {
            "cpu": cpu_usage,
            "memory": mem_usage,
            "storage": disk_usage,
            "fps": live_avg_fps,
        },
        "engine_reachable": engine_reachable,
        "database_backend": db_backend,
        "database_status": "connected",
    }
    _DASHBOARD_STATS_CACHE[cache_key] = {'time': now, 'data': payload}
    return JsonResponse(payload)


# =========================================================================
# CAMERAS APIS
# =========================================================================

def _inject_url_credentials(raw_source: str, username: str = "", password: str = "") -> str:
    """Safely injects URL-encoded username/password into RTSP or HTTP(S) stream URLs if provided."""
    user = str(username or "").strip()
    pwd = str(password or "").strip()
    if not user and not pwd:
        return raw_source
    from urllib.parse import urlparse, urlunparse, quote
    try:
        parsed = urlparse(raw_source)
        if parsed.scheme.lower() not in ("rtsp", "rtsps", "http", "https") or not parsed.hostname:
            return raw_source
        host_part = parsed.hostname
        if parsed.port:
            host_part = f"{host_part}:{parsed.port}"
        auth_part = quote(user, safe="")
        if pwd:
            auth_part = f"{auth_part}:{quote(pwd, safe='')}"
        new_netloc = f"{auth_part}@{host_part}"
        return urlunparse((parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return raw_source


def _mask_camera_source(raw_source: str) -> str:
    """Masks embedded credentials in camera source URLs before returning in JSON responses."""
    from apps.surveillance.camera.sources import mask_url_credentials
    return mask_url_credentials(str(raw_source or ""))


def _has_camera_credentials(raw_source: str) -> bool:
    """Checks whether the stored camera source contains embedded authentication credentials."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(raw_source or ""))
        return bool(parsed.username or parsed.password)
    except Exception:
        return "@" in str(raw_source or "")


def _validate_and_normalize_camera_payload(data: dict, existing_source: str = None):
    """
    Validates camera registration/update payload and blocks SSRF/unsafe targets.
    Supports optional username and password fields for authenticated RTSP/HTTP cameras.
    Returns (cleaned_dict, error_message).
    """
    from apps.surveillance.camera.sources import resolve_camera_capture_source, normalize_camera_source

    name = str(data.get("name") or "").strip()[:100]
    if not name:
        return None, "Camera name is required."

    source_type = str(data.get("source_type") or "webcam").strip().lower()
    if source_type == "stream":
        source_type = "http"
    if source_type not in ("browser", "webcam", "usb", "rtsp", "phone", "ipcamera", "video", "http", "https", "ip", "mjpeg"):
        return None, f"Unsupported camera source type: {source_type}"

    raw_source = str(data.get("source") if data.get("source") is not None else "").strip()
    if not raw_source and source_type in ("browser", "webcam", "usb", "phone"):
        raw_source = "0"
    if not raw_source:
        return None, "Camera source URL or device index is required."

    # Preserve stored credentials if updating a camera whose masked URL ('***:***@') was submitted unchanged
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "").strip()
    if existing_source and "***" in raw_source and not username and not password:
        if _mask_camera_source(existing_source) == raw_source:
            raw_source = existing_source

    if username or password:
        raw_source = _inject_url_credentials(raw_source, username, password)

    try:
        resolve_camera_capture_source(source_type, raw_source)
    except ValueError as ve:
        err_text = str(ve)
        if err_text.startswith("Security Error:"):
            return None, err_text
        if "Unsupported" in err_text or "must be" in err_text or "empty" in err_text.lower() or "port" in err_text.lower():
            return None, "Invalid or unsupported camera source configuration."
        return None, "Invalid camera stream source."

    normalized_source = str(normalize_camera_source(source_type, raw_source))

    location = str(data.get("location") or "").strip()[:120] or None
    return {
        "name": name,
        "source_type": source_type,
        "source": normalized_source,
        "location": location,
    }, None


@never_cache
@login_required
@handle_db_errors
def api_cameras_list(request):
    """
    GET: Returns cameras list for authenticated user with operational status.
    POST: Registers a new camera in SQLite inventory.
    """
    if request.method == "POST":
        if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        data = _parse_body(request)
        cleaned, err = _validate_and_normalize_camera_payload(data)
        if err:
            return JsonResponse({"success": False, "error": err}, status=400)

        existing_by_name = Camera.objects.filter(
            user_id=request.user.id,
            name__iexact=cleaned["name"],
        ).first()
        if existing_by_name:
            return JsonResponse({
                "success": False,
                "error": f"A camera named '{existing_by_name.name}' already exists.",
                "duplicate_camera_id": existing_by_name.id,
            }, status=409)

        is_explicit_source = (
            cleaned["source"].startswith(("rtsp://", "http://", "https://"))
            or (cleaned["source_type"] == "browser" and cleaned["source"] not in ("browser", "webcam", "0", ""))
        )
        if is_explicit_source:
            existing_by_source = Camera.objects.filter(
                user_id=request.user.id,
                source_type=cleaned["source_type"],
                source=cleaned["source"],
            ).first()
            if existing_by_source:
                return JsonResponse({
                    "success": False,
                    "error": f"This camera source is already registered as '{existing_by_source.name}'.",
                    "duplicate_camera_id": existing_by_source.id,
                }, status=409)

        now = timezone.now()
        initial_status = "offline"
        if cleaned["source_type"] in ("webcam", "usb"):
            from apps.surveillance.camera.registry import get_camera_registry
            from apps.surveillance.camera.sources import get_physical_source_key
            phys_key = get_physical_source_key(cleaned["source_type"], cleaned["source"])
            if get_camera_registry().get_physical_worker(phys_key) is not None:
                initial_status = "online"

        camera = Camera.objects.create(
            user_id=request.user.id,
            name=cleaned["name"],
            source_type=cleaned["source_type"],
            source=cleaned["source"],
            location=cleaned["location"],
            status=initial_status,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        from apps.cameras.surveillance_config import (
            get_camera_surveillance_config,
            save_camera_surveillance_config,
        )
        cfg_updates = {}
        for k in (
            "restricted_entry_enabled",
            "purpose",
            "entry_direction",
            "schedule",
            "alert_severity",
            "notification_recipients",
            "require_alert",
            "suppress_duplicates",
            "cooldown_seconds",
            "debounce_frames",
            "video_quality",
        ):
            if k in data:
                cfg_updates[k] = data[k]
        cam_cfg = save_camera_surveillance_config(camera.id, cfg_updates) if cfg_updates else get_camera_surveillance_config(camera.id)
        _invalidate_camera_zones(camera.id)

        _DASHBOARD_STATS_CACHE.clear()
        log_audit(
            request,
            action="CAMERA_CREATED",
            resource_type="camera",
            resource_id=camera.id,
            description=f"Registered camera '{camera.name}' ({camera.source_type}, purpose={cam_cfg.get('purpose', 'general')}).",
        )
        return JsonResponse({
            "success": True,
            "message": f"Camera '{camera.name}' registered successfully.",
            "camera": {
                "id": camera.id,
                "name": camera.name,
                "source_type": camera.source_type,
                "source": _mask_camera_source(camera.source),
                "has_credentials": _has_camera_credentials(camera.source),
                "location": camera.location or "Default Zone",
                "status": camera.status,
                "is_active": camera.is_active,
                "is_recording": False,
                "purpose": cam_cfg.get("purpose", "general"),
                "restricted_entry_enabled": bool(cam_cfg.get("restricted_entry_enabled", False)),
                "entry_direction": cam_cfg.get("entry_direction", "enter"),
                "schedule": cam_cfg.get("schedule"),
                "alert_severity": cam_cfg.get("alert_severity", "high"),
                "notification_recipients": cam_cfg.get("notification_recipients", []),
                "require_alert": bool(cam_cfg.get("require_alert", True)),
                "suppress_duplicates": bool(cam_cfg.get("suppress_duplicates", True)),
                "cooldown_seconds": cam_cfg.get("cooldown_seconds", 30.0),
                "video_quality": cam_cfg.get("video_quality", "high"),
                "zone_count": 0,
                "created_at": camera.created_at.isoformat() if camera.created_at else "",
            },
        }, status=201)

    cameras_qs = get_accessible_cameras_qs(request.user)
    status_filter = request.GET.get('status', 'all').strip().lower()

    cams_list = list(cameras_qs)
    cam_ids = [c.id for c in cams_list]
    active_recording_cam_ids = set(Recording.objects.filter(camera_id__in=cam_ids, status='recording').values_list('camera_id', flat=True))

    from apps.core.models import RestrictedZone
    from apps.cameras.surveillance_config import get_camera_surveillance_config
    from apps.surveillance.health.health_service import get_live_camera_status
    zone_counts = {}
    for zid_cid, enabled_flag in RestrictedZone.objects.filter(camera_id__in=cam_ids, enabled=True).values_list('camera_id', 'enabled'):
        if enabled_flag:
            zone_counts[zid_cid] = zone_counts.get(zid_cid, 0) + 1

    cameras = []
    for c in cams_list:
        linfo = get_live_camera_status(c.id)
        if status_filter in ('online', 'offline') and linfo["status"] != status_filter:
            continue
        z_cnt = zone_counts.get(c.id, 0)
        cam_cfg = get_camera_surveillance_config(c.id, has_enabled_zones=(z_cnt > 0))
        cameras.append({
            "id": c.id,
            "name": c.name,
            "source_type": c.source_type,
            "source": _mask_camera_source(c.source),
            "has_credentials": _has_camera_credentials(c.source),
            "location": c.location or "Default Zone",
            "status": linfo["status"],
            "live": linfo["live"],
            "signal_state": linfo["signal_state"],
            "frame_age_sec": linfo.get("frame_age_sec"),
            "is_active": c.is_active,
            "is_recording": c.id in active_recording_cam_ids,
            "purpose": cam_cfg.get("purpose", "general"),
            "restricted_entry_enabled": bool(cam_cfg.get("restricted_entry_enabled", z_cnt > 0)),
            "entry_direction": cam_cfg.get("entry_direction", "enter"),
            "schedule": cam_cfg.get("schedule"),
            "alert_severity": cam_cfg.get("alert_severity", "high"),
            "notification_recipients": cam_cfg.get("notification_recipients", []),
            "require_alert": bool(cam_cfg.get("require_alert", True)),
            "suppress_duplicates": bool(cam_cfg.get("suppress_duplicates", True)),
            "cooldown_seconds": cam_cfg.get("cooldown_seconds", 30.0),
            "video_quality": cam_cfg.get("video_quality", "high"),
            "zone_count": z_cnt,
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
@handle_db_errors
def api_camera_detail(request, camera_id):
    """
    GET: Returns single camera metadata and runtime state.
    PUT / PATCH: Updates camera configuration in SQLite.
    DELETE: Removes camera from active inventory (preserving historical forensic records if any exist).
    """
    camera = get_user_camera_or_404(request.user, camera_id)
    is_privileged = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)

    if request.method in ("PUT", "PATCH"):
        try:
            camera = get_user_camera_or_404(request.user, camera_id, require_write=True)
        except PermissionDenied:
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        data = _parse_body(request)
        merged = {
            "name": data.get("name", camera.name),
            "source_type": data.get("source_type", camera.source_type),
            "source": data.get("source", camera.source),
            "location": data.get("location", camera.location),
            "username": data.get("username", ""),
            "password": data.get("password", ""),
        }
        cleaned, err = _validate_and_normalize_camera_payload(merged, existing_source=camera.source)
        if err:
            return JsonResponse({"success": False, "error": err}, status=400)

        source_changed = (camera.source_type != cleaned["source_type"]) or (str(camera.source) != str(cleaned["source"]))
        camera.name = cleaned["name"]
        camera.source_type = cleaned["source_type"]
        camera.source = cleaned["source"]
        camera.location = cleaned["location"]
        camera.updated_at = timezone.now()
        camera.save(update_fields=["name", "source_type", "source", "location", "updated_at"])

        if source_changed:
            if is_camera_recording(camera.id, camera.user_id):
                try:
                    stop_camera_recording(camera.id, camera.user_id)
                except Exception:
                    pass
            try:
                from apps.surveillance.camera.registry import get_camera_registry
                from apps.surveillance.ai.registry import get_inference_registry
                from apps.surveillance.ai.reid import registry as reid_registry
                from apps.surveillance.streaming.stream_service import clear_camera_telemetry
                get_camera_registry().remove_camera(camera.id)
                get_inference_registry().remove_worker(camera.id)
                reid_registry.clear_camera(camera.id)
                clear_camera_telemetry(camera.id)
            except Exception:
                pass

        from apps.core.models import RestrictedZone
        from apps.cameras.surveillance_config import (
            get_camera_surveillance_config,
            save_camera_surveillance_config,
        )
        cfg_updates = {}
        for k in (
            "restricted_entry_enabled",
            "purpose",
            "entry_direction",
            "schedule",
            "alert_severity",
            "notification_recipients",
            "require_alert",
            "suppress_duplicates",
            "cooldown_seconds",
            "debounce_frames",
            "video_quality",
        ):
            if k in data:
                cfg_updates[k] = data[k]
        z_cnt = RestrictedZone.objects.filter(camera_id=camera.id, enabled=True).count()
        prev_cfg = get_camera_surveillance_config(camera.id, has_enabled_zones=(z_cnt > 0))
        cam_cfg = (
            save_camera_surveillance_config(camera.id, cfg_updates)
            if cfg_updates
            else prev_cfg
        )
        if not source_changed and cfg_updates.get("video_quality") and cfg_updates["video_quality"] != prev_cfg.get("video_quality"):
            try:
                from apps.surveillance.camera.registry import get_camera_registry
                get_camera_registry().remove_camera(camera.id)
            except Exception:
                pass
        _invalidate_camera_zones(camera.id)

        _DASHBOARD_STATS_CACHE.clear()
        log_audit(
            request,
            action="CAMERA_UPDATED",
            resource_type="camera",
            resource_id=camera.id,
            description=f"Updated camera '{camera.name}' ({camera.source_type}, purpose={cam_cfg.get('purpose', 'general')}).",
        )
        return JsonResponse({
            "success": True,
            "message": f"Camera '{camera.name}' updated successfully.",
            "camera": {
                "id": camera.id,
                "name": camera.name,
                "source_type": camera.source_type,
                "source": _mask_camera_source(camera.source),
                "has_credentials": _has_camera_credentials(camera.source),
                "location": camera.location or "Default Zone",
                "status": camera.status,
                "is_active": camera.is_active,
                "purpose": cam_cfg.get("purpose", "general"),
                "restricted_entry_enabled": bool(cam_cfg.get("restricted_entry_enabled", z_cnt > 0)),
                "entry_direction": cam_cfg.get("entry_direction", "enter"),
                "schedule": cam_cfg.get("schedule"),
                "alert_severity": cam_cfg.get("alert_severity", "high"),
                "notification_recipients": cam_cfg.get("notification_recipients", []),
                "require_alert": bool(cam_cfg.get("require_alert", True)),
                "suppress_duplicates": bool(cam_cfg.get("suppress_duplicates", True)),
                "cooldown_seconds": cam_cfg.get("cooldown_seconds", 30.0),
                "video_quality": cam_cfg.get("video_quality", "high"),
                "zone_count": z_cnt,
                "created_at": camera.created_at.isoformat() if camera.created_at else "",
            },
        })

    if request.method == "DELETE":
        try:
            camera = get_user_camera_or_404(request.user, camera_id, require_write=True)
        except PermissionDenied:
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)

        cam_name = camera.name
        if is_camera_recording(camera.id, camera.user_id):
            stop_camera_recording(camera.id, camera.user_id)
        try:
            from apps.surveillance.camera.registry import get_camera_registry
            from apps.surveillance.ai.registry import get_inference_registry
            from apps.surveillance.ai.reid import registry as reid_registry
            from apps.surveillance.streaming.stream_service import clear_camera_telemetry
            get_camera_registry().remove_camera(camera.id)
            get_inference_registry().remove_worker(camera.id)
            reid_registry.clear_camera(camera.id)
            clear_camera_telemetry(camera.id)
        except Exception:
            pass
        try:
            from apps.cameras.surveillance_config import delete_camera_surveillance_config
            delete_camera_surveillance_config(camera.id)
        except Exception:
            pass

        has_forensics = (
            Alert.objects.filter(camera_id=camera.id).exists()
            or Recording.objects.filter(camera_id=camera.id).exists()
            or Evidence.objects.filter(camera_id=camera.id).exists()
        )
        if has_forensics:
            # Preserve historical alerts/recordings/evidence while removing camera from active inventory
            camera.is_active = False
            camera.status = "offline"
            camera.updated_at = timezone.now()
            camera.save(update_fields=["is_active", "status", "updated_at"])
        else:
            from apps.core.models import RestrictedZone, DetectionProfile
            RestrictedZone.objects.filter(camera_id=camera.id).delete()
            DetectionProfile.objects.filter(camera_id=camera.id).delete()
            camera.delete()

        _DASHBOARD_STATS_CACHE.clear()
        log_audit(
            request,
            action="CAMERA_DELETED",
            resource_type="camera",
            resource_id=camera_id,
            description=f"Removed camera '{cam_name}' from inventory.",
        )
        return JsonResponse({
            "success": True,
            "message": f"Camera '{cam_name}' removed from inventory.",
        })
    engine_reachable = is_engine_reachable(timeout=0.5)
    is_recording = is_camera_recording(camera.id, camera.user_id)
    recordings_count = camera.recordings.filter(user_id=camera.user_id).count()
    alerts_count = camera.alerts.filter(user_id=camera.user_id).count()

    recent_recordings = []
    for r in camera.recordings.filter(user_id=camera.user_id).order_by('-started_at', '-id')[:5]:
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
    for a in camera.alerts.filter(user_id=camera.user_id).order_by('-detected_at', '-id')[:5]:
        recent_alerts.append({
            "id": a.id,
            "title": a.title or a.event_type or "Security Alert",
            "severity": a.severity,
            "status": a.status,
            "detected_at": a.detected_at.isoformat() if a.detected_at else "",
        })

    from apps.surveillance.health.health_service import get_live_camera_status
    detail_live = get_live_camera_status(camera.id)
    return JsonResponse({
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "source_type": camera.source_type,
            "source": _mask_camera_source(camera.source),
            "has_credentials": _has_camera_credentials(camera.source),
            "location": camera.location,
            "status": detail_live["status"],
            "live": detail_live["live"],
            "signal_state": detail_live["signal_state"],
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
# RESTRICTED ANOMALY ZONES APIS
# =========================================================================

def _invalidate_camera_zones(camera_id):
    try:
        from apps.surveillance.ai.registry import get_inference_registry
        reg = get_inference_registry()
        if reg:
            iw = reg.get_active_worker(camera_id)
            if iw:
                iw.invalidate_zones()
    except Exception:
        pass


@never_cache
@login_required
@handle_db_errors
def api_camera_zones(request, camera_id):
    """
    List or create/update restricted anomaly zones for a camera.
    GET: returns array of configured zones for camera (including normalized polygon points).
    POST/PUT: creates or updates a rectangle or polygon zone with full geometry validation.
    """
    from apps.core.models import RestrictedZone
    from apps.cameras.surveillance_config import (
        get_zone_metadata,
        rect_pixel_to_normalized_points,
        save_zone_metadata,
        validate_normalized_polygon,
    )

    if request.method in ("POST", "PUT"):
        try:
            camera = get_user_camera_or_404(request.user, camera_id, require_write=True)
        except PermissionDenied:
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        data = _parse_body(request)
        name = str(data.get("name") or "Restricted Zone").strip()[:100]
        raw_zone_id = data.get("zone_id") or data.get("id")
        shape = str(data.get("shape") or ("polygon" if data.get("points") else "rectangle")).strip().lower()
        if shape not in ("polygon", "rectangle"):
            shape = "rectangle"

        raw_points = data.get("points")
        norm_points = None
        if isinstance(raw_points, (list, tuple)) and len(raw_points) > 0:
            # If caller sent integer pixel polygon coordinates along with ref_width/ref_height, normalize to 0..1 first
            ref_w = float(data.get("ref_width") or 1280.0)
            ref_h = float(data.get("ref_height") or 720.0)
            pre_norm = []
            needs_scale = False
            for item in raw_points:
                try:
                    rx = float(item.get("x") if isinstance(item, dict) else item[0])
                    ry = float(item.get("y") if isinstance(item, dict) else item[1])
                except Exception:
                    return JsonResponse({"success": False, "error": "Invalid polygon point format."}, status=400)
                if rx > 1.0 or ry > 1.0:
                    needs_scale = True
                pre_norm.append({"x": rx, "y": ry})
            if needs_scale and ref_w > 0 and ref_h > 0:
                pre_norm = [{"x": p["x"] / ref_w, "y": p["y"] / ref_h} for p in pre_norm]

            valid_poly, poly_err, norm_points = validate_normalized_polygon(pre_norm)
            if not valid_poly:
                return JsonResponse({"success": False, "error": poly_err}, status=400)
            xs = [p["x"] for p in norm_points]
            ys = [p["y"] for p in norm_points]
            nx1 = int(round(min(xs) * 1280))
            ny1 = int(round(min(ys) * 720))
            nx2 = int(round(max(xs) * 1280))
            ny2 = int(round(max(ys) * 720))
        else:
            try:
                fx1 = float(data.get("x1", 300))
                fy1 = float(data.get("y1", 100))
                fx2 = float(data.get("x2", 800))
                fy2 = float(data.get("y2", 600))
            except (ValueError, TypeError):
                return JsonResponse({"success": False, "error": "Invalid zone coordinates"}, status=400)

            if min(fx1, fy1, fx2, fy2) >= 0.0 and max(fx1, fy1, fx2, fy2) <= 1.0 and (max(fx2, fy2) > 0.0):
                x1, y1, x2, y2 = int(round(fx1 * 1280)), int(round(fy1 * 720)), int(round(fx2 * 1280)), int(round(fy2 * 720))
            else:
                x1, y1, x2, y2 = int(round(fx1)), int(round(fy1)), int(round(fx2)), int(round(fy2))

            nx1, ny1, nx2, ny2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            if (nx2 - nx1) < 12 or (ny2 - ny1) < 12:
                return JsonResponse({"success": False, "error": "Restricted zone area is too small."}, status=400)
            norm_points = rect_pixel_to_normalized_points(nx1, ny1, nx2, ny2)

        enabled = bool(data.get("enabled", True))
        now = timezone.now()

        existing = None
        if raw_zone_id:
            existing = RestrictedZone.objects.filter(id=int(raw_zone_id), camera_id=camera.id).first()
            if existing is None:
                return JsonResponse({"success": False, "error": "Zone not found."}, status=404)
        else:
            existing = (
                RestrictedZone.objects.filter(camera_id=camera.id, x1=nx1, y1=ny1, x2=nx2, y2=ny2).order_by("-id").first()
                or RestrictedZone.objects.filter(camera_id=camera.id, name__iexact=name).order_by("-id").first()
            )
        if existing is not None:
            existing.name = name
            existing.x1 = nx1
            existing.y1 = ny1
            existing.x2 = nx2
            existing.y2 = ny2
            existing.enabled = enabled
            existing.updated_at = now
            existing.save(update_fields=["name", "x1", "y1", "x2", "y2", "enabled", "updated_at"])
            zone = existing
        else:
            zone = RestrictedZone.objects.create(
                user_id=request.user.id,
                camera_id=camera.id,
                name=name,
                x1=nx1,
                y1=ny1,
                x2=nx2,
                y2=ny2,
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )

        zmeta = save_zone_metadata(zone.id, camera.id, {
            "shape": shape,
            "points": norm_points,
            "entry_direction": data.get("entry_direction"),
            "color": data.get("color", "#ef4444"),
            "cooldown_seconds": data.get("cooldown_seconds"),
        })
        _invalidate_camera_zones(camera.id)
        log_audit(
            request,
            action="ZONE_SAVED",
            resource_type="restricted_zone",
            resource_id=zone.id,
            description=f"Saved security zone '{zone.name}' ({shape}, {len(norm_points or [])} pts) on camera #{camera.id}.",
        )
        return JsonResponse({
            "success": True,
            "message": "Security zone saved and activated.",
            "zone": {
                "id": zone.id,
                "name": zone.name,
                "x1": zone.x1,
                "y1": zone.y1,
                "x2": zone.x2,
                "y2": zone.y2,
                "shape": zmeta.get("shape", shape),
                "points": zmeta.get("points", norm_points),
                "entry_direction": zmeta.get("entry_direction", "enter"),
                "color": zmeta.get("color", "#ef4444"),
                "enabled": zone.enabled,
            }
        })

    camera = get_user_camera_or_404(request.user, camera_id)
    raw_zones = list(RestrictedZone.objects.filter(camera_id=camera.id).order_by("-id"))
    seen_coords = set()
    unique_zones = []
    for z in raw_zones:
        zmeta = get_zone_metadata(z.id)
        pts = zmeta.get("points")
        pts_sig = tuple((round(float(p["x"]), 4), round(float(p["y"]), 4)) for p in pts) if isinstance(pts, list) else None
        ckey = (pts_sig,) if pts_sig else (int(z.x1), int(z.y1), int(z.x2), int(z.y2))
        if ckey in seen_coords:
            continue
        seen_coords.add(ckey)
        unique_zones.append((z, zmeta))
    unique_zones.reverse()

    return JsonResponse({
        "success": True,
        "camera_id": camera.id,
        "zones": [
            {
                "id": z.id,
                "name": z.name,
                "x1": z.x1,
                "y1": z.y1,
                "x2": z.x2,
                "y2": z.y2,
                "shape": zmeta.get("shape", "rectangle"),
                "points": zmeta.get("points") or rect_pixel_to_normalized_points(z.x1, z.y1, z.x2, z.y2),
                "entry_direction": zmeta.get("entry_direction", "enter"),
                "color": zmeta.get("color", "#ef4444"),
                "cooldown_seconds": zmeta.get("cooldown_seconds"),
                "enabled": z.enabled,
                "created_at": z.created_at.isoformat() if z.created_at else "",
            }
            for z, zmeta in unique_zones
        ]
    })


@require_http_methods(["POST", "DELETE"])
@never_cache
@login_required
@handle_db_errors
def api_camera_zone_delete(request, camera_id, zone_id):
    """Deletes a restricted anomaly zone."""
    from apps.core.models import RestrictedZone
    from apps.cameras.surveillance_config import delete_zone_metadata
    try:
        camera = get_user_camera_or_404(request.user, camera_id, require_write=True)
    except PermissionDenied:
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    zone = get_object_or_404(RestrictedZone, id=zone_id, camera_id=camera.id)
    zname = zone.name
    zone.delete()
    delete_zone_metadata(zone_id)
    _invalidate_camera_zones(camera.id)
    log_audit(
        request,
        action="ZONE_DELETED",
        resource_type="restricted_zone",
        resource_id=zone_id,
        description=f"Deleted security zone '{zname}' on camera #{camera.id}.",
    )
    return JsonResponse({"success": True, "message": "Security zone deleted."})


@require_POST
@never_cache
@login_required
@handle_db_errors
def api_camera_zone_toggle(request, camera_id, zone_id):
    """Toggles active state of a restricted anomaly zone."""
    from apps.core.models import RestrictedZone
    try:
        camera = get_user_camera_or_404(request.user, camera_id, require_write=True)
    except PermissionDenied:
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    zone = get_object_or_404(RestrictedZone, id=zone_id, camera_id=camera.id)
    zone.enabled = not zone.enabled
    zone.updated_at = timezone.now()
    zone.save(update_fields=["enabled", "updated_at"])
    _invalidate_camera_zones(camera.id)
    log_audit(
        request,
        action="ZONE_TOGGLED",
        resource_type="restricted_zone",
        resource_id=zone.id,
        description=f"{'Activated' if zone.enabled else 'Deactivated'} security zone '{zone.name}' on camera #{camera.id}.",
    )
    return JsonResponse({
        "success": True,
        "enabled": zone.enabled,
        "message": f"Zone '{zone.name}' {'activated' if zone.enabled else 'deactivated'}."
    })


@never_cache
@login_required
@handle_db_errors
def api_detection_settings(request):
    """
    GET / POST live YOLO11n confidence threshold and AnomalyDetector rule configuration.
    Persists rule state in existing SQLite DetectionProfile rows (zero schema change)
    and updates active InferenceWorker instances in real time.
    """
    from apps.core.models import DetectionProfile
    from apps.surveillance.ai.registry import get_inference_registry

    inf_reg = get_inference_registry()
    accessible_cams = list(get_accessible_cameras_qs(request.user))
    primary_cam = next((c for c in accessible_cams if c.id == 4), None) or (accessible_cams[0] if accessible_cams else None)

    if request.method == "POST":
        if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        is_staff = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)
        has_own_cameras = any(c.user_id == request.user.id for c in accessible_cams)
        if not is_staff and not has_own_cameras:
            return JsonResponse({"success": False, "error": "Insufficient privileges to modify global detection rules."}, status=403)

        data = _parse_body(request)
        raw_conf = data.get("confidence_threshold", data.get("confThreshold"))
        raw_profile = data.get("ai_profile")
        conf_val = None
        if raw_conf is not None:
            try:
                conf_val = max(0.15, min(0.95, float(raw_conf)))
            except (ValueError, TypeError):
                return JsonResponse({"success": False, "error": "Invalid confidence threshold."}, status=400)

        rules_in = data.get("rules") if isinstance(data.get("rules"), dict) else data
        loitering = bool(rules_in.get("loitering", rules_in.get("loitering_enabled", True)))
        restricted_entry = bool(rules_in.get("restrictedEntry", rules_in.get("restricted_entry_enabled", True)))
        crowding = bool(rules_in.get("crowding", rules_in.get("crowding_enabled", True)))
        unusual_movement = bool(rules_in.get("unusualMovement", rules_in.get("unusual_movement_enabled", True)))
        rapid_movement = bool(rules_in.get("rapidMovement", rules_in.get("rapid_movement_enabled", True)))
        abandoned_object = bool(rules_in.get("abandonedObject", rules_in.get("abandoned_object_enabled", True)))

        now = timezone.now()
        target_cams = accessible_cams if is_staff else [c for c in accessible_cams if c.user_id == request.user.id]
        for cam in target_cams:
            prof = DetectionProfile.objects.filter(camera_id=cam.id).first()
            if prof is not None:
                prof.enabled = True
                prof.loitering_enabled = loitering
                prof.restricted_entry_enabled = restricted_entry
                prof.unusual_movement_enabled = unusual_movement
                prof.abandoned_object_enabled = abandoned_object
                prof.updated_at = now
                prof.save(update_fields=[
                    "enabled", "loitering_enabled", "restricted_entry_enabled",
                    "unusual_movement_enabled", "abandoned_object_enabled", "updated_at"
                ])
            elif cam == primary_cam:
                DetectionProfile.objects.create(
                    user_id=request.user.id,
                    camera_id=cam.id,
                    enabled=True,
                    loitering_enabled=loitering,
                    restricted_entry_enabled=restricted_entry,
                    unusual_movement_enabled=unusual_movement,
                    abandoned_object_enabled=abandoned_object,
                    stationary_distance_threshold=20.0,
                    stationary_time_threshold=3.0,
                    loitering_radius=80.0,
                    loitering_time_threshold=10.0,
                    speed_fast_threshold=150.0,
                    speed_slow_threshold=15.0,
                    unusual_movement_persistence_seconds=1.5,
                    anomaly_event_cooldown_seconds=30.0,
                    anomaly_display_seconds=5.0,
                    abandoned_object_time_threshold=10.0,
                    abandoned_object_distance_threshold=120.0,
                    person_object_association_distance=140.0,
                    created_at=now,
                    updated_at=now,
                )

        if inf_reg is not None:
            if is_staff:
                inf_reg.apply_runtime_settings(
                    confidence_threshold=conf_val,
                    ai_profile=raw_profile,
                    rules={
                        "LOITERING_ENABLED": loitering,
                        "RESTRICTED_ENTRY_ENABLED": restricted_entry,
                        "CROWDING_ENABLED": crowding,
                        "UNUSUAL_MOVEMENT_ENABLED": unusual_movement,
                        "RAPID_MOVEMENT_ENABLED": rapid_movement,
                        "ABANDONED_OBJECT_ENABLED": abandoned_object,
                    },
                )
            else:
                # Non-staff owners may only adjust their own camera workers without altering global runtime config.
                owner_cam_ids = {c.id for c in target_cams}
                for cid in owner_cam_ids:
                    iw = inf_reg.get_active_worker(cid)
                    if iw is not None and conf_val is not None and hasattr(iw, "tracker") and hasattr(iw.tracker, "confidence_threshold"):
                        iw.tracker.confidence_threshold = float(conf_val)

        rt = inf_reg.get_runtime_settings() if inf_reg else {"confidence_threshold": conf_val or 0.35, "ai_profile": "balanced", "rules": {}}
        from apps.surveillance.ai.onnx_runtime import get_effective_cpu_count, get_model_profile_catalog
        from apps.surveillance.ai.model_loader import get_shared_yolo_model
        shared_m = None
        try:
            shared_m = get_shared_yolo_model()
        except Exception:
            pass
        log_audit(
            request,
            action="DETECTION_SETTINGS_UPDATED",
            resource_type="detection_settings",
            description=f"Updated confidence_threshold={rt['confidence_threshold']}, ai_profile={rt.get('ai_profile', 'balanced')} and 6 security event rules.",
        )
        return JsonResponse({
            "success": True,
            "message": "Detection threshold and security event rules applied to active pipeline.",
            "confidence_threshold": rt["confidence_threshold"],
            "ai_profile": rt.get("ai_profile", "balanced"),
            "active_model": getattr(shared_m, "model_name", "yolo26s.onnx") if shared_m else "yolo26s.onnx",
            "detector_backend": getattr(shared_m, "backend_id", "unknown") if shared_m else "standby",
            "effective_cpus": get_effective_cpu_count(),
            "model_catalog": get_model_profile_catalog(),
            "rules": {
                "loitering": loitering,
                "restrictedEntry": restricted_entry,
                "crowding": crowding,
                "unusualMovement": unusual_movement,
                "rapidMovement": rapid_movement,
                "abandonedObject": abandoned_object,
            },
        })

    rt = inf_reg.get_runtime_settings() if inf_reg else {"confidence_threshold": 0.35, "ai_profile": "balanced", "rules": {}}
    prof = DetectionProfile.objects.filter(camera_id=primary_cam.id).first() if primary_cam else None
    rt_rules = rt.get("rules", {})
    from apps.surveillance.ai.onnx_runtime import get_effective_cpu_count, get_model_profile_catalog
    from apps.surveillance.ai.model_loader import get_shared_yolo_model
    shared_m = None
    try:
        shared_m = get_shared_yolo_model()
    except Exception:
        pass
    return JsonResponse({
        "success": True,
        "confidence_threshold": rt.get("confidence_threshold", 0.35),
        "ai_profile": rt.get("ai_profile", "balanced"),
        "active_model": getattr(shared_m, "model_name", "yolo26s.onnx") if shared_m else "yolo26s.onnx",
        "detector_backend": getattr(shared_m, "backend_id", "unknown") if shared_m else "standby",
        "effective_cpus": get_effective_cpu_count(),
        "model_catalog": get_model_profile_catalog(),
        "rules": {
            "loitering": bool(rt_rules.get("LOITERING_ENABLED", bool(prof.loitering_enabled) if prof is not None else True)),
            "restrictedEntry": bool(rt_rules.get("RESTRICTED_ENTRY_ENABLED", bool(prof.restricted_entry_enabled) if prof is not None else True)),
            "crowding": bool(rt_rules.get("CROWDING_ENABLED", True)),
            "unusualMovement": bool(rt_rules.get("UNUSUAL_MOVEMENT_ENABLED", bool(prof.unusual_movement_enabled) if prof is not None else True)),
            "rapidMovement": bool(rt_rules.get("RAPID_MOVEMENT_ENABLED", True)),
            "abandonedObject": bool(rt_rules.get("ABANDONED_OBJECT_ENABLED", bool(prof.abandoned_object_enabled) if prof is not None else True)),
        },
    })


@never_cache
@login_required
@handle_db_errors
def api_camera_rules(request, camera_id):
    """Per-camera alias for detection profile rules (GET / POST)."""
    get_user_camera_or_404(request.user, camera_id)
    return api_detection_settings(request)


@never_cache
@login_required
@handle_db_errors
def api_clip_settings(request):
    """
    Returns or updates configurable CLIP scene-understanding settings
    (enabled, backend, model_name, interval, cosine_threshold, scene_descriptions).
    """
    from apps.surveillance.ai.clip_service import get_clip_analyzer

    analyzer = get_clip_analyzer()
    if request.method == "POST":
        if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        is_staff = getattr(request.user, "role", "") in ("admin", "supervisor", "operator") or getattr(request.user, "is_superuser", False)
        if not is_staff:
            return JsonResponse({"success": False, "error": "Administrator or staff privileges required to modify CLIP configuration."}, status=403)

        data = _parse_body(request)
        try:
            updated = analyzer.update_config(data)
        except (ValueError, TypeError) as exc:
            logger.warning("[CLIP_CONFIG_INVALID] user=%s err=%s", getattr(request.user, "id", None), exc)
            return JsonResponse({"success": False, "error": "Invalid CLIP configuration parameters."}, status=400)

        log_audit(
            request,
            action="CLIP_SETTINGS_UPDATED",
            resource_type="clip_settings",
            description=(
                f"Updated CLIP enabled={updated.get('enabled')}, model={updated.get('model_name')}, "
                f"interval={updated.get('analysis_interval_seconds')}s, cos_thr={updated.get('cosine_threshold')}."
            ),
        )
        return JsonResponse({
            "success": True,
            "message": "CLIP scene understanding configuration saved.",
            "config": updated,
            "status": analyzer.get_status(),
        })

    return JsonResponse({
        "success": True,
        "config": analyzer.get_config(),
        "status": analyzer.get_status(),
    })


@never_cache
@login_required
@handle_db_errors
def api_camera_scene_status(request, camera_id):
    """
    GET: Returns latest CLIP scene understanding snapshot + recent scene events for this camera.
    POST: Triggers a bounded on-demand CLIP analysis on the latest live worker frame (non-viewer).
    """
    from apps.surveillance.ai.clip_service import get_clip_analyzer, get_clip_scheduler, list_scene_events
    from apps.surveillance.camera.registry import get_camera_registry

    camera = get_user_camera_or_404(request.user, camera_id)
    analyzer = get_clip_analyzer()
    scheduler = get_clip_scheduler()

    if request.method == "POST":
        if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        worker = get_camera_registry().get_active_worker(camera.id)
        if worker is None or worker.latest_frame is None:
            return JsonResponse({
                "success": False,
                "error": "No live camera frame available right now for CLIP scene inspection.",
                "clip_status": analyzer.get_status(),
            }, status=409)
        with worker.lock:
            frame_copy = worker.latest_frame.copy()
        res = analyzer.analyze_bgr_frame(frame_copy)
        res["camera_id"] = camera.id
        if res.get("analyzed"):
            scheduler._latest_by_camera[camera.id] = res
        return JsonResponse({
            "success": bool(res.get("analyzed")),
            "camera_id": camera.id,
            "scene": res,
            "clip_status": analyzer.get_status(),
        }, status=200 if res.get("analyzed") else 503 if res.get("status") in ("unavailable", "disabled_by_config") else 422)

    live_scene = scheduler.get_camera_scene(camera.id)
    events = list_scene_events(user_id=request.user.id, camera_id=camera.id, limit=15)
    return JsonResponse({
        "success": True,
        "camera_id": camera.id,
        "scene": live_scene,
        "events": events,
        "clip_status": analyzer.get_status(),
    })


@never_cache
@require_GET
@login_required
@handle_db_errors
def api_clip_events(request):
    """Returns strictly user-scoped recent CLIP scene-analysis events and runtime status."""
    from apps.surveillance.ai.clip_service import get_clip_analyzer, list_scene_events

    raw_cam = request.GET.get("camera_id", "").strip()
    cam_id = int(raw_cam) if raw_cam.isdigit() else None
    if cam_id is not None:
        get_user_camera_or_404(request.user, cam_id)
    limit = _parse_bounded_int(request.GET.get("limit"), 25, 1, 100)
    analyzer = get_clip_analyzer()
    return JsonResponse({
        "success": True,
        "status": analyzer.get_status(),
        "events": list_scene_events(user_id=request.user.id, camera_id=cam_id, limit=limit),
    })



# =========================================================================
# RECORDINGS APIS
# =========================================================================

@never_cache
@login_required
@handle_db_errors
def api_recordings_list(request):
    """Returns paginated recordings strictly scoped to the authenticated user."""
    try:
        from apps.surveillance.recording.recording_service import recover_interrupted_recordings
        recover_interrupted_recordings(user_id=request.user.id)
    except Exception:
        pass
    recordings_qs = Recording.objects.filter(user_id=request.user.id).select_related('camera')

    camera_id = request.GET.get('camera_id', '').strip() or request.GET.get('camera', '').strip()
    if camera_id and camera_id.isdigit():
        recordings_qs = recordings_qs.filter(camera_id=int(camera_id))

    search_query = request.GET.get('q', '').strip()
    if search_query:
        recordings_qs = recordings_qs.filter(
            Q(filename__icontains=search_query) | Q(camera__name__icontains=search_query)
        )

    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter in ('completed', 'recording', 'processing', 'uploading', 'failed', 'interrupted', 'stopped'):
        recordings_qs = recordings_qs.filter(status=status_filter)

    type_filter = request.GET.get('type', '').strip().lower()
    anomaly_q = Q(filename__icontains='ANOMALY') | Q(filename__istartswith='alert_') | Q(file_path__istartswith='evidence/')
    if type_filter == 'anomaly':
        recordings_qs = recordings_qs.filter(anomaly_q)
    elif type_filter in ('continuous', 'normal'):
        recordings_qs = recordings_qs.exclude(anomaly_q)

    recordings_qs = _apply_date_filter(recordings_qs, request, date_field='started_at')
    recordings_qs = recordings_qs.order_by('-started_at', '-id')
    page_number = _parse_bounded_int(request.GET.get('page'), 1, 1, 10000)
    per_page = _parse_bounded_int(request.GET.get('per_page'), 24, 1, 100)
    paginator = Paginator(recordings_qs, per_page)
    page_obj = paginator.get_page(page_number)

    items = []
    total_size = 0
    for r in page_obj:
        local_staged = resolve_local_staged_recording(r)
        file_exists = media_exists(r.file_path, kind='recording') or (local_staged is not None)
        scheme, _, _ = parse_storage_uri(r.file_path)
        can_retry = (r.status in ('failed', 'interrupted', 'uploading', 'processing')) and (local_staged is not None)
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
            "storage_backend": scheme,
            "is_persistent": scheme in ('supabase', 's3', 'pdir'),
            "can_retry_upload": can_retry,
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "ended_at": r.ended_at.isoformat() if r.ended_at else "",
            "status": r.status or "completed",
            "stream_url": f"/recordings/{r.id}/view/",
            "download_url": f"/recordings/{r.id}/download/",
        })

    user_cameras = [{"id": c.id, "name": c.name} for c in get_accessible_cameras_qs(request.user)]

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
        "storage_health": get_storage_health(),
    })


@never_cache
@login_required
@handle_db_errors
def api_recording_detail(request, recording_id):
    """Returns or deletes single recording metadata strictly scoped to the authenticated user."""
    recording = get_object_or_404(
        Recording.objects.select_related('camera'),
        id=recording_id,
        user_id=request.user.id,
    )
    local_staged = resolve_local_staged_recording(recording)
    file_exists = media_exists(recording.file_path, kind='recording') or (local_staged is not None)
    scheme, _, _ = parse_storage_uri(recording.file_path)

    if request.method == "DELETE":
        if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        rec_filename = recording.filename
        if recording.status == "recording" and recording.camera_id:
            try:
                stop_camera_recording(recording.camera_id, recording.user_id)
            except Exception:
                pass
        delete_stored_media(recording.file_path, kind='recording')
        if local_staged and os.path.exists(local_staged):
            try:
                os.remove(local_staged)
            except Exception:
                pass
        recording.delete()
        _DASHBOARD_STATS_CACHE.clear()
        log_audit(
            request,
            action="RECORDING_DELETED",
            resource_type="recording",
            resource_id=recording_id,
            description=f"Deleted recording '{rec_filename}'.",
        )
        return JsonResponse({
            "success": True,
            "message": f"Recording '{rec_filename}' deleted successfully.",
        })

    events = []
    if recording.camera and recording.started_at:
        events_qs = Alert.objects.filter(
            camera_id=recording.camera_id,
            user_id=request.user.id,
            detected_at__gte=recording.started_at,
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
            "file_exists": file_exists,
            "storage_backend": scheme,
            "is_persistent": scheme in ('supabase', 's3', 'pdir'),
            "can_retry_upload": (recording.status in ('failed', 'interrupted', 'uploading', 'processing')) and (local_staged is not None),
            "started_at": recording.started_at.isoformat() if recording.started_at else "",
            "ended_at": recording.ended_at.isoformat() if recording.ended_at else "",
            "status": recording.status or "completed",
            "stream_url": f"/recordings/{recording.id}/view/",
            "download_url": f"/recordings/{recording.id}/download/",
        },
        "events": events,
    })


@require_POST
@never_cache
@login_required
@handle_db_errors
def api_recording_retry_upload(request, recording_id):
    """Safely retries persistent storage upload for a failed or interrupted recording."""
    recording = get_object_or_404(Recording, id=recording_id, user_id=request.user.id)
    if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
        return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
    ok, msg = upload_recording_by_id(recording.id)
    recording.refresh_from_db()
    status_code = 200 if ok else 422
    return JsonResponse({
        "success": bool(ok),
        "message": msg,
        "status": recording.status,
        "file_size": recording.file_size,
        "storage_health": get_storage_health(),
    }, status=status_code)


@never_cache
@login_required
@handle_db_errors
def api_evidence_list(request):
    """Returns forensic evidence vault assets strictly scoped to the authenticated user."""
    evidence_qs = Evidence.objects.filter(user_id=request.user.id).select_related('camera', 'alert')

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

    evidence_qs = _apply_date_filter(evidence_qs, request, date_field='captured_at')
    evidence_qs = evidence_qs.order_by('-captured_at', '-id')
    page_number = _parse_bounded_int(request.GET.get('page'), 1, 1, 10000)
    per_page = _parse_bounded_int(request.GET.get('per_page'), 18, 1, 100)
    paginator = Paginator(evidence_qs, per_page)
    page_obj = paginator.get_page(page_number)

    items = []
    for ev in page_obj:
        local_ev = resolve_local_staged_evidence(ev)
        ev_available = media_exists(ev.file_path, kind='evidence') or (local_ev is not None)
        scheme, _, _ = parse_storage_uri(ev.file_path)
        items.append({
            "id": ev.id,
            "file_name": ev.file_name,
            "evidence_type": ev.evidence_type,
            "mime_type": ev.mime_type,
            "file_size": ev.file_size,
            "formatted_size": _format_size(ev.file_size),
            "file_available": ev_available,
            "storage_backend": scheme,
            "is_persistent": scheme in ('supabase', 's3', 'pdir'),
            "captured_at": ev.captured_at.isoformat() if ev.captured_at else "",
            "camera_id": ev.camera_id,
            "camera_name": ev.camera.name if ev.camera else "Channel 01",
            "alert_id": ev.alert_id,
            "alert_title": ev.alert.title if ev.alert else None,
            "preview_url": f"/evidence/{ev.id}/preview/",
            "download_url": f"/evidence/{ev.id}/download/",
        })

    user_cameras = [{"id": c.id, "name": c.name} for c in get_accessible_cameras_qs(request.user).order_by('name')]

    return JsonResponse({
        "evidence": items,
        "total_count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "cameras": user_cameras,
    })


@never_cache
@login_required
@handle_db_errors
def api_evidence_detail(request, evidence_id):
    """Returns or deletes single evidence metadata strictly scoped to the authenticated user."""
    ev = get_object_or_404(Evidence.objects.select_related('camera', 'alert'), id=evidence_id, user_id=request.user.id)
    local_ev = resolve_local_staged_evidence(ev)
    ev_available = media_exists(ev.file_path, kind='evidence') or (local_ev is not None)
    scheme, _, _ = parse_storage_uri(ev.file_path)

    if request.method == "DELETE":
        if getattr(request.user, "role", "") == "viewer" and not getattr(request.user, "is_superuser", False):
            return JsonResponse({"success": False, "error": "Permission denied."}, status=403)
        ev_name = ev.file_name
        delete_stored_media(ev.file_path, kind='evidence')
        if local_ev and os.path.exists(local_ev):
            try:
                os.remove(local_ev)
            except Exception:
                pass
        ev.delete()
        _DASHBOARD_STATS_CACHE.clear()
        log_audit(
            request,
            action="EVIDENCE_DELETED",
            resource_type="evidence",
            resource_id=evidence_id,
            description=f"Deleted evidence item '{ev_name}'.",
        )
        return JsonResponse({
            "success": True,
            "message": f"Evidence '{ev_name}' deleted successfully.",
        })

    return JsonResponse({
        "evidence": {
            "id": ev.id,
            "file_name": ev.file_name,
            "evidence_type": ev.evidence_type,
            "mime_type": ev.mime_type,
            "file_size": ev.file_size,
            "formatted_size": _format_size(ev.file_size),
            "file_available": ev_available,
            "storage_backend": scheme,
            "is_persistent": scheme in ('supabase', 's3', 'pdir'),
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
@handle_db_errors
def api_alerts_list(request):
    """Returns alerts inbox with severity/status filters, media flags, case association, and metrics."""
    alerts_qs = Alert.objects.filter(user_id=request.user.id).select_related('camera')

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

    alerts_qs = _apply_date_filter(alerts_qs, request, date_field='detected_at')
    alerts_qs = alerts_qs.order_by('-detected_at', '-id').prefetch_related('evidence_items', 'incident_cases')
    page_number = _parse_bounded_int(request.GET.get('page'), 1, 1, 10000)
    per_page = _parse_bounded_int(request.GET.get('per_page'), 20, 1, 100)
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

    user_all = Alert.objects.filter(user_id=request.user.id)
    user_cameras = [{"id": c.id, "name": c.name} for c in get_accessible_cameras_qs(request.user).order_by('name')]
    total_count = user_all.count()
    new_count = user_all.filter(status='new').count()
    active_high_count = user_all.filter(status='new', severity__in=['high', 'critical']).count()
    resolved_count = user_all.filter(status='resolved').count()
    with_video_count = user_all.filter(evidence_items__evidence_type='video').distinct().count()
    with_case_count = user_all.filter(incident_cases__isnull=False).distinct().count()

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
    """Returns ONLY the forensic case strictly belonging to this incident, or creates one if POST."""
    if request.method == "POST":
        return api_alert_create_case(request, alert_id)
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
    if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
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
    log_audit(
        request,
        action="CASE_CREATED",
        resource_type="incident_case",
        resource_id=case.id,
        description=f"Created incident case {case.case_number} for alert #{alert.id}.",
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
    if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
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
@handle_db_errors
def api_cases_list(request):
    """Returns incident cases list strictly scoped to the authenticated user."""
    cases_qs = IncidentCase.objects.filter(user_id=request.user.id).select_related('alert', 'alert__camera').order_by('-created_at')

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

    cases_qs = _apply_date_filter(cases_qs, request, date_field='created_at')
    total_count = cases_qs.count()
    limit = _parse_bounded_int(request.GET.get('limit'), 50, 1, 100)
    cases_page = cases_qs[:limit]

    items = []
    for c in cases_page:
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

    return JsonResponse({"cases": items, "total": total_count, "total_count": total_count})


@never_cache
@login_required
def api_case_detail(request, case_id):
    """Returns single case details with forensic timeline notes, or updates case status/priority (PATCH/POST)."""
    case = get_object_or_404(IncidentCase.objects.select_related('alert', 'alert__camera'), id=case_id, user_id=request.user.id)

    if request.method in ("PATCH", "PUT", "POST"):
        if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        data = _parse_body(request)
        updated_fields = []
        raw_status = data.get("status")
        if isinstance(raw_status, str) and raw_status.strip():
            norm_s = raw_status.strip().lower()
            if norm_s == "investigating":
                norm_s = "in_progress"
            if norm_s in ("open", "in_progress", "resolved", "closed"):
                case.status = norm_s
                updated_fields.append("status")
                if norm_s in ("resolved", "closed") and not case.closed_at:
                    case.closed_at = timezone.now()
                    updated_fields.append("closed_at")
                elif norm_s in ("open", "in_progress") and case.closed_at is not None:
                    case.closed_at = None
                    updated_fields.append("closed_at")
            else:
                return JsonResponse({"success": False, "error": "Invalid case status."}, status=400)

        raw_prio = data.get("priority")
        if isinstance(raw_prio, str) and raw_prio.strip():
            norm_p = raw_prio.strip().upper()
            if norm_p in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                case.priority = norm_p
                updated_fields.append("priority")
            else:
                return JsonResponse({"success": False, "error": "Invalid case priority."}, status=400)

        if "assigned_to" in data:
            clean_assignee, _ = sanitize_untrusted_text(data.get("assigned_to") or "", max_len=100)
            case.assigned_to = clean_assignee or None
            updated_fields.append("assigned_to")

        if updated_fields:
            case.save(update_fields=list(dict.fromkeys(updated_fields + ["updated_at"])))
            log_audit(
                request,
                action="CASE_UPDATED",
                resource_type="incident_case",
                resource_id=case.id,
                description=f"Updated case {case.case_number} (status={case.status}, priority={case.priority}).",
            )

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
        "success": True,
        "case": {
            "id": case.id,
            "case_number": case.case_number,
            "title": case.title,
            "description": case.description or "",
            "priority": case.priority,
            "status": case.status,
            "assigned_to": case.assigned_to or "Unassigned",
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
    if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
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


@never_cache
@require_GET
@login_required
@handle_db_errors
def api_audit_logs(request):
    """
    Returns recent security audit logs.
    Restricted via RBAC strictly to privileged staff roles ('admin', 'supervisor', 'operator').
    """
    is_staff = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)
    if not is_staff:
        return JsonResponse({
            "success": False,
            "error": "Insufficient privileges to access security audit logs.",
        }, status=403)

    limit = _parse_bounded_int(request.GET.get("limit"), 50, 1, 100)
    qs = AuditLog.objects.select_related("user").order_by("-created_at", "-id")[:limit]
    items = []
    for entry in qs:
        items.append({
            "id": entry.id,
            "user_id": entry.user_id,
            "user_email": entry.user.email if entry.user else None,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "description": entry.description or "",
            "ip_address": entry.ip_address or "",
            "created_at": entry.created_at.isoformat() if entry.created_at else "",
        })
    return JsonResponse({
        "success": True,
        "audit_logs": items,
        "total": len(items),
    })


# =========================================================================
# SOC TRIAGE, BULK ACTIONS, POLICIES & PLAYBOOKS APIS
# =========================================================================

@never_cache
@require_POST
@login_required
@handle_db_errors
def api_alert_analyze(request, alert_id):
    """Runs evidence-linked SOC analysis and duplicate correlation for an alert (supervised read/report)."""
    context = get_incident_context(alert_id, user_id=request.user.id)
    log_audit(
        request,
        action="ALERT_SOC_ANALYZED",
        resource_type="alert",
        resource_id=alert_id,
        description=f"Generated evidence-linked SOC triage analysis for Alert #{alert_id}.",
    )
    return JsonResponse({
        "success": True,
        "alert_id": alert_id,
        "ai_analysis": context.get("ai_analysis"),
    })


@require_POST
@login_required
@handle_db_errors
def api_alerts_bulk_action(request):
    """Operator-confirmed bulk acknowledge or resolve action on user-owned alerts."""
    if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
    data = _parse_body(request)
    action = str(data.get("action") or "").strip().lower()
    raw_ids = data.get("alert_ids")
    if action not in ("acknowledge", "resolve"):
        return JsonResponse({"success": False, "error": "Action must be 'acknowledge' or 'resolve'."}, status=400)
    if not isinstance(raw_ids, list) or not raw_ids:
        return JsonResponse({"success": False, "error": "alert_ids list is required."}, status=400)

    clean_ids = []
    for item in raw_ids[:50]:
        try:
            clean_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    if not clean_ids:
        return JsonResponse({"success": False, "error": "No valid alert IDs supplied."}, status=400)

    now = timezone.now()
    qs = Alert.objects.filter(id__in=clean_ids, user_id=request.user.id)
    if action == "acknowledge":
        target_qs = qs.filter(status="new")
        updated = target_qs.update(status="acknowledged", acknowledged_at=now)
    else:
        target_qs = qs.filter(status__in=["new", "acknowledged"])
        updated = target_qs.update(status="resolved", resolved_at=now)

    log_audit(
        request,
        action=f"ALERTS_BULK_{action.upper()}",
        resource_type="alert",
        resource_id=",".join(str(x) for x in clean_ids[:10]),
        description=f"Operator bulk {action} applied to {updated} alert(s).",
    )
    _DASHBOARD_STATS_CACHE.clear()
    return JsonResponse({"success": True, "action": action, "updated": int(updated)})


@never_cache
@login_required
@handle_db_errors
def api_soc_policies(request, policy_id=None):
    """Lists or manages SOC IncidentPolicy SLA & Escalation definitions (zero schema change)."""
    if policy_id is not None:
        policy = get_object_or_404(IncidentPolicy, id=policy_id, user_id=request.user.id)
        if request.method == "DELETE":
            if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
                return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
            pname = policy.name
            policy.delete()
            log_audit(request, action="POLICY_DELETED", resource_type="incident_policy", resource_id=policy_id, description=f"Deleted policy '{pname}'.")
            return JsonResponse({"success": True})
        if request.method in ("PUT", "PATCH", "POST"):
            if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
                return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
            data = _parse_body(request)
            if "name" in data:
                clean_name, _ = sanitize_untrusted_text(data["name"], max_len=100)
                if clean_name:
                    policy.name = clean_name
            if "description" in data:
                clean_desc, _ = sanitize_untrusted_text(data["description"], max_len=240)
                policy.description = clean_desc
            if "enabled" in data:
                policy.enabled = bool(data["enabled"])
            if "severity" in data and str(data["severity"]).strip().lower() in ("low", "medium", "high", "critical"):
                policy.severity = str(data["severity"]).strip().lower()
            for num_field, lo, hi in (("initial_response_minutes", 1, 1440), ("escalation_minutes", 1, 2880), ("resolution_minutes", 5, 10080)):
                if num_field in data:
                    try:
                        setattr(policy, num_field, max(lo, min(hi, int(data[num_field]))))
                    except (TypeError, ValueError):
                        pass
            for bfield in ("auto_escalate", "auto_create_case", "notify_on_escalation"):
                if bfield in data:
                    setattr(policy, bfield, bool(data[bfield]))
            policy.save()
            log_audit(request, action="POLICY_UPDATED", resource_type="incident_policy", resource_id=policy.id, description=f"Updated SLA policy '{policy.name}'.")
            return JsonResponse({"success": True, "id": policy.id})

    if request.method == "POST":
        if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        data = _parse_body(request)
        name, _ = sanitize_untrusted_text(data.get("name") or "High Severity SLA", max_len=100)
        desc, _ = sanitize_untrusted_text(data.get("description") or "", max_len=240)
        sev = str(data.get("severity") or "high").strip().lower()
        if sev not in ("low", "medium", "high", "critical"):
            sev = "high"
        policy = IncidentPolicy.objects.create(
            user_id=request.user.id,
            name=name or "SOC SLA Policy",
            description=desc,
            enabled=bool(data.get("enabled", True)),
            severity=sev,
            initial_response_minutes=max(1, min(1440, int(data.get("initial_response_minutes") or 15))),
            escalation_minutes=max(1, min(2880, int(data.get("escalation_minutes") or 30))),
            resolution_minutes=max(5, min(10080, int(data.get("resolution_minutes") or 120))),
            auto_escalate=bool(data.get("auto_escalate", True)),
            auto_create_case=bool(data.get("auto_create_case", True)),
            notify_on_escalation=bool(data.get("notify_on_escalation", True)),
        )
        log_audit(request, action="POLICY_CREATED", resource_type="incident_policy", resource_id=policy.id, description=f"Created SLA policy '{policy.name}'.")
        return JsonResponse({"success": True, "id": policy.id}, status=201)

    policies = []
    for p in IncidentPolicy.objects.filter(user_id=request.user.id).order_by("initial_response_minutes", "id"):
        clean_name, _ = sanitize_untrusted_text(p.name, max_len=100)
        clean_desc, _ = sanitize_untrusted_text(p.description or "", max_len=240)
        policies.append({
            "id": p.id,
            "name": clean_name,
            "description": clean_desc,
            "enabled": bool(p.enabled),
            "severity": p.severity,
            "initial_response_minutes": p.initial_response_minutes,
            "escalation_minutes": p.escalation_minutes,
            "resolution_minutes": p.resolution_minutes,
            "auto_escalate": bool(p.auto_escalate),
            "auto_create_case": bool(p.auto_create_case),
            "notify_on_escalation": bool(p.notify_on_escalation),
        })
    return JsonResponse({"success": True, "policies": policies})


@never_cache
@login_required
@handle_db_errors
def api_soc_playbooks(request, playbook_id=None):
    """Lists or manages SOC IncidentPlaybook response templates (never alters history silently)."""
    if playbook_id is not None:
        pb = get_object_or_404(IncidentPlaybook, id=playbook_id, user_id=request.user.id)
        if request.method == "DELETE":
            if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
                return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
            pb.delete()
            log_audit(request, action="PLAYBOOK_DELETED", resource_type="incident_playbook", resource_id=playbook_id, description=f"Deleted playbook #{playbook_id}.")
            return JsonResponse({"success": True})
        if request.method in ("PUT", "PATCH", "POST"):
            if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
                return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
            data = _parse_body(request)
            if "name" in data:
                pb.name, _ = sanitize_untrusted_text(data["name"], max_len=100)
            if "description" in data:
                pb.description, _ = sanitize_untrusted_text(data["description"], max_len=240)
            if "enabled" in data:
                pb.enabled = bool(data["enabled"])
            pb.save()
            log_audit(request, action="PLAYBOOK_UPDATED", resource_type="incident_playbook", resource_id=pb.id, description=f"Updated playbook '{pb.name}'.")
            return JsonResponse({"success": True, "id": pb.id})

    if request.method == "POST":
        if getattr(request.user, 'role', '') == 'viewer' and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({"success": False, "error": "Viewer accounts have read-only access."}, status=403)
        data = _parse_body(request)
        name, _ = sanitize_untrusted_text(data.get("name") or "Perimeter Intrusion Playbook", max_len=100)
        desc, _ = sanitize_untrusted_text(data.get("description") or "", max_len=240)
        pb = IncidentPlaybook.objects.create(
            user_id=request.user.id,
            name=name or "SOC Playbook",
            description=desc,
            enabled=bool(data.get("enabled", True)),
            priority=max(1, min(100, int(data.get("priority") or 1))),
            severity=(str(data.get("severity") or "").strip().lower() or None),
            event_type=(str(data.get("event_type") or "").strip().lower() or None),
            create_case=bool(data.get("create_case", True)),
            auto_escalate=bool(data.get("auto_escalate", True)),
            send_notification=bool(data.get("send_notification", True)),
            apply_sla_policy=bool(data.get("apply_sla_policy", True)),
            cooldown_seconds=max(10, min(3600, int(data.get("cooldown_seconds") or 300))),
        )
        log_audit(request, action="PLAYBOOK_CREATED", resource_type="incident_playbook", resource_id=pb.id, description=f"Created playbook '{pb.name}'.")
        return JsonResponse({"success": True, "id": pb.id}, status=201)

    playbooks = []
    for pb in IncidentPlaybook.objects.filter(user_id=request.user.id).order_by("priority", "id"):
        cname, _ = sanitize_untrusted_text(pb.name, max_len=100)
        cdesc, _ = sanitize_untrusted_text(pb.description or "", max_len=240)
        playbooks.append({
            "id": pb.id,
            "name": cname,
            "description": cdesc,
            "enabled": bool(pb.enabled),
            "priority": pb.priority,
            "severity": pb.severity,
            "event_type": pb.event_type,
            "create_case": bool(pb.create_case),
            "auto_escalate": bool(pb.auto_escalate),
            "send_notification": bool(pb.send_notification),
            "apply_sla_policy": bool(pb.apply_sla_policy),
            "cooldown_seconds": pb.cooldown_seconds,
        })
    return JsonResponse({"success": True, "playbooks": playbooks})


# =========================================================================
# WEBSITE UPTIME MONITORING APIS (SSRF-SAFE, HMAC + ADMIN RBAC PROTECTED)
# =========================================================================

@csrf_exempt
@require_POST
@handle_db_errors
def api_uptime_ingest(request):
    """
    Receives signed uptime probe results from the scheduled external monitor
    (`.github/workflows/uptime-monitor.yml`). Enforces constant-time HMAC-SHA256 verification
    and strict owned-host HTTPS SSRF validation.
    """
    from apps.core.uptime_service import verify_ingest_hmac, record_uptime_results

    sig = request.headers.get("X-DeepVision-Uptime-Signature", "")
    ts = request.headers.get("X-DeepVision-Uptime-Timestamp", "")
    ok, reason = verify_ingest_hmac(request.body, sig, ts)
    if not ok:
        code = 503 if "not configured" in reason.lower() else 401
        return JsonResponse({"success": False, "error": reason}, status=code)

    data = _parse_body(request)
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return JsonResponse({"success": False, "error": "results list is required."}, status=400)

    try:
        outcome = record_uptime_results(results[:20], source="github_actions_external")
    except ValueError as err:
        logger.warning("[UPTIME_INGEST_INVALID] %s", err)
        return JsonResponse({"success": False, "error": "Invalid uptime monitoring result payload."}, status=400)

    return JsonResponse({"success": True, **outcome})


@never_cache
@require_GET
@login_required
@handle_db_errors
def api_uptime_status(request):
    """
    Admin/Staff-only Website Uptime Status endpoint reporting external probe history,
    latency, consecutive failures, outage duration, and historical availability.
    """
    is_staff = getattr(request.user, 'role', '') in ('admin', 'supervisor', 'operator') or getattr(request.user, 'is_superuser', False)
    if not is_staff:
        return JsonResponse({"success": False, "error": "Administrator or staff privileges required."}, status=403)

    from apps.core.uptime_service import get_uptime_status_summary
    summary = get_uptime_status_summary()
    return JsonResponse({"success": True, **summary})


@require_POST
@login_required
@handle_db_errors
def api_uptime_check_now(request):
    """
    Admin-only manual HTTPS availability check against strict owned-domain allowlist ONLY.
    """
    is_admin = getattr(request.user, 'role', '') == 'admin' or getattr(request.user, 'is_superuser', False)
    if not is_admin:
        return JsonResponse({"success": False, "error": "Administrator privileges required to trigger live probes."}, status=403)

    from apps.core.uptime_service import (
        probe_allowlisted_targets,
        record_uptime_results,
        get_uptime_status_summary,
    )
    results = probe_allowlisted_targets(timeout_seconds=8.0, max_retries=1)
    outcome = record_uptime_results(results, source="admin_live_probe")
    log_audit(
        request,
        action="UPTIME_PROBE_EXECUTED",
        resource_type="uptime_monitor",
        description=f"Executed live HTTPS availability check across {len(results)} allowlisted endpoints.",
    )
    return JsonResponse({
        "success": True,
        "probe_results": results,
        "transitions": outcome.get("transitions", []),
        **get_uptime_status_summary(),
    })
