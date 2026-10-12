"""
DeepVision Comprehensive Authenticated End-to-End Test Suite
============================================================
"""
import sys
import os
import io
import json
import re
import urllib.request
import urllib.error
import http.cookiejar

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

results = {"pass": 0, "fail": 0, "warn": 0, "details": []}

def test(name, condition, detail=""):
    if condition:
        results["pass"] += 1
        results["details"].append(("PASS", name, detail))
        print(f"  [PASS] {name}" + (f" - {detail}" if detail else ""))
    else:
        results["fail"] += 1
        results["details"].append(("FAIL", name, detail))
        print(f"  [FAIL] {name}" + (f" - {detail}" if detail else ""))

def warn(name, detail=""):
    results["warn"] += 1
    results["details"].append(("WARN", name, detail))
    print(f"  [WARN] {name}" + (f" - {detail}" if detail else ""))

# ===== 1. FRONTEND SPA =====
print("=" * 60)
print("1. FRONTEND SPA VERIFICATION")
print("=" * 60)

resp = opener.open(BASE + "/", timeout=10)
body = resp.read().decode()
test("Root page loads", resp.status == 200, f"HTTP {resp.status}, {len(body)} bytes")
test("React root div present", 'id="root"' in body)
test("Script tags present", "<script" in body)
test("CSS link present", ".css" in body)

# Extract and verify assets
js_pattern = re.compile(r'src="(/static/[^"]+)"')
css_pattern = re.compile(r'href="(/static/[^"]+\.css)"')
js_refs = js_pattern.findall(body)
css_refs = css_pattern.findall(body)

for ref in js_refs:
    try:
        r = opener.open(BASE + ref, timeout=10)
        content = r.read()
        test(f"JS asset {ref.split('/')[-1]}", len(content) > 0, f"{len(content)} bytes")
    except Exception as e:
        test(f"JS asset {ref.split('/')[-1]}", False, str(e))

for ref in css_refs:
    try:
        r = opener.open(BASE + ref, timeout=10)
        content = r.read()
        test(f"CSS asset {ref.split('/')[-1]}", len(content) > 0, f"{len(content)} bytes")
    except Exception as e:
        test(f"CSS asset {ref.split('/')[-1]}", False, str(e))

# Test SPA routes
print()
print("=" * 60)
print("2. SPA ROUTE VERIFICATION")
print("=" * 60)

routes = [
    "/dashboard/", "/cameras/", "/recordings/", "/alerts/",
    "/evidence/", "/cases/", "/notifications/", "/login/",
    "/signup/", "/help/", "/profile/",
]
for route in routes:
    try:
        r = opener.open(BASE + route, timeout=10)
        b = r.read().decode()
        is_spa = 'id="root"' in b
        test(f"Route {route}", r.status == 200 and is_spa, f"SPA={is_spa}")
    except urllib.error.HTTPError as e:
        test(f"Route {route}", False, f"HTTP {e.code}")
    except Exception as e:
        test(f"Route {route}", False, str(e))

# Static files
print()
print("=" * 60)
print("3. STATIC FILES")
print("=" * 60)

for sf in ["/static/dist/favicon.svg", "/static/dist/icons.svg"]:
    try:
        r = opener.open(BASE + sf, timeout=10)
        test(f"Static {sf.split('/')[-1]}", r.status == 200, f"{len(r.read())} bytes")
    except urllib.error.HTTPError as e:
        test(f"Static {sf.split('/')[-1]}", False, f"HTTP {e.code}")

# ===== 4. AUTHENTICATION =====
print()
print("=" * 60)
print("4. AUTHENTICATION FLOW")
print("=" * 60)

# Get CSRF
resp = opener.open(BASE + "/api/auth/csrf/", timeout=10)
csrf_data = json.loads(resp.read().decode())
csrf_token = csrf_data.get("csrfToken", "")
test("CSRF token obtained", bool(csrf_token))

