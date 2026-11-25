"""
Custom authentication decorators for DeepVision views.
"""
from functools import wraps
from urllib.parse import urlencode, urlsplit
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def _safe_next_path(request) -> str:
    raw_next = str(request.get_full_path() or "/")
    parsed = urlsplit(raw_next)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or not url_has_allowed_host_and_scheme(
            raw_next,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return "/"
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def login_required(view_func):
    """
    Decorator for views that checks that the user is logged in,
    redirecting to the log-in page if necessary.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            if (
                request.path.startswith('/api/') or
                '/stream' in request.path or
                '/snapshot' in request.path or
                '/view' in request.path or
                request.headers.get('Accept') == 'application/json' or
                request.content_type == 'application/json'
            ):
                from django.http import JsonResponse
                return JsonResponse({"error": "Authentication required", "success": False, "authenticated": False}, status=401)
            login_url = reverse('login')
            safe_next = _safe_next_path(request)
            return redirect(f"{login_url}?{urlencode({'next': safe_next})}")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
