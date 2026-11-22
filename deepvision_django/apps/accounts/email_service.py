"""Django-backed email delivery for authentication and security alerts."""
import json
import logging
import os
import urllib.request
import urllib.error
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

# Process-local runtime telemetry for the most recent email delivery attempt (no secrets or PII stored)
_EMAIL_RUNTIME_STATUS = {
    "tested": False,
    "last_status": None,       # "provider_accepted" | "delivered" | "failed" | None
    "last_provider": None,     # "resend" | "brevo" | "sendgrid" | "smtp" | None
    "last_message_id": None,   # Provider message ID (e.g. Resend email id) if returned
    "last_error_code": None,   # HTTP status code or error category string
}


def get_email_runtime_status():
    """Returns a copy of the process-local email delivery runtime telemetry."""
    return dict(_EMAIL_RUNTIME_STATUS)


def reset_email_runtime_status():
    """Resets runtime email telemetry (used for deterministic test isolation)."""
    _EMAIL_RUNTIME_STATUS["tested"] = False
    _EMAIL_RUNTIME_STATUS["last_status"] = None
    _EMAIL_RUNTIME_STATUS["last_provider"] = None
    _EMAIL_RUNTIME_STATUS["last_message_id"] = None
    _EMAIL_RUNTIME_STATUS["last_error_code"] = None


def _record_delivery_outcome(status_or_accepted, provider: str, error_code=None, message_id=None):
    if isinstance(status_or_accepted, bool):
        status = "provider_accepted" if status_or_accepted else "failed"
    else:
        status = status_or_accepted
    _EMAIL_RUNTIME_STATUS["tested"] = True
    _EMAIL_RUNTIME_STATUS["last_status"] = status
    _EMAIL_RUNTIME_STATUS["last_provider"] = provider
    _EMAIL_RUNTIME_STATUS["last_message_id"] = message_id if status in ("provider_accepted", "delivered") else None
    _EMAIL_RUNTIME_STATUS["last_error_code"] = None if status in ("provider_accepted", "delivered") else error_code


def confirm_email_delivered(provider: str = None, message_id: str = None):
    """Records verified delivery evidence (e.g. from provider webhook or verified receipt)."""
    _EMAIL_RUNTIME_STATUS["tested"] = True
    _EMAIL_RUNTIME_STATUS["last_status"] = "delivered"
    if provider:
        _EMAIL_RUNTIME_STATUS["last_provider"] = provider
    if message_id:
        _EMAIL_RUNTIME_STATUS["last_message_id"] = message_id
    _EMAIL_RUNTIME_STATUS["last_error_code"] = None


