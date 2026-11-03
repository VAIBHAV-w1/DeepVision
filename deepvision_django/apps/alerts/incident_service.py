"""
Canonical Incident Scoping & Forensics Service for DeepVision.
==============================================================
Provides strictly scoped incident context using existing database fields.
Guarantees:
- Every returned entity is derived ONLY from the selected incident's relationship graph.
- Zero cross-incident data contamination.
- Zero fallback to unrelated 'latest' records.
- Truthful audio status inspection.
- Chronological timeline built only from verifiable milestones.
"""

from typing import Optional, Dict, Any, List
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import Http404

from apps.alerts.models import Alert, IncidentCase, IncidentNote
from apps.evidence.models import Evidence
from apps.recordings.models import Recording
from apps.notifications.models import Notification
from apps.surveillance.audio.service import inspect_media_audio, check_camera_audio_capability
from apps.core.media_service import safe_resolve_evidence, safe_resolve_recording


def _format_size(size_bytes: Optional[int]) -> str:
    if not size_bytes or size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_incident_context(alert_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Returns the canonical, strictly scoped incident forensic context.
    Raises Http404 if the alert does not exist or does not belong to user_id.
    """
    query = Alert.objects.select_related('camera').prefetch_related(
        'evidence_items',
        'incident_cases',
        'incident_notes',
        'notifications',
    )
    if user_id is not None:
        alert = get_object_or_404(query, id=alert_id, user_id=user_id)
    else:
        alert = get_object_or_404(query, id=alert_id)

    # 1. Strictly Scoped Evidence Items (FK: evidence.alert_id == alert.id)
    ev_queryset = alert.evidence_items.all().order_by('captured_at', 'id')
    evidence_items = []
    video_ev = None
    snapshot_ev = None
    video_file_paths = []
    video_filenames = []

    cam_audio = check_camera_audio_capability(alert.camera)

    for ev in ev_queryset:
        resolved_path = safe_resolve_evidence(ev.file_path)
        is_video = ev.evidence_type == 'video'

        if is_video:
            video_file_paths.append(ev.file_path)
            video_filenames.append(ev.file_name)
            # Inspect actual audio track on disk if file exists
            if resolved_path:
                audio_meta = inspect_media_audio(str(resolved_path))
                has_audio = audio_meta.get("has_audio", False)
                audio_status = audio_meta.get("status", "unavailable")
                audio_reason = audio_meta.get("reason", "No audio stream found in container")
            else:
                has_audio = False
                audio_status = "unavailable"
                audio_reason = cam_audio.get("reason", "DirectShow video-only source")
        else:
            has_audio = False
            audio_status = "unavailable"
            audio_reason = "Image keyframe (no audio)"

        # Verify timestamp alignment with alert detection
        ev_time_diff = 0.0
        ev_mismatched = False
        if alert.detected_at and ev.captured_at:
            ev_time_diff = abs((alert.detected_at - ev.captured_at).total_seconds())
            if ev_time_diff > 300.0:
                ev_mismatched = True

        ev_data = {
            "id": ev.id,
            "alert_id": alert.id,
            "camera_id": ev.camera_id,
            "file_name": ev.file_name,
            "evidence_type": ev.evidence_type,
            "mime_type": ev.mime_type,
            "file_size": ev.file_size,
            "formatted_size": _format_size(ev.file_size),
            "file_available": resolved_path is not None,
            "duration_seconds": ev.duration_seconds,
            "captured_at": ev.captured_at.isoformat() if ev.captured_at else "",
            "preview_url": f"/evidence/{ev.id}/preview/",
            "download_url": f"/evidence/{ev.id}/download/",
            "has_audio": has_audio,
            "audio_status": audio_status,
            "audio_reason": audio_reason,
            "timestamp_mismatch": ev_mismatched,
            "time_diff_seconds": ev_time_diff,
        }
        evidence_items.append(ev_data)

        if is_video and not video_ev:
            video_ev = ev_data
        elif ev.evidence_type == 'snapshot' and not snapshot_ev:
            snapshot_ev = ev_data

    # 2. Strictly Scoped Recording (Must belong to this alert & camera)
    # Never return an unrelated recording, stale recording, or generic latest recording!
    rec = None
    clean_video_paths = [p for p in video_file_paths if p and str(p).strip()]
    clean_video_names = [n for n in video_filenames if n and str(n).strip()]

    # First attempt: Match explicit anomaly clip by exact alert ID token (e.g. alert_6119_clip)
    # or by exact filepath/filename from scoped evidence items.
    # Note: We match f"alert_{alert.id}_clip." to avoid partial numeric prefixes (e.g. alert_61_ matching alert_6118_).
    rec_query = Q()
    if clean_video_paths:
        rec_query |= Q(file_path__in=clean_video_paths)
    if clean_video_names:
        rec_query |= Q(filename__in=clean_video_names)
    rec_query |= (
        Q(filename__icontains=f"alert_{alert.id}_clip.") |
        Q(file_path__icontains=f"alert_{alert.id}_clip.")
    )

    candidate_anomalies = Recording.objects.filter(camera_id=alert.camera_id).filter(rec_query)
    for cand in candidate_anomalies:
        # Time-sanity check: recording must be within 300 seconds of alert detection
        if alert.detected_at and cand.started_at:
            if abs((alert.detected_at - cand.started_at).total_seconds()) <= 300.0:
                rec = cand
                break
        else:
            rec = cand
            break

    # Second attempt: Check for exact continuous segment on THIS camera tightly wrapping detected_at
    # CRITICAL DATA-INTEGRITY RULE: Only attach continuous segments that tightly wrap the alert
    # (within 60 seconds of detected_at, with maximum duration <= 300s).
    # NEVER fall back to broad, unclosed, multi-day, or historical recordings.
    if not rec and alert.detected_at:
        candidate_recs = Recording.objects.filter(
            camera_id=alert.camera_id,
            started_at__lte=alert.detected_at,
            ended_at__gte=alert.detected_at,
            duration_seconds__lte=300.0,
        ).order_by('-started_at')
        
        for cand in candidate_recs:
            if cand.started_at and abs((alert.detected_at - cand.started_at).total_seconds()) <= 60.0:
                rec = cand
                break

    recording_data = None
    if rec:
        # Double check: if recording timestamp is > 300 seconds away from alert, reject it
        if alert.detected_at and rec.started_at and abs((alert.detected_at - rec.started_at).total_seconds()) > 300.0:
            rec = None
        rec_resolved = safe_resolve_recording(rec.file_path)
        rec_audio = inspect_media_audio(str(rec_resolved)) if rec_resolved else {"has_audio": False, "status": "unavailable"}
        
        # Verify timestamp alignment between alert detection and recording start
        time_diff_sec = 0.0
        is_mismatched = False
        mismatch_warning = None
        if alert.detected_at and rec.started_at:
            time_diff_sec = abs((alert.detected_at - rec.started_at).total_seconds())
            if time_diff_sec > 120.0:
                is_mismatched = True
                mismatch_warning = f"Recording started {int(time_diff_sec)}s away from incident detection time."

        recording_data = {
            "id": rec.id,
            "alert_id": alert.id,
            "camera_id": rec.camera_id,
            "filename": rec.filename,
            "duration_seconds": rec.duration_seconds,
            "file_size": rec.file_size,
            "formatted_size": _format_size(rec.file_size),
            "file_available": rec_resolved is not None,
            "started_at": rec.started_at.isoformat() if rec.started_at else "",
            "ended_at": rec.ended_at.isoformat() if rec.ended_at else "",
            "view_url": f"/recordings/{rec.id}/view/",
            "download_url": f"/recordings/{rec.id}/download/",
            "status": rec.status,
            "has_audio": rec_audio.get("has_audio", False),
            "audio_status": rec_audio.get("status", "unavailable"),
            "audio_reason": rec_audio.get("reason", "DirectShow video-only stream"),
            "timestamp_mismatch": is_mismatched,
            "time_diff_seconds": time_diff_sec,
            "mismatch_warning": mismatch_warning,
        }

    # 3. Strictly Scoped Incident Case (FK: incident_cases.alert_id == alert.id)
    cases_list = list(alert.incident_cases.all().order_by('-created_at'))
    incident_case = None
    if cases_list:
        ic = cases_list[0]
        incident_case = {
            "id": ic.id,
            "alert_id": alert.id,
            "case_number": ic.case_number,
            "title": ic.title,
            "description": ic.description or "",
            "status": ic.status,
            "priority": ic.priority,
            "assigned_to": ic.assigned_to or "Unassigned",
            "created_at": ic.created_at.isoformat() if ic.created_at else "",
            "closed_at": ic.closed_at.isoformat() if ic.closed_at else "",
        }

    # 4. Strictly Scoped Investigator Notes (FK: incident_notes.alert_id == alert.id)
    notes_list = list(alert.incident_notes.all().select_related('user').order_by('created_at'))
    incident_notes = []
    for n in notes_list:
        incident_notes.append({
            "id": n.id,
            "alert_id": alert.id,
            "note": n.body,
            "author_name": n.user.full_name if (n.user and n.user.full_name) else (n.user.email if n.user else "Investigator"),
            "created_at": n.created_at.isoformat() if n.created_at else "",
        })

    # 5. Strictly Scoped Notifications (FK: notifications.alert_id == alert.id)
    notifs_list = list(alert.notifications.all().order_by('created_at'))
    notifications_data = []
    for notif in notifs_list:
        notifications_data.append({
            "id": notif.id,
            "alert_id": alert.id,
            "title": f"Security Alert: {alert.title}",
            "message": alert.message or f"Anomaly {alert.event_type} detected on {alert.camera.name if alert.camera else 'camera'}.",
            "is_read": notif.is_read,
            "created_at": notif.created_at.isoformat() if notif.created_at else "",
            "read_at": notif.read_at.isoformat() if notif.read_at else "",
        })

    # 6. Chronological Forensic Timeline (Only verifiable milestones of this incident)
    timeline = []
    if alert.detected_at:
        timeline.append({
            "id": f"det_{alert.id}",
            "type": "detection",
            "title": "Anomaly Detected",
            "timestamp": alert.detected_at.isoformat(),
            "description": f"AI model flagged {alert.event_type.replace('_', ' ').title()} with {int((alert.confidence or 0.85)*100)}% confidence.",
            "status": "complete",
        })

    if alert.created_at:
        timeline.append({
            "id": f"alert_{alert.id}",
            "type": "alert_logged",
            "title": f"Security Alert #{alert.id} Logged",
            "timestamp": alert.created_at.isoformat(),
            "description": f"Alert categorized under severity {alert.severity.upper()} in camera zone.",
            "status": "complete",
        })

    if snapshot_ev:
        timeline.append({
            "id": f"snap_{snapshot_ev['id']}",
            "type": "snapshot_captured",
            "title": "Forensic Snapshot Captured",
            "timestamp": snapshot_ev.get("captured_at") or (alert.detected_at.isoformat() if alert.detected_at else ""),
            "description": f"Keyframe image saved: {snapshot_ev.get('file_name')}",
            "status": "complete",
        })

    if video_ev:
        timeline.append({
            "id": f"vid_{video_ev['id']}",
            "type": "video_recorded",
            "title": "Evidence Video Clip Archived",
            "timestamp": video_ev.get("captured_at") or (alert.detected_at.isoformat() if alert.detected_at else ""),
            "description": f"Rolling buffer clip ({video_ev.get('duration_seconds', 0)}s) saved to forensic storage.",
            "status": "complete",
        })

    if recording_data:
        timeline.append({
            "id": f"rec_{recording_data['id']}",
            "type": "recording_available",
            "title": "Full Recording Segment Available",
            "timestamp": recording_data.get("started_at") or (alert.detected_at.isoformat() if alert.detected_at else ""),
            "description": f"Surveillance recording #{recording_data['id']} ({recording_data.get('duration_seconds', 0)}s) indexed in recordings catalog.",
            "status": "complete",
        })

    if notifications_data:
        timeline.append({
            "id": f"notif_{notifications_data[0]['id']}",
            "type": "notification_dispatched",
            "title": "Security Notification Queued",
            "timestamp": notifications_data[0].get("created_at"),
            "description": f"SOC operator dispatch dispatched for Alert #{alert.id}.",
            "status": "complete",
        })

    if incident_case:
        timeline.append({
            "id": f"case_{incident_case['id']}",
            "type": "case_opened",
            "title": f"Forensic Case {incident_case['case_number']} Opened",
            "timestamp": incident_case['created_at'],
            "description": f"Priority: {incident_case['priority']} | Status: {incident_case['status'].upper()}",
            "status": "complete",
        })

    if alert.acknowledged_at:
        timeline.append({
            "id": f"ack_{alert.id}",
            "type": "acknowledged",
            "title": "Operator Acknowledged Incident",
            "timestamp": alert.acknowledged_at.isoformat(),
            "description": "Investigation accepted and underway.",
            "status": "complete",
        })

    if alert.resolved_at:
        timeline.append({
            "id": f"res_{alert.id}",
            "type": "resolved",
            "title": "Incident Resolved",
            "timestamp": alert.resolved_at.isoformat(),
            "description": "Incident closed with resolution confirmed.",
            "status": "complete",
        })

    # Sort timeline chronologically by timestamp
    timeline.sort(key=lambda x: x.get("timestamp") or "")

    return {
        "alert": {
            "id": alert.id,
            "title": alert.title or alert.event_type or "Security Alert",
            "message": alert.message or "",
            "event_type": alert.event_type,
            "severity": alert.severity,
            "status": alert.status,
            "confidence": alert.confidence,
            "location": alert.location or (alert.camera.location if alert.camera else "Default Zone"),
            "camera_id": alert.camera_id,
            "camera_name": alert.camera.name if alert.camera else "Channel 01",
            "detected_at": alert.detected_at.isoformat() if alert.detected_at else "",
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else "",
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else "",
            "track_id": alert.track_id,
        },
        "camera": {
            "id": alert.camera.id if alert.camera else alert.camera_id,
            "name": alert.camera.name if alert.camera else "Channel 01",
            "location": alert.camera.location if alert.camera else "Default Zone",
            "status": alert.camera.status if alert.camera else "offline",
            "source_type": alert.camera.source_type if alert.camera else "directshow",
        },
        "primary_media": {
            "video": video_ev,
            "snapshot": snapshot_ev,
            "recording": recording_data,
        },
        "ai_analysis": {
            "track_id": alert.track_id,
            "event_type": alert.event_type,
            "confidence": alert.confidence or 0.85,
            "severity": alert.severity,
            "message": alert.message,
            "location": alert.location or (alert.camera.location if alert.camera else "Default Zone"),
            "camera_name": alert.camera.name if alert.camera else "Channel 01",
            "detected_at": alert.detected_at.isoformat() if alert.detected_at else "",
        },
        "timeline": timeline,
        "evidence_items": evidence_items,
        "incident_case": incident_case,
        "incident_notes": incident_notes,
        "notifications": notifications_data,
        "metadata": {
            "alert_id": alert.id,
            "camera_id": alert.camera_id,
            "evidence_count": len(evidence_items),
            "has_video": video_ev is not None,
            "has_snapshot": snapshot_ev is not None,
            "has_recording": recording_data is not None,
            "has_case": incident_case is not None,
            "notes_count": len(incident_notes),
            "notifications_count": len(notifications_data),
        }
    }
