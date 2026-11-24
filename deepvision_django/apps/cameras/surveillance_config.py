"""
Schema-Safe Surveillance Camera & Polygon Zone Configuration Store.

Persists extended per-camera restricted-entry settings (purpose, schedule,
entry direction, severity, recipients, deduplication controls) and normalized
polygon zone geometry outside the locked 18-table SQLite schema so existing
database structure and `start_deepvision.py` schema signature remain intact.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_CONFIG_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

VALID_PURPOSES = frozenset({"general", "restricted_entry"})
VALID_VIDEO_QUALITIES = frozenset({"standard", "high", "full"})
VIDEO_QUALITY_PROFILES = {
    "standard": {
        "id": "standard",
        "label": "Standard (480p)",
        "max_width": 640,
        "max_height": 480,
        "stream_jpeg_quality": 78,
        "browser_jpeg_quality": 0.78,
        "browser_max_fps": 24,
    },
    "high": {
        "id": "high",
        "label": "High HD (720p)",
        "max_width": 1280,
        "max_height": 720,
        "stream_jpeg_quality": 86,
        "browser_jpeg_quality": 0.85,
        "browser_max_fps": 30,
    },
    "full": {
        "id": "full",
        "label": "Full Resolution / Source Quality",
        "max_width": 1920,
        "max_height": 1080,
        "stream_jpeg_quality": 92,
        "browser_jpeg_quality": 0.91,
        "browser_max_fps": 30,
    },
}


def resolve_video_quality_profile(quality: Any) -> Dict[str, Any]:
    q = str(quality or "high").strip().lower()
    if q not in VIDEO_QUALITY_PROFILES:
        q = "high"
    return dict(VIDEO_QUALITY_PROFILES[q])


VALID_DIRECTIONS = frozenset({
    "any",
    "enter",
    "exit",
    "inward",
    "outward",
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
})
VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low"})


def _get_config_path() -> str:
    override = os.getenv("DEEPVISION_SURVEILLANCE_CONFIG_PATH")
    if override:
        os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
        return override
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "instance"))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "camera_surveillance_config.json")


def _load_raw_store() -> Dict[str, Any]:
    path = _get_config_path()
    if not os.path.exists(path):
        return {"cameras": {}, "zones": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"cameras": {}, "zones": {}}
        if not isinstance(data.get("cameras"), dict):
            data["cameras"] = {}
        if not isinstance(data.get("zones"), dict):
            data["zones"] = {}
        return data
    except Exception:
        return {"cameras": {}, "zones": {}}


def _save_raw_store(data: Dict[str, Any]) -> None:
    path = _get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp.{threading.get_ident()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def normalize_recipients(recipients: Any) -> List[str]:
    if recipients is None:
        return []
    if isinstance(recipients, str):
        items = [part.strip() for part in recipients.replace(";", ",").split(",")]
    elif isinstance(recipients, (list, tuple, set)):
        items = [str(part).strip() for part in recipients]
    else:
        return []
    seen = set()
    cleaned: List[str] = []
    for email in items:
        low = email.lower()
        if not email or not _EMAIL_RE.match(email) or low in seen:
            continue
        seen.add(low)
        cleaned.append(email)
    return cleaned


def default_camera_config(has_enabled_zones: bool = False) -> Dict[str, Any]:
    return {
        "purpose": "restricted_entry" if has_enabled_zones else "general",
        "restricted_entry_enabled": bool(has_enabled_zones),
        "entry_direction": "enter",
        "schedule": {
            "mode": "always",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "start_time": "00:00",
            "end_time": "23:59",
        },
        "alert_severity": "high",
        "notification_recipients": [],
        "require_alert": True,
        "suppress_duplicates": True,
        "cooldown_seconds": 30.0,
        "debounce_frames": 2,
        "video_quality": "high",
        "updated_at": None,
    }


def _sanitize_schedule(raw: Any) -> Dict[str, Any]:
    default_sched = {
        "mode": "always",
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start_time": "00:00",
        "end_time": "23:59",
    }
    if not isinstance(raw, dict):
        return default_sched
    mode = str(raw.get("mode") or "always").strip().lower()
    if mode not in ("always", "custom"):
        mode = "always"
    days_raw = raw.get("days")
    if isinstance(days_raw, list):
        days = sorted({int(d) for d in days_raw if isinstance(d, (int, float, str)) and str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            days = [0, 1, 2, 3, 4, 5, 6]
    else:
        days = [0, 1, 2, 3, 4, 5, 6]
    start_time = str(raw.get("start_time") or "00:00").strip()
    end_time = str(raw.get("end_time") or "23:59").strip()
    if not re.match(r"^\d{2}:\d{2}$", start_time):
        start_time = "00:00"
    if not re.match(r"^\d{2}:\d{2}$", end_time):
        end_time = "23:59"
    return {
        "mode": mode,
        "days": days,
        "start_time": start_time,
        "end_time": end_time,
    }


def is_schedule_active(schedule: Optional[Dict[str, Any]], now_dt: Optional[datetime] = None) -> bool:
    if not isinstance(schedule, dict) or schedule.get("mode", "always") == "always":
        return True
    now_local = now_dt or datetime.now()
    weekday = now_local.weekday()  # Monday=0 .. Sunday=6
    allowed_days = schedule.get("days") or [0, 1, 2, 3, 4, 5, 6]
    if weekday not in allowed_days:
        return False
    start_str = str(schedule.get("start_time") or "00:00")
    end_str = str(schedule.get("end_time") or "23:59")
    cur_hm = now_local.strftime("%H:%M")
    if start_str <= end_str:
        return start_str <= cur_hm <= end_str
    # Overnight window (e.g. 22:00 -> 06:00)
    return cur_hm >= start_str or cur_hm <= end_str


def get_camera_surveillance_config(camera_id: int, has_enabled_zones: bool = False) -> Dict[str, Any]:
    key = str(int(camera_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        saved = store["cameras"].get(key)
    cfg = default_camera_config(has_enabled_zones=has_enabled_zones)
    if isinstance(saved, dict):
        cfg.update(saved)
        cfg["schedule"] = _sanitize_schedule(cfg.get("schedule"))
        cfg["notification_recipients"] = normalize_recipients(cfg.get("notification_recipients"))
    return cfg


def save_camera_surveillance_config(camera_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    key = str(int(camera_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        current = default_camera_config(has_enabled_zones=False)
        existing = store["cameras"].get(key)
        if isinstance(existing, dict):
            current.update(existing)

        if "restricted_entry_enabled" in updates:
            enabled = bool(updates["restricted_entry_enabled"])
            current["restricted_entry_enabled"] = enabled
            if "purpose" not in updates:
                current["purpose"] = "restricted_entry" if enabled else "general"
        if "purpose" in updates:
            p = str(updates["purpose"] or "general").strip().lower()
            if p in VALID_PURPOSES:
                current["purpose"] = p
                if "restricted_entry_enabled" not in updates:
                    current["restricted_entry_enabled"] = (p == "restricted_entry")
        if "entry_direction" in updates:
            d = str(updates["entry_direction"] or "enter").strip().lower()
            if d in VALID_DIRECTIONS:
                current["entry_direction"] = d
        if "schedule" in updates:
            current["schedule"] = _sanitize_schedule(updates["schedule"])
        if "alert_severity" in updates:
            sev = str(updates["alert_severity"] or "high").strip().lower()
            if sev in VALID_SEVERITIES:
                current["alert_severity"] = sev
        if "notification_recipients" in updates:
            current["notification_recipients"] = normalize_recipients(updates["notification_recipients"])
        if "require_alert" in updates:
            current["require_alert"] = bool(updates["require_alert"])
        if "suppress_duplicates" in updates:
            current["suppress_duplicates"] = bool(updates["suppress_duplicates"])
        if "cooldown_seconds" in updates:
            try:
                current["cooldown_seconds"] = max(2.0, min(3600.0, float(updates["cooldown_seconds"])))
            except (TypeError, ValueError):
                pass
        if "debounce_frames" in updates:
            try:
                current["debounce_frames"] = max(1, min(15, int(updates["debounce_frames"])))
            except (TypeError, ValueError):
                pass
        if "video_quality" in updates:
            vq = str(updates["video_quality"] or "high").strip().lower()
            if vq in VALID_VIDEO_QUALITIES:
                current["video_quality"] = vq

        current["updated_at"] = datetime.utcnow().isoformat() + "Z"
        store["cameras"][key] = current
        _save_raw_store(store)
        return dict(current)


def delete_camera_surveillance_config(camera_id: int) -> None:
    key = str(int(camera_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        changed = False
        if key in store["cameras"]:
            store["cameras"].pop(key, None)
            changed = True
        for zkey, zdata in list(store["zones"].items()):
            if isinstance(zdata, dict) and str(zdata.get("camera_id")) == key:
                store["zones"].pop(zkey, None)
                changed = True
        if changed:
            _save_raw_store(store)


def _segments_intersect(a1: Tuple[float, float], a2: Tuple[float, float], b1: Tuple[float, float], b2: Tuple[float, float]) -> bool:
    def ccw(p1, p2, p3):
        return (p3[1] - p1[1]) * (p2[0] - p1[0]) - (p2[1] - p1[1]) * (p3[0] - p1[0])

    d1 = ccw(b1, b2, a1)
    d2 = ccw(b1, b2, a2)
    d3 = ccw(a1, a2, b1)
    d4 = ccw(a1, a2, b2)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def validate_normalized_polygon(raw_points: Any) -> Tuple[bool, Optional[str], List[Dict[str, float]]]:
    """
    Validates normalized (0..1) polygon points:
    - At least 3 distinct vertices
    - Every coordinate finite and within [0.0, 1.0]
    - Non-degenerate enclosed area
    - Non-self-intersecting polygon edges
    """
    if not isinstance(raw_points, (list, tuple)) or len(raw_points) < 3:
        return False, "Polygon zone requires at least 3 vertices.", []
    if len(raw_points) > 32:
        return False, "Polygon zone supports at most 32 vertices.", []

    pts: List[Dict[str, float]] = []
    for item in raw_points:
        if isinstance(item, dict):
            px, py = item.get("x"), item.get("y")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            px, py = item[0], item[1]
        else:
            return False, "Each polygon point must provide x and y coordinates.", []
        try:
            fx = float(px)
            fy = float(py)
        except (TypeError, ValueError):
            return False, "Polygon coordinates must be numeric.", []
        if not (math.isfinite(fx) and math.isfinite(fy)):
            return False, "Polygon coordinates must be finite numbers.", []
        if fx < 0.0 or fx > 1.0 or fy < 0.0 or fy > 1.0:
            return False, "Normalized polygon coordinates must be between 0.0 and 1.0.", []
        pts.append({"x": round(fx, 6), "y": round(fy, 6)})

    # Remove near-duplicate adjacent vertices
    deduped: List[Dict[str, float]] = []
    for p in pts:
        if not deduped or math.hypot(p["x"] - deduped[-1]["x"], p["y"] - deduped[-1]["y"]) > 1e-4:
            deduped.append(p)
    if len(deduped) >= 2 and math.hypot(deduped[0]["x"] - deduped[-1]["x"], deduped[0]["y"] - deduped[-1]["y"]) <= 1e-4:
        deduped.pop()
    if len(deduped) < 3:
        return False, "Polygon vertices are too close together or degenerate.", []

    # Check non-adjacent edges for self-intersection BEFORE shoelace area check
    # (symmetric bowtie polygons cancel out to zero signed area)
    n = len(deduped)
    if n >= 4:
        coords = [(p["x"], p["y"]) for p in deduped]
        for i in range(n):
            a1 = coords[i]
            a2 = coords[(i + 1) % n]
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                b1 = coords[j]
                b2 = coords[(j + 1) % n]
                if _segments_intersect(a1, a2, b1, b2):
                    return False, "Polygon edges cannot self-intersect.", []

    # Shoelace area check
    area2 = 0.0
    for i in range(n):
        j = (i + 1) % n
        area2 += deduped[i]["x"] * deduped[j]["y"] - deduped[j]["x"] * deduped[i]["y"]
    if abs(area2) * 0.5 < 0.0002:
        return False, "Restricted zone polygon area is too small.", []

    return True, None, deduped


def save_zone_metadata(zone_id: int, camera_id: int, metadata: Dict[str, Any]) -> Dict[str, Any]:
    key = str(int(zone_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        current = dict(store["zones"].get(key) or {})
        current["camera_id"] = int(camera_id)
        shape = str(metadata.get("shape") or current.get("shape") or "rectangle").strip().lower()
        if shape not in ("rectangle", "polygon"):
            shape = "rectangle"
        current["shape"] = shape
        if isinstance(metadata.get("points"), list) and len(metadata["points"]) >= 3:
            current["points"] = metadata["points"]
        if metadata.get("entry_direction"):
            ed = str(metadata["entry_direction"]).strip().lower()
            if ed in VALID_DIRECTIONS:
                current["entry_direction"] = ed
        if metadata.get("color"):
            current["color"] = str(metadata["color"]).strip()[:32]
        if "cooldown_seconds" in metadata and metadata["cooldown_seconds"] is not None:
            try:
                current["cooldown_seconds"] = max(2.0, min(3600.0, float(metadata["cooldown_seconds"])))
            except (TypeError, ValueError):
                pass
        current["reference_point"] = "foot_point"
        current["updated_at"] = datetime.utcnow().isoformat() + "Z"
        store["zones"][key] = current
        _save_raw_store(store)
        return dict(current)


def get_zone_metadata(zone_id: int) -> Dict[str, Any]:
    key = str(int(zone_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        val = store["zones"].get(key)
        return dict(val) if isinstance(val, dict) else {}


def delete_zone_metadata(zone_id: int) -> None:
    key = str(int(zone_id))
    with _CONFIG_LOCK:
        store = _load_raw_store()
        if key in store["zones"]:
            store["zones"].pop(key, None)
            _save_raw_store(store)


def rect_pixel_to_normalized_points(
    x1: float, y1: float, x2: float, y2: float, ref_w: float = 1280.0, ref_h: float = 720.0
) -> List[Dict[str, float]]:
    lx1, rx2 = min(float(x1), float(x2)), max(float(x1), float(x2))
    ty1, by2 = min(float(y1), float(y2)), max(float(y1), float(y2))
    if max(lx1, rx2) <= 1.0 and max(ty1, by2) <= 1.0 and (rx2 > 0.0 or by2 > 0.0):
        nx1, ny1, nx2, ny2 = lx1, ty1, rx2, by2
    else:
        rw = float(ref_w or 1280.0)
        rh = float(ref_h or 720.0)
        nx1 = max(0.0, min(1.0, lx1 / rw))
        ny1 = max(0.0, min(1.0, ty1 / rh))
        nx2 = max(0.0, min(1.0, rx2 / rw))
        ny2 = max(0.0, min(1.0, by2 / rh))
    return [
        {"x": round(nx1, 6), "y": round(ny1, 6)},
        {"x": round(nx2, 6), "y": round(ny1, 6)},
        {"x": round(nx2, 6), "y": round(ny2, 6)},
        {"x": round(nx1, 6), "y": round(ny2, 6)},
    ]


def matches_entry_direction(direction_rule: str, vx: float = 0.0, vy: float = 0.0, transition: str = "enter") -> bool:
    rule = str(direction_rule or "any").strip().lower()
    if rule in ("any", ""):
        return True
    if rule in ("enter", "inward"):
        return transition == "enter"
    if rule in ("exit", "outward"):
        return transition == "exit"
    if transition != "enter":
        return False
    # Vector rules evaluate direction of motion upon entry
    if rule == "left_to_right":
        return vx > 1.5 or abs(vx) < 0.5  # permit near-stationary spawn if boundary crossed rightwards or unmeasured
    if rule == "right_to_left":
        return vx < -1.5 or abs(vx) < 0.5
    if rule == "top_to_bottom":
        return vy > 1.5 or abs(vy) < 0.5
    if rule == "bottom_to_top":
        return vy < -1.5 or abs(vy) < 0.5
    return True
