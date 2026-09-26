import os
import sys
import requests

sys.path.insert(0, "deepvision_django")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.sessions.backends.signed_cookies import SessionStore

s = SessionStore()
s['user_id'] = 2
s.save()
session_key = s.session_key

BASE_URL = "http://127.0.0.1:8000"
client = requests.Session()
client.cookies.set("deepvision_django_session", session_key, domain="127.0.0.1", path="/")

# Fetch CSRF token
csrf_resp = client.get(f"{BASE_URL}/api/auth/csrf/")
csrf_token = csrf_resp.json().get("csrfToken")
client.headers.update({"X-CSRFToken": csrf_token})
print(f"CSRF token obtained: {csrf_token[:10]}...")

# 1. Test api_alerts_list
list_resp = client.get(f"{BASE_URL}/api/alerts/?per_page=5")
print("Alerts list status:", list_resp.status_code)
assert list_resp.status_code == 200, f"Expected 200, got {list_resp.status_code}"
list_data = list_resp.json()
print("Total count:", list_data.get("total_count"), "Num pages:", list_data.get("num_pages"))
print("Metrics:", list_data.get("metrics"))

alerts = list_data.get("alerts", [])
assert len(alerts) > 0, "Expected at least 1 alert"
first_alert = alerts[0]
print("\nFirst alert summary:", first_alert)
alert_id = first_alert["id"]

# 2. Test api_alert_detail
detail_resp = client.get(f"{BASE_URL}/api/alerts/{alert_id}/")
print(f"\nAlert {alert_id} detail status:", detail_resp.status_code)
assert detail_resp.status_code == 200
detail_data = detail_resp.json()
print("Primary media:", detail_data.get("primary_media"))
print("AI Analysis:", detail_data.get("ai_analysis"))
print("Timeline entries count:", len(detail_data.get("timeline", [])))
for t in detail_data.get("timeline", []):
    print("  -", t["type"], ":", t["title"])
print("Incident Case:", detail_data.get("incident_case"))
print("Evidence Items count:", len(detail_data.get("evidence_items", [])))
print("Incident Notes count:", len(detail_data.get("incident_notes", [])))

# 3. Test note addition
note_resp = client.post(
    f"{BASE_URL}/api/alerts/{alert_id}/note/",
    json={"note": "Forensic inspection verified by SOC operator."}
)
print("\nAdd note response:", note_resp.status_code, note_resp.json())
assert note_resp.status_code == 200
assert note_resp.json().get("success") is True

# 4. Test case creation (or existing case return)
case_resp = client.post(
    f"{BASE_URL}/api/alerts/{alert_id}/case/",
    json={"title": f"Incident Investigation for Alert #{alert_id}", "priority": "HIGH"}
)
print("\nCreate case response:", case_resp.status_code, case_resp.json())
assert case_resp.status_code == 200
assert case_resp.json().get("success") is True

# 5. Test filter has_video
video_filter_resp = client.get(f"{BASE_URL}/api/alerts/?has_video=true&per_page=3")
print("\nFilter has_video count:", video_filter_resp.json().get("total_count"))
assert video_filter_resp.status_code == 200
for a in video_filter_resp.json().get("alerts", []):
    print("  Alert with video:", a["id"], a["title"], "has_video:", a["has_video"], "video_ev_id:", a["video_ev_id"])

# 6. Test detail for an alert with video
video_alerts = video_filter_resp.json().get("alerts", [])
if video_alerts:
    vid_alert_id = video_alerts[0]["id"]
    vid_detail_resp = client.get(f"{BASE_URL}/api/alerts/{vid_alert_id}/")
    v_data = vid_detail_resp.json()
    print(f"\nAlert {vid_alert_id} with video primary_media:", v_data.get("primary_media"))
    assert v_data.get("primary_media", {}).get("video") is not None
    assert v_data["primary_media"]["video"]["has_audio"] is False
    assert v_data["primary_media"]["video"]["audio_status"] == "unavailable"

print("\n>>> ALL UNIFIED ALERTS API CHECKS PASSED PERFECTLY! <<<")
