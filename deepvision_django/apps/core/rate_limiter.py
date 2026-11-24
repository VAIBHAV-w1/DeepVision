"""
DeepVision Security Rate Limiter.
Shared, backend-enforced rate limiter supporting serverless Vercel (Supabase PostgreSQL)
and containerized edge deployments (SQLite) without extra paid third-party infrastructure.
"""

import hashlib
import ipaddress
import random
import logging
import datetime
from functools import wraps
from typing import Tuple, Optional
from django.utils import timezone
from django.http import JsonResponse

from apps.core.models import AuditLog

logger = logging.getLogger(__name__)


_INTERNAL_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_internal_proxy_ip(ip_obj) -> bool:
    if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_unspecified:
        return True
    return any(ip_obj in net for net in _INTERNAL_PROXY_NETWORKS)


def _normalize_valid_ip(candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return None
    val = str(candidate).strip()
    if not val or len(val) > 45:
        return None
    try:
        return str(ipaddress.ip_address(val))
    except ValueError:
        return None


def get_client_ip(request) -> str:
    """
    Extracts validated client IP from verified proxy infrastructure while
    rejecting spoofable non-authoritative client headers (`True-Client-IP`,
    public `X-Real-IP`, and left-most `X-Forwarded-For` entries).
    """
    import os

    running_on_render = bool(os.getenv("RENDER"))
    if running_on_render:
        # Verified live on Render Cloudflare edge: forged CF-Connecting-IP is
        # rejected (HTTP 403) and overwritten by Cloudflare edge.
        cf_ip = _normalize_valid_ip(request.META.get("HTTP_CF_CONNECTING_IP"))
        if cf_ip:
            return cf_ip

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        valid_hops = []
        for part in x_forwarded_for.split(","):
            norm = _normalize_valid_ip(part)
            if norm:
                valid_hops.append(norm)
        # Walk right-to-left skipping internal proxy hops so client-prepended headers cannot spoof rate limits.
        for norm in reversed(valid_hops):
            ip_obj = ipaddress.ip_address(norm)
            if not _is_internal_proxy_ip(ip_obj):
                return norm
        if valid_hops:
            return valid_hops[-1]

    remote = _normalize_valid_ip(request.META.get("REMOTE_ADDR"))
    if not remote or _is_internal_proxy_ip(ipaddress.ip_address(remote)):
        # Only honor X-Real-IP when originating behind an internal proxy / loopback socket
        x_real_ip = _normalize_valid_ip(request.META.get("HTTP_X_REAL_IP"))
        if x_real_ip:
            return x_real_ip
    return remote or "127.0.0.1"


def _scope_resource_key(scope: str, account_key: Optional[str] = None) -> str:
    cleaned = str(account_key or "").strip().lower()
    if not cleaned:
        return scope
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
    return f"{scope}:{digest}"


def check_rate_limit(
    request,
    scope: str,
    limit: int,
    window_seconds: int,
    account_key: Optional[str] = None,
) -> Tuple[bool, int]:
    """
    Checks if client has exceeded the request threshold within the time window.
    When ``account_key`` is supplied (e.g. login/OTP email), buckets per ``(ip, account_hash)``
    with a generous shared-proxy ceiling so users behind a shared CDN PoP (Vercel -> Render)
    never falsely lock each other out, while preserving strict per-account and IP ceilings.
    Returns (is_limited, retry_after_seconds).
    """
    ip = get_client_ip(request)
    now = timezone.now()
    window_start = now - datetime.timedelta(seconds=window_seconds)
    action_key = f"rate_limit:{scope}"
    resource_key = _scope_resource_key(scope, account_key)

    try:
        # Query existing attempts in current window with a single bounded query
        scoped_qs = AuditLog.objects.filter(
            action=action_key,
            ip_address=ip,
            created_at__gte=window_start,
        )
        if resource_key != scope:
            recent_timestamps = list(
                scoped_qs.filter(resource_id=resource_key)
                .order_by("created_at")
                .values_list("created_at", flat=True)[:limit]
            )
            ip_ceiling = max(limit * 5, 50)
            if len(recent_timestamps) < limit:
                ip_timestamps = list(
                    scoped_qs.order_by("created_at").values_list("created_at", flat=True)[:ip_ceiling]
                )
                if len(ip_timestamps) >= ip_ceiling:
                    recent_timestamps = ip_timestamps
                    limit_hit_ceiling = ip_ceiling
                else:
                    limit_hit_ceiling = limit
            else:
                limit_hit_ceiling = limit
        else:
            recent_timestamps = list(
                scoped_qs.filter(resource_id=scope)
                .order_by("created_at")
                .values_list("created_at", flat=True)[:limit]
            )
            limit_hit_ceiling = limit

        count = len(recent_timestamps)
        if count >= limit_hit_ceiling:
            oldest_created_at = recent_timestamps[0]
            if oldest_created_at:
                elapsed = (now - oldest_created_at).total_seconds()
                retry_after = max(1, int(window_seconds - elapsed))
            else:
                retry_after = window_seconds
            logger.warning(f"[RATE_LIMIT_BLOCKED] scope={scope} ip={ip} attempts={count}/{limit_hit_ceiling} retry_after={retry_after}s")
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
            resource_id=resource_key,
            description=f"Rate limit counter for {scope}",
            ip_address=ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
            created_at=now,
        )
        return False, 0
    except Exception as e:
        logger.warning(f"[RATE_LIMIT_EXCEPTION] {e} - failing open to preserve availability")
        return False, 0


def _extract_request_account_key(request, key_field: Optional[str]) -> Optional[str]:
    if not key_field:
        return None
    try:
        if hasattr(request, "POST") and request.POST.get(key_field):
            return str(request.POST.get(key_field)).strip().lower()
        body = getattr(request, "body", b"") or b""
        if body and len(body) <= 16384:
            import json
            parsed = json.loads(body.decode("utf-8", errors="ignore"))
            if isinstance(parsed, dict) and parsed.get(key_field):
                return str(parsed.get(key_field)).strip().lower()
        session = getattr(request, "session", None)
        if session and session.get("pending_login_email"):
            return str(session.get("pending_login_email")).strip().lower()
    except Exception:
        pass
    return None


def ratelimit(scope: str, limit: int = 10, window: int = 60, key_field: Optional[str] = None):
    """
    Decorator enforcing rate limits on Django API endpoints.
    Returns HTTP 429 Too Many Requests with Retry-After header when exceeded.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            account_key = _extract_request_account_key(request, key_field)
            is_limited, retry_after = check_rate_limit(
                request, scope, limit, window, account_key=account_key
            )
            if is_limited:
                resp = JsonResponse({
                    "success": False,
                    "code": "RATE_LIMITED",
                    "error": f"Too many requests for {scope}. Please wait {retry_after} seconds before trying again.",
                    "retry_after": retry_after,
                    "scope": scope,
                }, status=429)
                resp["Retry-After"] = str(retry_after)
                return resp
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
