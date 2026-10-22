"""
Custom authentication decorators for DeepVision views.
"""
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse


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
            next_url = request.get_full_path()
            return redirect(f"{login_url}?next={next_url}")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
