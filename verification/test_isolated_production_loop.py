"""
DeepVision 1.1.0 — Isolated Production Verification & Persistence Loop
======================================================================
Executes Phases 4 and 5 of the production verification loop against
deepvision:1.1.0-hardened on an isolated loopback port (18006).

Validates:
1. Production container launch using Gunicorn WSGI (1 worker, 8 threads).
2. Absence of development server warning and unapplied migrations warning.
3. Health check, React SPA delivery, and static assets under Gunicorn.
4. Database initialization (18 custom tables, 0 django_migrations, integrity OK).
5. Complete 2FA operator authentication lifecycle (signup -> OTP -> login step 1 -> OTP -> session).
6. Protected API rejection (HTTP 401 unauthenticated) & authorized API access.
7. YOLO11n singleton preservation (load count == 1, shared weights).
8. Data persistence across container stop and restart (Phase 5).
9. Safe, clean disposal of only test resources in cleanup trap.
"""

import sys
import time
import json
import random
import string
import requests
import subprocess
import re

PORT = 18006
BASE_URL = f"http://127.0.0.1:{PORT}"
CONTAINER_NAME = "deepvision-prod-verify"
VOL_DATA = "deepvision-verify-data"
VOL_REC = "deepvision-verify-rec"
IMAGE_NAME = "deepvision:1.1.0-hardened"

RESULTS = {}

def log(msg):
    print(f"[VERIFY] {msg}")

def check_out(cmd):
    return subprocess.check_output(cmd, encoding="utf-8", errors="replace").strip()

