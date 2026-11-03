"""Django-backed email delivery for authentication and security alerts."""
import logging
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _send_email(recipient_email, subject, html_content):
    """Send through Django's configured backend and report actual delivery."""
    if not all((settings.EMAIL_HOST, settings.EMAIL_HOST_USER,
                settings.EMAIL_HOST_PASSWORD, settings.DEFAULT_FROM_EMAIL)):
        logger.warning("Email delivery skipped: SMTP configuration is incomplete.")
        return False

    try:
        connection = get_connection(
            fail_silently=False,
            timeout=getattr(settings, "EMAIL_TIMEOUT", 8),
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
            return False
        logger.info("Email delivered via configured backend (type=%s).", subject)
        return True
    except Exception:
        # SMTP exceptions can contain provider details; keep credentials and
        # recipient data out of logs and let callers report a generic failure.
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
