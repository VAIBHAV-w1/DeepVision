"""
Authentication Middleware for DeepVision Django.
Reads session user_id and sets request.user.
"""
import hashlib
import hmac
from django.db import InterfaceError, OperationalError, close_old_connections
from apps.accounts.models import User


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
                    expected_fp = hashlib.sha256((user.password_hash or '').encode('utf-8')).hexdigest()[:16]
                    if not hmac.compare_digest(str(sess_fp), expected_fp):
                        request.session.flush()
                        user = None
            request.user = user if user else AnonymousUser()
        else:
            request.user = AnonymousUser()

        return self.get_response(request)
