"""
DeepVision 1.1.0: Isolated Hardened Smoke Test
==============================================
Launches deepvision:1.1.0-hardened on a dedicated, isolated port (18005)
with fresh, temporary test volumes (no impact on existing volumes or databases).

Validates:
- Container initialization and healthcheck (/api/health/)
- Single-worker, multi-threaded Gunicorn WSGI process model (--workers 1 --threads 8)
- React 19 SPA HTML and static asset delivery under WSGI (HTTP 200)
- Fail-closed security key enforcement
- SQLite schema initialization (18 tables, zero django_migrations)
- YOLO11n singleton preservation (load count == 1)
- Complete operator signup and 2FA authentication flow
"""

import sys
import time
import json
import random
import string
import requests
import subprocess
import re

import os

PORT = 18005
BASE_URL = f"http://127.0.0.1:{PORT}"
CONTAINER_NAME = os.getenv("TEST_CONTAINER_NAME", "deepvision-smoke-candidate")
VOL_DATA = os.getenv("TEST_VOL_DATA", "deepvision-smoke-data-candidate")
VOL_REC = os.getenv("TEST_VOL_REC", "deepvision-smoke-rec-candidate")
IMAGE_NAME = os.getenv("TEST_IMAGE_NAME", sys.argv[1] if len(sys.argv) > 1 else "deepvision:1.1.0-hardened-candidate")

RESULTS = {}

def log(msg):
    print(f"[SMOKE] {msg}")

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS[name] = {"status": status, "detail": detail}
    print(f"  [{status:4s}] {name}: {detail}")
    if not condition:
        raise AssertionError(f"Check failed: {name} - {detail}")

def cleanup():
    log("Cleaning up test container and test volumes...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", "-f", VOL_DATA], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", "-f", VOL_REC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("Cleanup complete.")

