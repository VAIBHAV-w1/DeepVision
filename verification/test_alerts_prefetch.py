import os
import sys
import time
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.abspath('deepvision_django'))
django.setup()

from apps.alerts.models import Alert
from apps.evidence.models import Evidence
from apps.recordings.models import Recording

t0 = time.time()
alerts_qs = Alert.objects.filter(user_id=2).select_related('camera').prefetch_related('evidence_items', 'incident_cases').order_by('-detected_at')[:20]
items = []
for a in alerts_qs:
    ev_list = list(a.evidence_items.all())
    cases_list = list(a.incident_cases.all())
    has_video = any(ev.evidence_type == 'video' for ev in ev_list)
    has_snapshot = any(ev.evidence_type == 'snapshot' for ev in ev_list)
    video_ev = next((ev for ev in ev_list if ev.evidence_type == 'video'), None)
    snapshot_ev = next((ev for ev in ev_list if ev.evidence_type == 'snapshot'), None)
    case_obj = cases_list[0] if cases_list else None

    # Check if a recording row also exists for this alert clip
    rec = Recording.objects.filter(file_path__icontains=f"alert_{a.id}_clip.mp4").first()

    items.append({
        "id": a.id,
        "title": a.title,
        "event_type": a.event_type,
        "severity": a.severity,
        "status": a.status,
        "has_video": has_video,
        "video_ev_id": video_ev.id if video_ev else None,
        "has_snapshot": has_snapshot,
        "snapshot_ev_id": snapshot_ev.id if snapshot_ev else None,
        "has_audio": False,  # DirectShow video-only source
        "audio_status": "unavailable",
        "audio_reason": "DirectShow video-only source",
        "has_case": bool(case_obj),
        "case_id": case_obj.id if case_obj else None,
        "case_number": case_obj.case_number if case_obj else None,
        "recording_id": rec.id if rec else None,
    })

t1 = time.time()
print(f"Loaded {len(items)} alerts for user 2 in {round((t1-t0)*1000, 2)} ms")
for it in items[:5]:
    print(it)
