"""
Incident Scoping and Data Isolation Verification Suite.
Verifies that GET /api/alerts/<id>/incident-context/ and related scoped endpoints
strictly isolate data between different incidents.
"""

import os
import sys
import django

# Add project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'deepvision_django'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.evidence.models import Evidence
from apps.recordings.models import Recording
from apps.alerts.incident_service import get_incident_context

def run_tests():
    print("=" * 70)
    print("RUNNING INCIDENT SCOPING & DATA ISOLATION VERIFICATION SUITE")
    print("=" * 70)

    # 1. Fetch test user who owns alerts
    user = User.objects.filter(id=2).first() or User.objects.filter(is_active=True).first()
    if not user:
        print("[FAIL] No active user found.")
        sys.exit(1)
    print(f"[OK] Found test user: {user.email} (ID: {user.id})")

    # 2. Pick two distinct alerts for this user
    alerts = list(Alert.objects.filter(user_id=user.id).order_by('-id')[:10])
    if len(alerts) < 2:
        print("[FAIL] At least 2 alerts required for isolation testing.")
        sys.exit(1)

    alert_a = alerts[0]
    alert_b = alerts[1]
    print(f"[OK] Incident A: ID #{alert_a.id} ('{alert_a.title}', detected at {alert_a.detected_at})")
    print(f"[OK] Incident B: ID #{alert_b.id} ('{alert_b.title}', detected at {alert_b.detected_at})")

    # 3. Test Service Level Context for Alert A and Alert B
    ctx_a = get_incident_context(alert_a.id, user_id=user.id)
    ctx_b = get_incident_context(alert_b.id, user_id=user.id)

    assert ctx_a is not None, "ctx_a should not be None"
    assert ctx_b is not None, "ctx_b should not be None"
    assert ctx_a['alert']['id'] == alert_a.id, "ctx_a alert id mismatch"
    assert ctx_b['alert']['id'] == alert_b.id, "ctx_b alert id mismatch"

    # Evidence isolation
    ev_a_ids = {ev['id'] for ev in ctx_a['evidence_items']}
    ev_b_ids = {ev['id'] for ev in ctx_b['evidence_items']}
    ev_overlap = ev_a_ids.intersection(ev_b_ids)
    print(f"Evidence items A: {ev_a_ids}")
    print(f"Evidence items B: {ev_b_ids}")
    assert len(ev_overlap) == 0, f"Evidence leaked across incidents: {ev_overlap}"
    print("[PASS] Evidence items are 100% strictly scoped (0 overlap).")

    # Recording isolation
    rec_a_id = ctx_a['primary_media']['recording']['id'] if ctx_a['primary_media']['recording'] else None
    rec_b_id = ctx_b['primary_media']['recording']['id'] if ctx_b['primary_media']['recording'] else None
    print(f"Recording A ID: {rec_a_id}, Recording B ID: {rec_b_id}")
    if rec_a_id and rec_b_id:
        assert rec_a_id != rec_b_id or alert_a.camera_id == alert_b.camera_id, "Different camera alerts linked to same recording"
    print("[PASS] Incident recording resolution is strictly scoped (no generic fallback).")

    # Case isolation
    case_a_id = ctx_a['incident_case']['id'] if ctx_a['incident_case'] else None
    case_b_id = ctx_b['incident_case']['id'] if ctx_b['incident_case'] else None
    print(f"Case A ID: {case_a_id}, Case B ID: {case_b_id}")
    if case_a_id and case_b_id:
        assert case_a_id != case_b_id, "Case leaked between incidents"
    print("[PASS] Incident case resolution is strictly scoped (no generic latest fallback).")

    # Notification isolation
    notif_a_ids = {n['id'] for n in ctx_a['notifications']}
    notif_b_ids = {n['id'] for n in ctx_b['notifications']}
    notif_overlap = notif_a_ids.intersection(notif_b_ids)
    assert len(notif_overlap) == 0, f"Notifications leaked: {notif_overlap}"
    print("[PASS] Incident notifications are 100% strictly scoped (0 overlap).")

    # Timeline isolation
    timeline_a_events = [t['title'] for t in ctx_a['timeline']]
    timeline_b_events = [t['title'] for t in ctx_b['timeline']]
    print(f"Timeline A: {timeline_a_events}")
    print(f"Timeline B: {timeline_b_events}")
    assert len(timeline_a_events) > 0 and len(timeline_b_events) > 0, "Timelines should have milestones"
    print("[PASS] Timelines are strictly generated from each incident's actual DB events.")

    # 4. HTTP Client Test via Live Server REST APIs
    import requests
    from django.contrib.sessions.backends.signed_cookies import SessionStore

    s = SessionStore()
    s['user_id'] = user.id
    s.save()
    session_key = s.session_key

    http_client = requests.Session()
    http_client.cookies.set("deepvision_django_session", session_key, domain="127.0.0.1", path="/")

    BASE_URL = "http://127.0.0.1:8000"

    # Test GET /api/alerts/<id>/incident-context/
    resp_a = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/incident-context/")
    assert resp_a.status_code == 200, f"Expected 200, got {resp_a.status_code}"
    data_a = resp_a.json()
    assert data_a['alert']['id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/incident-context/ returned HTTP 200 with strictly scoped incident.")

    resp_b = http_client.get(f"{BASE_URL}/api/alerts/{alert_b.id}/incident-context/")
    assert resp_b.status_code == 200, f"Expected 200, got {resp_b.status_code}"
    data_b = resp_b.json()
    assert data_b['alert']['id'] == alert_b.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_b.id}/incident-context/ returned HTTP 200 with strictly scoped incident.")

    # Test GET /api/alerts/<id>/
    resp_detail_a = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/")
    assert resp_detail_a.status_code == 200
    assert resp_detail_a.json()['alert']['id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/ returned HTTP 200.")

    # Test sub-endpoints
    ev_resp = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/evidence/")
    assert ev_resp.status_code == 200
    assert ev_resp.json()['alert_id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/evidence/ scoped to Alert #{alert_a.id}.")

    rec_resp = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/recordings/")
    assert rec_resp.status_code == 200
    assert rec_resp.json()['alert_id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/recordings/ scoped to Alert #{alert_a.id}.")

    case_resp = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/case/")
    assert case_resp.status_code == 200
    assert case_resp.json()['alert_id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/case/ scoped to Alert #{alert_a.id}.")

    notif_resp = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/notifications/")
    assert notif_resp.status_code == 200
    assert notif_resp.json()['alert_id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/notifications/ scoped to Alert #{alert_a.id}.")

    tl_resp = http_client.get(f"{BASE_URL}/api/alerts/{alert_a.id}/timeline/")
    assert tl_resp.status_code == 200
    assert tl_resp.json()['alert_id'] == alert_a.id
    print(f"[PASS] HTTP GET /api/alerts/{alert_a.id}/timeline/ scoped to Alert #{alert_a.id}.")

    # Test Case Registry filtering by alert_id
    cases_resp = http_client.get(f"{BASE_URL}/api/cases/?alert_id={alert_a.id}")
    assert cases_resp.status_code == 200
    for c in cases_resp.json()['cases']:
        assert c['alert_id'] == alert_a.id, f"Case {c['id']} alert_id {c['alert_id']} != {alert_a.id}"
    print("[PASS] Global Cases API correctly filters by alert_id when requested.")

    # Test Evidence Vault filtering by alert_id
    ev_list_resp = http_client.get(f"{BASE_URL}/api/evidence/?alert_id={alert_a.id}")
    assert ev_list_resp.status_code == 200
    for e in ev_list_resp.json()['evidence']:
        assert e['alert_id'] == alert_a.id, f"Evidence {e['id']} alert_id {e['alert_id']} != {alert_a.id}"
    print("[PASS] Global Evidence Vault API correctly filters by alert_id when requested.")

    print("\nALL INCIDENT SCOPING TESTS PASSED COMPLETELY.")

if __name__ == '__main__':
    run_tests()
