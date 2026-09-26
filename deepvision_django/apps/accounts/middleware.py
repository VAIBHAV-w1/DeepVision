"""
Authentication Middleware for DeepVision Django.
Reads session user_id and sets request.user.
"""
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
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user = User.objects.filter(id=user_id, is_active=True).first()
                request.user = user if user else AnonymousUser()
            except Exception:
                request.user = AnonymousUser()
        else:
            request.user = AnonymousUser()

        return self.get_response(request)
