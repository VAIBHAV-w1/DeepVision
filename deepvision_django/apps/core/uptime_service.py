"""
DeepVision Secure Website Uptime & Availability Service.

Provides:
  - Strict HTTPS-only, SSRF-guarded owned-host target validation.
  - Durable, bounded uptime & state-transition log (instance/uptime_monitor_history.json).
  - Constant-time HMAC-SHA256 webhook ingestion from external scheduled monitors
    (e.g. GitHub Actions `.github/workflows/uptime-monitor.yml`).
  - Admin-initiated live probes for allowlisted targets ONLY.
  - Transition-based logging (zero alert spam on repeated unchanged checks).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_UPTIME_LOCK = threading.Lock()
_MAX_HISTORY_RECORDS = 150
_MAX_TRANSITIONS = 100
_UPTIME_CHECKPOINT_ACTION = "UPTIME_STATE_CHECKPOINT"
_UPTIME_CHECKPOINT_RESOURCE = "uptime_state"
_UPTIME_CHECKPOINT_ID = "global"
_UPTIME_TRANSITION_ACTION = "UPTIME_TRANSITION"
_UPTIME_TRANSITION_RESOURCE = "uptime_monitor"

DEFAULT_ALLOWED_UPTIME_HOSTS = frozenset({
    "vsw-deepvision.vercel.app",
    "deepvision-6ie7.onrender.com",
    "deepvision-soc.vercel.app",
    "deepvision-backend.onrender.com",
    "vsw-deepvision.com",
    "www.vsw-deepvision.com",
})

DEFAULT_MONITORED_TARGETS = [
    {
        "id": "frontend_vercel",
        "name": "DeepVision Frontend (Vercel)",
        "url": "https://vsw-deepvision.vercel.app/",
        "expected_kind": "html",
    },
    {
        "id": "backend_live_render",
        "name": "DeepVision Backend Liveness (Render)",
        "url": "https://deepvision-6ie7.onrender.com/api/health/live/",
        "expected_kind": "json_live",
    },
    {
        "id": "backend_ready_render",
        "name": "DeepVision Backend Readiness & DB (Render)",
        "url": "https://deepvision-6ie7.onrender.com/api/health/",
        "expected_kind": "json_health",
    },
]

HOSTING_TIER_DISCLOSURE = (
    "Uptime checks run independently via scheduled HTTPS probes every 15 minutes. "
    "Note: Free/starter Render instances spin down after idle periods; the external probe wakes "
    "and measures real cold/warm response latency accurately, without simulating user activity."
)


def _get_store_path() -> str:
    override = (os.getenv("DEEPVISION_UPTIME_STORE_PATH") or "").strip()
    if override:
        os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "uptime_monitor_history.json")


def _allowed_hosts() -> frozenset:
    extra = (os.getenv("DEEPVISION_UPTIME_ALLOWED_HOSTS") or "").strip()
    if not extra:
        return DEFAULT_ALLOWED_UPTIME_HOSTS
    hosts = {h.strip().lower() for h in extra.split(",") if h.strip()}
    return frozenset(DEFAULT_ALLOWED_UPTIME_HOSTS | hosts)


def _is_public_global_ip(ip_obj) -> bool:
    mapped = getattr(ip_obj, "ipv4_mapped", None)
    cand = mapped if mapped is not None else ip_obj
    if (
        cand.is_private
        or cand.is_loopback
        or cand.is_link_local
        or cand.is_multicast
        or cand.is_reserved
        or cand.is_unspecified
    ):
        return False
    return bool(cand.is_global)


def validate_uptime_target_url(raw_url: str, resolve_dns: bool = True) -> str:
    """
    Strictly validates external uptime probe targets:
      - HTTPS scheme ONLY
      - Non-empty hostname in the owned-host allowlist
      - Rejects credentials in URL
      - Rejects private/loopback/link-local/metadata/multicast IPs and DNS SSRF aliases
    """
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("Uptime target URL cannot be empty.")
    cleaned = raw_url.strip()
    parsed = urllib.parse.urlsplit(cleaned)
    if (parsed.scheme or "").lower() != "https":
        raise ValueError("Security Error: Uptime monitoring permits HTTPS targets only.")
    if parsed.username or parsed.password:
        raise ValueError("Security Error: Embedded credentials are prohibited in uptime URLs.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Security Error: Target hostname is missing.")
    if host not in _allowed_hosts():
        raise ValueError(f"Security Error: Host '{host}' is not in the owned-domain uptime allowlist.")

    try:
        ip_obj = ipaddress.ip_address(host)
        if not _is_public_global_ip(ip_obj):
            raise ValueError(f"Security Error: Non-public IP literal '{host}' blocked by SSRF guard.")
        return cleaned
    except ValueError as exc:
        if "Security Error" in str(exc):
            raise

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as gerr:
            raise ValueError(f"DNS resolution failed for '{host}': {gerr}") from gerr
        if not infos:
            raise ValueError(f"No DNS records resolved for '{host}'.")
        for info in infos:
            sockaddr = info[4]
            if sockaddr and sockaddr[0]:
                ip_str = str(sockaddr[0]).split("%", 1)[0]
                ip_obj = ipaddress.ip_address(ip_str)
                if not _is_public_global_ip(ip_obj):
                    raise ValueError(f"Security Error: Target '{host}' resolved to prohibited IP '{ip_str}'.")

    return cleaned


class _StrictUptimeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirects = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        next_url = urllib.parse.urljoin(req.full_url, str(newurl))
        validate_uptime_target_url(next_url, resolve_dns=True)
        return super().redirect_request(req, fp, code, msg, headers, next_url)


def _empty_store() -> Dict[str, Any]:
    return {"targets": {}, "history": [], "transitions": []}


def _normalize_store(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        return {
            "targets": dict(data.get("targets") or {}),
            "history": list(data.get("history") or [])[-_MAX_HISTORY_RECORDS:],
            "transitions": list(data.get("transitions") or [])[-_MAX_TRANSITIONS:],
        }
    return _empty_store()


def _db_backend_label() -> str:
    try:
        from django.db import connection
        vendor = str(getattr(connection, "vendor", "") or "").lower()
        if vendor == "postgresql":
            return "postgresql"
        if vendor:
            return vendor
    except Exception:
        pass
    return "ephemeral_json_fallback"


def _load_transitions_from_audit_rows() -> List[Dict[str, Any]]:
    from apps.core.models import AuditLog

    rows = (
        AuditLog.objects.filter(
            action=_UPTIME_TRANSITION_ACTION,
            resource_type=_UPTIME_TRANSITION_RESOURCE,
        )
        .order_by("created_at", "id")[:_MAX_TRANSITIONS]
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            parsed = json.loads(row.description or "{}")
            if isinstance(parsed, dict) and parsed.get("target_id"):
                out.append(parsed)
        except Exception:
            continue
    return out


def _load_store_from_db(for_update: bool = False) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Loads authoritative uptime state from database (`audit_logs` checkpoint row).
    Returns `(store_dict, db_available)`. If checkpoint row doesn't exist yet, reconstructs
    any prior `UPTIME_TRANSITION` rows safely or returns empty store.
    """
    try:
        from apps.core.models import AuditLog

        qs = AuditLog.objects.filter(
            action=_UPTIME_CHECKPOINT_ACTION,
            resource_type=_UPTIME_CHECKPOINT_RESOURCE,
            resource_id=_UPTIME_CHECKPOINT_ID,
        ).order_by("-id")
        if for_update and _db_backend_label() == "postgresql":
            qs = qs.select_for_update()
        rows = list(qs[:1])
        if rows:
            raw = rows[0].description or "{}"
            store = _normalize_store(json.loads(raw))
            if not store["transitions"]:
                recovered = _load_transitions_from_audit_rows()
                if recovered:
                    store["transitions"] = recovered[-_MAX_TRANSITIONS:]
            return store, True

        recovered = _load_transitions_from_audit_rows()
        store = _empty_store()
        store["transitions"] = recovered[-_MAX_TRANSITIONS:]
        return store, True
    except Exception as exc:
        logger.warning("[UPTIME_DB_LOAD_FALLBACK] %s", exc)
        return None, False