def record(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS[name] = {"status": status, "detail": detail}
    print(f"  [{status:4s}] {name}: {detail}")
    if not condition:
        raise AssertionError(f"Check failed: {name} - {detail}")

def cleanup():
    log("Cleaning up test container and disposable test volumes...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", "-f", VOL_DATA], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", "-f", VOL_REC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("Disposable test cleanup complete.")

def main():
    log("=" * 70)
    log(f"Starting Isolated Production & Persistence Loop on port {PORT}")
    log("=" * 70)

    cleanup()

    try:
        # Generate random 50-character high-entropy secret key
        chars = string.ascii_letters + string.digits
        secret_key = "".join(random.choice(chars) for _ in range(50))

        log("Launching hardened container in isolated test environment...")
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
        container_id = check_out(run_cmd)
        log(f"Container launched with ID: {container_id[:12]}")

        # Wait for healthcheck
        log("Waiting for container to report healthy...")
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
                        log(f"Container healthy after {i+1} seconds.")
                        break
            except Exception:
                pass

        record("CONTAINER_HEALTHY", healthy, "Health endpoint /api/health/ 200 OK after launch")

        # 1. Health payload
        r_health = client.get(f"{BASE_URL}/api/health/", timeout=5)
        d_health = r_health.json()
        record("HEALTH_DB_CONNECTED", d_health.get("database") == "connected", f"Database: {d_health.get('database')}")
        record("HEALTH_ENGINE_HEALTHY", d_health.get("surveillance_engine") == "healthy", f"Engine: {d_health.get('surveillance_engine')}")

        # 2. Process inspection: Gunicorn strictly single-worker and 8 threads
        ps_out = check_out([
            "docker", "exec", CONTAINER_NAME, "python", "-c",
            "import psutil; [print(p.pid, p.name(), ' '.join(p.cmdline())) for p in psutil.process_iter()]"
        ])
        record("GUNICORN_MASTER_ACTIVE", "gunicorn" in ps_out, "Gunicorn process found in container")
        record("GUNICORN_SINGLE_WORKER_8_THREADS", "--workers 1" in ps_out and "--threads 8" in ps_out, "Gunicorn configured with --workers 1 and --threads 8")

        # 3. Startup log analysis: Confirm absence of dev server and migration warnings
        logs_out = check_out(["docker", "logs", CONTAINER_NAME])
        record("LOGS_NO_DEV_SERVER_WARNING", "Starting development server" not in logs_out, "Development server warning is absent from logs")
        record("LOGS_NO_UNAPPLIED_MIGRATIONS", "unapplied migration" not in logs_out.lower(), "Unapplied migrations warning is absent from logs")
        record("LOGS_GUNICORN_STARTED", "gunicorn" in logs_out.lower(), "Gunicorn launch confirmed in container logs")

        # 4. React SPA HTML & static assets under WSGI
        r_root = client.get(f"{BASE_URL}/", timeout=5)
        record("SPA_HTML_SERVED", r_root.status_code == 200 and '<div id="root"></div>' in r_root.text, f"HTTP 200, length {len(r_root.text)} bytes")

        js_m = re.search(r'src="(/static/dist/assets/[^"]+\.js)"', r_root.text)
        css_m = re.search(r'href="(/static/dist/assets/[^"]+\.css)"', r_root.text)
        record("SPA_STATIC_TAGS_FOUND", bool(js_m and css_m), f"Found JS tag: {bool(js_m)}, CSS tag: {bool(css_m)}")

        if js_m and css_m:
            r_js = client.get(f"{BASE_URL}{js_m.group(1)}", timeout=5)
            r_css = client.get(f"{BASE_URL}{css_m.group(1)}", timeout=5)
            record("STATIC_JS_HTTP_200", r_js.status_code == 200 and len(r_js.content) > 10000, f"HTTP 200, {len(r_js.content)} bytes")
            record("STATIC_CSS_HTTP_200", r_css.status_code == 200 and len(r_css.content) > 1000, f"HTTP 200, {len(r_css.content)} bytes")

        # 5. Database contract
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
        db_res = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", db_py])
        record("DB_CONTRACT_INITIALIZED", "INTEGRITY=ok:TABLES=18:MIGRATIONS=0" in db_res, f"Database: {db_res}")

        # 6. Model singleton
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
        yolo_res = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", yolo_py])
        record("YOLO_SINGLETON_VERIFIED", "COUNT=1:SAME=True" in yolo_res, f"YOLO singleton preserved: {yolo_res}")

        # 7. Unauthenticated guards
        r_csrf = client.get(f"{BASE_URL}/api/auth/csrf/", timeout=5)
        csrf_token = r_csrf.json().get("csrfToken", "")
        record("CSRF_TOKEN_ACQUIRED", r_csrf.status_code == 200 and len(csrf_token) >= 32, f"CSRF token length: {len(csrf_token)}")
        headers = {"X-CSRFToken": csrf_token}

        for ep in ["/api/cameras/", "/api/alerts/", "/api/recordings/", "/api/evidence/", "/api/cases/"]:
            r_unauth = client.get(f"{BASE_URL}{ep}", timeout=5)
            record(f"UNAUTH_GUARD_{ep.split('/')[2].upper()}", r_unauth.status_code == 401, f"{ep} returned HTTP {r_unauth.status_code}")

        # 8. Full 2FA Authentication Flow
        signup_payload = {
            "full_name": "Production Verification Operator",
            "email": "prod_op@verify.local",
            "password": "VerifyPassword2026!",
            "confirm_password": "VerifyPassword2026!"
        }
        r_signup = client.post(f"{BASE_URL}/api/auth/signup/", json=signup_payload, headers=headers)
        record("AUTH_SIGNUP", r_signup.status_code == 200 and r_signup.json().get("success") is True, f"Signup HTTP {r_signup.status_code}")

        # Extract signup OTP
        otp_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.accounts.models import User; "
            "u = User.objects.get(email='prod_op@verify.local'); "
            "otp = u.generate_otp(purpose='signup'); "
            "u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts']); "
            "print(otp)"
        )
        signup_otp = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", otp_py])
        r_verify_otp = client.post(f"{BASE_URL}/api/auth/verify-otp/", json={"email": "prod_op@verify.local", "otp": signup_otp}, headers=headers)
        record("AUTH_SIGNUP_OTP_VERIFY", r_verify_otp.status_code == 200 and r_verify_otp.json().get("success") is True, f"Signup OTP verify HTTP {r_verify_otp.status_code}")

        # Login Step 1
        r_login1 = client.post(f"{BASE_URL}/api/auth/login/", json={"email": "prod_op@verify.local", "password": "VerifyPassword2026!"}, headers=headers)
        record("AUTH_LOGIN_STEP1_OTP_PROMPT", r_login1.status_code == 200 and r_login1.json().get("requires_otp") is True, f"Login step 1 required OTP: {r_login1.json().get('requires_otp')}")

        # Login Step 2 (Verify Login OTP)
        login_otp_py = (
            "import sys, os, django; "
            "sys.path.insert(0, '/app/deepvision_django'); "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from apps.accounts.models import User; "
            "u = User.objects.get(email='prod_op@verify.local'); "
            "otp = u.generate_otp(purpose='login'); "
            "u.save(update_fields=['email_otp_hash', 'email_otp_expires_at', 'email_otp_sent_at', 'email_otp_attempts']); "
            "print(otp)"
        )
        login_otp = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", login_otp_py])
        r_login2 = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": "prod_op@verify.local", "otp": login_otp}, headers=headers)
        record("AUTH_LOGIN_STEP2_SUCCESS", r_login2.status_code == 200 and r_login2.json().get("success") is True, f"Login step 2 HTTP {r_login2.status_code}")

        # Authenticated Session Verification
        r_me = client.get(f"{BASE_URL}/api/auth/me/")
        record("AUTH_SESSION_VALID", r_me.status_code == 200 and r_me.json().get("authenticated") is True, f"User authenticated: {r_me.json().get('user', {}).get('email')}")

        r_cameras = client.get(f"{BASE_URL}/api/cameras/")
        record("AUTH_CAMERAS_ACCESS", r_cameras.status_code == 200, f"/api/cameras/ HTTP {r_cameras.status_code}")

        # =========================================================================
        # PHASE 5 — PERSISTENCE VERIFICATION ACROSS CONTAINER RESTART
        # =========================================================================
        log("-" * 65)
        log("Phase 5: Verifying Data Persistence Across Container Stop and Restart...")
        log("-" * 65)

        # 1. Verify User Count before restart in test volume
        count_py = (
            "import sqlite3; "
            "conn = sqlite3.connect('/app/instance/deepvision.db'); "
            "c = conn.cursor(); "
            "c.execute(\"SELECT count(*) FROM users WHERE email='prod_op@verify.local'\"); "
            "cnt = c.fetchone()[0]; "
            "conn.close(); "
            "print(f'USER_EXISTS={cnt}')"
        )
        pre_restart = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", count_py])
        record("PRE_RESTART_USER_PERSISTED", "USER_EXISTS=1" in pre_restart, f"User persisted in DB before restart ({pre_restart})")

        # 2. Stop container
        log("Stopping test container...")
        subprocess.check_call(["docker", "stop", CONTAINER_NAME])

        # 3. Restart container
        log("Restarting test container (re-attaching same named volumes)...")
        subprocess.check_call(["docker", "start", CONTAINER_NAME])

        # 4. Wait for healthy status again
        restarted_healthy = False
        for i in range(30):
            time.sleep(1)
            try:
                r = client.get(f"{BASE_URL}/api/health/", timeout=2)
                if r.status_code == 200 and r.json().get("status") == "healthy":
                    restarted_healthy = True
                    log(f"Container healthy again after restart ({i+1} seconds).")
                    break
            except Exception:
                pass

        record("POST_RESTART_CONTAINER_HEALTHY", restarted_healthy, "Container healthy after restart")

        # 5. Verify data persisted in volume across restart
        post_restart = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", count_py])
        record("POST_RESTART_USER_PERSISTED", "USER_EXISTS=1" in post_restart, f"User preserved in named volume after restart ({post_restart})")

        # 6. Verify named volume mounts
        inspect_mounts = check_out([
            "docker", "inspect", CONTAINER_NAME,
            "--format", "{{range .Mounts}}{{.Name}}:{{.Destination}} {{end}}"
        ])
        record("NAMED_VOLUMES_MAPPED", f"{VOL_DATA}:/app/instance" in inspect_mounts and f"{VOL_REC}:/app/recordings" in inspect_mounts, f"Mounts: {inspect_mounts}")

        # 7. Authenticate with persisted user after restart
        r_login_after = client.post(f"{BASE_URL}/api/auth/login/", json={"email": "prod_op@verify.local", "password": "VerifyPassword2026!"}, headers=headers)
        record("POST_RESTART_LOGIN_STEP1", r_login_after.status_code == 200 and r_login_after.json().get("requires_otp") is True, f"Login step 1 after restart: {r_login_after.json().get('requires_otp')}")

        login_otp_after = check_out(["docker", "exec", CONTAINER_NAME, "python", "-c", login_otp_py])
        r_login2_after = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": "prod_op@verify.local", "otp": login_otp_after}, headers=headers)
        record("POST_RESTART_LOGIN_STEP2", r_login2_after.status_code == 200 and r_login2_after.json().get("success") is True, f"Login step 2 after restart: HTTP {r_login2_after.status_code}")

        r_me_after = client.get(f"{BASE_URL}/api/auth/me/")
        record("POST_RESTART_SESSION_VALID", r_me_after.status_code == 200 and r_me_after.json().get("authenticated") is True, f"User authenticated after restart: {r_me_after.json().get('user', {}).get('email')}")

        log("=" * 70)
        log("PRODUCTION VERIFICATION & PERSISTENCE LOOP: ALL CHECKS PASSED")
        log("=" * 70)

    finally:
        cleanup()

if __name__ == "__main__":
    main()
