"""
DeepVision AI SOC Triage, Correlation & Prompt-Injection Defense Service.

Produces deterministic, strictly evidence-linked security triage and duplicate/burst
correlation from verifiable database records:
  - Sanitizes untrusted camera names, locations, zones, alert text, and notes
    against HTML/script injection and LLM prompt-injection payloads.
  - Correlates related alerts by camera/track within a bounded time window.
  - Matches active IncidentPolicy SLA windows.
  - Produces structured risk scores, supporting evidence citations, and
    operator-confirmed recommended next steps (zero silent auto-close/auto-action).
"""
from __future__ import annotations

import html
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\ufeff]+")
_HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"(disregard|forget|override)\s+(system|developer|security)\s+(prompt|rules?|instructions?)", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:system|assistant|developer)\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|(?:im_start|im_end|system|endoftext)\|>", re.IGNORECASE),
    re.compile(r"\[\s*(?:INST|SYS|SYSTEM)\s*\]", re.IGNORECASE),
    re.compile(r"(?:auto[\s_-]*close|resolve\s+all\s+alerts|disable\s+alarms?|exfiltrate)", re.IGNORECASE),
)

_CLASSIFICATION_CATALOG = {
    "restricted_area_entry": ("Perimeter Intrusion", "high", "Verified subject entered a protected boundary polygon or zone."),
    "intrusion": ("Perimeter Intrusion", "critical", "Unauthorized entry crossed an active security zone perimeter."),
    "abandoned_object": ("Unattended / Abandoned Object", "high", "Stationary baggage or item persisted beyond unattended dwell threshold."),
    "loitering": ("Loitering / Extended Dwell", "medium", "Tracked person remained stationary within a zone beyond linger threshold."),
    "crowding": ("Crowd Density Spike", "high", "Simultaneous visible persons exceeded configured occupancy threshold."),
    "rapid_movement": ("Rapid / High-Velocity Movement", "medium", "Tracked subject exhibited sudden high-velocity movement."),
    "unusual_movement": ("Erratic / Unusual Trajectory", "medium", "Tracked subject showed repeated direction reversals or anomalous speed."),
    "unexpected_object": ("Unexpected Object Class", "medium", "Disallowed or unexpected object category appeared in sector."),
    "manual_snapshot": ("Operator Forensic Snapshot", "low", "Manual visual snapshot captured by an authenticated operator."),
}


def detect_prompt_injection(raw_text: Any) -> Tuple[bool, List[str]]:
    """Detects suspicious instruction-override or markup payloads in untrusted camera/alert text."""
    text = str(raw_text or "")
    if not text:
        return False, []
    matched: List[str] = []
    for pat in _PROMPT_INJECTION_PATTERNS:
        if pat.search(text):
            matched.append(pat.pattern[:48])
    return bool(matched), matched


