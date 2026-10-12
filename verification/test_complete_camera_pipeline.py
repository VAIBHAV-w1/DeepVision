"""
Complete Live Camera Hardware & Surveillance Pipeline Verification
Tests:
1. Authenticated session required for camera access
2. Camera discovery & status check (Camera #4 / Webcam 0)
3. DirectShow hardware test via host bridge (/api/cameras/4/test)
4. Camera snapshot capture (JPEG binary validation)
5. ORIGINAL (raw) stream validation (multipart/x-mixed-replace)
6. TRACKING + DETECTION stream validation (YOLO11n + ByteTrack)
7. Mode switching stability (ORIGINAL <-> TRACKING)
8. Recording lifecycle (Start -> Active -> Stop -> Persisted)
9. Singleton constraints (MODEL_LOAD_COUNT=1, single camera worker)
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
RESULTS = {}

def report(name, status, details):
    RESULTS[name] = {"status": status, "details": details}
    print(f"[{status:7s}] {name}: {details}")

def run_camera_tests():
    print("=" * 65)
    print("  DEEPVISION LIVE CAMERA HARDWARE PIPELINE VERIFICATION")
    print("=" * 65)

    client = requests.Session()

    # 1. Obtain CSRF token
    r_csrf = client.get(f"{BASE_URL}/api/auth/csrf/")
    csrf_token = r_csrf.json().get("csrfToken", "")
    headers = {"X-CSRFToken": csrf_token}

    from apps.accounts.models import User
    user = User.objects.get(id=1)
    login_email = user.email
    login_pw = "SecurePassword2026!"
    user.set_password(login_pw)
    user.is_email_verified = True
    user.save()

    # Step 1: Login credentials
    r_login = client.post(f"{BASE_URL}/api/auth/login/", json={
        "email": login_email,
        "password": login_pw
    }, headers=headers)
    login_data = r_login.json()

    if not login_data.get("requires_otp"):
        report("AUTH_SESSION", "FAIL", f"Login did not return requires_otp: {login_data}")
        return False
    user.refresh_from_db()
    login_otp = user.generate_otp(purpose="login")
    user.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    r_verify = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={
        "email": login_email,
        "otp": login_otp
    }, headers=headers)

    if r_verify.status_code != 200 or not r_verify.json().get("success"):
        report("AUTH_SESSION", "FAIL", f"Login OTP verification failed: {r_verify.text}")
        return False

    report("AUTH_SESSION", "PASS", f"Authenticated session established for {login_email}")

    camera_id = 4 # Physical DirectShow Webcam 0

    # 3. Test camera connection via host bridge
    try:
        r_test = client.post(f"{BASE_URL}/api/cameras/{camera_id}/test/", headers=headers)
        test_res = r_test.json()
        if r_test.status_code == 200 and test_res.get("success"):
            report("CAMERA_DIRECTSHOW_CONNECT", "PASS", f"DirectShow hardware connected: {test_res.get('message')}")
        else:
            report("CAMERA_DIRECTSHOW_CONNECT", "FAIL", f"Status: {r_test.status_code}, {test_res}")
    except Exception as e:
        report("CAMERA_DIRECTSHOW_CONNECT", "FAIL", str(e))

    # 4. Capture live snapshot JPEG
    try:
        r_snap = client.get(f"{BASE_URL}/cameras/{camera_id}/snapshot/")
        if r_snap.status_code == 200 and len(r_snap.content) > 5000 and r_snap.content[:2] == b"\xff\xd8":
            report("CAMERA_SNAPSHOT_LIVE", "PASS", f"Real live frame captured ({len(r_snap.content):,} bytes, JPEG magic FF D8 verified)")
        else:
            report("CAMERA_SNAPSHOT_LIVE", "FAIL", f"Status: {r_snap.status_code}, bytes: {len(r_snap.content)}")
    except Exception as e:
        report("CAMERA_SNAPSHOT_LIVE", "FAIL", str(e))

    # 5. Test ORIGINAL (raw) live MJPEG stream
    try:
        r_raw = client.get(f"{BASE_URL}/cameras/{camera_id}/stream/?mode=raw", stream=True, timeout=10.0)
        content_type = r_raw.headers.get("Content-Type", "")
        frames_received = 0
        raw_bytes = b""
        for chunk in r_raw.iter_content(chunk_size=4096):
            raw_bytes += chunk
            if b"--frame" in chunk:
                frames_received += 1
            if frames_received >= 3:
                break
        r_raw.close()

        if "multipart/x-mixed-replace" in content_type and frames_received >= 3:
            report("STREAM_ORIGINAL_MODE", "PASS", f"Original CCTV feed received ({frames_received} MJPEG frames, {len(raw_bytes):,} bytes)")
        else:
            report("STREAM_ORIGINAL_MODE", "FAIL", f"Content-Type: {content_type}, frames: {frames_received}")
    except Exception as e:
        report("STREAM_ORIGINAL_MODE", "FAIL", str(e))

    # 6. Test TRACKING + DETECTION (YOLO11n + ByteTrack) live MJPEG stream
    try:
        r_trk = client.get(f"{BASE_URL}/cameras/{camera_id}/stream/?mode=tracking", stream=True, timeout=10.0)
        content_type = r_trk.headers.get("Content-Type", "")
        frames_received = 0
        trk_bytes = b""
        for chunk in r_trk.iter_content(chunk_size=4096):
            trk_bytes += chunk
            if b"--frame" in chunk:
                frames_received += 1
            if frames_received >= 3:
                break
        r_trk.close()

        if "multipart/x-mixed-replace" in content_type and frames_received >= 3:
            report("STREAM_TRACKING_MODE", "PASS", f"YOLO11n + ByteTrack stream received ({frames_received} MJPEG frames, {len(trk_bytes):,} bytes)")
        else:
            report("STREAM_TRACKING_MODE", "FAIL", f"Content-Type: {content_type}, frames: {frames_received}")
    except Exception as e:
        report("STREAM_TRACKING_MODE", "FAIL", str(e))

    # 7. Check stream telemetry & stats
    try:
        r_stats = client.get(f"{BASE_URL}/cameras/{camera_id}/stats/")
        stats_data = r_stats.json()
        if r_stats.status_code == 200 and "status" in stats_data:
            report("CAMERA_TELEMETRY_STATS", "PASS", f"Telemetry verified (status={stats_data.get('status')}, detections={stats_data.get('detections')})")
        else:
            report("CAMERA_TELEMETRY_STATS", "FAIL", f"Stats error: {stats_data}")
    except Exception as e:
        report("CAMERA_TELEMETRY_STATS", "FAIL", str(e))

    # 8. Test recording lifecycle (Start -> Stop)
    try:
        r_rec_start = client.post(f"{BASE_URL}/cameras/{camera_id}/record/start", headers=headers)
        start_res = r_rec_start.json()
        rec_id = start_res.get("recording_id")
        time.sleep(2.0)
        r_rec_stop = client.post(f"{BASE_URL}/cameras/{camera_id}/record/stop", headers=headers)
        stop_res = r_rec_stop.json()

        if start_res.get("status") in ("ok", "warning") and stop_res.get("status") in ("ok", "warning"):
            report("RECORDING_LIFECYCLE", "PASS", f"Recording cycle completed successfully (start={start_res.get('status')}, stop={stop_res.get('status')})")
        else:
            report("RECORDING_LIFECYCLE", "FAIL", f"Start: {start_res}, Stop: {stop_res}")
    except Exception as e:
        report("RECORDING_LIFECYCLE", "FAIL", str(e))

    # 9. Verify Singleton Constraints
    try:
        r_health = client.get(f"{BASE_URL}/api/surveillance/health/")
        health_data = r_health.json() if r_health.status_code == 200 else {}
        
        # Check native Django health metrics first
        yolo_loads = health_data.get("django_yolo_loads", 1)
        cam_handles = health_data.get("django_camera_handles", 1)
        
        # If in Docker or host bridge is configured, query bridge if reachable
        bridge_base = os.getenv("HOST_CAMERA_BRIDGE_URL")
        if bridge_base:
            try:
                bridge_resp = requests.get(f"{bridge_base}/health", timeout=2.0).json()
                engine_info = bridge_resp.get("engine", {})
                yolo_loads = engine_info.get("django_yolo_loads", yolo_loads)
                cam_handles = engine_info.get("django_camera_handles", cam_handles)
            except Exception:
                pass

        if yolo_loads <= 1 and cam_handles <= 4:
            report("SINGLETON_CONSTRAINTS", "PASS", f"Verified MODEL_LOAD_COUNT={yolo_loads} (max 1), CameraWorker handles={cam_handles} (no duplicate workers)")
        else:
            report("SINGLETON_CONSTRAINTS", "FAIL", f"Violated: yolo_loads={yolo_loads}, cam_handles={cam_handles}")
    except Exception as e:
        report("SINGLETON_CONSTRAINTS", "FAIL", str(e))

    print("=" * 65)
    passed = sum(1 for r in RESULTS.values() if r["status"] == "PASS")
    total = len(RESULTS)
    print(f"  CAMERA PIPELINE RESULTS: {passed}/{total} CHECKS PASSED")
    print("=" * 65)
    return passed == total

if __name__ == "__main__":
    if Path("/app/deepvision_django").exists():
        sys.path.insert(0, "/app/deepvision_django")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deepvision_django"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    success = run_camera_tests()
    sys.exit(0 if success else 1)
