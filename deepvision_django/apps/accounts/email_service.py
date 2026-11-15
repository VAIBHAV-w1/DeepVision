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
    """Send through Django's configured backend (or HTTPS API fallback) and report actual provider acceptance."""
    if not all((settings.EMAIL_HOST, settings.EMAIL_HOST_USER,
                settings.EMAIL_HOST_PASSWORD, settings.DEFAULT_FROM_EMAIL)):
        if _send_via_http_api(recipient_email, subject, html_content):
            return True
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
    return _send_email(recipient_email, "DeepVision - Email Verification", body)


def send_password_reset_email(recipient_email, otp, full_name=None):
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    body = _otp_email(
        greeting,
        "Use this code to continue resetting your DeepVision password:",
        otp,
        accent="#b42318",
    )
    return _send_email(recipient_email, "DeepVision - Password Reset Verification", body)


def send_login_otp_email(recipient_email, otp, full_name=None):
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    body = _otp_email(greeting, "Use this code to complete your DeepVision sign-in:", otp)
    return _send_email(recipient_email, "DeepVision - Sign-In Verification Code", body)


def send_security_alert_email(user_id, alert):
    """Email opted-in high/critical events using existing notification preferences."""
    from apps.accounts.models import User
    from apps.notifications.models import NotificationPreference

    severity = (alert.severity or "").lower()
    if severity not in {"high", "critical"}:
        return False

    preferences = NotificationPreference.objects.filter(user_id=user_id).first()
    if preferences:
        if not preferences.enabled or not getattr(preferences, f"notify_{severity}", False):
            return False
        event_type = (alert.event_type or "").lower()
        event_preference = {
            "loitering": "notify_loitering",
            "restricted_area_entry": "notify_restricted_entry",
            "intrusion": "notify_restricted_entry",
            "unusual_movement": "notify_unusual_movement",
            "rapid_movement": "notify_unusual_movement",
            "abandoned_object": "notify_abandoned_object",
        }.get(event_type)
        if event_preference and not getattr(preferences, event_preference, False):
            return False

    user = User.objects.filter(id=user_id, is_active=True).only("email").first()
    if not user or not user.email:
        return False

    title = escape(alert.title or "Security event")
    camera_id = escape(str(alert.camera_id or "System"))
    message = escape(alert.message or "A security event requires review.")
    body = f"""<html><body style="font-family:Arial,sans-serif;color:#222;line-height:1.6">
      <h2>DeepVision security alert</h2><p><strong>{escape(severity.upper())}</strong>: {title}</p>
      <p>{message}</p><p>Camera: {camera_id} · Event #{escape(str(alert.id))}</p>
      <p>Sign in to DeepVision to review this event and its evidence.</p>
    </body></html>"""
    return _send_email(user.email, f"DeepVision {severity.upper()} security alert", body)
