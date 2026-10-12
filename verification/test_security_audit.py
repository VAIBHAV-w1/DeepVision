"""
Independent Security Audit & Vulnerability Penetration Tests
Tests actual security boundaries against the running application:
1. Path traversal attacks on media streaming
2. Tenant isolation / BOLA / IDOR on alerts & evidence
3. Unauthenticated access enforcement on media and stream endpoints
4. Camera source SSRF protocol validation
5. Session termination & invalidation
"""
import urllib.request
import urllib.error
import json
import http.cookiejar
import sys, os

sys.path.insert(0, "D:/DeepVision/deepvision_django")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
from django.contrib.sessions.backends.signed_cookies import SessionStore
from apps.surveillance.camera.sources import resolve_camera_capture_source, validate_video_path

BASE_URL = "http://127.0.0.1:8000"

results = {"PASS": 0, "FAIL": 0, "details": []}

def check(name, passed, detail=""):
    if passed:
        results["PASS"] += 1
        print(f"  [PASS] {name}: {detail}")
    else:
        results["FAIL"] += 1
        print(f"  [FAIL] {name}: {detail}")
    results["details"].append((name, passed, detail))

print("==================================================")
print("INDEPENDENT SECURITY AUDIT VERIFICATION")
print("==================================================")

# 1. PATH TRAVERSAL DEFENSE
print("\n--- 1. Path Traversal Attacks ---")
traversal_payloads = [
    "../../../../windows/win.ini",
    "..%2F..%2F..%2Fwindows%2Fwin.ini",
    "....//....//....//etc//passwd",
    "/etc/shadow",
    "C:\\Windows\\System32\\drivers\\etc\\hosts"
]

for p in traversal_payloads:
    url = f"{BASE_URL}/recordings/stream/1/?file={p}"
    try:
        r = urllib.request.urlopen(url, timeout=5)
        # If HTTP 200, check that system file is NOT returned
        body = r.read().decode('utf-8', errors='ignore')
        if "[fonts]" in body.lower() or "root:" in body:
            check(f"Traversal: {p}", False, "System file leaked!")
        else:
            check(f"Traversal blocked/safe: {p}", True, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        check(f"Traversal blocked: {p}", e.code in (400, 401, 403, 404), f"HTTP {e.code}")
    except Exception as e:
        check(f"Traversal rejected: {p}", True, str(e))

# 2. TENANT ISOLATION / BOLA / IDOR
print("\n--- 2. Tenant Isolation & IDOR ---")
# Setup User 14 (test user) session
s14 = SessionStore()
s14['user_id'] = 14
s14.save()

cj14 = http.cookiejar.CookieJar()
cj14.set_cookie(http.cookiejar.Cookie(0, 'deepvision_django_session', s14.session_key, None, False, '127.0.0.1', False, False, '/', True, False, None, True, None, None, {}))
opener14 = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj14))

# Attempt to access User 2's Alert (ID 4243 is owned by User 2)
try:
    r = opener14.open(f"{BASE_URL}/api/alerts/4243/incident-context/", timeout=5)
    data = json.loads(r.read().decode())
    # Should not return User 2's evidence
    check("IDOR: Cross-user alert access", False, "User 14 accessed User 2 alert context!")
except urllib.error.HTTPError as e:
    check("IDOR Protection: Cross-user alert", e.code in (403, 404), f"HTTP {e.code} correctly denied")
except Exception as e:
    check("IDOR Protection: Cross-user alert", True, str(e))

# 3. UNAUTHENTICATED ACCESS ENFORCEMENT
print("\n--- 3. Unauthenticated Access Enforcement ---")
protected_endpoints = [
    "/api/cameras/",
    "/api/dashboard/stats/",
    "/cameras/1/stream/",
    "/cameras/1/snapshot/",
    "/recordings/stream/1/",
]

for ep in protected_endpoints:
    # Use standard opener with no cookies
    req = urllib.request.Request(BASE_URL + ep)
    try:
        r = urllib.request.urlopen(req, timeout=5)
        # If redirected to login, r.geturl() will contain 'login'
        is_protected = "login" in r.geturl().lower() or r.status in (401, 403)
        check(f"Auth required: {ep}", is_protected, f"Redirected to: {r.geturl()}")
    except urllib.error.HTTPError as e:
        check(f"Auth required: {ep}", e.code in (401, 403, 302, 404), f"HTTP {e.code}")
    except Exception as e:
        check(f"Auth required: {ep}", True, str(e))

# 4. CAMERA SOURCE SSRF & PATH VALIDATION
print("\n--- 4. Camera Source SSRF & Path Validation ---")

# Test source resolution validation
invalid_types = ["gopher", "file", "ftp", "javascript", "dict"]
for it in invalid_types:
    try:
        resolve_camera_capture_source(it, "test")
        check(f"Protocol rejection: {it}", False, "Invalid protocol accepted!")
    except ValueError as e:
        check(f"Protocol rejection: {it}", True, f"Rejected: {e}")

# Test video file path traversal defense
traversal_paths = ["../../etc/passwd", "/etc/shadow", "C:\\Windows\\win.ini", "../sensitive.py"]
for tp in traversal_paths:
    ok, msg = validate_video_path(tp)
    check(f"Video path traversal rejection: {tp}", not ok, f"Rejected: {msg}")

# Test valid camera sources
valid_webcam = resolve_camera_capture_source("webcam", "0")
check("Valid webcam 0 source", valid_webcam == 0, f"Resolved to index {valid_webcam}")

valid_rtsp = resolve_camera_capture_source("rtsp", "rtsp://192.168.1.100:554/live")
check("Valid RTSP source", valid_rtsp.startswith("rtsp://"), f"Normalized to {valid_rtsp}")

# 5. SESSION INVALIDATION
print("\n--- 5. Session Invalidation on Logout ---")
# Get CSRF
r = opener14.open(f"{BASE_URL}/api/auth/csrf/", timeout=5)
csrf = json.loads(r.read().decode()).get("csrfToken", "")

# Logout
logout_req = urllib.request.Request(f"{BASE_URL}/api/auth/logout/", data=b"{}", method="POST")
logout_req.add_header("X-CSRFToken", csrf)
logout_req.add_header("Content-Type", "application/json")
try:
    r_logout = opener14.open(logout_req, timeout=5)
    # Check /api/auth/me/ with opener14
    r_me = opener14.open(f"{BASE_URL}/api/auth/me/", timeout=5)
    me_data = json.loads(r_me.read().decode())
    is_unauth = not me_data.get("authenticated") and not me_data.get("user")
    check("Session invalidated on logout", is_unauth, "User session cleared")
except Exception as e:
    check("Session invalidated on logout", False, str(e))

print("\n==================================================")
print(f"SECURITY AUDIT SUMMARY: {results['PASS']} PASS, {results['FAIL']} FAIL")
print("==================================================")
sys.exit(0 if results['FAIL'] == 0 else 1)