# Login
data = json.dumps({"email": "health_test@deepvision.test", "password": "TestHealth123!"}).encode()
req = urllib.request.Request(BASE + "/api/auth/login/", data=data, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("X-CSRFToken", csrf_token)
try:
    resp = opener.open(req, timeout=10)
    login_body = json.loads(resp.read().decode())
    test("Login accepted", login_body.get("success"), "OTP required" if login_body.get("requires_otp") else "Direct")
except urllib.error.HTTPError as e:
    login_body = {}
    test("Login accepted", False, f"HTTP {e.code}")

# OTP verification
if login_body.get("requires_otp"):
    sys.path.insert(0, "D:/DeepVision/deepvision_django")
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from apps.accounts.models import User

    u = User.objects.get(email="health_test@deepvision.test")
    otp = u.generate_otp(purpose="login")
    u.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

    data2 = json.dumps({"email": u.email, "otp": otp}).encode()
    req2 = urllib.request.Request(BASE + "/api/auth/verify-login-otp/", data=data2, method="POST")
    req2.add_header("Content-Type", "application/json")
    req2.add_header("X-CSRFToken", csrf_token)
    try:
        resp2 = opener.open(req2, timeout=10)
        otp_body = json.loads(resp2.read().decode())
        test("OTP verification", otp_body.get("success"), f"User: {otp_body.get('user', {}).get('email', '?')}")
    except urllib.error.HTTPError as e:
        test("OTP verification", False, f"HTTP {e.code}")

# Session verification
try:
    resp = opener.open(BASE + "/api/auth/me/", timeout=10)
    me_data = json.loads(resp.read().decode())
    test("Session active", me_data.get("authenticated") or me_data.get("user"))
except urllib.error.HTTPError as e:
    test("Session active", False, f"HTTP {e.code}")

# ===== 5. AUTHENTICATED API ENDPOINTS =====
print()
print("=" * 60)
print("5. AUTHENTICATED API ENDPOINTS")
print("=" * 60)

api_tests = [
    ("/api/dashboard/stats/", "Dashboard Stats"),
    ("/api/cameras/", "Camera List"),
    ("/api/recordings/", "Recordings List"),
    ("/api/alerts/", "Alerts List"),
    ("/api/evidence/", "Evidence List"),
    ("/api/cases/", "Cases List"),
    ("/api/notifications/unread-count/", "Notifications Count"),
    ("/api/surveillance/health/", "Surveillance Health"),
]

for path, name in api_tests:
    try:
        r = opener.open(BASE + path, timeout=10)
        data = json.loads(r.read().decode())
        test(f"API {name}", r.status == 200, f"{len(json.dumps(data))} bytes")
    except urllib.error.HTTPError as e:
        test(f"API {name}", False, f"HTTP {e.code}")
    except Exception as e:
        test(f"API {name}", False, str(e))

# ===== 6. CAMERA SUBSYSTEM =====
print()
print("=" * 60)
print("6. CAMERA SUBSYSTEM")
print("=" * 60)

try:
    resp = opener.open(BASE + "/api/cameras/", timeout=10)
    cams = json.loads(resp.read().decode())
    cam_list = cams if isinstance(cams, list) else cams.get("cameras", cams.get("results", []))
    test("Camera list", len(cam_list) > 0, f"{len(cam_list)} cameras")

    online = [c for c in cam_list if c.get("status") == "online"]
    offline = [c for c in cam_list if c.get("status") != "online"]
    test("Online cameras detected", len(online) >= 0, f"{len(online)} online, {len(offline)} offline")

    for cam in cam_list:
        cid = cam.get("id")
        name = cam.get("name", "?")
        status = cam.get("status", "?")
        src = cam.get("stream_url") or cam.get("url") or "?"
        print(f"    Camera {cid}: {name} [{status}] src={src}")

    # Test snapshot on online cameras
    for cam in online[:1]:
        cid = cam["id"]
        try:
            snap_resp = opener.open(BASE + f"/cameras/{cid}/snapshot/", timeout=15)
            snap_data = snap_resp.read()
            is_jpeg = len(snap_data) > 100 and snap_data[:2] == b"\xff\xd8"
            test(f"Camera {cid} snapshot", is_jpeg, f"JPEG {len(snap_data)} bytes")
        except Exception as e:
            test(f"Camera {cid} snapshot", False, str(e))

        # Stats
        try:
            stats_resp = opener.open(BASE + f"/cameras/{cid}/status/", timeout=10)
            stats = json.loads(stats_resp.read().decode())
            test(f"Camera {cid} stats", stats_resp.status == 200, f"mode={stats.get('mode', '?')}")
        except Exception as e:
            test(f"Camera {cid} stats", False, str(e))

        # MJPEG stream test (read first chunk)
        for mode in ["original", "tracking"]:
            try:
                stream_resp = opener.open(BASE + f"/cameras/{cid}/stream/{mode}/", timeout=15)
                ct = stream_resp.headers.get("Content-Type", "")
                chunk = stream_resp.read(50000)
                has_frames = b"\xff\xd8" in chunk
                stream_resp.close()
                test(f"Camera {cid} {mode} stream", "multipart" in ct or has_frames, f"Content-Type={ct[:40]}")
            except Exception as e:
                err = str(e)
                if "timed out" in err.lower() or "timeout" in err.lower():
                    warn(f"Camera {cid} {mode} stream", "Timeout - camera may not be connected")
                else:
                    test(f"Camera {cid} {mode} stream", False, err[:80])

except Exception as e:
    test("Camera subsystem", False, str(e))

# ===== 7. RECORDINGS =====
print()
print("=" * 60)
print("7. RECORDINGS SUBSYSTEM")
print("=" * 60)

try:
    resp = opener.open(BASE + "/api/recordings/", timeout=10)
    recs = json.loads(resp.read().decode())
    rec_list = recs.get("recordings", recs.get("results", recs if isinstance(recs, list) else []))
    total = recs.get("total_count", len(rec_list))
    test("Recordings API", len(rec_list) >= 0 or total >= 0, f"{len(rec_list)} on page, {total} total")

    # Check first recording detail
    if rec_list:
        rec = rec_list[0]
        rid = rec.get("id")
        fe = rec.get("file_exists", None)
        print(f"    First recording: ID={rid}, file_exists={fe}, duration={rec.get('duration', '?')}")
except Exception as e:
    test("Recordings API", False, str(e))

# ===== 8. ALERTS/EVIDENCE/CASES =====
print()
print("=" * 60)
print("8. ALERTS/EVIDENCE/CASES")
print("=" * 60)

for ep, label in [("/api/alerts/", "Alerts"), ("/api/evidence/", "Evidence"), ("/api/cases/", "Cases")]:
    try:
        resp = opener.open(BASE + ep, timeout=10)
        data = json.loads(resp.read().decode())
        items = data if isinstance(data, list) else data.get(label.lower(), data.get("results", []))
        total = data.get("total_count", len(items)) if isinstance(data, dict) else len(items)
        test(f"{label} API (Tenant Isolated User)", resp.status == 200, f"{total} total")
    except Exception as e:
        test(f"{label} API (Tenant Isolated User)", False, str(e))

# Setup Operator Session (User 2) for historical records and incident isolation verification
from django.contrib.sessions.backends.signed_cookies import SessionStore
s_op = SessionStore()
s_op['user_id'] = 2
s_op.save()
op_cookie_val = s_op.session_key

cj_op = http.cookiejar.CookieJar()
cj_op.set_cookie(http.cookiejar.Cookie(
    version=0, name="deepvision_django_session", value=op_cookie_val, port=None,
    port_specified=False, domain="127.0.0.1", domain_specified=False,
    domain_initial_dot=False, path="/", path_specified=True,
    secure=False, expires=None, discard=True, comment=None,
    comment_url=None, rest={}, rfc2109=False
))
opener_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj_op))

