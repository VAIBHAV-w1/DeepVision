"""
DeepVision End-to-End Full-System Verification Script
Validates:
1. Routing & Rewrite configurations (vercel.json, frontend/vercel.json)
2. HTTP 206 Partial Content video streaming & range headers
3. Camera telemetry & dynamic status contracts (no mock 28 FPS)
4. Forensic evidence metadata & vault resilience
5. Frontend bundle splitting & enterprise theme / logo assets
6. Secret scanning & zero credential leak policy
"""

import os
import sys
import json
import re
import urllib.request
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

def run_test(name, fn):
    print(f"\n[RUNNING] {name}...")
    try:
        res = fn()
        if res is True or res is None:
            print(f"[PASS] {name}")
            return True
        else:
            print(f"[FAIL] {name}: {res}")
            return False
    except Exception as e:
        print(f"[ERROR] {name}: {type(e).__name__} - {e}")
        return False

def test_vercel_routing_contract():
    """Verify vercel.json and frontend/vercel.json have the required route rewrites and security headers."""
    for config_path in ["vercel.json", "frontend/vercel.json"]:
        full_path = os.path.join(REPO_ROOT, config_path)
        assert os.path.exists(full_path), f"Missing {config_path}"
        with open(full_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        rewrites = cfg.get("rewrites", [])
        rewrite_sources = [r.get("source") for r in rewrites]
        
        # Verify media and API routing
        expected_routes = [
            "/api/(.*)",
            "/cameras/(.*)",
            "/recordings/(.*)",
            "/evidence/(.*)",
            "/alerts/(.*)",
            "/notifications/(.*)",
            "/health"
        ]
        for route in expected_routes:
            assert any(route in s for s in rewrite_sources), f"Route {route} missing from {config_path} rewrites"
        
        # Verify SPA fallback is at the end
        assert rewrite_sources[-1] in ("/(.*)", "/(.*)"), f"SPA fallback /(.*) should be the last rewrite in {config_path}"
        
        # Verify x-vercel-toolbar suppression header
        headers = cfg.get("headers", [])
        toolbar_suppressed = any(
            any(h.get("key") == "x-vercel-toolbar" and h.get("value") == "off" for h in item.get("headers", []))
            for item in headers
        )
        assert toolbar_suppressed, f"x-vercel-toolbar suppression header missing in {config_path}"
    return True

def test_camera_telemetry_no_mock_fps():
    """Verify camera files no longer use hardcoded fake 28 FPS or 25 FPS fallbacks."""
    files_to_check = [
        "frontend/src/pages/Cameras.jsx",
        "frontend/src/pages/CameraPreview.jsx"
    ]
    for rel_path in files_to_check:
        full_path = os.path.join(REPO_ROOT, rel_path)
        assert os.path.exists(full_path), f"Missing {rel_path}"
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Assert no hardcoded fps: 28
        assert "fps: 28" not in content, f"Hardcoded 'fps: 28' found in {rel_path}"
        # Assert no fallback fps || 25
        assert "fps || 25" not in content, f"Fallback 'fps || 25' found in {rel_path}"
        # Assert no hardcoded '430kb/s'
        assert "430kb/s" not in content, f"Hardcoded '430kb/s' found in {rel_path}"
    return True

def test_logo_and_theme_assets():
    """Verify enterprise Logo component and SVG favicons exist and are referenced."""
    logo_path = os.path.join(REPO_ROOT, "frontend/src/components/common/Logo.jsx")
    assert os.path.exists(logo_path), "Logo.jsx component missing"
    
    with open(logo_path, "r", encoding="utf-8") as f:
        logo_content = f.read()
    assert "surveillance-reticle" in logo_content or "svg" in logo_content, "Invalid Logo component"
    
    # Check favicons
    favicons = [
        "frontend/public/favicon.svg",
        "deepvision_django/static/dist/favicon.svg",
        "deepvision_django/static/images/favicon.svg"
    ]
    for fav in favicons:
        p = os.path.join(REPO_ROOT, fav)
        assert os.path.exists(p), f"Favicon missing: {fav}"
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        assert "<svg" in c and "#10b981" in c, f"Favicon {fav} does not contain SVG surveillance brand elements"

    # Check globals.css for dark and light theme tokens & toolbar suppression
    css_path = os.path.join(REPO_ROOT, "frontend/src/styles/globals.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    assert '[data-theme="light"]' in css_content, "Light theme tokens missing in globals.css"
    assert 'vercel-live-feedback' in css_content, "Vercel toolbar CSS suppression missing in globals.css"
    return True

def test_frontend_bundle_splitting():
    """Verify frontend build outputs code-split chunks rather than a monolithic bundle."""
    dist_dir = os.path.join(REPO_ROOT, "frontend", "dist", "assets")
    assert os.path.exists(dist_dir), "frontend/dist/assets does not exist. Run 'npm --prefix frontend run build' first."
    
    files = os.listdir(dist_dir)
    js_files = [f for f in files if f.endswith(".js")]
    
    vendor_chunks = [f for f in js_files if "vendor" in f]
    assert len(vendor_chunks) > 0, f"No vendor chunks found in {dist_dir}"
    
    # Verify we have multiple split route chunks
    assert len(js_files) >= 8, f"Expected at least 8 code-split chunks, but found {len(js_files)}: {js_files}"
    
    # Verify index/entry chunk is lightweight (< 100 KB)
    index_chunk = next(f for f in js_files if f.startswith("index-"))
    index_size_kb = os.path.getsize(os.path.join(dist_dir, index_chunk)) / 1024
    print(f"  Entry chunk ({index_chunk}): {index_size_kb:.2f} KB")
    assert index_size_kb < 100, f"Entry chunk too large: {index_size_kb:.2f} KB >= 100 KB"
    return True

def test_local_docker_health_and_206():
    """Verify local Docker edge container serves health check and strict HTTP 206 Partial Content."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/health/")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200, f"Health check returned HTTP {res.status}"
            data = json.loads(res.read().decode("utf-8"))
            assert data.get("status") == "healthy", f"Health status not healthy: {data}"
            print(f"  Health endpoint verified: {data.get('status')}")
    except Exception as e:
        return f"Docker edge container health check failed: {e}"

    # Setup Django environment for signed session generation
    import django
    from django.conf import settings
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        sys.path.insert(0, os.path.join(REPO_ROOT, "deepvision_django"))
        django.setup()

    from django.contrib.sessions.backends.signed_cookies import SessionStore
    from apps.recordings.models import Recording
    from apps.core.media_service import safe_resolve_recording

    # Find a real recording with a physical file on disk
    recording = None
    full_path = None
    for r in Recording.objects.all().order_by("-id")[:50]:
        resolved = safe_resolve_recording(r.file_path)
        if resolved and os.path.isfile(resolved) and r.file_size > 1024:
            recording = r
            full_path = resolved
            break

    if not recording:
        return "No physical recording file with size > 1024 found on disk"

    actual_file_size = os.path.getsize(full_path)

    # Generate authenticated session cookie
    s = SessionStore()
    s["user_id"] = recording.user_id
    s.save()
    session_cookie = s.session_key

    # 1. Genuine HTTP 206 Partial Content Range Request (bytes 0-1023)
    req_206 = urllib.request.Request(
        f"http://127.0.0.1:8000/recordings/{recording.id}/view/",
        headers={
            "Range": "bytes=0-1023",
            "Cookie": f"deepvision_django_session={session_cookie}"
        }
    )
    with urllib.request.urlopen(req_206, timeout=5) as res:
        assert res.status == 206, f"Expected HTTP 206, got {res.status}"
        content_range = res.headers.get("Content-Range")
        expected_range = f"bytes 0-1023/{actual_file_size}"
        assert content_range == expected_range, f"Expected Content-Range '{expected_range}', got '{content_range}'"
        content_len_hdr = res.headers.get("Content-Length")
        assert content_len_hdr == "1024", f"Expected Content-Length 1024, got {content_len_hdr}"
        body = res.read()
        assert len(body) == 1024, f"Expected 1024 bytes body, got {len(body)}"
        print(f"  Recording #{recording.id} HTTP 206 Verified: Range: {content_range}, Length: {content_len_hdr}")

    # 2. Unsatisfiable Range (bytes 999999999-999999999) -> Expect HTTP 416
    req_416 = urllib.request.Request(
        f"http://127.0.0.1:8000/recordings/{recording.id}/view/",
        headers={
            "Range": "bytes=999999999-999999999",
            "Cookie": f"deepvision_django_session={session_cookie}"
        }
    )
    try:
        with urllib.request.urlopen(req_416, timeout=5) as res:
            return f"Expected HTTP 416 for out-of-range bytes, got {res.status}"
    except urllib.error.HTTPError as he:
        assert he.code == 416, f"Expected HTTP 416, got {he.code}"
        assert he.headers.get("Content-Range") == f"bytes */{actual_file_size}", "Invalid 416 Content-Range header"
        print(f"  Recording #{recording.id} HTTP 416 Out-of-Range Guard Verified")

    # 3. Full request (No Range header) -> Expect HTTP 200 with complete file
    req_200 = urllib.request.Request(
        f"http://127.0.0.1:8000/recordings/{recording.id}/view/",
        headers={
            "Cookie": f"deepvision_django_session={session_cookie}"
        }
    )
    with urllib.request.urlopen(req_200, timeout=5) as res:
        assert res.status == 200, f"Expected HTTP 200 for full stream, got {res.status}"
        assert res.headers.get("Accept-Ranges") == "bytes", "Missing Accept-Ranges: bytes"
        assert res.headers.get("Content-Length") == str(actual_file_size), "Mismatched full Content-Length"
        print(f"  Recording #{recording.id} HTTP 200 Full Stream Verified: Length: {actual_file_size} bytes")

    return True

def test_evidence_vault_resilience():
    """Verify Evidence page has defensive rendering against missing physical files."""
    evidence_path = os.path.join(REPO_ROOT, "frontend/src/pages/Evidence.jsx")
    with open(evidence_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "item.file_available" in content, "Evidence.jsx does not check item.file_available"
    assert "onError" in content, "Evidence.jsx does not include onError fallback handler"
    assert "Evidence Vault" in content or "Forensic" in content or "Vault" in content, "Evidence page missing vault UI"
    return True

def test_secret_safety_check():
    """Verify no secret credentials or API keys were accidentally committed into code."""
    sensitive_patterns = [
        re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
        re.compile(r"postgres://[^:]+:[^@]+@"),
        re.compile(r"postgresql://[^:]+:[^@]+@"),
        re.compile(r"smtp_password\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE)
    ]
    
    # Check git tracked files only
    import subprocess
    tracked_files = subprocess.check_output(
        ["git", "ls-files"], cwd=REPO_ROOT, text=True
    ).splitlines()
    
    leaks = []
    for rel_path in tracked_files:
        # Skip env files or verification tests that contain regex patterns
        if rel_path.endswith((".py", ".js", ".jsx", ".json", ".html")):
            if "test_e2e_full_system.py" in rel_path or "secret_scanner.py" in rel_path:
                continue
            full_path = os.path.join(REPO_ROOT, rel_path)
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                for pat in sensitive_patterns:
                    if pat.search(text):
                        leaks.append((rel_path, pat.pattern))
            except Exception:
                pass
    
    assert len(leaks) == 0, f"Sensitive credential leaks detected: {leaks}"
    return True

if __name__ == "__main__":
    tests = [
        ("Vercel Routing & Media Rewrites", test_vercel_routing_contract),
        ("Camera Telemetry & Dynamic Status", test_camera_telemetry_no_mock_fps),
        ("Brand Identity & Theme Assets", test_logo_and_theme_assets),
        ("Frontend Bundle Code-Splitting", test_frontend_bundle_splitting),
        ("Local Docker Health & HTTP 206 Streaming", test_local_docker_health_and_206),
        ("Forensic Evidence Vault Resilience", test_evidence_vault_resilience),
        ("Secret Safety & Zero Credential Leak", test_secret_safety_check),
    ]
    
    print("=" * 70)
    print("DEEPVISION FULL-SYSTEM END-TO-END VERIFICATION")
    print("=" * 70)
    
    passed = 0
    total = len(tests)
    for name, fn in tests:
        if run_test(name, fn):
            passed += 1
            
    print("\n" + "=" * 70)
    print(f"VERIFICATION RESULTS: {passed}/{total} SUITES PASSED")
    print("=" * 70)
    
    if passed == total:
        print("\nALL VERIFICATION CRITERIA SATISFIED.")
        sys.exit(0)
    else:
        print(f"\n{total - passed} CRITERIA FAILED.")
        sys.exit(1)
