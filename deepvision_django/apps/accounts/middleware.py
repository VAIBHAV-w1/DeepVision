"""
Authentication Middleware for DeepVision Django.
Reads session user_id and sets request.user, plus applies baseline HTTP security headers.
"""
import hmac
from django.conf import settings
from django.db import InterfaceError, OperationalError, close_old_connections
from django.utils.crypto import salted_hmac
from apps.accounts.models import User


_PERMISSIONS_POLICY = "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
_API_FALLBACK_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none';"


def compute_session_password_fingerprint(password_hash: str) -> str:
    """Computes a server-keyed HMAC session revocation token from an already-hashed credential."""
    return salted_hmac(
        "deepvision.auth.session_pw_fp",
        str(password_hash or ""),
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()[:16]


class AnonymousUser:
    id = None
    email = ''
    full_name = 'Guest'
    role = 'guest'
    is_authenticated = False
    is_anonymous = True
    is_staff = False
    is_superuser = False

    def __str__(self):
        return 'AnonymousUser'


class AuthenticationMiddleware:
    """
    Middleware that populates request.user from signed session cookies.
    Self-heals once if a pooled PostgreSQL connection was closed upstream.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id')
        if user_id:
            user = None
            try:
                user = User.objects.filter(id=user_id, is_active=True).first()
            except (OperationalError, InterfaceError):
                try:
                    close_old_connections()
                    user = User.objects.filter(id=user_id, is_active=True).first()
                except Exception:
                    user = None
            except Exception:
                user = None

            if user is not None:
                sess_fp = request.session.get('pw_fp')
                if sess_fp is not None:
                    expected_fp = compute_session_password_fingerprint(user.password_hash)
                    if not hmac.compare_digest(str(sess_fp), expected_fp):
                        request.session.flush()
                        user = None
            request.user = user if user else AnonymousUser()
        else:
            request.user = AnonymousUser()

        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Ensures consistent security hardening headers (Permissions-Policy, COOP/CORP,
    fallback Content-Security-Policy on non-HTML routes, and no-store on /api/*) across
    all Django responses without breaking Browser Webcam or same-origin CSRF fetch.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = _API_FALLBACK_CSP
        if request.path.startswith("/api/") and "Cache-Control" not in response:
            response["Cache-Control"] = "no-store, private"
        return response