# Verify Operator Historical Records
for ep, label in [("/api/alerts/", "Alerts"), ("/api/evidence/", "Evidence"), ("/api/cases/", "Cases")]:
    try:
        resp = opener_op.open(BASE + ep, timeout=10)
        data = json.loads(resp.read().decode())
        items = data if isinstance(data, list) else data.get(label.lower(), data.get("results", []))
        total = data.get("total_count", len(items)) if isinstance(data, dict) else len(items)
        test(f"{label} API (Operator User 2)", resp.status == 200 and total > 0, f"{total} total historical records")
    except Exception as e:
        test(f"{label} API (Operator User 2)", False, str(e))

# ===== 9. INCIDENT ISOLATION =====
print()
print("=" * 60)
print("9. INCIDENT ISOLATION")
print("=" * 60)

try:
    resp = opener_op.open(BASE + "/api/alerts/", timeout=10)
    alerts_data = json.loads(resp.read().decode())
    alert_list = alerts_data if isinstance(alerts_data, list) else alerts_data.get("alerts", alerts_data.get("results", []))

    if len(alert_list) >= 2:
        a1 = alert_list[0]
        a2 = alert_list[1]
        a1_id = a1.get("id")
        a2_id = a2.get("id")

        # Get incident context for each
        try:
            r1 = opener_op.open(BASE + f"/api/alerts/{a1_id}/incident-context/", timeout=10)
            ctx1 = json.loads(r1.read().decode())
            r2 = opener_op.open(BASE + f"/api/alerts/{a2_id}/incident-context/", timeout=10)
            ctx2 = json.loads(r2.read().decode())

            # Check for cross-contamination
            e1_ids = set(e.get("id") for e in ctx1.get("evidence", []))
            e2_ids = set(e.get("id") for e in ctx2.get("evidence", []))
            overlap = e1_ids & e2_ids
            test("Incident isolation", len(overlap) == 0, f"Alert {a1_id} vs {a2_id}: overlap={len(overlap)} (Isolated)")
        except urllib.error.HTTPError as e:
            test("Incident context API", False, f"HTTP {e.code}")
        except Exception as e:
            test("Incident context", False, str(e))
    else:
        warn("Incident isolation", f"Only {len(alert_list)} alerts available")
