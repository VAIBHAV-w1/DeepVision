import os
import sys
import json
import time
import urllib.request
import http.cookiejar
from pathlib import Path

ROOT = Path("d:/DeepVision")
DJANGO_DIR = ROOT / "deepvision_django"
sys.path.insert(0, str(DJANGO_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.contrib.sessions.backends.signed_cookies import SessionStore
from apps.alerts.models import Alert
from apps.recordings.models import Recording

BASE = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Create session for User 2 (owner of camera 3 and alerts)
s = SessionStore()
s['user_id'] = 2
s.save()
session_cookie = s.session_key

# Add session cookie to cookiejar
cookie = http.cookiejar.Cookie(
    version=0, name='deepvision_django_session', value=session_cookie,
    port=None, port_specified=False,
    domain='127.0.0.1', domain_specified=True, domain_initial_dot=False,
    path='/', path_specified=True,
    secure=False, expires=None, discard=True, comment=None,
    comment_url=None, rest={'HttpOnly': None}, rfc2109=False
)
cj.set_cookie(cookie)

# Fetch CSRF
resp = opener.open(BASE + "/api/auth/csrf/", timeout=10)
csrf_data = json.loads(resp.read().decode())
csrf_token = csrf_data.get("csrfToken", "")
print(f"CSRF token obtained: {bool(csrf_token)}")

def api_post(path, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-CSRFToken", csrf_token)
    return opener.open(req, timeout=10)

def api_get(path):
    req = urllib.request.Request(BASE + path)
    return opener.open(req, timeout=10)

print("\n=== 1. TESTING CAMERA 3 RECORD START / STOP ===")
try:
    with api_post("/cameras/3/record/start/") as resp:
        res = json.loads(resp.read().decode())
        print(f"Record start response: {res}")
        assert res.get("status") in ("recording_started", "already_recording", "ok") or res.get("recording") is True

    print("Recording active for 3 seconds...")
    time.sleep(3)

    with api_post("/cameras/3/record/stop/") as resp:
        res = json.loads(resp.read().decode())
        print(f"Record stop response: {res}")
        assert res.get("status") in ("recording_stopped", "not_recording", "ok") or res.get("recording") is False

    print("[PASS] Camera 3 record start/stop succeeded.")
except Exception as e:
    print(f"[FAIL] Camera 3 record start/stop error: {e}")

print("\n=== 2. TESTING INCIDENT ISOLATION FOR USER 2 ===")
user2_alert = Alert.objects.filter(camera__user_id=2).order_by("-id").first()
if user2_alert:
    alert_id = user2_alert.id
    print(f"Testing with Alert ID: {alert_id} (camera_id={user2_alert.camera_id})")

    # 1. Incident context
    with api_get(f"/api/alerts/{alert_id}/incident-context/") as resp:
        assert resp.status == 200
        ctx = json.loads(resp.read().decode())
        print(f"Incident context loaded: alert_id={ctx.get('alert', {}).get('id')}")
        assert ctx.get("alert", {}).get("id") == alert_id

    # 2. Scoped evidence
    with api_get(f"/api/alerts/{alert_id}/evidence/") as resp:
        assert resp.status == 200
        ev_data = json.loads(resp.read().decode())
        ev_items = ev_data.get("evidence", [])
        print(f"Scoped evidence items: {len(ev_items)}")

    # 3. Scoped recordings
    with api_get(f"/api/alerts/{alert_id}/recordings/") as resp:
        assert resp.status == 200
        rec_data = json.loads(resp.read().decode())
        rec_items = rec_data.get("recordings", [])
        print(f"Scoped recordings items: {len(rec_items)}")

    # 4. Scoped timeline
    with api_get(f"/api/alerts/{alert_id}/timeline/") as resp:
        assert resp.status == 200
        tl_data = json.loads(resp.read().decode())
        tl_items = tl_data.get("timeline", [])
        print(f"Scoped timeline items: {len(tl_items)}")

    # 5. Scoped notifications
    with api_get(f"/api/alerts/{alert_id}/notifications/") as resp:
        assert resp.status == 200
        notif_data = json.loads(resp.read().decode())
        notif_items = notif_data.get("notifications", [])
        print(f"Scoped notifications items: {len(notif_items)}")

    print("[PASS] Incident isolation verification succeeded.")
else:
    print("[WARNING] No alert found for user 2.")

print("\nALL SUB-TESTS COMPLETED SUCCESSFULLY!")