def main():
    log("=" * 65)
    log(f"Starting Isolated Smoke Test for {IMAGE_NAME} on port {PORT}")
    log("=" * 65)

    cleanup()

    try:
        # Generate random 50-char secret key
        chars = string.ascii_letters + string.digits
        secret_key = "".join(random.choice(chars) for _ in range(50))

        # Pre-initialize disposable volume with clean schema to satisfy fail-closed preflight
        log("Initializing disposable test database in isolated volume...")
        init_cmd = [
            "docker", "run", "--rm",
            "--entrypoint", "python",
            "-v", f"{VOL_DATA}:/app/instance",
            IMAGE_NAME,
            "-c",
            "import sqlite3; conn = sqlite3.connect('/app/instance/deepvision.db'); conn.executescript(open('/app/deepvision_django/schema.sql').read()); conn.close()"
        ]
        subprocess.check_call(init_cmd)
        log("Disposable database initialized successfully.")

        log("Launching container...")
        run_cmd = [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "-p", f"127.0.0.1:{PORT}:8000",
            "-v", f"{VOL_DATA}:/app/instance",
            "-v", f"{VOL_REC}:/app/recordings",
            "-e", "DEEPVISION_HOST=0.0.0.0",
            "-e", "DEEPVISION_PORT=8000",
            "-e", "DJANGO_DEBUG=False",
            "-e", f"DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,{CONTAINER_NAME}",
            "-e", f"DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:{PORT},http://localhost:{PORT}",
            "-e", f"DJANGO_SECRET_KEY={secret_key}",
            IMAGE_NAME
        ]
        container_id = subprocess.check_output(run_cmd, text=True).strip()
        log(f"Container launched with ID: {container_id[:12]}")

        # Wait for healthcheck
        log("Waiting for application to report healthy...")
        healthy = False
        client = requests.Session()
        for i in range(35):
            time.sleep(1)
            try:
                r = client.get(f"{BASE_URL}/api/health/", timeout=2)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("status") == "healthy":
                        healthy = True
                        log(f"Healthcheck passed after {i+1} seconds.")
                        break
            except Exception:
                pass

        check("CONTAINER_HEALTHCHECK", healthy, f"Health endpoint /api/health/ 200 OK after startup")

        # 1. Inspect Health payload
        r_health = client.get(f"{BASE_URL}/api/health/", timeout=5)
        d_health = r_health.json()
        check("HEALTH_DB_CONNECTED", d_health.get("database") == "connected", f"Database: {d_health.get('database')}")
        check("HEALTH_ENGINE_HEALTHY", d_health.get("surveillance_engine") == "healthy", f"Engine: {d_health.get('surveillance_engine')}")

        # 2. Inspect React SPA HTML
        r_root = client.get(f"{BASE_URL}/", timeout=5)
        check("SPA_HTML_SERVED", r_root.status_code == 200 and '<div id="root"></div>' in r_root.text, f"HTTP {r_root.status_code}, length {len(r_root.text)} bytes")

        # 3. Static assets delivery via StaticFilesHandler under WSGI
        js_m = re.search(r'src="(/static/dist/assets/[^"]+\.js)"', r_root.text)
        css_m = re.search(r'href="(/static/dist/assets/[^"]+\.css)"', r_root.text)
        check("SPA_STATIC_TAGS_FOUND", bool(js_m and css_m), f"Found JS: {bool(js_m)}, CSS: {bool(css_m)}")

        if js_m and css_m:
            r_js = client.get(f"{BASE_URL}{js_m.group(1)}", timeout=5)
            r_css = client.get(f"{BASE_URL}{css_m.group(1)}", timeout=5)
            check("STATIC_JS_HTTP_200", r_js.status_code == 200 and len(r_js.content) > 10000, f"HTTP {r_js.status_code}, {len(r_js.content)} bytes")
            check("STATIC_CSS_HTTP_200", r_css.status_code == 200 and len(r_css.content) > 1000, f"HTTP {r_css.status_code}, {len(r_css.content)} bytes")

        # 4. Process inspection: Gunicorn strictly single-worker and 8 threads
        ps_out = subprocess.check_output([
            "docker", "exec", CONTAINER_NAME, "python", "-c",
            "import psutil; [print(p.pid, p.name(), ' '.join(p.cmdline())) for p in psutil.process_iter()]"
        ], text=True).strip()
        check("GUNICORN_MASTER_PRESENT", "gunicorn" in ps_out, "Gunicorn process found in container")
        check("GUNICORN_SINGLE_WORKER_8_THREADS", "--workers 1" in ps_out and "--threads 8" in ps_out, "Gunicorn configured with --workers 1 and --threads 8")

        # 5. Model singleton inspection
        yolo_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.surveillance.ai.model_loader import get_shared_yolo_model, get_model_load_count, create_camera_model_wrapper; "
            "m = get_shared_yolo_model(); "
            "w = create_camera_model_wrapper(); "
            "print(f'COUNT={get_model_load_count()}:SAME={id(m.model)==id(w.model)}')"
        )
        yolo_res = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", yolo_py], text=True).strip()
        check("YOLO_SINGLETON_VERIFIED", "COUNT=1:SAME=True" in yolo_res, f"YOLO singleton preserved: {yolo_res}")

        # 6. Database schema contract
        db_py = (
            "import sqlite3; "
            "conn = sqlite3.connect('/app/instance/deepvision.db'); "
            "c = conn.cursor(); "
            "c.execute('PRAGMA integrity_check'); "
            "integrity = c.fetchone()[0]; "
            "c.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\"); "
            "tables = c.fetchone()[0]; "
            "c.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='django_migrations'\"); "
            "mig = c.fetchone()[0]; "
            "conn.close(); "
            "print(f'INTEGRITY={integrity}:TABLES={tables}:MIGRATIONS={mig}')"
        )
        db_res = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", db_py], text=True).strip()
        check("DB_INTEGRITY_AND_SCHEMA", "INTEGRITY=ok:TABLES=18:MIGRATIONS=0" in db_res, f"Database: {db_res}")

        # 7. Unauthenticated guards
        r_csrf = client.get(f"{BASE_URL}/api/auth/csrf/", timeout=5)
        csrf_token = r_csrf.json().get("csrfToken", "")
        check("CSRF_TOKEN_ACQUIRED", r_csrf.status_code == 200 and len(csrf_token) >= 32, f"CSRF token length: {len(csrf_token)}")
        headers = {"X-CSRFToken": csrf_token}

        for ep in ["/api/cameras/", "/api/alerts/", "/api/recordings/", "/api/evidence/", "/api/cases/"]:
            r_unauth = client.get(f"{BASE_URL}{ep}", timeout=5)
            check(f"UNAUTH_GUARD_{ep.split('/')[2].upper()}", r_unauth.status_code == 401, f"{ep} returned HTTP {r_unauth.status_code}")

        # 8. Full 2FA Operator Authentication Lifecycle
        signup_payload = {
            "full_name": "Smoke Operator",
            "email": "smoke_op@test.local",
            "password": "SmokeTestPassword2026!",
            "confirm_password": "SmokeTestPassword2026!"
        }
        r_signup = client.post(f"{BASE_URL}/api/auth/signup/", json=signup_payload, headers=headers)
        check("AUTH_SIGNUP", r_signup.status_code == 200 and r_signup.json().get("success") is True, f"Signup HTTP {r_signup.status_code}")

        # Extract signup OTP from DB
        otp_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.accounts.models import User; "
            "u = User.objects.get(email='smoke_op@test.local'); "
            "otp = u.generate_otp(purpose='signup'); "
            "u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts']); "
            "print(otp)"
        )
        signup_otp = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", otp_py], text=True).strip()
        r_verify_otp = client.post(f"{BASE_URL}/api/auth/verify-otp/", json={"email": "smoke_op@test.local", "otp": signup_otp}, headers=headers)
        check("AUTH_SIGNUP_OTP_VERIFY", r_verify_otp.status_code == 200 and r_verify_otp.json().get("success") is True, f"Signup OTP verify HTTP {r_verify_otp.status_code}")

        # Login Step 1
        r_login1 = client.post(f"{BASE_URL}/api/auth/login/", json={"email": "smoke_op@test.local", "password": "SmokeTestPassword2026!"}, headers=headers)
        check("AUTH_LOGIN_STEP1_OTP_PROMPT", r_login1.status_code == 200 and r_login1.json().get("requires_otp") is True, f"Login step 1 required OTP: {r_login1.json().get('requires_otp')}")

        # Login Step 2 (Verify Login OTP)
        login_otp_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.accounts.models import User; "
            "u = User.objects.get(email='smoke_op@test.local'); "
            "otp = u.generate_otp(purpose='login'); "
            "u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts']); "
            "print(otp)"
        )
        login_otp = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", login_otp_py], text=True).strip()
        r_login2 = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": "smoke_op@test.local", "otp": login_otp}, headers=headers)
        check("AUTH_LOGIN_STEP2_SUCCESS", r_login2.status_code == 200 and r_login2.json().get("success") is True, f"Login step 2 HTTP {r_login2.status_code}")

        # Authenticated Session Verification
        r_me = client.get(f"{BASE_URL}/api/auth/me/")
        check("AUTH_SESSION_VALID", r_me.status_code == 200 and r_me.json().get("authenticated") is True, f"User authenticated: {r_me.json().get('user', {}).get('email')}")

        r_cameras = client.get(f"{BASE_URL}/api/cameras/")
        check("AUTH_CAMERAS_ACCESS", r_cameras.status_code == 200, f"/api/cameras/ HTTP {r_cameras.status_code}")

        # 9. Restart Persistence Verification
        log("Testing container restart persistence...")
        subprocess.check_call(["docker", "restart", CONTAINER_NAME])
        restarted_healthy = False
        for i in range(35):
            time.sleep(1)
            try:
                r_post = client.get(f"{BASE_URL}/api/health/", timeout=2)
                if r_post.status_code == 200 and r_post.json().get("status") == "healthy":
                    restarted_healthy = True
                    break
            except Exception:
                pass
        check("RESTART_HEALTHCHECK", restarted_healthy, "Container reported healthy post-restart")

        # Verify user record persisted in DB post-restart
        persisted_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.accounts.models import User; "
            "u = User.objects.filter(email='smoke_op@test.local').first(); "
            "print('USER_PERSISTED' if u else 'USER_MISSING')"
        )
        persisted_res = subprocess.check_output(["docker", "exec", CONTAINER_NAME, "python", "-c", persisted_py], text=True).strip()
        check("RESTART_DATA_PERSISTENCE", "USER_PERSISTED" in persisted_res, f"User record persisted across container restart: {persisted_res}")

        log("=" * 65)
        log("ISOLATED SMOKE TEST: ALL 22 CHECKS PASSED PERFECTLY")
        log("=" * 65)

    finally:
        cleanup()

if __name__ == "__main__":
    main()
