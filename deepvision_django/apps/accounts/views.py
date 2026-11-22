"""
Authentication Compatibility Views & Validation Helpers for DeepVision Django Application.
Primary authentication flows run through CSRF-protected JSON OTP endpoints in `apps.core.api`;
this module retains shared input/password validators and routed compatibility handlers
(`verify-email/`, `resend-otp/`, `verify-success/`, `resend-reset-otp/`, `logout/`).
"""
import logging
import re
from datetime import datetime, timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from apps.accounts.models import User
from apps.accounts.email_service import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_signup_inputs(full_name, email, password, confirm_password):
    if not full_name or not full_name.strip():
        return "Full Name is required and cannot be empty."
    if not email or not email.strip():
        return "Email is required."
    email_clean = email.strip().lower()
    if not EMAIL_REGEX.match(email_clean):
        return "Please enter a valid email address."
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    if not any(not c.isalnum() and not c.isspace() for c in password):
        return "Password must contain at least one special character."
    if not confirm_password:
        return "Please confirm your password."
    if password != confirm_password:
        return "Passwords do not match."
    return None


def validate_password_strength(password):
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    if not any(not c.isalnum() and not c.isspace() for c in password):
        return "Password must contain at least one special character."
    return None


@require_http_methods(["GET", "POST"])
def verify_email_view(request):
    email = request.session.get("signup_email")
    if not email:
        messages.warning(request, "Session expired or invalid. Please sign up again.")
        return redirect("signup")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, "User not found. Please sign up again.")
        return redirect("signup")

    if user.is_email_verified:
        messages.success(request, "Your email is already verified. You can now log in.")
        return redirect("verify_success")

    if request.method == "POST":
        otp = request.POST.get("otp", "").strip()
        if not otp or len(otp) != 6 or not otp.isdigit():
            messages.error(request, "Please enter a valid 6-digit numeric verification code.")
            return render(request, "pages/auth/verify_email.html", {"email": email})

        success, error_msg = user.verify_otp(otp)
        user.save()

        if not success:
            messages.error(request, error_msg)
            return render(request, "pages/auth/verify_email.html", {"email": email})

        request.session.pop("signup_email", None)
        return redirect("verify_success")

    return render(request, "pages/auth/verify_email.html", {"email": email})


@require_http_methods(["POST"])
def resend_otp_view(request):
    email = request.session.get("signup_email")
    if not email:
        messages.warning(request, "Session expired. Please sign up again.")
        return redirect("signup")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, "User not found. Please sign up again.")
        return redirect("signup")

    now = datetime.now(timezone.utc)
    sent_at = user.email_otp_sent_at
    if sent_at:
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed = (now - sent_at).total_seconds()
        if elapsed < 60:
            remaining = 60 - int(elapsed)
            messages.warning(request, f"Please wait {remaining} seconds before requesting a new code.")
            return redirect("verify_email")

    try:
        otp = user.generate_otp()
        user.save()
        sent = send_verification_email(user.email, otp)
        if sent:
            messages.success(request, "A new verification code has been sent to your email.")
        else:
            logger.warning("[AUTH] Verification code resend failed for user_id=%s.", user.id)
            user.email_otp_sent_at = None
            user.save(update_fields=["email_otp_sent_at"])
            messages.error(request, "Failed to send verification code. Please try again later.")
    except Exception:
        logger.warning("[AUTH] Verification code resend failed for user_id=%s.", user.id)
        user.email_otp_sent_at = None
        user.save(update_fields=["email_otp_sent_at"])
        messages.error(request, "Failed to send verification code. Please try again later.")

    return redirect("verify_email")


def verify_success_view(request):
    return render(request, "pages/auth/verify_success.html")


@require_http_methods(["POST"])
def resend_reset_otp_view(request):
    email = request.session.get("reset_email")
    if not email:
        messages.warning(request, "Session expired. Please start again.")
        return redirect("forgot_password")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.success(request, "If an account exists, a new reset message will be sent when email delivery is available.")
        return redirect("reset_password")

    now = datetime.now(timezone.utc)
    sent_at = user.password_reset_otp_sent_at
    if sent_at:
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed = (now - sent_at).total_seconds()
        if elapsed < 60:
            remaining = 60 - int(elapsed)
            messages.warning(request, f"Please wait {remaining} seconds before requesting a new code.")
            return redirect("reset_password")

    try:
        otp = user.generate_reset_otp()
        user.save()
        sent = send_password_reset_email(user.email, otp)
        if sent:
            messages.success(request, "A new reset verification code has been sent to your email.")
        else:
            logger.warning("[AUTH] Password reset code resend failed for user_id=%s.", user.id)
            user.password_reset_otp_sent_at = None
            user.save(update_fields=["password_reset_otp_sent_at"])
            messages.error(request, "Failed to send reset code. Please try again later.")
    except Exception:
        logger.warning("[AUTH] Password reset code resend failed for user_id=%s.", user.id)
        user.password_reset_otp_sent_at = None
        user.save(update_fields=["password_reset_otp_sent_at"])
        messages.error(request, "Failed to send reset code. Please try again later.")

    return redirect("reset_password")


@require_http_methods(["GET", "POST"])
def logout_view(request):
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")
