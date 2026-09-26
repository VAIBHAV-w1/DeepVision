"""
DeepVision Forensic Orphan and Relationship Consistency Audit.
Audits database relationships and file availability without deleting or altering records.
"""

import os
import sys
import django

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'deepvision_django'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.alerts.models import Alert, IncidentCase
from apps.evidence.models import Evidence
from apps.recordings.models import Recording
from apps.notifications.models import Notification
from apps.core.media_service import safe_resolve_evidence, safe_resolve_recording

def audit():
    print("=" * 70)
    print("RUNNING DEEPVISION FORENSIC ORPHAN & CONSISTENCY AUDIT")
    print("=" * 70)

    # 1. Alerts without evidence
    alerts_no_ev = Alert.objects.filter(evidence_items__isnull=True).values_list('id', flat=True)
    alerts_no_ev_count = alerts_no_ev.count()
    print(f"1. Alerts with zero linked evidence: {alerts_no_ev_count}")

    # 2. Evidence without alert
    ev_no_alert = Evidence.objects.filter(alert_id__isnull=True).values_list('id', flat=True)
    ev_no_alert_count = ev_no_alert.count()
    print(f"2. Evidence items with no linked alert: {ev_no_alert_count}")

    # 3. Evidence pointing to missing disk file
    ev_missing_file = []
    for ev in Evidence.objects.all():
        if not safe_resolve_evidence(ev.file_path):
            ev_missing_file.append(ev.id)
    print(f"3. Evidence items missing physical files on disk: {len(ev_missing_file)}")

    # 4. Recordings pointing to missing disk file
    rec_missing_file = []
    for rec in Recording.objects.all():
        if not safe_resolve_recording(rec.file_path):
            rec_missing_file.append(rec.id)
    print(f"4. Recordings missing physical files on disk: {len(rec_missing_file)}")

    # 5. Cases with missing originating alert
    cases_no_alert = IncidentCase.objects.filter(alert_id__isnull=True).values_list('id', flat=True)
    print(f"5. Cases with no linked originating alert: {cases_no_alert.count()}")

    # 6. Notifications with missing alert
    notifs_no_alert = Notification.objects.filter(alert_id__isnull=True).values_list('id', flat=True)
    print(f"6. Notifications with no linked alert: {notifs_no_alert.count()}")

    # 7. Inconsistent camera references between Alert and Evidence
    inconsistent_ev_camera = []
    for ev in Evidence.objects.filter(alert_id__isnull=False).select_related('alert'):
        if ev.camera_id != ev.alert.camera_id:
            inconsistent_ev_camera.append((ev.id, ev.alert_id, ev.camera_id, ev.alert.camera_id))
    print(f"7. Evidence items with camera_id mismatching linked alert: {len(inconsistent_ev_camera)}")

    print("\nAUDIT SUMMARY COMPLETED.")
    return {
        "alerts_no_ev_count": alerts_no_ev_count,
        "ev_no_alert_count": ev_no_alert_count,
        "ev_missing_file_count": len(ev_missing_file),
        "rec_missing_file_count": len(rec_missing_file),
        "cases_no_alert_count": cases_no_alert.count(),
        "notifs_no_alert_count": notifs_no_alert.count(),
        "inconsistent_ev_camera_count": len(inconsistent_ev_camera)
    }

if __name__ == '__main__':
    audit()
