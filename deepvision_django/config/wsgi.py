import os
import sys
from pathlib import Path
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


class _HardenedStaticFilesHandler(StaticFilesHandler):
    """Wraps Django's StaticFilesHandler to ensure static assets also carry transport & MIME security headers."""

    def get_response(self, request):
        response = super().get_response(request)
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=(), payment=(), usb=()')
        response.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        if not settings.DEBUG and (request.is_secure() or os.getenv('RENDER') or os.getenv('VERCEL')):
            response.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
        return response


# Wrap WSGI application with _HardenedStaticFilesHandler to ensure React SPA static assets
# are served reliably and securely when DEBUG=False under Gunicorn/Waitress.
application = _HardenedStaticFilesHandler(get_wsgi_application())
