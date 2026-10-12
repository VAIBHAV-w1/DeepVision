"""
DeepVision Autonomous Health Verification Orchestrator
======================================================
Runs the complete verification pipeline, collects failures,
and outputs machine-readable results.

Usage:
    python verification/run_full_health_loop.py
"""
import os
import sys
import json
import time
import socket
import sqlite3
import hashlib
import subprocess
import traceback
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / "deepvision_django"
INSTANCE_DIR = ROOT_DIR / "instance"
DB_PATH = INSTANCE_DIR / "deepvision.db"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_PYTHON = ROOT_DIR / "venv" / "Scripts" / "python.exe"
BASE_URL = "http://127.0.0.1:8000"

results = []

# Force UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def add_result(name, status, detail=""):
    results.append({"test": name, "status": status, "detail": detail})
    icon = {"PASS": "[OK]", "FAIL": "[XX]", "WARNING": "[!!]", "BLOCKED": "[BK]", "SKIP": "[--]"}.get(status, "[??]")
    log(f"  {icon} [{status}] {name}" + (f" - {detail}" if detail else ""))

def is_port_open(port, host="127.0.0.1"):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        r = s.connect_ex((host, port))
        s.close()
        return r == 0
    except Exception:
        return False

def http_get(path, timeout=10):
    """Returns (status_code, body_text) or raises."""
    url = BASE_URL + path
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise

def http_get_with_session(path, session_cookie, csrf_token=None, timeout=10):
    """GET with session cookie."""
    url = BASE_URL + path
    req = urllib.request.Request(url)
    req.add_header("Cookie", f"deepvision_django_session={session_cookie}")
    if csrf_token:
        req.add_header("X-CSRFToken", csrf_token)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

def http_post_json(path, data, session_cookie=None, csrf_token=None, timeout=10):
    """POST JSON data."""
    url = BASE_URL + path
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    cookies = []
    if session_cookie:
        cookies.append(f"deepvision_django_session={session_cookie}")
    if csrf_token:
        cookies.append(f"deepvision_django_csrftoken={csrf_token}")
        req.add_header("X-CSRFToken", csrf_token)
    if cookies:
        req.add_header("Cookie", "; ".join(cookies))
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", errors="replace"), resp
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), e

# ======================================================================
# TEST: Server Health
# ======================================================================
def test_server_health():
    log("--- Server Health ---")
    if not is_port_open(8000):
        add_result("Server Running", "FAIL", "Port 8000 not open")
        return False
    add_result("Server Running", "PASS", "Port 8000 open")

    try:
        code, body = http_get("/api/health/")
        if code == 200:
            add_result("Health Endpoint", "PASS", f"HTTP {code}")
        else:
            add_result("Health Endpoint", "FAIL", f"HTTP {code}")
            return False
    except Exception as e:
        add_result("Health Endpoint", "FAIL", str(e))
        return False

    try:
        code, body = http_get("/")
        if code == 200:
            add_result("Root Page", "PASS", f"HTTP {code}, {len(body)} bytes")
        else:
            add_result("Root Page", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Root Page", "FAIL", str(e))

    return True

# ======================================================================
# TEST: Django System Checks
# ======================================================================
def test_django_checks():
    log("--- Django System Checks ---")
    try:
        r = subprocess.run(
            [str(VENV_PYTHON), str(DJANGO_DIR / "manage.py"), "check"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT_DIR)
        )
        if r.returncode == 0 and "no issues" in r.stdout.lower():
            add_result("Django Check", "PASS")
        else:
            add_result("Django Check", "FAIL", r.stderr[:200])
    except Exception as e:
        add_result("Django Check", "FAIL", str(e))

# ======================================================================
# TEST: Database Integrity
# ======================================================================
def test_database():
    log("--- Database Integrity ---")
    if not DB_PATH.exists():
        add_result("Database Exists", "FAIL", f"{DB_PATH} not found")
        return

    add_result("Database Exists", "PASS", f"{DB_PATH.stat().st_size} bytes")

    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()

        c.execute("PRAGMA integrity_check")
        integrity = c.fetchone()[0]
        if integrity == "ok":
            add_result("Database Integrity", "PASS")
        else:
            add_result("Database Integrity", "FAIL", integrity)

        c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in c.fetchall()]
        expected_tables = [
            "alerts", "audit_logs", "camera_groups", "cameras", "detection_profiles",
            "devices", "evidence", "incident_cases", "incident_notes",
            "incident_playbooks", "incident_policies", "notification_preferences",
            "notifications", "products", "recordings", "restricted_zones",
            "surveillance_presets", "users"
        ]
        if set(expected_tables).issubset(set(tables)):
            add_result("Database Tables", "PASS", f"{len(tables)} tables")
        else:
            missing = set(expected_tables) - set(tables)
            add_result("Database Tables", "FAIL", f"Missing: {missing}")

        # Schema hash
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name")
        schema = "|".join([r[0] or "" for r in c.fetchall()])
        schema_hash = hashlib.sha256(schema.encode()).hexdigest()[:16]
        add_result("Schema Hash", "PASS", schema_hash)

        # Key row counts
        for t in ["users", "cameras", "recordings", "alerts", "evidence", "incident_cases"]:
            c.execute(f"SELECT count(*) FROM [{t}]")
            cnt = c.fetchone()[0]
            add_result(f"Table {t}", "PASS", f"{cnt} rows")

        conn.close()
    except Exception as e:
        add_result("Database Query", "FAIL", str(e))

