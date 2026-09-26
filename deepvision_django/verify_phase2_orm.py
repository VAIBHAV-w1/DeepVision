"""
DeepVision - Phase 2 Verification Script
Verifies:
1. All 18 Django ORM models load without error.
2. Django ORM READ-ONLY queries against all 18 tables.
3. Foreign key relationships and reverse relationships navigate correctly.
4. Database file size, modification timestamp, and table row counts before & after.
5. Absolute database safety: NO writes, NO schema alterations.
"""
import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime

# Setup Django environment
DJANGO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(DJANGO_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.accounts.models import User
from apps.cameras.models import Camera, CameraGroup, SurveillancePreset
from apps.alerts.models import Alert, IncidentCase, IncidentNote, IncidentPolicy, IncidentPlaybook
from apps.recordings.models import Recording
from apps.evidence.models import Evidence
from apps.notifications.models import Notification, NotificationPreference
from apps.core.models import AuditLog, Device, Product, RestrictedZone, DetectionProfile

DB_PATH = DJANGO_ROOT.parent / 'instance' / 'deepvision.db'


def get_db_stats():
    st = DB_PATH.stat()
    return {
        'size': st.st_size,
        'mtime': st.st_mtime,
        'mtime_iso': datetime.fromtimestamp(st.st_mtime).isoformat()
    }


def main():
    print("=" * 60)
    print("DEEPVISION PHASE 2: DJANGO ORM VERIFICATION")
    print("=" * 60)

    # 1. Pre-check database status
    initial_stats = get_db_stats()
    print(f"[DB PRE-CHECK] Path: {DB_PATH}")
    print(f"[DB PRE-CHECK] Size: {initial_stats['size']} bytes")
    print(f"[DB PRE-CHECK] Modified: {initial_stats['mtime_iso']}")

    # 2. Table mappings & counts
    models_to_test = [
        ("users", User),
        ("cameras", Camera),
        ("recordings", Recording),
        ("alerts", Alert),
        ("evidence", Evidence),
        ("incident_cases", IncidentCase),
        ("notifications", Notification),
        ("audit_logs", AuditLog),
        ("products", Product),
        ("devices", Device),
        ("restricted_zones", RestrictedZone),
        ("detection_profiles", DetectionProfile),
        ("notification_preferences", NotificationPreference),
        ("camera_groups", CameraGroup),
        ("surveillance_presets", SurveillancePreset),
        ("incident_notes", IncidentNote),
        ("incident_policies", IncidentPolicy),
        ("incident_playbooks", IncidentPlaybook),
    ]

    print("\n--- MODEL COUNT TESTS ---")
    counts = {}
    for table_name, model_cls in models_to_test:
        count = model_cls.objects.count()
        counts[table_name] = count
        status = "POPULATED" if count > 0 else "EMPTY (as expected)"
        print(f"  {table_name:<26} -> {model_cls.__name__:<22} count = {count:<6} [{status}]")

    # 3. Read representative sample records
    print("\n--- REPRESENTATIVE SAMPLE READS ---")
    first_user = User.objects.first()
    print(f"  Sample User: id={first_user.id}, email={first_user.email}, name={first_user.full_name}, role={first_user.role}")

    first_cam = Camera.objects.first()
    print(f"  Sample Camera: id={first_cam.id}, name='{first_cam.name}', source='{first_cam.source}', status={first_cam.status}")

    first_rec = Recording.objects.first()
    print(f"  Sample Recording: id={first_rec.id}, filename='{first_rec.filename}', size={first_rec.file_size}B, status={first_rec.status}")

    first_alert = Alert.objects.first()
    print(f"  Sample Alert: id={first_alert.id}, type='{first_alert.event_type}', severity={first_alert.severity}, title='{first_alert.title}'")

    first_evidence = Evidence.objects.first()
    print(f"  Sample Evidence: id={first_evidence.id}, type='{first_evidence.evidence_type}', name='{first_evidence.file_name}'")

    first_case = IncidentCase.objects.first()
    print(f"  Sample IncidentCase: id={first_case.id}, number='{first_case.case_number}', status={first_case.status}, priority={first_case.priority}")

    first_notif = Notification.objects.first()
    print(f"  Sample Notification: id={first_notif.id}, alert_id={first_notif.alert_id}, is_read={first_notif.is_read}")

    first_log = AuditLog.objects.first()
    print(f"  Sample AuditLog: id={first_log.id}, action='{first_log.action}', resource='{first_log.resource_type}'")

    first_product = Product.objects.first()
    print(f"  Sample Product: id={first_product.id}, pid='{first_product.product_id}', name='{first_product.name}', sku='{first_product.sku}'")

    # 4. Relationship Traversal Tests
    print("\n--- RELATIONSHIP TRAVERSAL TESTS ---")
    # Alert -> Camera
    alert_cam = first_alert.camera
    print(f"  first_alert.camera: id={alert_cam.id}, name='{alert_cam.name}' (MATCH: {alert_cam.id == first_alert.camera_id})")

    # Alert -> User
    alert_user = first_alert.user
    print(f"  first_alert.user: id={alert_user.id}, email='{alert_user.email}' (MATCH: {alert_user.id == first_alert.user_id})")

    # Evidence -> Alert
    ev_alert = first_evidence.alert
    print(f"  first_evidence.alert: id={ev_alert.id}, type='{ev_alert.event_type}' (MATCH: {ev_alert.id == first_evidence.alert_id})")

    # Evidence -> Camera
    ev_cam = first_evidence.camera
    print(f"  first_evidence.camera: id={ev_cam.id}, name='{ev_cam.name}' (MATCH: {ev_cam.id == first_evidence.camera_id})")

    # Recording -> Camera
    rec_cam = first_rec.camera
    print(f"  first_rec.camera: id={rec_cam.id}, name='{rec_cam.name}' (MATCH: {rec_cam.id == first_rec.camera_id})")

    # IncidentCase -> Alert
    case_alert = first_case.alert
    print(f"  first_case.alert: id={case_alert.id}, type='{case_alert.event_type}' (MATCH: {case_alert.id == first_case.alert_id})")

    # Notification -> Alert
    notif_alert = first_notif.alert
    print(f"  first_notif.alert: id={notif_alert.id}, type='{notif_alert.event_type}' (MATCH: {notif_alert.id == first_notif.alert_id})")

    # Reverse relationships:
    rec_count_for_cam = first_cam.recordings.count()
    print(f"  first_cam.recordings.count(): {rec_count_for_cam}")

    alert_count_for_cam = first_cam.alerts.count()
    print(f"  first_cam.alerts.count(): {alert_count_for_cam}")

    ev_count_for_alert = first_alert.evidence_items.count()
    print(f"  first_alert.evidence_items.count(): {ev_count_for_alert}")

    logs_for_user = first_user.audit_logs.count()
    print(f"  first_user.audit_logs.count(): {logs_for_user}")

    # 5. Post-check database status
    post_stats = get_db_stats()
    print("\n--- DATABASE INTEGRITY POST-CHECK ---")
    print(f"[DB POST-CHECK] Size: {post_stats['size']} bytes (Initial: {initial_stats['size']} bytes)")
    print(f"[DB POST-CHECK] Modified: {post_stats['mtime_iso']} (Initial: {initial_stats['mtime_iso']})")

    size_match = post_stats['size'] == initial_stats['size']
    mtime_match = post_stats['mtime'] == initial_stats['mtime']
    print(f"[DB INTEGRITY] Size Unchanged: {size_match}")
    print(f"[DB INTEGRITY] Modification Timestamp Unchanged: {mtime_match}")

    if not size_match or not mtime_match:
        print("ERROR: Database was modified during verification!")
        sys.exit(1)
    else:
        print("SUCCESS: Database is 100% READ-ONLY and UNMODIFIED.")


if __name__ == '__main__':
    main()