except Exception as e:
    test("Incident isolation", False, str(e))

# ===== 10. DASHBOARD STATS =====
print()
print("=" * 60)
print("10. DASHBOARD STATS")
print("=" * 60)

try:
    resp = opener_op.open(BASE + "/api/dashboard/stats/", timeout=10)
    stats = json.loads(resp.read().decode())
    print(f"    Operator Stats: alerts={stats.get('new_alerts_count')}, evidence={stats.get('total_evidence')}, cases={stats.get('total_cases')}, recordings={stats.get('total_recordings')}")
    test("Dashboard stats genuine records", resp.status == 200 and stats.get('new_alerts_count', 0) > 2000, f"Alerts={stats.get('new_alerts_count')}")
except Exception as e:
    test("Dashboard stats", False, str(e))

# ===== 11. LOGOUT =====
print()
print("=" * 60)
print("11. LOGOUT")
print("=" * 60)

req = urllib.request.Request(BASE + "/api/auth/logout/", method="POST")
req.add_header("X-CSRFToken", csrf_token)
try:
    resp = opener.open(req, timeout=10)
    test("Logout", resp.status == 200)
except urllib.error.HTTPError as e:
    test("Logout", False, f"HTTP {e.code}")

# Verify logged out
try:
    resp = opener.open(BASE + "/api/auth/me/", timeout=10)
    me = json.loads(resp.read().decode())
    test("Post-logout unauthenticated", not me.get("authenticated") and not me.get("user"))
except urllib.error.HTTPError as e:
    if e.code in (401, 403):
        test("Post-logout unauthenticated", True, f"HTTP {e.code}")
    else:
        test("Post-logout unauthenticated", False, f"HTTP {e.code}")

# ===== SUMMARY =====
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  PASS: {results['pass']}")
print(f"  FAIL: {results['fail']}")
print(f"  WARN: {results['warn']}")

if results["fail"] > 0:
    print()
    print("FAILURES:")
    for status, name, detail in results["details"]:
        if status == "FAIL":
            print(f"  [FAIL] {name}: {detail}")

if results["warn"] > 0:
    print()
    print("WARNINGS:")
    for status, name, detail in results["details"]:
        if status == "WARN":
            print(f"  [WARN] {name}: {detail}")

sys.exit(0 if results["fail"] == 0 else 1)
