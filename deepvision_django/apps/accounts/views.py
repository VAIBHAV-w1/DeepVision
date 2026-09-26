"""
Authentication Views for DeepVision Django Application.
Provides:
- Login (with existing Werkzeug scrypt hash compatibility)
- Signup (validation, existing users table write, OTP dispatch)
- Email Verification (6-digit OTP, attempts limit, 60s cooldown)
- Forgot Password & Password Reset
- Logout (styled banner notification)
"""
import re
from datetime import datetime, timezone
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.http import url_has_allowed_host_and_scheme
from apps.accounts.models import User
from apps.accounts.email_service import send_verification_email, send_password_reset_email

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
def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        if not email:
            messages.error(request, "Email is required.")
            return render(request, "pages/auth/login.html", {"email": email})
        if not EMAIL_REGEX.match(email):
            messages.error(request, "Please enter a valid email address.")
            return render(request, "pages/auth/login.html", {"email": email})
        if not password:
            messages.error(request, "Password is required.")
            return render(request, "pages/auth/login.html", {"email": email})

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "Invalid email or password.")
            return render(request, "pages/auth/login.html", {"email": email})

        if not user.check_password(password):
            messages.error(request, "Invalid email or password.")
            return render(request, "pages/auth/login.html", {"email": email})

        if not user.is_email_verified:
            request.session["signup_email"] = user.email
            messages.warning(request, "Please verify your email before logging in.")
            return redirect("verify_email")

        if not user.is_active:
            messages.error(request, "Your account is currently inactive. Please contact an administrator.")
            return render(request, "pages/auth/login.html", {"email": email})

        # Session fixation protection & establish session
        request.session.flush()
        request.session["user_id"] = user.id

        next_url = request.GET.get("next") or request.POST.get("next")
        if not next_url or not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("dashboard")
        return redirect(next_url)

    return render(request, "pages/auth/login.html")


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        error_msg = validate_signup_inputs(full_name, email, password, confirm_password)
        if error_msg:
            messages.error(request, error_msg)
            return render(request, "pages/auth/signup.html", {"full_name": full_name, "email": email})

        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, "pages/auth/signup.html", {"full_name": full_name, "email": email})

        try:
            new_user = User(
                full_name=full_name,
                email=email,
                role="user",
                is_email_verified=False,
                is_active=True,
            )
            new_user.set_password(password)
            otp = new_user.generate_otp()
            new_user.save()

            try:
                send_verification_email(email, otp)
            except Exception as mail_err:
                print(f"[AUTH] Could not deliver verification email via SMTP: {mail_err}")

            request.session["signup_email"] = email
            messages.success(request, "Account created successfully. A verification code has been sent to your email.")
            return redirect("verify_email")

        except Exception as e:
            print(f"[AUTH] Registration error: {e}")
            messages.error(request, "An error occurred during account registration. Please try again.")
            return render(request, "pages/auth/signup.html", {"full_name": full_name, "email": email})

    return render(request, "pages/auth/signup.html")


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
        send_verification_email(user.email, otp)
        messages.success(request, "A new verification code has been sent to your email.")
    except Exception as e:
        print(f"[AUTH] Failed to resend OTP: {e}")
        messages.error(request, "Failed to send verification code. Please try again later.")

    return redirect("verify_email")


def verify_success_view(request):
    return render(request, "pages/auth/verify_success.html")


@require_http_methods(["GET", "POST"])
def forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email or not EMAIL_REGEX.match(email):
            messages.error(request, "Please enter a valid email address.")
            return render(request, "pages/auth/forgot_password.html", {"email": email})

        user = User.objects.filter(email=email).first()
        request.session["reset_email"] = email
        request.session["reset_otp_verified"] = False

        if user:
            try:
                otp = user.generate_reset_otp()
                user.save()
                send_password_reset_email(user.email, otp)
            except Exception as e:
                print(f"[AUTH] Forgot password setup error: {e}")

        messages.success(request, "If the account exists, a password reset code has been sent to the email address.")
        return redirect("reset_password")

    return render(request, "pages/auth/forgot_password.html")


@require_http_methods(["GET", "POST"])
def reset_password_view(request):
    email = request.session.get("reset_email")
    if not email:
        messages.warning(request, "Session expired or invalid. Please start again.")
        return redirect("forgot_password")

    user = User.objects.filter(email=email).first()

    if request.method == "POST":
        is_verified = request.session.get("reset_otp_verified", False)

        if not is_verified:
            otp = request.POST.get("otp", "").strip()
            if not otp or len(otp) != 6 or not otp.isdigit():
                messages.error(request, "Please enter a valid 6-digit numeric verification code.")
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 1})

            if not user:
                messages.error(request, "Invalid verification code.")
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 1})

            success, error_msg = user.verify_reset_otp(otp)
            user.save()

            if not success:
                messages.error(request, error_msg)
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 1})

            request.session["reset_otp_verified"] = True
            messages.success(request, "Code verified successfully. Please enter your new password.")
            return render(request, "pages/auth/reset_password.html", {"email": email, "step": 2})
        else:
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")

            policy_error = validate_password_strength(password)
            if policy_error:
                messages.error(request, policy_error)
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 2})

            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 2})

            if not user:
                messages.error(request, "User session invalid.")
                return redirect("forgot_password")

            try:
                user.set_password(password)
                user.clear_reset_otp()
                user.save()

                request.session.pop("reset_email", None)
                request.session.pop("reset_otp_verified", None)
                request.session.pop("user_id", None)

                messages.success(request, "Password reset successfully. Please log in with your new password.")
                return redirect("login")
            except Exception as e:
                print(f"[AUTH] Error during password update: {e}")
                messages.error(request, "An error occurred during password update. Please try again.")
                return render(request, "pages/auth/reset_password.html", {"email": email, "step": 2})

    step = 2 if request.session.get("reset_otp_verified", False) else 1
    return render(request, "pages/auth/reset_password.html", {"email": email, "step": step})


@require_http_methods(["POST"])
def resend_reset_otp_view(request):
    email = request.session.get("reset_email")
    if not email:
        messages.warning(request, "Session expired. Please start again.")
        return redirect("forgot_password")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.success(request, "A new reset verification code has been sent to your email.")
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
        send_password_reset_email(user.email, otp)
        messages.success(request, "A new reset verification code has been sent to your email.")
    except Exception as e:
        print(f"[AUTH] Failed to resend reset OTP: {e}")
        messages.error(request, "Failed to send reset code. Please try again later.")

    return redirect("reset_password")


@require_http_methods(["GET", "POST"])
def logout_view(request):
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")