def _send_via_http_api(recipient_email, subject, html_content):
    """
    HTTPS port-443 email delivery fallback for cloud platforms (such as Render free tier)
    that block outbound SMTP ports 25/465/587.
    Supports Resend, Brevo, or SendGrid when configured via environment variables.
    """
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or os.getenv("MAIL_DEFAULT_SENDER", "") or "noreply@deepvision.internal"
    text_body = strip_tags(html_content)

    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key:
        try:
            payload = json.dumps({
                "from": os.getenv("RESEND_FROM_EMAIL", "").strip() or from_email,
                "to": [recipient_email],
                "subject": subject,
                "html": html_content,
                "text": text_body,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "DeepVision-Mailer/4.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if 200 <= resp.status < 300:
                    msg_id = None
                    try:
                        raw = resp.read()
                        if isinstance(raw, (bytes, str)) and raw:
                            parsed = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
                            if isinstance(parsed, dict):
                                msg_id = parsed.get("id")
                    except Exception:
                        msg_id = None
                    logger.info("Email request accepted by Resend HTTPS API (type=%s).", subject)
                    _record_delivery_outcome("provider_accepted", "resend", message_id=msg_id)
                    return True
                _record_delivery_outcome("failed", "resend", f"HTTP_{resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning("Resend HTTPS email delivery rejected (status=%s, type=%s).", e.code, subject)
            _record_delivery_outcome("failed", "resend", f"HTTP_{e.code}")
        except Exception:
            logger.warning("Resend HTTPS email delivery failed (type=%s).", subject)
            _record_delivery_outcome("failed", "resend", "NETWORK_ERROR")

    brevo_key = os.getenv("BREVO_API_KEY", "").strip()
    if brevo_key:
        try:
            payload = json.dumps({
                "sender": {"name": "DeepVision", "email": from_email},
                "to": [{"email": recipient_email}],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_body,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=payload,
                headers={
                    "api-key": brevo_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Email request accepted by Brevo HTTPS API (type=%s).", subject)
                    _record_delivery_outcome("provider_accepted", "brevo")
                    return True
                _record_delivery_outcome("failed", "brevo", f"HTTP_{resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning("Brevo HTTPS email delivery rejected (status=%s, type=%s).", e.code, subject)
            _record_delivery_outcome("failed", "brevo", f"HTTP_{e.code}")
        except Exception:
            logger.warning("Brevo HTTPS email delivery failed (type=%s).", subject)
            _record_delivery_outcome("failed", "brevo", "NETWORK_ERROR")

    sendgrid_key = os.getenv("SENDGRID_API_KEY", "").strip()
    if sendgrid_key:
        try:
            payload = json.dumps({
                "personalizations": [{"to": [{"email": recipient_email}]}],
                "from": {"email": from_email, "name": "DeepVision"},
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": text_body},
                    {"type": "text/html", "value": html_content},
                ],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.sendgrid.com/v3/mail/send",
                data=payload,
                headers={
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Email request accepted by SendGrid HTTPS API (type=%s).", subject)
                    _record_delivery_outcome("provider_accepted", "sendgrid")
                    return True
                _record_delivery_outcome("failed", "sendgrid", f"HTTP_{resp.status}")
        except urllib.error.HTTPError as e:
            logger.warning("SendGrid HTTPS email delivery rejected (status=%s, type=%s).", e.code, subject)
            _record_delivery_outcome("failed", "sendgrid", f"HTTP_{e.code}")
        except Exception:
            logger.warning("SendGrid HTTPS email delivery failed (type=%s).", subject)
            _record_delivery_outcome("failed", "sendgrid", "NETWORK_ERROR")

    return False


def _send_email(recipient_email, subject, html_content):
    """Send through configured HTTPS email API (preferred in cloud containers) or Django's email backend."""
    email_backend = getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    has_http_api = bool(
        os.environ.get("RESEND_API_KEY", "").strip()
        or os.environ.get("BREVO_API_KEY", "").strip()
        or os.environ.get("SENDGRID_API_KEY", "").strip()
    )

    # Prefer HTTPS API over raw SMTP when running with default SMTP backend and an HTTPS API key is present
    if email_backend == "django.core.mail.backends.smtp.EmailBackend" and has_http_api:
        if _send_via_http_api(recipient_email, subject, html_content):
            return True

    if not all((settings.EMAIL_HOST, settings.EMAIL_HOST_USER,
                settings.EMAIL_HOST_PASSWORD, settings.DEFAULT_FROM_EMAIL)):
        if _send_via_http_api(recipient_email, subject, html_content):
            return True
        if not has_http_api:
            _record_delivery_outcome("failed", "smtp", "CONFIG_INCOMPLETE")
        logger.warning("Email delivery skipped: SMTP configuration is incomplete.")
        return False

    try:
        connection = get_connection(
            fail_silently=False,
            timeout=getattr(settings, "EMAIL_TIMEOUT", 5),
        )
        message = EmailMultiAlternatives(
            subject=subject,
            body=strip_tags(html_content),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
            connection=connection,
        )
        message.attach_alternative(html_content, "text/html")
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            logger.warning("Email backend did not accept the message (type=%s).", subject)
            if _send_via_http_api(recipient_email, subject, html_content):
                return True
            _record_delivery_outcome("failed", "smtp", "REJECTED")
            return False
        logger.info("Email request accepted by configured SMTP backend (type=%s).", subject)
        _record_delivery_outcome("provider_accepted", "smtp")
        return True
    except Exception:
        # SMTP exceptions can contain provider details; keep credentials and
        # recipient data out of logs and try HTTPS API fallback before failing.
        if _send_via_http_api(recipient_email, subject, html_content):
            return True
        _record_delivery_outcome("failed", "smtp", "SMTP_ERROR")
        logger.warning("Email delivery failed (type=%s).", subject)
        return False


def _send_email_tracked(
    recipient_email,
    subject,
    html_content,
    *,
    category="security_alert",
    user_id=None,
    camera_id=None,
    alert_id=None,
    severity=None,
    max_attempts=2,
    async_retries=False,
):
    """
    Sends email with durable delivery audit tracking, idempotency protection,
    and bounded retries on transient SMTP/network errors.
    """
    import threading
    import time
    from apps.notifications.delivery_service import (
        build_idempotency_key,
        create_or_update_delivery_record,
        was_already_delivered,
    )

    idem_extra = f"{subject}:{int(time.time() // 60)}" if alert_id is None else None
    idem_key = build_idempotency_key(category, recipient_email, alert_id=alert_id, extra=idem_extra)
    if alert_id is not None and was_already_delivered(idem_key):
        return True

    delivery_id = create_or_update_delivery_record(
        idempotency_key=idem_key,
        category=category,
        recipient=recipient_email,
        subject=subject,
        status="pending",
        attempts=0,
        max_attempts=max_attempts,
        user_id=user_id,
        camera_id=camera_id,
        alert_id=alert_id,
        severity=severity,
    )

    def _try_once(attempt_num: int) -> bool:
        ok = _send_email(recipient_email, subject, html_content)
        rt = get_email_runtime_status()
        err_code = rt.get("last_error_code")
        provider = rt.get("last_provider")
        msg_id = rt.get("last_message_id")
        if ok:
            create_or_update_delivery_record(
                delivery_id=delivery_id,
                idempotency_key=idem_key,
                category=category,
                recipient=recipient_email,
                subject=subject,
                status="sent",
                attempts=attempt_num,
                max_attempts=max_attempts,
                provider=provider,
                error_code=None,
                user_id=user_id,
                camera_id=camera_id,
                alert_id=alert_id,
                severity=severity,
                message_id=msg_id,
            )
            return True
        return False

    if _try_once(1):
        return True

    err_code = get_email_runtime_status().get("last_error_code")
    provider = get_email_runtime_status().get("last_provider")

    # Never retry permanent incomplete-config failures
    if err_code == "CONFIG_INCOMPLETE" or max_attempts <= 1:
        create_or_update_delivery_record(
            delivery_id=delivery_id,
            idempotency_key=idem_key,
            category=category,
            recipient=recipient_email,
            subject=subject,
            status="failed",
            attempts=1,
            max_attempts=max_attempts,
            provider=provider,
            error_code=err_code or "SEND_FAILED",
            user_id=user_id,
            camera_id=camera_id,
            alert_id=alert_id,
            severity=severity,
        )
        return False

    if async_retries:
        create_or_update_delivery_record(
            delivery_id=delivery_id,
            idempotency_key=idem_key,
            category=category,
            recipient=recipient_email,
            subject=subject,
            status="retry_scheduled",
            attempts=1,
            max_attempts=max_attempts,
            provider=provider,
            error_code=err_code,
            user_id=user_id,
            camera_id=camera_id,
            alert_id=alert_id,
            severity=severity,
        )

        def _bg_retry(attempt_idx: int):
            if _try_once(attempt_idx):
                return
            next_err = get_email_runtime_status().get("last_error_code")
            next_prov = get_email_runtime_status().get("last_provider")
            if attempt_idx < max_attempts and next_err != "CONFIG_INCOMPLETE":
                create_or_update_delivery_record(
                    delivery_id=delivery_id,
                    idempotency_key=idem_key,
                    category=category,
                    recipient=recipient_email,
                    subject=subject,
                    status="retry_scheduled",
                    attempts=attempt_idx,
                    max_attempts=max_attempts,
                    provider=next_prov,
                    error_code=next_err,
                    user_id=user_id,
                    camera_id=camera_id,
                    alert_id=alert_id,
                    severity=severity,
                )
                delay = min(4.0, 0.5 * (2 ** (attempt_idx - 1)))
                t = threading.Timer(delay, _bg_retry, args=(attempt_idx + 1,))
                t.daemon = True
                t.start()
            else:
                create_or_update_delivery_record(
                    delivery_id=delivery_id,
                    idempotency_key=idem_key,
                    category=category,
                    recipient=recipient_email,
                    subject=subject,
                    status="failed",
                    attempts=attempt_idx,
                    max_attempts=max_attempts,
                    provider=next_prov,
                    error_code=next_err or "MAX_RETRIES_EXCEEDED",
                    user_id=user_id,
                    camera_id=camera_id,
                    alert_id=alert_id,
                    severity=severity,
                )

        timer = threading.Timer(0.4, _bg_retry, args=(2,))
        timer.daemon = True
        timer.start()
        return False

    # Synchronous bounded fast retry for interactive flows (OTP / test email)
    for attempt_idx in range(2, max_attempts + 1):
        time.sleep(0.25)
        if _try_once(attempt_idx):
            return True
    final_rt = get_email_runtime_status()
    create_or_update_delivery_record(
        delivery_id=delivery_id,
        idempotency_key=idem_key,
        category=category,
        recipient=recipient_email,
        subject=subject,
        status="failed",
        attempts=max_attempts,
        max_attempts=max_attempts,
        provider=final_rt.get("last_provider"),
        error_code=final_rt.get("last_error_code") or "MAX_RETRIES_EXCEEDED",
        user_id=user_id,
        camera_id=camera_id,
        alert_id=alert_id,
        severity=severity,
    )
    return False


def _otp_email(greeting, intro, otp, accent="#2b5c8f"):
    safe_greeting = escape(greeting)
    safe_otp = escape(str(otp))
    return f"""
    <html><body style="font-family:Arial,sans-serif;padding:20px;color:#333;line-height:1.6">
      <h2 style="color:{accent};border-bottom:2px solid {accent};padding-bottom:10px">DeepVision</h2>
      <p>{safe_greeting}</p><p>{intro}</p>
      <p style="font-size:28px;font-weight:bold;background:#f4f6f9;padding:15px 25px;display:inline-block;letter-spacing:4px;border-radius:6px;border:1px solid #e1e4e8;color:{accent}">{safe_otp}</p>
      <p>This code expires in 15 minutes. If you did not request it, you can ignore this email.</p>
      <hr style="border:0;border-top:1px solid #eee;margin-top:30px">
      <p style="font-size:11px;color:#999">Automated message. Please do not reply.</p>
    </body></html>"""


def send_verification_email(recipient_email, otp, full_name=None):
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    body = _otp_email(greeting, "Use this code to verify your DeepVision email address:", otp)
    return _send_email_tracked(
        recipient_email,
        "DeepVision - Email Verification",
        body,
        category="otp_verification",
        max_attempts=2,
        async_retries=False,
    )


def send_password_reset_email(recipient_email, otp, full_name=None):
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    body = _otp_email(
        greeting,
        "Use this code to continue resetting your DeepVision password:",
        otp,
        accent="#b42318",
    )
    return _send_email_tracked(
        recipient_email,
        "DeepVision - Password Reset Verification",
        body,
        category="password_reset",
        max_attempts=2,
        async_retries=False,
    )


def send_login_otp_email(recipient_email, otp, full_name=None):
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    body = _otp_email(greeting, "Use this code to complete your DeepVision sign-in:", otp)
    return _send_email_tracked(
        recipient_email,
        "DeepVision - Sign-In Verification Code",
        body,
        category="login_otp",
        max_attempts=2,
        async_retries=False,
    )


def send_test_email(recipient_email, full_name=None, user_id=None):
    greeting = f"Hello {escape(full_name)}," if full_name else "Hello,"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;padding:20px;color:#333;line-height:1.6">
      <h2 style="color:#0891b2;border-bottom:2px solid #0891b2;padding-bottom:10px">DeepVision Surveillance</h2>
      <p>{greeting}</p>
      <p>This is a confirmation message verifying that DeepVision security alert and OTP email notifications are working cleanly.</p>
      <p style="font-size:12px;color:#64748b">You can customize severity filters, event types, and camera alert recipients inside Notification Settings.</p>
    </body></html>"""
    return _send_email_tracked(
        recipient_email,
        "DeepVision - Notification Delivery Test",
        body,
        category="test_email",
        user_id=user_id,
        max_attempts=2,
        async_retries=False,
    )


def send_security_alert_email(user_id, alert, camera_recipients=None, force_restricted_recipients=False):
    """Email opted-in security alerts using notification preferences and optional camera recipients."""
    from apps.accounts.models import User
    from apps.cameras.surveillance_config import get_camera_surveillance_config, normalize_recipients
    from apps.notifications.models import NotificationPreference

    severity = (getattr(alert, "severity", None) or "").lower()
    if severity not in {"medium", "high", "critical"}:
        return False

    preferences = NotificationPreference.objects.filter(user_id=user_id).first()

    # Check severity threshold (high/critical by default, plus medium if opted in cleanly)
    allowed_severities = {"high", "critical"}
    if preferences and getattr(preferences, "notify_medium", False):
        allowed_severities.add("medium")
    if severity not in allowed_severities:
        return False

    user_email_enabled = True
    if preferences:
        if not preferences.enabled or not getattr(preferences, f"notify_{severity}", False):
            user_email_enabled = False
        event_type = (getattr(alert, "event_type", None) or "").lower()
        event_preference = {
            "loitering": "notify_loitering",
            "restricted_area_entry": "notify_restricted_entry",
            "intrusion": "notify_restricted_entry",
            "unusual_movement": "notify_unusual_movement",
            "rapid_movement": "notify_unusual_movement",
            "abandoned_object": "notify_abandoned_object",
        }.get(event_type)
        if event_preference and not getattr(preferences, event_preference, False):
            user_email_enabled = False

    cam_id = getattr(alert, "camera_id", None)
    cam_cfg = get_camera_surveillance_config(cam_id) if cam_id else {}
    configured_cam_recipients = normalize_recipients(
        camera_recipients if camera_recipients is not None else cam_cfg.get("notification_recipients")
    )

    recipients = []
    seen = set()
    if user_email_enabled:
        user = User.objects.filter(id=user_id, is_active=True).only("email").first()
        if user and user.email and user.email.lower() not in seen:
            seen.add(user.email.lower())
            recipients.append(user.email)

    # Include camera-specific recipients if enabled or explicitly configured on restricted-entry camera
    if configured_cam_recipients and (user_email_enabled or force_restricted_recipients or cam_cfg.get("restricted_entry_enabled")):
        for rec in configured_cam_recipients:
            if rec.lower() not in seen:
                seen.add(rec.lower())
                recipients.append(rec)

    if not recipients:
        return False

    cam_obj = getattr(alert, "camera", None)
    cam_name = getattr(cam_obj, "name", None) or (f"Camera #{cam_id}" if cam_id else "System")
    cam_location = getattr(cam_obj, "location", None) or getattr(alert, "location", None) or "Monitored Area"
    detected_str = ""
    if getattr(alert, "detected_at", None):
        try:
            detected_str = alert.detected_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            detected_str = str(alert.detected_at)

    title = escape(alert.title or "Security event")
    safe_cam = escape(str(cam_name))
    safe_loc = escape(str(cam_location))
    message = escape(alert.message or "A security event requires review.")
    event_id_str = escape(str(getattr(alert, "id", "")))
    subject = f"DeepVision {severity.upper()} security alert"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#222;line-height:1.6">
      <h2>DeepVision security alert</h2><p><strong>{escape(severity.upper())}</strong>: {title}</p>
      <p>{message}</p>
      <p>Camera: {safe_cam} ({safe_loc}) · Event #{event_id_str}{(' · ' + escape(detected_str)) if detected_str else ''}</p>
      <p>Sign in to DeepVision to review this event and its evidence.</p>
    </body></html>"""

    any_sent = False
    for target_email in recipients:
        if _send_email_tracked(
            target_email,
            subject,
            body,
            category="security_alert",
            user_id=user_id,
            camera_id=cam_id,
            alert_id=getattr(alert, "id", None),
            severity=severity,
            max_attempts=3,
            async_retries=True,
        ):
            any_sent = True
    return any_sent


def send_camera_offline_email(camera_id, reason="Camera stream disconnected or unreachable", cooldown_seconds=300):
    """
    Sends deduplicated camera-offline alert emails to the camera owner (if notify_system_events
    and enabled are active) and configured per-camera notification_recipients.
    """
    import time
    from apps.accounts.models import User
    from apps.cameras.models import Camera
    from apps.cameras.surveillance_config import get_camera_surveillance_config, normalize_recipients
    from apps.notifications.models import NotificationPreference

    cam = Camera.objects.filter(id=camera_id, is_active=True).first()
    if not cam:
        return False

    # Process-local cooldown to suppress repeated camera-offline notifications during flapping
    now_ts = time.time()
    cache = getattr(send_camera_offline_email, "_cooldown_cache", None)
    if cache is None:
        cache = {}
        setattr(send_camera_offline_email, "_cooldown_cache", cache)
    last_sent = cache.get(int(camera_id))
    if last_sent is not None and (now_ts - last_sent) < float(cooldown_seconds):
        return False

    preferences = NotificationPreference.objects.filter(user_id=cam.user_id).first()
    user_email_enabled = True
    if preferences and (not preferences.enabled or not getattr(preferences, "notify_system_events", True)):
        user_email_enabled = False

    cam_cfg = get_camera_surveillance_config(camera_id)
    cam_recipients = normalize_recipients(cam_cfg.get("notification_recipients"))

    recipients = []
    seen = set()
    if user_email_enabled:
        owner = User.objects.filter(id=cam.user_id, is_active=True).only("email").first()
        if owner and owner.email and owner.email.lower() not in seen:
            seen.add(owner.email.lower())
            recipients.append(owner.email)
    for rec in cam_recipients:
        if rec.lower() not in seen:
            seen.add(rec.lower())
            recipients.append(rec)

    if not recipients:
        return False

    cache[int(camera_id)] = now_ts
    safe_name = escape(cam.name or f"Camera #{cam.id}")
    safe_loc = escape(cam.location or "Default Zone")
    safe_reason = escape(str(reason or "Stream unreachable"))
    subject = f"DeepVision Camera Offline Alert — {cam.name or f'Camera #{cam.id}'}"
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#222;line-height:1.6">
      <h2 style="color:#b42318">DeepVision Camera Offline</h2>
      <p><strong>Camera:</strong> {safe_name} ({safe_loc})</p>
      <p><strong>Status:</strong> Unexpectedly Offline</p>
      <p><strong>Detail:</strong> {safe_reason}</p>
      <p>Check camera connectivity or reconnect from the DeepVision Camera Management workspace.</p>
    </body></html>"""

    any_sent = False
    for target_email in recipients:
        if _send_email_tracked(
            target_email,
            subject,
            body,
            category="camera_offline",
            user_id=cam.user_id,
            camera_id=cam.id,
            severity="high",
            max_attempts=3,
            async_retries=True,
        ):
            any_sent = True
    return any_sent
