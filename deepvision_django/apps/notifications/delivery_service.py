"""
Schema-Safe Notification & Email Delivery Log and Retry Tracker.

Records durable delivery state (`pending`, `retry_scheduled`, `sent`, `failed`, `skipped`),
attempt counts, safe error codes, timestamps, and idempotency keys in a bounded JSON
store (`instance/notification_delivery_log.json`) without modifying the locked SQLite schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DELIVERY_LOCK = threading.Lock()
_MAX_LOG_ENTRIES = 1000


def _get_log_path() -> str:
    override = os.getenv("DEEPVISION_NOTIFICATION_LOG_PATH")
    if override:
        os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
        return override
    try:
        from django.conf import settings
        if getattr(settings, "EMAIL_BACKEND", "") == "django.core.mail.backends.locmem.EmailBackend":
            import tempfile
            return os.path.join(tempfile.gettempdir(), f"deepvision_test_notif_log_{os.getpid()}.json")
    except Exception:
        pass
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "notification_delivery_log.json")


def _mask_email(addr: str) -> str:
    raw = str(addr or "").strip()
    if "@" not in raw:
        return raw[:4] + "***" if raw else ""
    local, dom = raw.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "***" + local[-1:]
    return f"{masked_local}@{dom}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_records() -> List[Dict[str, Any]]:
    path = _get_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data["records"]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_records(records: List[Dict[str, Any]]) -> None:
    path = _get_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    trimmed = records[-_MAX_LOG_ENTRIES:]
    tmp_path = f"{path}.tmp.{threading.get_ident()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"records": trimmed}, f, indent=2)
    os.replace(tmp_path, path)


def build_idempotency_key(category: str, recipient: str, alert_id: Optional[int] = None, extra: Optional[str] = None) -> str:
    rec_norm = str(recipient or "").strip().lower()
    if alert_id is not None:
        raw = f"{category}:alert={alert_id}:{rec_norm}"
    else:
        raw = f"{category}:{extra or uuid.uuid4().hex}:{rec_norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def was_already_delivered(idempotency_key: str) -> bool:
    if not idempotency_key:
        return False
    with _DELIVERY_LOCK:
        for rec in _load_records():
            if rec.get("idempotency_key") == idempotency_key and rec.get("status") == "sent":
                return True
    return False


def create_or_update_delivery_record(
    *,
    delivery_id: Optional[str] = None,
    idempotency_key: str,
    category: str,
    recipient: str,
    subject: str,
    status: str,
    attempts: int = 1,
    max_attempts: int = 3,
    provider: Optional[str] = None,
    error_code: Optional[str] = None,
    user_id: Optional[int] = None,
    camera_id: Optional[int] = None,
    alert_id: Optional[int] = None,
    severity: Optional[str] = None,
    message_id: Optional[str] = None,
) -> str:
    now_iso = _now_iso()
    did = delivery_id or f"dlv_{uuid.uuid4().hex[:12]}"
    with _DELIVERY_LOCK:
        records = _load_records()
        target = None
        for rec in reversed(records):
            if rec.get("delivery_id") == did or (idempotency_key and rec.get("idempotency_key") == idempotency_key):
                target = rec
                break
        if target is None:
            target = {
                "delivery_id": did,
                "idempotency_key": idempotency_key,
                "category": category,
                "recipient_masked": _mask_email(recipient),
                "recipient_domain": recipient.split("@", 1)[1].lower() if "@" in str(recipient) else "",
                "subject": str(subject or "")[:120],
                "user_id": int(user_id) if user_id is not None else None,
                "camera_id": int(camera_id) if camera_id is not None else None,
                "alert_id": int(alert_id) if alert_id is not None else None,
                "severity": str(severity or "").lower() or None,
                "created_at": now_iso,
            }
            records.append(target)
        target["status"] = status
        target["attempts"] = int(attempts)
        target["max_attempts"] = int(max_attempts)
        target["provider"] = provider
        target["error_code"] = error_code
        if message_id:
            target["message_id"] = str(message_id)[:100]
        target["last_attempt_at"] = now_iso
        target["updated_at"] = now_iso
        _save_records(records)
        return str(target["delivery_id"])


def get_delivery_records(user_id: Optional[int] = None, limit: int = 30) -> Dict[str, Any]:
    with _DELIVERY_LOCK:
        records = list(reversed(_load_records()))
    if user_id is not None:
        uid = int(user_id)
        filtered = [r for r in records if r.get("user_id") in (uid, None)]
    else:
        filtered = records
    summary = {"sent": 0, "failed": 0, "retry_scheduled": 0, "pending": 0, "skipped": 0}
    for r in filtered:
        st = r.get("status", "")
        if st in summary:
            summary[st] += 1
    return {
        "summary": summary,
        "records": filtered[: max(1, min(100, int(limit or 30)))],
    }


def clear_delivery_log() -> None:
    with _DELIVERY_LOCK:
        _save_records([])
