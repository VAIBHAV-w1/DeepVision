import os
import sys
import json
import urllib.request
from pathlib import Path

ROOT = Path("d:/DeepVision")
DJANGO_DIR = ROOT / "deepvision_django"
sys.path.insert(0, str(DJANGO_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.contrib.sessions.backends.signed_cookies import SessionStore

# Create session for user 2 (owns 894 recordings)
s = SessionStore()
s['user_id'] = 2
s.save()
session_cookie = s.session_key
auth_cookie = f"deepvision_django_session={session_cookie}"

def api_get(path):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        headers={"Cookie": auth_cookie, "Accept": "application/json"}
    )
    return urllib.request.urlopen(req, timeout=10)

# Test 1: Page 1 with per_page=12
with api_get("/api/recordings/?page=1&per_page=12") as resp:
    assert resp.status == 200, f"Expected 200, got {resp.status}"
    data = json.loads(resp.read().decode('utf-8'))
    print("Total recordings in DB:", data["total_count"])
    print("Num pages:", data["num_pages"])
    print("Current page:", data["current_page"])
    print("Has next:", data["has_next"])
    print("Returned items:", len(data["recordings"]))
    assert data["total_count"] >= 800, "User 2 should have >= 800 recordings"
    assert data["num_pages"] > 50, "Should have > 50 pages of recordings"
    assert data["has_next"] is True, "Page 1 should have next page"

    cont_recs = [r for r in data["recordings"] if r["file_exists"]]
    print(f"Valid recordings on page 1: {len(cont_recs)}")
    for cr in cont_recs[:5]:
        print(f"  ID {cr['id']} ({cr['filename']}): file_exists={cr['file_exists']}, size={cr['formatted_size']}")

# Test 2: HTTP 206 streaming for a continuous recording
rec_id = cont_recs[0]["id"]
req_range = urllib.request.Request(
    f"http://127.0.0.1:8000/recordings/{rec_id}/view/",
    headers={"Cookie": auth_cookie, "Range": "bytes=0-1024"}
)
with urllib.request.urlopen(req_range, timeout=10) as resp_media:
    print(f"HTTP 206 playback for continuous recording {rec_id}: status={resp_media.status}, range={resp_media.getheader('Content-Range')}, content_type={resp_media.getheader('Content-Type')}")
    assert resp_media.status == 206, f"Expected 206, got {resp_media.status}"
    assert "video/mp4" in resp_media.getheader("Content-Type")

# Test 3: Anomaly type filter and HTTP 206 on an anomaly recording
with api_get("/api/recordings/?type=anomaly&page=1&per_page=5") as resp_anom:
    data_anom = json.loads(resp_anom.read().decode('utf-8'))
    print("Total anomaly recordings:", data_anom["total_count"])
    assert data_anom["total_count"] > 800, "Should have > 800 anomaly recordings"
    ev_rec = data_anom["recordings"][0]
    print(f"Top anomaly recording: ID {ev_rec['id']}, exists={ev_rec['file_exists']}, size={ev_rec['formatted_size']}")
    assert ev_rec["file_exists"] is True, f"Anomaly recording {ev_rec['id']} should exist on disk!"

    # Test HTTP 206 on anomaly clip
    req_anom_range = urllib.request.Request(
        f"http://127.0.0.1:8000/recordings/{ev_rec['id']}/view/",
        headers={"Cookie": auth_cookie, "Range": "bytes=0-1024"}
    )
    with urllib.request.urlopen(req_anom_range, timeout=10) as resp_ev:
        print(f"HTTP 206 playback for anomaly recording {ev_rec['id']}: status={resp_ev.status}, range={resp_ev.getheader('Content-Range')}")
        assert resp_ev.status == 206

# Test 4: Continuous type filter
with api_get("/api/recordings/?type=continuous") as resp_cont:
    data_cont = json.loads(resp_cont.read().decode('utf-8'))
    print("Total continuous recordings:", data_cont["total_count"])
    assert data_cont["total_count"] > 0, "Should have continuous recordings"

print("ALL RECORDINGS API CHECKS PASSED!")