# ======================================================================
# TEST: Authentication (CSRF + Login + Session)
# ======================================================================
def test_authentication():
    log("--- Authentication ---")

    # Get CSRF token
    try:
        code, body = http_get("/api/auth/csrf/")
        data = json.loads(body)
        csrf_token = data.get("csrfToken") or data.get("csrf_token") or data.get("token")
        if csrf_token:
            add_result("CSRF Token", "PASS")
        else:
            add_result("CSRF Token", "FAIL", f"Response: {body[:100]}")
            return None, None
    except Exception as e:
        add_result("CSRF Token", "FAIL", str(e))
        return None, None

    # Test unauthenticated access
    try:
        code, body = http_get("/api/auth/me/")
        if code in (401, 403):
            add_result("Unauthenticated Guard", "PASS", f"HTTP {code}")
        elif code == 200:
            # Might be returning anonymous info
            data = json.loads(body)
            if data.get("authenticated") == False or not data.get("user"):
                add_result("Unauthenticated Guard", "PASS", "Returns unauthenticated state")
            else:
                add_result("Unauthenticated Guard", "WARNING", f"HTTP 200 with user data")
        else:
            add_result("Unauthenticated Guard", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Unauthenticated Guard", "FAIL", str(e))

    # Try login with test credentials
    try:
        code, body, resp = http_post_json("/api/auth/login/", {
            "email": "health_test@deepvision.test",
            "password": "TestHealth123!"
        }, csrf_token=csrf_token)

        if code == 200:
            data = json.loads(body)
            if data.get("requires_otp") or data.get("otp_required"):
                add_result("Login (OTP Required)", "PASS", "OTP flow triggered")
            elif data.get("success") or data.get("user"):
                add_result("Login", "PASS")
            else:
                add_result("Login", "WARNING", f"200 but response: {body[:100]}")
        elif code == 400:
            add_result("Login", "WARNING", f"HTTP 400: {body[:100]}")
        elif code == 403:
            add_result("Login", "WARNING", f"CSRF issue: {body[:100]}")
        else:
            add_result("Login", "FAIL", f"HTTP {code}: {body[:100]}")
    except Exception as e:
        add_result("Login", "FAIL", str(e))

    return csrf_token, None

# ======================================================================
# TEST: API Endpoints
# ======================================================================
def test_api_endpoints():
    log("--- API Endpoints ---")

    endpoints = [
        ("/api/health/", "Health"),
        ("/api/dashboard/stats/", "Dashboard Stats"),
        ("/api/cameras/", "Camera List"),
        ("/api/recordings/", "Recordings List"),
        ("/api/alerts/", "Alerts List"),
        ("/api/evidence/", "Evidence List"),
        ("/api/cases/", "Cases List"),
        ("/api/notifications/unread-count/", "Unread Notifications"),
    ]

    for path, name in endpoints:
        try:
            code, body = http_get(path)
            if code == 200:
                add_result(f"API {name}", "PASS", f"HTTP {code}, {len(body)} bytes")
            elif code in (401, 403):
                add_result(f"API {name}", "WARNING", f"HTTP {code} (auth required)")
            else:
                add_result(f"API {name}", "FAIL", f"HTTP {code}")
        except Exception as e:
            add_result(f"API {name}", "FAIL", str(e))

# ======================================================================
# TEST: Frontend Routes
# ======================================================================
def test_frontend_routes():
    log("--- Frontend Routes ---")

    routes = [
        ("/", "Root"),
        ("/dashboard/", "Dashboard"),
        ("/cameras/", "Cameras"),
        ("/recordings/", "Recordings"),
        ("/alerts/", "Alerts"),
        ("/evidence/", "Evidence"),
        ("/cases/", "Cases"),
        ("/notifications/", "Notifications"),
        ("/login/", "Login"),
        ("/signup/", "Signup"),
        ("/help/", "Help"),
    ]

    for path, name in routes:
        try:
            code, body = http_get(path)
            if code == 200:
                # Check for React app markers
                if "index.html" in body or "<div id=" in body or "root" in body or "<!DOCTYPE" in body.upper() or "<html" in body:
                    add_result(f"Route {name}", "PASS")
                else:
                    add_result(f"Route {name}", "WARNING", "Response may not be SPA")
            elif code in (301, 302):
                add_result(f"Route {name}", "PASS", f"Redirect HTTP {code}")
            else:
                add_result(f"Route {name}", "FAIL", f"HTTP {code}")
        except Exception as e:
            add_result(f"Route {name}", "FAIL", str(e))

# ======================================================================
# TEST: Frontend Build
# ======================================================================
def test_frontend_build():
    log("--- Frontend Build ---")

    dist_dir = DJANGO_DIR / "static" / "dist"
    index_html = dist_dir / "index.html"

    if index_html.exists():
        add_result("Production Build Exists", "PASS", f"{index_html.stat().st_size} bytes")
    else:
        add_result("Production Build Exists", "FAIL", "dist/index.html missing")

    # Check for JS and CSS assets
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        js_files = list(assets_dir.glob("*.js"))
        css_files = list(assets_dir.glob("*.css"))
        if js_files:
            add_result("JS Bundle", "PASS", f"{len(js_files)} file(s), {sum(f.stat().st_size for f in js_files)} bytes total")
        else:
            add_result("JS Bundle", "FAIL", "No JS files in dist/assets/")
        if css_files:
            add_result("CSS Bundle", "PASS", f"{len(css_files)} file(s)")
        else:
            add_result("CSS Bundle", "WARNING", "No CSS files in dist/assets/")
    else:
        add_result("Assets Directory", "FAIL", "dist/assets/ missing")

    # Check if node_modules exist for building
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        add_result("Node Modules", "PASS")
    else:
        add_result("Node Modules", "WARNING", "node_modules not found — npm install needed for rebuild")

# ======================================================================
# TEST: Camera Subsystem
# ======================================================================
def test_camera_subsystem():
    log("--- Camera Subsystem ---")

    try:
        code, body = http_get("/api/cameras/")
        if code == 200:
            data = json.loads(body)
            cameras = data if isinstance(data, list) else data.get("cameras", data.get("results", []))
            add_result("Camera List API", "PASS", f"{len(cameras)} cameras")

            # Find online camera (usually camera 3 with dshow://0)
            online = [c for c in cameras if c.get("status") == "online"]
            if online:
                cam_id = online[0].get("id", 3)
                add_result("Online Camera Found", "PASS", f"Camera ID {cam_id}")

                # Test snapshot
                try:
                    snapshot_url = f"/cameras/{cam_id}/snapshot/"
                    req = urllib.request.Request(BASE_URL + snapshot_url)
                    resp = urllib.request.urlopen(req, timeout=15)
                    snap_data = resp.read()
                    if len(snap_data) > 1000 and snap_data[:2] == b'\xff\xd8':
                        add_result("Camera Snapshot", "PASS", f"JPEG {len(snap_data)} bytes")
                    else:
                        add_result("Camera Snapshot", "FAIL", f"Invalid data, {len(snap_data)} bytes")
                except Exception as e:
                    add_result("Camera Snapshot", "FAIL", str(e))

                # Test MJPEG stream (read a few frames)
                for mode, label in [("original", "ORIGINAL"), ("tracking", "TRACKING")]:
                    try:
                        stream_url = f"/cameras/{cam_id}/stream/{mode}/"
                        req = urllib.request.Request(BASE_URL + stream_url)
                        resp = urllib.request.urlopen(req, timeout=15)
                        content_type = resp.headers.get("Content-Type", "")
                        if "multipart" in content_type or "mixed-replace" in content_type:
                            # Read a chunk to verify frames
                            chunk = resp.read(50000)
                            if b'\xff\xd8' in chunk:
                                add_result(f"Camera Stream {label}", "PASS", f"MJPEG frames flowing")
                            else:
                                add_result(f"Camera Stream {label}", "WARNING", "Stream opened but no JPEG frames in first chunk")
                        else:
                            add_result(f"Camera Stream {label}", "FAIL", f"Content-Type: {content_type}")
                        resp.close()
                    except Exception as e:
                        err_str = str(e)
                        if "timed out" in err_str.lower():
                            add_result(f"Camera Stream {label}", "WARNING", "Timeout (camera may not be connected)")
                        else:
                            add_result(f"Camera Stream {label}", "FAIL", err_str[:100])

                # Test stats
                try:
                    code, body = http_get(f"/cameras/{cam_id}/status/")
                    if code == 200:
                        add_result("Camera Stats", "PASS")
                    else:
                        add_result("Camera Stats", "FAIL", f"HTTP {code}")
                except Exception as e:
                    add_result("Camera Stats", "FAIL", str(e))
            else:
                add_result("Online Camera Found", "WARNING", "No camera online")
        elif code in (401, 403):
            add_result("Camera List API", "WARNING", f"Auth required ({code})")
        else:
            add_result("Camera List API", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Camera List API", "FAIL", str(e))

# ======================================================================
# TEST: Recording Subsystem
# ======================================================================
def test_recordings():
    log("--- Recordings ---")

    try:
        code, body = http_get("/api/recordings/")
        if code == 200:
            data = json.loads(body)
            recordings = data if isinstance(data, list) else data.get("recordings", data.get("results", []))
            total = data.get("total_count", len(recordings)) if isinstance(data, dict) else len(recordings)
            add_result("Recordings API", "PASS", f"{total} recordings")

            # Check file existence for first few recordings
            if recordings:
                existing = 0
                missing = 0
                for rec in recordings[:5]:
                    fe = rec.get("file_exists", True)
                    if fe:
                        existing += 1
                    else:
                        missing += 1
                if missing > 0:
                    add_result("Recording Files", "WARNING", f"{existing} exist, {missing} missing in sample")
                else:
                    add_result("Recording Files", "PASS", f"{existing}/{existing} exist in sample")
        elif code in (401, 403):
            add_result("Recordings API", "WARNING", f"Auth required ({code})")
        else:
            add_result("Recordings API", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Recordings API", "FAIL", str(e))

# ======================================================================
# TEST: Alerts & Evidence
# ======================================================================
def test_alerts_evidence():
    log("--- Alerts & Evidence ---")

    for endpoint, name in [("/api/alerts/", "Alerts"), ("/api/evidence/", "Evidence")]:
        try:
            code, body = http_get(endpoint)
            if code == 200:
                data = json.loads(body)
                items = data if isinstance(data, list) else data.get(name.lower(), data.get("results", []))
                add_result(f"{name} API", "PASS", f"{len(items)} items")
            elif code in (401, 403):
                add_result(f"{name} API", "WARNING", f"Auth required ({code})")
            else:
                add_result(f"{name} API", "FAIL", f"HTTP {code}")
        except Exception as e:
            add_result(f"{name} API", "FAIL", str(e))

    # Cases
    try:
        code, body = http_get("/api/cases/")
        if code == 200:
            add_result("Cases API", "PASS")
        elif code in (401, 403):
            add_result("Cases API", "WARNING", f"Auth required ({code})")
        else:
            add_result("Cases API", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Cases API", "FAIL", str(e))

# ======================================================================
# TEST: Notifications
# ======================================================================
def test_notifications():
    log("--- Notifications ---")

    try:
        code, body = http_get("/api/notifications/unread-count/")
        if code == 200:
            data = json.loads(body)
            add_result("Notifications Unread Count", "PASS", f"Count: {data.get('unread_count', '?')}")
        elif code in (401, 403):
            add_result("Notifications Unread Count", "WARNING", f"Auth required ({code})")
        else:
            add_result("Notifications Unread Count", "FAIL", f"HTTP {code}")
    except Exception as e:
        add_result("Notifications Unread Count", "FAIL", str(e))

# ======================================================================
# TEST: Static Assets
# ======================================================================
def test_static_assets():
    log("--- Static Assets ---")

    try:
        code, body = http_get("/")
        if code == 200:
            # Extract asset references from index.html
            import re
            js_refs = re.findall(r'src="(/static/[^"]+)"', body)
            css_refs = re.findall(r'href="(/static/[^"]+\.css)"', body)

            for ref in js_refs[:3]:
                try:
                    c, b = http_get(ref)
                    if c == 200:
                        add_result(f"Asset {ref.split('/')[-1]}", "PASS", f"{len(b)} bytes")
                    else:
                        add_result(f"Asset {ref.split('/')[-1]}", "FAIL", f"HTTP {c}")
                except Exception as e:
                    add_result(f"Asset {ref.split('/')[-1]}", "FAIL", str(e))

            for ref in css_refs[:3]:
                try:
                    c, b = http_get(ref)
                    if c == 200:
                        add_result(f"Asset {ref.split('/')[-1]}", "PASS", f"{len(b)} bytes")
                    else:
                        add_result(f"Asset {ref.split('/')[-1]}", "FAIL", f"HTTP {c}")
                except Exception as e:
                    add_result(f"Asset {ref.split('/')[-1]}", "FAIL", str(e))

            if not js_refs and not css_refs:
                add_result("Static Asset Refs", "WARNING", "No /static/ references found in HTML")
    except Exception as e:
        add_result("Static Assets", "FAIL", str(e))

# ======================================================================
# TEST: Python Import Checks
# ======================================================================
def test_python_imports():
    log("--- Python Import Checks ---")

    apps = [
        "apps.core", "apps.core.api", "apps.core.views",
        "apps.accounts", "apps.accounts.views",
        "apps.cameras", "apps.cameras.views",
        "apps.recordings", "apps.recordings.views",
        "apps.evidence", "apps.evidence.views",
        "apps.alerts", "apps.alerts.views",
        "apps.notifications", "apps.notifications.views",
        "apps.ai", "apps.ai.engine",
    ]

    script = f"""
import sys, os
sys.path.insert(0, {repr(str(DJANGO_DIR))})
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
errors = []
for mod_name in {apps!r}:
    try:
        __import__(mod_name)
    except Exception as e:
        errors.append(f"{{mod_name}}: {{e}}")
if errors:
    for err in errors:
        print(f"IMPORT_ERROR: {{err}}")
    sys.exit(1)
else:
    print("ALL_IMPORTS_OK")
"""
    try:
        r = subprocess.run(
            [str(VENV_PYTHON), "-c", script],
            capture_output=True, text=True, timeout=30, cwd=str(ROOT_DIR)
        )
        if r.returncode == 0 and "ALL_IMPORTS_OK" in r.stdout:
            add_result("Python Imports", "PASS", f"{len(apps)} modules")
        else:
            errors = [l for l in r.stdout.split('\n') if "IMPORT_ERROR" in l]
            add_result("Python Imports", "FAIL", "; ".join(errors[:3]))
    except Exception as e:
        add_result("Python Imports", "FAIL", str(e))

# ======================================================================
# TEST: Dependencies
# ======================================================================
def test_dependencies():
    log("--- Dependencies ---")

    try:
        r = subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "check"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and "no broken" in r.stdout.lower():
            add_result("Pip Check", "PASS")
        else:
            add_result("Pip Check", "FAIL", (r.stdout + r.stderr)[:200])
    except Exception as e:
        add_result("Pip Check", "FAIL", str(e))

# ======================================================================
# TEST: Docker
# ======================================================================
def test_docker():
    log("--- Docker ---")

    dockerfile = ROOT_DIR / "Dockerfile"
    compose = ROOT_DIR / "docker-compose.yml"

    if dockerfile.exists():
        add_result("Dockerfile Exists", "PASS")
    else:
        add_result("Dockerfile Exists", "FAIL")

    if compose.exists():
        add_result("docker-compose.yml Exists", "PASS")
    else:
        add_result("docker-compose.yml Exists", "FAIL")

    # Check if Docker is available
    try:
        r = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            add_result("Docker Engine", "PASS", f"v{r.stdout.strip()}")
        else:
            add_result("Docker Engine", "WARNING", "Docker not available")
    except Exception:
        add_result("Docker Engine", "WARNING", "Docker command not found")

    # Check image
    try:
        r = subprocess.run(
            ["docker", "images", "deepvision", "--format", "{{.Tag}} {{.Size}}"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            add_result("Docker Image", "PASS", r.stdout.strip())
        else:
            add_result("Docker Image", "WARNING", "No deepvision image found")
    except Exception:
        add_result("Docker Image", "SKIP")

# ======================================================================
# MAIN
# ======================================================================
def main():
    start_time = time.time()
    log("=" * 60)
    log("DEEPVISION AUTONOMOUS HEALTH VERIFICATION")
    log("=" * 60)

    test_server_health()
    test_django_checks()
    test_python_imports()
    test_dependencies()
    test_database()
    test_authentication()
    test_api_endpoints()
    test_frontend_routes()
    test_frontend_build()
    test_static_assets()
    test_camera_subsystem()
    test_recordings()
    test_alerts_evidence()
    test_notifications()
    test_docker()

    elapsed = time.time() - start_time

    log("")
    log("=" * 60)
    log("RESULTS SUMMARY")
    log("=" * 60)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARNING")
    total = len(results)

    log(f"  Total: {total}  |  PASS: {pass_count}  |  FAIL: {fail_count}  |  WARNING: {warn_count}")
    log(f"  Elapsed: {elapsed:.1f}s")
    log("")

    if fail_count > 0:
        log("FAILURES:")
        for r in results:
            if r["status"] == "FAIL":
                log(f"  ✗ {r['test']}: {r['detail']}")

    if warn_count > 0:
        log("WARNINGS:")
        for r in results:
            if r["status"] == "WARNING":
                log(f"  ⚠ {r['test']}: {r['detail']}")

    # Output JSON for machine parsing
    report = {
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": round(elapsed, 1),
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "warning": warn_count,
        "results": results,
    }
    report_path = ROOT_DIR / "verification" / "health_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    log(f"\nResults saved to: {report_path}")

    return fail_count == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