def sanitize_untrusted_text(raw_text: Any, max_len: int = 240, neutralize_injection: bool = True) -> Tuple[str, bool]:
    """
    Sanitizes untrusted telemetry strings (camera name, zone label, alert text, notes)
    before rendering into SOC narratives or assistant context.
    Returns `(clean_text, injection_flag)`.
    """
    text = str(raw_text or "")
    text = _CONTROL_CHARS_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    flagged, _ = detect_prompt_injection(text)
    if neutralize_injection and flagged:
        for pat in _PROMPT_INJECTION_PATTERNS:
            text = pat.sub("[filtered-untrusted-directive]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return html.escape(text, quote=False), flagged


def find_correlated_alerts(alert, window_minutes: int = 30, limit: int = 12) -> List[Dict[str, Any]]:
    """
    Finds genuine related alerts on the same camera/track within `±window_minutes`
    for operator duplicate/burst triage (never alters or auto-closes alerts).
    """
    from apps.alerts.models import Alert

    anchor = alert.detected_at or alert.created_at or timezone.now()
    delta = timedelta(minutes=max(5, int(window_minutes)))
    qs = (
        Alert.objects.filter(
            user_id=alert.user_id,
            camera_id=alert.camera_id,
            detected_at__gte=anchor - delta,
            detected_at__lte=anchor + delta,
        )
        .exclude(id=alert.id)
        .select_related("camera")
        .order_by("-detected_at", "-id")[:limit]
    )

    correlated: List[Dict[str, Any]] = []
    for rel in qs:
        same_track = alert.track_id is not None and rel.track_id == alert.track_id
        same_type = str(rel.event_type or "").lower() == str(alert.event_type or "").lower()
        clean_title, _ = sanitize_untrusted_text(rel.title or rel.event_type or f"Alert #{rel.id}", max_len=100)
        reason = []
        if same_track:
            reason.append(f"same track #{rel.track_id}")
        if same_type:
            reason.append("same rule")
        if not reason:
            reason.append("same camera window")
        correlated.append({
            "id": rel.id,
            "title": clean_title,
            "event_type": str(rel.event_type or "anomaly"),
            "severity": str(rel.severity or "medium").lower(),
            "status": str(rel.status or "new").lower(),
            "track_id": rel.track_id,
            "confidence": round(float(rel.confidence or 0.0), 3) if rel.confidence is not None else None,
            "detected_at": rel.detected_at.isoformat() if rel.detected_at else "",
            "correlation_basis": ", ".join(reason),
        })
    return correlated


def match_sla_policy(alert) -> Optional[Dict[str, Any]]:
    """Evaluates active IncidentPolicy for this alert severity without modifying data."""
    from apps.alerts.models import IncidentPolicy

    sev = str(alert.severity or "medium").strip().lower()
    policy = (
        IncidentPolicy.objects.filter(user_id=alert.user_id, enabled=True, severity__iexact=sev)
        .order_by("initial_response_minutes", "id")
        .first()
    )
    if policy is None:
        return None

    anchor = alert.detected_at or alert.created_at
    now = timezone.now()
    elapsed_min = round(max(0.0, (now - anchor).total_seconds() / 60.0), 1) if anchor else 0.0
    if alert.status == "resolved":
        sla_state = "resolved"
    elif alert.status == "acknowledged":
        sla_state = "breached" if elapsed_min > float(policy.resolution_minutes or 60) else "within_sla"
    else:
        resp_min = float(policy.initial_response_minutes or 15)
        if elapsed_min > resp_min:
            sla_state = "breached"
        elif elapsed_min >= resp_min * 0.75:
            sla_state = "approaching_breach"
        else:
            sla_state = "within_sla"

    clean_policy_name, _ = sanitize_untrusted_text(policy.name, max_len=100)
    return {
        "policy_id": policy.id,
        "policy_name": clean_policy_name,
        "severity": sev,
        "initial_response_minutes": int(policy.initial_response_minutes or 15),
        "escalation_minutes": int(policy.escalation_minutes or 30),
        "resolution_minutes": int(policy.resolution_minutes or 60),
        "elapsed_minutes": elapsed_min,
        "sla_state": sla_state,
        "auto_create_case": bool(policy.auto_create_case),
    }


def analyze_incident(
    alert,
    evidence_items: Optional[List[Dict[str, Any]]] = None,
    recording_data: Optional[Dict[str, Any]] = None,
    incident_case: Optional[Dict[str, Any]] = None,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Builds evidence-linked AI SOC analysis for a single incident.
    All untrusted camera/alert fields are sanitized against prompt injection, and all
    recommended actions remain strictly supervised by the human analyst.
    """
    ev_list = list(evidence_items or [])
    raw_type = str(alert.event_type or "anomaly").strip().lower()
    sev = str(alert.severity or "medium").strip().lower()
    conf = float(alert.confidence) if alert.confidence is not None else 0.85
    conf = max(0.0, min(1.0, conf))

    cam_raw = alert.camera.name if getattr(alert, "camera", None) else f"Camera {alert.camera_id}"
    loc_raw = alert.location or (alert.camera.location if getattr(alert, "camera", None) else "Default Zone")
    clean_cam, flag_cam = sanitize_untrusted_text(cam_raw, max_len=100)
    clean_loc, flag_loc = sanitize_untrusted_text(loc_raw, max_len=100)
    clean_msg, flag_msg = sanitize_untrusted_text(alert.message or "", max_len=360)
    clean_title, flag_title = sanitize_untrusted_text(alert.title or raw_type, max_len=120)

    injection_fields = []
    if flag_cam:
        injection_fields.append("camera_name")
    if flag_loc:
        injection_fields.append("location")
    if flag_msg:
        injection_fields.append("message")
    if flag_title:
        injection_fields.append("title")

    cls_label, default_cls_sev, cls_summary = _CLASSIFICATION_CATALOG.get(
        raw_type,
        (raw_type.replace("_", " ").title() or "Security Anomaly", sev, "Real-time behavioral or spatial anomaly rule triggered."),
    )

    correlated = find_correlated_alerts(alert)
    sla_policy = match_sla_policy(alert)

    has_video = any(e.get("evidence_type") == "video" and e.get("file_available") for e in ev_list)
    has_snap = any(e.get("evidence_type") == "snapshot" and e.get("file_available") for e in ev_list)
    has_rec = bool(recording_data and recording_data.get("file_available"))

    sev_base = {"critical": 82, "high": 66, "medium": 46, "low": 24}.get(sev, 45)
    burst_bonus = min(14, len(correlated) * 4)
    conf_bonus = int(round((conf - 0.5) * 16))
    risk_score = max(10, min(100, sev_base + burst_bonus + conf_bonus))
    risk_level = "critical" if risk_score >= 85 else "high" if risk_score >= 65 else "medium" if risk_score >= 40 else "low"

    supporting_evidence: List[Dict[str, Any]] = []
    if alert.detected_at:
        supporting_evidence.append({
            "kind": "detection",
            "label": f"YOLO26 + BoT-SORT detection ({int(round(conf * 100))}% conf)",
            "timestamp": alert.detected_at.isoformat(),
            "available": True,
        })
    for ev in ev_list[:4]:
        supporting_evidence.append({
            "kind": str(ev.get("evidence_type") or "artifact"),
            "label": str(ev.get("file_name") or f"Evidence #{ev.get('id')}"),
            "timestamp": ev.get("captured_at") or "",
            "available": bool(ev.get("file_available")),
        })
    if recording_data:
        supporting_evidence.append({
            "kind": "recording",
            "label": str(recording_data.get("filename") or f"Recording #{recording_data.get('id')}"),
            "timestamp": recording_data.get("started_at") or "",
            "available": bool(recording_data.get("file_available")),
        })

    ts_label = alert.detected_at.isoformat() if alert.detected_at else "recorded timestamp"
    track_label = f"track #{alert.track_id}" if alert.track_id is not None else "sector cluster"
    burst_text = (
        f" Correlated with {len(correlated)} related event(s) on this camera within +/-30 minutes (review as possible duplicate burst before resolving)."
        if correlated
        else " No duplicate/burst events detected on this camera within +/-30 minutes."
    )
    media_text = (
        " Video and snapshot evidence are attached."
        if (has_video and has_snap)
        else " Forensic evidence artifact is attached."
        if (has_video or has_snap or has_rec)
        else " No persisted media clip available on disk for this timestamp; rely on frame metadata and timeline."
    )
    explanation = (
        f"{cls_label} flagged at {ts_label} on untrusted telemetry source '{clean_cam}' "
        f"(sector '{clean_loc}', {track_label}, {int(round(conf * 100))}% confidence). "
        f"{cls_summary}{media_text}{burst_text}"
    )

    next_steps: List[Dict[str, Any]] = []
    if has_video or has_rec:
        next_steps.append({
            "step": "Inspect scoped video/recording clip to confirm visual ground truth.",
            "action_hint": "review_media",
            "requires_operator_confirmation": True,
        })
    elif has_snap:
        next_steps.append({
            "step": "Inspect forensic keyframe snapshot for false-positive verification.",
            "action_hint": "review_snapshot",
            "requires_operator_confirmation": True,
        })
    if alert.status == "new":
        next_steps.append({
            "step": "Acknowledge incident once initial telemetry check confirms signal validity.",
            "action_hint": "acknowledge",
            "requires_operator_confirmation": True,
        })
    if correlated:
        next_steps.append({
            "step": f"Group or review {len(correlated)} correlated alert(s) on '{clean_cam}' before resolving.",
            "action_hint": "review_correlated",
            "requires_operator_confirmation": True,
        })
    if not incident_case and sev in ("critical", "high"):
        next_steps.append({
            "step": "Open a formal Incident Case to document investigator notes and audit trail.",
            "action_hint": "open_case",
            "requires_operator_confirmation": True,
        })
    if alert.status != "resolved":
        next_steps.append({
            "step": "Resolve incident manually after verification and case documentation.",
            "action_hint": "resolve",
            "requires_operator_confirmation": True,
        })

    return {
        "track_id": alert.track_id,
        "event_type": raw_type,
        "classification": cls_label,
        "confidence": conf,
        "severity": sev,
        "default_rule_severity": default_cls_sev,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "title": clean_title,
        "message": clean_msg,
        "location": clean_loc,
        "camera_name": clean_cam,
        "detected_at": alert.detected_at.isoformat() if alert.detected_at else "",
        "explanation": explanation,
        "supporting_evidence": supporting_evidence,
        "correlated_alerts": correlated,
        "correlation_count": len(correlated),
        "burst_detected": len(correlated) >= 2,
        "sla_policy": sla_policy,
        "recommended_next_steps": next_steps,
        "supervised_only": True,
        "security_sanitization": {
            "untrusted_fields_sanitized": True,
            "prompt_injection_detected": bool(injection_fields),
            "flagged_fields": injection_fields,
        },
        "timeline_milestones": len(timeline or []),
    }
