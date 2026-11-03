"""
Centralized Security Audit Logging Helper for DeepVision.
Persists structured security and operational events into the existing SQLite
'audit_logs' table (apps.core.models.AuditLog) without schema modifications.
"""

import logging
from django.utils import timezone
from apps.core.models import AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    if request is None:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        ip = xff.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "") or ""
    return ip[:45]


def log_audit(
    request,
    action: str,
    resource_type: str,
    resource_id=None,
    description: str = "",
    user=None,
):
    """
    Safely writes an AuditLog entry. Never raises exceptions into request flow.
    """
    try:
        actor = user
        if actor is None and request is not None:
            req_user = getattr(request, "user", None)
            if req_user is not None and getattr(req_user, "is_authenticated", False):
                actor = req_user

        actor_id = getattr(actor, "id", None) if actor is not None else None
        ip_addr = get_client_ip(request) or None
        ua = ((request.META.get("HTTP_USER_AGENT", "") if request is not None else "") or "")[:255] or None
        res_id_str = str(resource_id)[:100] if resource_id is not None else None

        return AuditLog.objects.create(
            user_id=actor_id,
            action=str(action)[:100],
            resource_type=str(resource_type)[:100],
            resource_id=res_id_str,
            description=str(description) if description else None,
            ip_address=ip_addr,
            user_agent=ua,
            created_at=timezone.now(),
        )
    except Exception as exc:
        logger.warning(f"[AUDIT_LOG_WARN] action={action} resource={resource_type}: {exc}")
        return None