def _save_store_to_db(store: Dict[str, Any], new_transitions: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Persists bounded uptime checkpoint and immutable status transitions into PostgreSQL/SQLite."""
    try:
        from django.utils import timezone as dj_tz
        from apps.core.models import AuditLog

        now_dt = dj_tz.now()
        payload = _normalize_store(store)
        serialized = json.dumps(payload, separators=(",", ":"))

        existing = list(
            AuditLog.objects.filter(
                action=_UPTIME_CHECKPOINT_ACTION,
                resource_type=_UPTIME_CHECKPOINT_RESOURCE,
                resource_id=_UPTIME_CHECKPOINT_ID,
            )
            .order_by("-id")[:1]
        )
        if existing:
            row = existing[0]
            row.description = serialized
            row.created_at = now_dt
            row.save(update_fields=["description", "created_at"])
        else:
            AuditLog.objects.create(
                user_id=None,
                action=_UPTIME_CHECKPOINT_ACTION,
                resource_type=_UPTIME_CHECKPOINT_RESOURCE,
                resource_id=_UPTIME_CHECKPOINT_ID,
                description=serialized,
                created_at=now_dt,
            )

        for tr in new_transitions or []:
            tr_ts = now_dt
            raw_changed = tr.get("changed_at")
            if isinstance(raw_changed, str) and raw_changed.strip():
                try:
                    tr_ts = datetime.fromisoformat(raw_changed.replace("Z", "+00:00"))
                except Exception:
                    tr_ts = now_dt
            AuditLog.objects.create(
                user_id=None,
                action=_UPTIME_TRANSITION_ACTION,
                resource_type=_UPTIME_TRANSITION_RESOURCE,
                resource_id=str(tr.get("target_id") or "")[:100],
                description=json.dumps(tr, separators=(",", ":"))[:4000],
                created_at=tr_ts,
            )
        return True
    except Exception as exc:
        logger.warning("[UPTIME_DB_SAVE_FALLBACK] %s", exc)
        return False


def _load_json_store() -> Dict[str, Any]:
    path = _get_store_path()
    if not os.path.exists(path):
        return _empty_store()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _normalize_store(json.load(fh))
    except Exception:
        pass
    return _empty_store()


def _save_json_store(data: Dict[str, Any]) -> None:
    path = _get_store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    normalized = _normalize_store(data)
    tmp = f"{path}.tmp.{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(normalized, fh, indent=2)
    os.replace(tmp, path)


def _load_store(for_update: bool = False) -> Tuple[Dict[str, Any], str]:
    db_store, db_ok = _load_store_from_db(for_update=for_update)
    if db_ok and db_store is not None:
        return db_store, _db_backend_label()
    return _load_json_store(), "ephemeral_json_fallback"


def _save_store(data: Dict[str, Any], new_transitions: Optional[List[Dict[str, Any]]] = None) -> str:
    if _save_store_to_db(data, new_transitions=new_transitions):
        if (os.getenv("DEEPVISION_UPTIME_STORE_PATH") or "").strip():
            try:
                _save_json_store(data)
            except Exception:
                pass
        return _db_backend_label()
    _save_json_store(data)
    return "ephemeral_json_fallback"


def record_uptime_results(results: List[Dict[str, Any]], source: str = "external_monitor") -> Dict[str, Any]:
    """
    Records normalized check results (`target_id`, `name`, `url`, `status`: up|degraded|down,
    `http_status`, `latency_ms`, `checked_at`, `detail`), tracks consecutive failures & outage duration,
    and logs ONLY state transitions.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    recorded_transitions: List[Dict[str, Any]] = []
    persistence_backend = "ephemeral_json_fallback"

    from django.db import transaction

    with _UPTIME_LOCK:
        with transaction.atomic():
            store, _ = _load_store(for_update=True)
            targets_map = store["targets"]

            for item in results:
                tid = str(item.get("target_id") or item.get("id") or "").strip()[:64]
                url = validate_uptime_target_url(str(item.get("url") or ""), resolve_dns=False)
                if not tid:
                    tid = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
                status = str(item.get("status") or "down").strip().lower()
                if status not in ("up", "degraded", "down"):
                    status = "down"
                checked_at = str(item.get("checked_at") or now_iso)
                latency_ms = round(max(0.0, float(item.get("latency_ms") or 0.0)), 1)
                http_status = int(item.get("http_status") or 0)
                detail = str(item.get("detail") or "")[:200]
                name = str(item.get("name") or tid)[:120]

                prev = dict(targets_map.get(tid) or {})
                prev_status = prev.get("current_status")
                total_checks = int(prev.get("total_checks") or 0) + 1
                up_checks = int(prev.get("up_checks") or 0) + (1 if status in ("up", "degraded") else 0)
                consec_fail = 0 if status in ("up", "degraded") else (int(prev.get("consecutive_failures") or 0) + 1)

                outage_started_at = prev.get("outage_started_at")
                last_outage_dur = prev.get("last_outage_duration_seconds")
                if status == "down":
                    if not outage_started_at:
                        outage_started_at = checked_at
                else:
                    if outage_started_at:
                        try:
                            t_start = datetime.fromisoformat(outage_started_at.replace("Z", "+00:00"))
                            t_end = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                            last_outage_dur = round(max(0.0, (t_end - t_start).total_seconds()), 1)
                        except Exception:
                            last_outage_dur = prev.get("last_outage_duration_seconds")
                        outage_started_at = None

                current_outage_dur = 0.0
                if outage_started_at:
                    try:
                        t_start = datetime.fromisoformat(outage_started_at.replace("Z", "+00:00"))
                        t_now = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
                        current_outage_dur = round(max(0.0, (t_now - t_start).total_seconds()), 1)
                    except Exception:
                        current_outage_dur = 0.0

                if prev_status and prev_status != status:
                    transition = {
                        "target_id": tid,
                        "name": name,
                        "from_status": prev_status,
                        "to_status": status,
                        "changed_at": checked_at,
                        "http_status": http_status,
                        "latency_ms": latency_ms,
                        "outage_duration_seconds": last_outage_dur if status != "down" else current_outage_dur,
                        "source": source,
                    }
                    store["transitions"].append(transition)
                    recorded_transitions.append(transition)
                    logger.warning(
                        f"[UPTIME_TRANSITION] target={tid} {prev_status}->{status} "
                        f"http={http_status} latency={latency_ms}ms source={source}"
                    )

                targets_map[tid] = {
                    "target_id": tid,
                    "name": name,
                    "url": url,
                    "current_status": status,
                    "last_checked_at": checked_at,
                    "last_latency_ms": latency_ms,
                    "last_http_status": http_status,
                    "detail": detail,
                    "consecutive_failures": consec_fail,
                    "outage_started_at": outage_started_at,
                    "current_outage_duration_seconds": current_outage_dur,
                    "last_outage_duration_seconds": last_outage_dur,
                    "total_checks": total_checks,
                    "up_checks": up_checks,
                    "availability_pct": round((up_checks / total_checks) * 100.0, 2) if total_checks else 0.0,
                    "source": source,
                }

                store["history"].append({
                    "target_id": tid,
                    "status": status,
                    "http_status": http_status,
                    "latency_ms": latency_ms,
                    "checked_at": checked_at,
                    "source": source,
                })

            persistence_backend = _save_store(store, new_transitions=recorded_transitions)

    return {
        "recorded": len(results),
        "transitions": recorded_transitions,
        "persistence_backend": persistence_backend,
    }


def probe_allowlisted_targets(timeout_seconds: float = 10.0, max_retries: int = 2) -> List[Dict[str, Any]]:
    """
    Runs bounded HTTPS probes strictly against the owned allowlisted DeepVision endpoints.
    Uses TLS verification and SSRF-validated redirects cleanly.
    """
    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _StrictUptimeRedirectHandler(),
        urllib.request.HTTPSHandler(context=ctx),
    )

    out: List[Dict[str, Any]] = []
    for target in DEFAULT_MONITORED_TARGETS:
        url = validate_uptime_target_url(target["url"], resolve_dns=True)
        expected_kind = target["expected_kind"]
        final_status = "down"
        http_code = 0
        latency_ms = 0.0
        detail = ""

        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "DeepVision-UptimeMonitor/1.0", "Accept": "application/json,text/html,*/*"},
                )
                with opener.open(req, timeout=timeout_seconds) as resp:
                    http_code = int(getattr(resp, "status", 200))
                    body = resp.read(65536).decode("utf-8", errors="replace")
                    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)

                if expected_kind == "json_health":
                    parsed = json.loads(body)
                    app_st = str(parsed.get("status") or "").lower()
                    if http_code == 200 and app_st == "healthy":
                        final_status = "up"
                    elif http_code == 200 and app_st == "degraded":
                        final_status = "degraded"
                    else:
                        final_status = "down"
                    detail = str(parsed.get("diagnostic") or f"status={app_st}")[:160]
                elif expected_kind == "json_live":
                    parsed = json.loads(body)
                    final_status = "up" if (http_code == 200 and str(parsed.get("status")).lower() == "alive") else "degraded"
                    detail = f"django_app={parsed.get('django_app', 'unknown')}"
                else:
                    final_status = "up" if (200 <= http_code < 400 and ("DeepVision" in body or "<html" in body.lower())) else "degraded"
                    detail = f"HTTP {http_code}"
                break
            except urllib.error.HTTPError as he:
                http_code = int(he.code)
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                detail = f"HTTP {he.code}"
                if http_code < 500 or attempt >= max_retries:
                    break
            except Exception as exc:
                logger.warning("[UPTIME_PROBE_ERROR] url=%s err=%s", url, exc)
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                detail = "Probe connection or TLS check failed"
                if attempt >= max_retries:
                    break
            time.sleep(min(4.0, 1.5 * (attempt + 1)))

        out.append({
            "target_id": target["id"],
            "name": target["name"],
            "url": url,
            "status": final_status,
            "http_status": http_code,
            "latency_ms": latency_ms,
            "detail": detail,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def verify_ingest_hmac(raw_body: bytes, signature_header: str, timestamp_header: str) -> Tuple[bool, str]:
    """Verifies constant-time HMAC-SHA256 webhook signature (`sha256=<hex>`) within +/-300s."""
    secret = (os.getenv("UPTIME_INGEST_SECRET") or "").strip()
    if not secret:
        return False, "UPTIME_INGEST_SECRET is not configured on this server."
    if not signature_header or not timestamp_header:
        return False, "Missing signature or timestamp header."
    try:
        ts_val = int(timestamp_header.strip())
    except ValueError:
        return False, "Invalid timestamp header."
    if abs(int(time.time()) - ts_val) > 300:
        return False, "Stale webhook timestamp."

    msg = timestamp_header.strip().encode("utf-8") + b"." + (raw_body or b"")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header.strip()):
        return False, "Invalid HMAC signature."
    return True, "ok"


def get_uptime_status_summary() -> Dict[str, Any]:
    """Returns read-only uptime status summary from PostgreSQL/SQLite persistence."""
    with _UPTIME_LOCK:
        store, persistence_backend = _load_store(for_update=False)

    targets_out: List[Dict[str, Any]] = []
    targets_map = store.get("targets", {})
    for base in DEFAULT_MONITORED_TARGETS:
        saved = targets_map.get(base["id"])
        if saved:
            targets_out.append(saved)
        else:
            targets_out.append({
                "target_id": base["id"],
                "name": base["name"],
                "url": base["url"],
                "current_status": "not_yet_checked",
                "last_checked_at": None,
                "last_latency_ms": None,
                "last_http_status": None,
                "detail": "Awaiting first external scheduled probe or manual admin check.",
                "consecutive_failures": 0,
                "current_outage_duration_seconds": 0.0,
                "last_outage_duration_seconds": None,
                "total_checks": 0,
                "up_checks": 0,
                "availability_pct": None,
                "source": "uninitialized",
            })

    return {
        "targets": targets_out,
        "transitions": list(reversed(store.get("transitions", [])))[:25],
        "recent_checks_count": len(store.get("history", [])),
        "persistence_backend": persistence_backend,
        "external_workflow": ".github/workflows/uptime-monitor.yml",
        "tier_disclosure": HOSTING_TIER_DISCLOSURE,
    }
