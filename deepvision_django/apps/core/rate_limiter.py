"""
DeepVision Security Rate Limiter.
Shared, backend-enforced rate limiter supporting serverless Vercel (Supabase PostgreSQL)
and containerized edge deployments (SQLite) without extra paid third-party infrastructure.
"""

import random
import logging
import datetime
from functools import wraps
from typing import Tuple, Optional
from django.utils import timezone
from django.http import JsonResponse

from apps.core.models import AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Extracts client IP address respecting reverse proxies and CDNs."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def check_rate_limit(request, scope: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
    """
    Checks if client has exceeded the request threshold within the time window.
    Returns (is_limited, retry_after_seconds).
    """
    ip = get_client_ip(request)
    now = timezone.now()
    window_start = now - datetime.timedelta(seconds=window_seconds)
    action_key = f"rate_limit:{scope}"

    try:
        # Periodic cleanup of rate limit logs older than 1 hour (5% sampling rate)
        if random.random() < 0.05:
            prune_threshold = now - datetime.timedelta(hours=1)
            AuditLog.objects.filter(action__startswith="rate_limit:", created_at__lt=prune_threshold).delete()

        # Query existing attempts in current window
        attempts = AuditLog.objects.filter(
            action=action_key,
            ip_address=ip,
            created_at__gte=window_start
        ).order_by("created_at")

        count = attempts.count()
        if count >= limit:
            oldest = attempts.first()
            if oldest and oldest.created_at:
                elapsed = (now - oldest.created_at).total_seconds()
                retry_after = max(1, int(window_seconds - elapsed))
            else:
                retry_after = window_seconds
            logger.warning(f"[RATE_LIMIT_BLOCKED] scope={scope} ip={ip} attempts={count}/{limit} retry_after={retry_after}s")
            return True, retry_after

        # Record this attempt
        user_id = None
        if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
            user_id = request.user.id
        elif "pending_login_user_id" in getattr(request, "session", {}):
            user_id = request.session.get("pending_login_user_id")

        AuditLog.objects.create(
            user_id=user_id,
            action=action_key,
            resource_type="rate_limit",
            resource_id=scope,
            description=f"Rate limit counter for {scope}",
            ip_address=ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
            created_at=now,
        )
        return False, 0
    except Exception as e:
        logger.warning(f"[RATE_LIMIT_EXCEPTION] {e} - failing open to preserve availability")
        return False, 0


def ratelimit(scope: str, limit: int = 10, window: int = 60):
    """
    Decorator enforcing rate limits on Django API endpoints.
    Returns HTTP 429 Too Many Requests with Retry-After header when exceeded.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            is_limited, retry_after = check_rate_limit(request, scope, limit, window)
            if is_limited:
                resp = JsonResponse({
                    "success": False,
                    "error": f"Too many requests for {scope}. Please wait {retry_after} seconds before trying again.",
                    "retry_after": retry_after,
                    "scope": scope,
                }, status=429)
                resp["Retry-After"] = str(retry_after)
                return resp
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
