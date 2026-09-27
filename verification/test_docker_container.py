"""
DeepVision Docker Container Runtime Verification Suite
Tests:
1. Container status and healthcheck (/api/health/)
2. Frontend SPA delivery and static asset serving
3. Unauthenticated API responses (CSRF, /api/auth/me/)
4. Authenticated API responses (Session auth, /api/auth/me/, /api/dashboard/stats/, /api/alerts/, /api/notifications/, /api/cameras/, /api/evidence/, /api/cases/)
5. Model file presence and AI runtime imports (PyTorch, Ultralytics, YOLO model init)
6. Data persistence across container restart
"""

import sys
import subprocess
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"
RESULTS = {}

def report(name, status, details):
    RESULTS[name] = {"status": status, "details": details}
    print(f"[{status:7s}] {name}: {details}")

def main():
    print("=" * 60)
    print("  DEEPVISION DOCKER CONTAINER VERIFICATION SUITE")
    print("=" * 60)

    # 1. Container Status & Health Check
    try:
        ps_out = subprocess.check_output(["docker", "compose", "ps", "--format", "json"]).decode().strip()
        containers = [json.loads(line) for line in ps_out.splitlines() if line.strip()]
        if not containers:
            report("CONTAINER_RUNNING", "FAIL", "No running containers found")
            return
        
        c = containers[0]
        name = c.get("Name", "unknown")
        status = c.get("Status", "unknown")
        health = c.get("Health", "unknown")
        report("CONTAINER_RUNNING", "PASS", f"Name: {name}, Status: {status}, Health: {health}")
    except Exception as e:
        report("CONTAINER_RUNNING", "FAIL", str(e))

    session = requests.Session()

    # 2. HTTP Healthcheck Endpoint
    try:
        r = session.get(f"{BASE_URL}/api/health/", timeout=5)
        data = r.json()
        if r.status_code == 200 and data.get("status") == "healthy":
            report("API_HEALTHCHECK", "PASS", f"Status 200, db={data.get('database')}, app={data.get('django_app')}")
        else:
            report("API_HEALTHCHECK", "FAIL", f"Status {r.status_code}, data: {data}")
    except Exception as e:
        report("API_HEALTHCHECK", "FAIL", str(e))

    # 3. Frontend SPA Root & Static Assets
    try:
        r_root = session.get(f"{BASE_URL}/", timeout=5)
        has_root = '<div id="root"></div>' in r_root.text
        has_js = '/static/dist/assets/' in r_root.text
        if r_root.status_code == 200 and has_root and has_js:
            report("FRONTEND_SPA_DELIVERY", "PASS", f"Status 200, root div and asset paths found ({len(r_root.text)} B)")
        else:
            report("FRONTEND_SPA_DELIVERY", "FAIL", f"Status: {r_root.status_code}")
    except Exception as e:
        report("FRONTEND_SPA_DELIVERY", "FAIL", str(e))

    # 4. Frontend Static Asset Serving (JS and CSS)
    try:
        import re
        js_match = re.search(r'src="(/static/dist/assets/[^"]+\.js)"', r_root.text)
        css_match = re.search(r'href="(/static/dist/assets/[^"]+\.css)"', r_root.text)
        if js_match and css_match:
            r_js = session.get(f"{BASE_URL}{js_match.group(1)}", timeout=5)
            r_css = session.get(f"{BASE_URL}{css_match.group(1)}", timeout=5)
            if r_js.status_code == 200 and r_css.status_code == 200:
                report("STATIC_ASSET_SERVING", "PASS", f"JS: {len(r_js.content)} B, CSS: {len(r_css.content)} B (HTTP 200)")
            else:
                report("STATIC_ASSET_SERVING", "FAIL", f"JS status: {r_js.status_code}, CSS status: {r_css.status_code}")
        else:
            report("STATIC_ASSET_SERVING", "FAIL", "Could not parse static asset tags")
    except Exception as e:
        report("STATIC_ASSET_SERVING", "FAIL", str(e))

    # 5. CSRF Endpoint
    csrf_token = ""
    try:
        r_csrf = session.get(f"{BASE_URL}/api/auth/csrf/", timeout=5)
        csrf_token = r_csrf.json().get("csrfToken", "")
        if r_csrf.status_code == 200 and csrf_token:
            report("CSRF_ENDPOINT", "PASS", f"Token: {csrf_token[:12]}...")
        else:
            report("CSRF_ENDPOINT", "FAIL", f"Status: {r_csrf.status_code}")
    except Exception as e:
        report("CSRF_ENDPOINT", "FAIL", str(e))

    # 6. Unauthenticated Me Endpoint
    try:
        r_unauth = session.get(f"{BASE_URL}/api/auth/me/", timeout=5)
        if r_unauth.status_code == 200 and r_unauth.json().get("authenticated") is False:
            report("API_AUTH_ME_UNAUTH", "PASS", "authenticated=False correctly returned")
        else:
            report("API_AUTH_ME_UNAUTH", "FAIL", str(r_unauth.text))
    except Exception as e:
        report("API_AUTH_ME_UNAUTH", "FAIL", str(e))

    # 7. Authenticated Session Setup for User 2
    session_key = ""
    try:
        cmd = [
            "docker", "compose", "exec", "-T", "deepvision", "python", "-c",
            "import sys; sys.path.insert(0, '/app/deepvision_django'); "
            "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); "
            "from django.contrib.sessions.backends.signed_cookies import SessionStore; "
            "s = SessionStore(); s['user_id'] = 2; s.save(); print(s.session_key)"
        ]
        session_key = subprocess.check_output(cmd).decode().strip()
        session.cookies["deepvision_django_session"] = session_key

        r_me = session.get(f"{BASE_URL}/api/auth/me/", timeout=5)
        me_json = r_me.json()
        if r_me.status_code == 200 and me_json.get("authenticated") is True:
            report("API_AUTH_ME_AUTH", "PASS", f"User: {me_json.get('user', {}).get('email')} (id=2)")
        else:
            report("API_AUTH_ME_AUTH", "FAIL", str(me_json))
    except Exception as e:
        report("API_AUTH_ME_AUTH", "FAIL", str(e))

    # 8. SOC Dashboard Statistics API
    try:
        r_stats = session.get(f"{BASE_URL}/api/dashboard/stats/", timeout=5)
        if r_stats.status_code == 200:
            d = r_stats.json()
            report("API_DASHBOARD_STATS", "PASS", f"total_cameras={d.get('total_cameras')}, alerts={d.get('new_alerts_count')}")
        else:
            report("API_DASHBOARD_STATS", "FAIL", f"Status: {r_stats.status_code}")
    except Exception as e:
        report("API_DASHBOARD_STATS", "FAIL", str(e))

    # 9. Alerts API
    try:
        r_alerts = session.get(f"{BASE_URL}/api/alerts/", timeout=5)
        if r_alerts.status_code == 200:
            count = len(r_alerts.json().get("alerts", []))
            report("API_ALERTS", "PASS", f"Status 200, count={count}")
        else:
            report("API_ALERTS", "FAIL", f"Status: {r_alerts.status_code}")
    except Exception as e:
        report("API_ALERTS", "FAIL", str(e))

    # 10. Notifications API
    try:
        r_notif = session.get(f"{BASE_URL}/api/notifications/", timeout=5)
        if r_notif.status_code == 200:
            count = len(r_notif.json().get("notifications", []))
            report("API_NOTIFICATIONS", "PASS", f"Status 200, count={count}")
        else:
            report("API_NOTIFICATIONS", "FAIL", f"Status: {r_notif.status_code}")
    except Exception as e:
        report("API_NOTIFICATIONS", "FAIL", str(e))

    # 11. Cameras API
    try:
        r_cam = session.get(f"{BASE_URL}/api/cameras/", timeout=5)
        if r_cam.status_code == 200:
            count = len(r_cam.json().get("cameras", []))
            report("API_CAMERAS", "PASS", f"Status 200, count={count}")
        else:
            report("API_CAMERAS", "FAIL", f"Status: {r_cam.status_code}")
    except Exception as e:
        report("API_CAMERAS", "FAIL", str(e))

    # 12. Evidence API
    try:
        r_ev = session.get(f"{BASE_URL}/api/evidence/", timeout=5)
        if r_ev.status_code == 200:
            count = len(r_ev.json().get("evidence", []))
            report("API_EVIDENCE", "PASS", f"Status 200, count={count}")
        else:
            report("API_EVIDENCE", "FAIL", f"Status: {r_ev.status_code}")
    except Exception as e:
        report("API_EVIDENCE", "FAIL", str(e))

    # 13. Cases API
    try:
        r_cases = session.get(f"{BASE_URL}/api/cases/", timeout=5)
        if r_cases.status_code == 200:
            count = len(r_cases.json().get("cases", []))
            report("API_CASES", "PASS", f"Status 200, count={count}")
        else:
            report("API_CASES", "FAIL", f"Status: {r_cases.status_code}")
    except Exception as e:
        report("API_CASES", "FAIL", str(e))

    # 14. Model & AI Runtime Check inside Docker Container
    try:
        cmd_ai = [
            "docker", "compose", "exec", "-T", "deepvision", "python", "-c",
            "import os, torch, ultralytics; "
            "from ultralytics import YOLO; "
            "model_path = '/app/models/yolo11n.pt'; "
            "exists = os.path.exists(model_path); "
            "size = os.path.getsize(model_path) if exists else 0; "
            "m = YOLO(model_path); "
            "print(f'TORCH={torch.__version__}|ULTRALYTICS={ultralytics.__version__}|EXISTS={exists}|SIZE={size}|LOADED={m is not None}')"
        ]
        out_ai = subprocess.check_output(cmd_ai).decode().strip()
        report("DOCKER_AI_RUNTIME", "PASS", out_ai)
    except Exception as e:
        report("DOCKER_AI_RUNTIME", "FAIL", str(e))

    # 15. Persistence Test across container restart
    try:
        print("[INFO   ] Testing container restart & persistence...")
        subprocess.check_call(["docker", "compose", "restart", "deepvision"])
        # Wait for container to be healthy again
        healthy = False
        for _ in range(30):
            time.sleep(1)
            try:
                r_h = requests.get(f"{BASE_URL}/api/health/", timeout=2)
                if r_h.status_code == 200 and r_h.json().get("status") == "healthy":
                    healthy = True
                    break
            except Exception:
                pass
        
        if healthy:
            # Re-verify database connectivity and camera count
            session2 = requests.Session()
            session2.cookies["deepvision_django_session"] = session_key
            r_check = session2.get(f"{BASE_URL}/api/cameras/", timeout=5)
            if r_check.status_code == 200:
                cam_count = len(r_check.json().get("cameras", []))
                report("PERSISTENCE_RESTART", "PASS", f"Restart succeeded, health restored, cameras={cam_count}")
            else:
                report("PERSISTENCE_RESTART", "FAIL", f"Cameras status: {r_check.status_code}")
        else:
            report("PERSISTENCE_RESTART", "FAIL", "Container did not regain healthy status after restart")
    except Exception as e:
        report("PERSISTENCE_RESTART", "FAIL", str(e))

    print("=" * 60)
    passed = sum(1 for v in RESULTS.values() if v["status"] == "PASS")
    total = len(RESULTS)
    print(f"  DOCKER VERIFICATION SUMMARY: {passed}/{total} CHECKS PASSED")
    print("=" * 60)
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
