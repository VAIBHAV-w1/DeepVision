"""
Hardened Docker Container Full Verification
===========================================
Runs comprehensive verification against deepvision:1.1.0-hardened running on port 18002:
1. Gunicorn WSGI single worker process (workers=1, threads=8)
2. Healthcheck response
3. React SPA HTML delivery
4. Static assets (JS & CSS) served via StaticFilesHandler under Gunicorn (HTTP 200)
5. CSRF token generation
6. Protected endpoints rejection (HTTP 401)
7. Model singleton (MODEL_LOAD_COUNT == 1)
8. SQLite database contract (18 tables, zero django_migrations, integrity check OK)
9. Operator signup & authentication flow
"""

import sys
import requests
import subprocess
import re

BASE = "http://127.0.0.1:18002"
CONTAINER = "deepvision-hardened-test"

def check(name, condition, detail):
    status = "PASS" if condition else "FAIL"
    print(f"[{status:4s}] {name}: {detail}")
    assert condition, f"FAILED: {name} - {detail}"

def main():
    print("=" * 65)
    print("  VERIFYING HARDENED DOCKER CONTAINER ON PORT 18002")
    print("=" * 65)

    client = requests.Session()

    # 1. Healthcheck
    r_health = client.get(f"{BASE}/api/health/", timeout=5)
    d_health = r_health.json()
    check("HEALTHCHECK_STATUS_200", r_health.status_code == 200, f"HTTP {r_health.status_code}")
    check("HEALTHCHECK_STATUS_HEALTHY", d_health.get("status") == "healthy", f"Status: {d_health.get('status')}")
    check("HEALTHCHECK_DATABASE_CONNECTED", d_health.get("database") == "connected", f"DB: {d_health.get('database')}")
    check("HEALTHCHECK_ENGINE_HEALTHY", d_health.get("surveillance_engine") == "healthy", f"Engine: {d_health.get('surveillance_engine')}")

    # 2. React SPA HTML
    r_root = client.get(f"{BASE}/", timeout=5)
    check("SPA_HTML_DELIVERY", r_root.status_code == 200 and '<div id="root"></div>' in r_root.text, f"HTTP {r_root.status_code}, {len(r_root.text)} bytes")

    # 3. Static assets via StaticFilesHandler under Gunicorn
    js_m = re.search(r'src="(/static/dist/assets/[^"]+\.js)"', r_root.text)
    css_m = re.search(r'href="(/static/dist/assets/[^"]+\.css)"', r_root.text)
    check("STATIC_TAGS_FOUND", bool(js_m and css_m), f"JS tag: {bool(js_m)}, CSS tag: {bool(css_m)}")

    if js_m and css_m:
        r_js = client.get(f"{BASE}{js_m.group(1)}", timeout=5)
        r_css = client.get(f"{BASE}{css_m.group(1)}", timeout=5)
        check("STATIC_JS_HTTP_200", r_js.status_code == 200 and len(r_js.content) > 10000, f"JS bundle: HTTP {r_js.status_code}, {len(r_js.content)} bytes")
        check("STATIC_CSS_HTTP_200", r_css.status_code == 200 and len(r_css.content) > 1000, f"CSS bundle: HTTP {r_css.status_code}, {len(r_css.content)} bytes")

    # 4. CSRF
    r_csrf = client.get(f"{BASE}/api/auth/csrf/", timeout=5)
    csrf_token = r_csrf.json().get("csrfToken", "")
    check("CSRF_TOKEN_ACQUISITION", r_csrf.status_code == 200 and len(csrf_token) >= 32, f"HTTP {r_csrf.status_code}, length {len(csrf_token)}")
    headers = {"X-CSRFToken": csrf_token}

    # 5. Protected endpoints unauthenticated
    for ep in ["/api/cameras/", "/api/alerts/", "/api/recordings/", "/api/evidence/", "/api/cases/"]:
        r_unauth = client.get(f"{BASE}{ep}", timeout=5)
        check(f"UNAUTH_GUARD_{ep.split('/')[2]}", r_unauth.status_code == 401, f"{ep} returned HTTP {r_unauth.status_code}")

    # 6. Process inspection in container: Gunicorn running with 1 worker and gthread
    ps_out = subprocess.check_output([
        "docker", "exec", CONTAINER, "python", "-c",
        "import psutil; [print(p.pid, p.name(), ' '.join(p.cmdline())) for p in psutil.process_iter()]"
    ], text=True).strip()
    check("GUNICORN_MASTER_RUNNING", "gunicorn: master" in ps_out or "gunicorn" in ps_out, "Gunicorn process found in container")
    check("GUNICORN_SINGLE_WORKER_THREADED", "--workers 1" in ps_out and "--threads 8" in ps_out, "Gunicorn running strictly with --workers 1 and --threads 8")

    # 7. Model singleton and load count in container
    yolo_py = """
import sys, os, django
sys.path.insert(0, '/app/deepvision_django')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_model_load_count, create_camera_model_wrapper
m = get_shared_yolo_model()
w = create_camera_model_wrapper()
print(f"COUNT={get_model_load_count()}:SAME={id(m.model)==id(w.model)}")
"""
    yolo_res = subprocess.check_output(["docker", "exec", CONTAINER, "python", "-c", yolo_py], text=True).strip()
    check("YOLO_SINGLETON_LOAD_COUNT_1", "COUNT=1:SAME=True" in yolo_res, f"YOLO singleton preserved: {yolo_res}")

    # 8. Database integrity and table count in isolated volume
    db_py = """
import sqlite3
conn = sqlite3.connect('/app/instance/deepvision.db')
c = conn.cursor()
c.execute("PRAGMA integrity_check")
integrity = c.fetchone()[0]
c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
tables = c.fetchone()[0]
c.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='django_migrations'")
mig = c.fetchone()[0]
conn.close()
print(f"INTEGRITY={integrity}:TABLES={tables}:MIGRATIONS={mig}")
"""
    db_res = subprocess.check_output(["docker", "exec", CONTAINER, "python", "-c", db_py], text=True).strip()
    check("DATABASE_INTEGRITY_OK", "INTEGRITY=ok" in db_res, f"SQLite integrity check passed ({db_res})")
    check("DATABASE_18_TABLES", "TABLES=18" in db_res, f"18 tables present ({db_res})")
    check("DATABASE_ZERO_MIGRATIONS", "MIGRATIONS=0" in db_res, f"Zero django_migrations ({db_res})")

    # 9. Signup in isolated volume
    signup_payload = {
        "full_name": "Hardened Operator",
        "email": "hardened_op@audit.test",
        "password": "HardenedPass2026!",
        "confirm_password": "HardenedPass2026!"
    }
    r_sign = client.post(f"{BASE}/api/auth/signup/", json=signup_payload, headers=headers)
    check("OPERATOR_SIGNUP_SUCCESS", r_sign.status_code == 200 and r_sign.json().get("success") is True, f"Signup HTTP {r_sign.status_code}: {r_sign.json()}")

    # 10. Verify signup OTP
    otp_py = """
import sys, os, django
sys.path.insert(0, '/app/deepvision_django')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import User
u = User.objects.get(email='hardened_op@audit.test')
otp = u.generate_otp(purpose='signup')
u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts'])
print(otp)
"""
    otp = subprocess.check_output(["docker", "exec", CONTAINER, "python", "-c", otp_py], text=True).strip()
    r_ver = client.post(f"{BASE}/api/auth/verify-otp/", json={"email": "hardened_op@audit.test", "otp": otp}, headers=headers)
    check("OTP_VERIFICATION_SUCCESS", r_ver.status_code == 200 and r_ver.json().get("success") is True, f"OTP HTTP {r_ver.status_code}: {r_ver.json()}")

    # 11. Login Step 1
    r_log1 = client.post(f"{BASE}/api/auth/login/", json={"email": "hardened_op@audit.test", "password": "HardenedPass2026!"}, headers=headers)
    check("LOGIN_STEP1_OTP_REQUIRED", r_log1.status_code == 200 and r_log1.json().get("requires_otp") is True, f"Login Step 1: {r_log1.json()}")

    # 12. Verify Login OTP Step 2
    login_otp_py = """
import sys, os, django
sys.path.insert(0, '/app/deepvision_django')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import User
u = User.objects.get(email='hardened_op@audit.test')
otp = u.generate_otp(purpose='login')
u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts'])
print(otp)
"""
    login_otp = subprocess.check_output(["docker", "exec", CONTAINER, "python", "-c", login_otp_py], text=True).strip()
    r_log2 = client.post(f"{BASE}/api/auth/verify-login-otp/", json={"email": "hardened_op@audit.test", "otp": login_otp}, headers=headers)
    check("LOGIN_STEP2_SUCCESS", r_log2.status_code == 200 and r_log2.json().get("success") is True, f"Login Step 2: {r_log2.json()}")

    # 13. Authenticated API access
    r_me = client.get(f"{BASE}/api/auth/me/")
    check("AUTHENTICATED_ME_ENDPOINT", r_me.status_code == 200 and r_me.json().get("authenticated") is True, f"/api/auth/me/: {r_me.json().get('user')}")

    r_cams_auth = client.get(f"{BASE}/api/cameras/")
    check("AUTHENTICATED_CAMERAS_API", r_cams_auth.status_code == 200, f"/api/cameras/ HTTP {r_cams_auth.status_code}")

    r_dash_auth = client.get(f"{BASE}/api/dashboard/stats/")
    check("AUTHENTICATED_DASHBOARD_STATS", r_dash_auth.status_code == 200, f"/api/dashboard/stats/ HTTP {r_dash_auth.status_code}")

    print("\n" + "=" * 65)
    print("  ALL HARDENED DOCKER PRODUCTION CHECKS COMPLETED SUCCESSFULLY")
    print("=" * 65)

if __name__ == "__main__":
    main()
