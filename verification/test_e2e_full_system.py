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
        "frontend/src/pages/Surveillance.jsx",
        "frontend/src/components/common/CameraLivePlayer.jsx"
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

    # Verify actual telemetry binding in CameraLivePlayer and Surveillance
    live_player_path = os.path.join(REPO_ROOT, "frontend/src/components/common/CameraLivePlayer.jsx")
    with open(live_player_path, "r", encoding="utf-8") as f:
        lp_content = f.read()
    assert "liveStats?.fps" in lp_content or "measuredFps" in lp_content, "CameraLivePlayer not bound to dynamic telemetry"

    surveillance_path = os.path.join(REPO_ROOT, "frontend/src/pages/Surveillance.jsx")
    with open(surveillance_path, "r", encoding="utf-8") as f:
        surv_content = f.read()
    assert "inference_fps" in surv_content, "Surveillance.jsx missing telemetry bindings"
    return True

def test_logo_and_theme_assets():
    """Verify enterprise Logo component and SVG favicons exist and are referenced."""
    logo_path = os.path.join(REPO_ROOT, "frontend/src/components/common/Logo.jsx")
    assert os.path.exists(logo_path), "Logo.jsx component missing"
    
    with open(logo_path, "r", encoding="utf-8") as f:
        logo_content = f.read()
    assert "surveillance-reticle" in logo_content or "svg" in logo_content, "Invalid Logo component"
    
    # Check favicons with DeepVision cyan/blue optical lens and reticle brand palette
    favicons = [
        "frontend/public/favicon.svg",
        "frontend/public/static/images/favicon.svg",
        "deepvision_django/static/images/favicon.svg"
    ]
    dist_fav = os.path.join(REPO_ROOT, "deepvision_django/static/dist/favicon.svg")
    if os.path.exists(dist_fav):
        favicons.append("deepvision_django/static/dist/favicon.svg")

    approved_brand_colors = ["#00F5D4", "#00C9FF", "#0072FF", "#00AFC4", "#0B0F19", "#38BDF8", "#2563EB", "#1D4ED8", "#0EA5E9"]
    for fav in favicons:
        p = os.path.join(REPO_ROOT, fav)
        assert os.path.exists(p), f"Favicon missing: {fav}"
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        assert "<svg" in c, f"Favicon {fav} does not contain valid SVG markup"
        assert any(color.lower() in c.lower() for color in approved_brand_colors), (
            f"Favicon {fav} does not contain DeepVision approved brand palette"
        )
        assert "<circle" in c or "<path" in c, f"Favicon {fav} missing surveillance geometry elements"

    # Verify index.html references the SVG favicon
    index_html = os.path.join(REPO_ROOT, "frontend/index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        idx_c = f.read()
    assert 'rel="icon"' in idx_c and "favicon.svg" in idx_c, "frontend/index.html does not link SVG favicon"

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
    base_url = os.getenv("DEEPVISION_BASE_URL", "http://127.0.0.1:8000")
    health_url = f"{base_url.rstrip('/')}/api/health/"

    # Setup Django environment
    import django
    from django.conf import settings
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        sys.path.insert(0, os.path.join(REPO_ROOT, "deepvision_django"))
        django.setup()

    server_live = False
    try:
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=3) as res:
            assert res.status == 200, f"Health check returned HTTP {res.status}"
            data = json.loads(res.read().decode("utf-8"))
            assert data.get("status") == "healthy", f"Health status not healthy: {data}"
            print(f"  Live Health endpoint verified: {data.get('status')}")
            server_live = True
    except Exception as e:
        print(f"  Live server not reachable ({e}); validating via Django test engine...")
        from django.test import Client
        c = Client()
        res = c.get("/api/health/")
        assert res.status_code == 200, f"Health check returned HTTP {res.status_code}"
        data = res.json()
        assert data.get("status") == "healthy", f"Health status not healthy: {data}"
        print(f"  In-process Health endpoint verified: {data.get('status')}")

    from django.contrib.sessions.backends.signed_cookies import SessionStore
    from apps.recordings.models import Recording
    from apps.core.media_service import safe_resolve_recording

    # Find a real recording with a physical file on disk, OR create an isolated test fixture
    recording = None
    full_path = None
    cleanup_fixture = False

    for r in Recording.objects.all().order_by("-id")[:50]:
        resolved = safe_resolve_recording(r.file_path)
        if resolved and os.path.isfile(resolved) and r.file_size > 1024:
            recording = r
            full_path = resolved
            break

    # If no existing physical recording on disk (e.g. CI or fresh container), create a safe test fixture
    if not recording:
        rec_dir = os.path.join(REPO_ROOT, "recordings")
        os.makedirs(rec_dir, exist_ok=True)
        fixture_filename = "ci_test_fixture_206.mp4"
        full_path = os.path.join(rec_dir, fixture_filename)
        # Create 4096 bytes dummy MP4 fixture
        with open(full_path, "wb") as f:
            f.write(b"\x00" * 4096)
        
        recording = Recording.objects.create(
            camera_id=1,
            user_id=1,
            file_name=fixture_filename,
            file_path=full_path,
            file_size=4096,
            duration=10,
            status="completed"
        )
        cleanup_fixture = True
        print(f"  Created isolated test recording fixture: ID #{recording.id} (4096 bytes)")

    try:
        actual_file_size = os.path.getsize(full_path)

        # Generate authenticated session cookie
        s = SessionStore()
        s["user_id"] = recording.user_id
        s.save()
        session_cookie = s.session_key

        expected_range = f"bytes 0-1023/{actual_file_size}"

        if server_live:
            # 1. Genuine HTTP 206 Partial Content Range Request (bytes 0-1023)
            req_206 = urllib.request.Request(
                f"{base_url.rstrip('/')}/recordings/{recording.id}/view/",
                headers={
                    "Range": "bytes=0-1023",
                    "Cookie": f"deepvision_django_session={session_cookie}"
                }
            )
            with urllib.request.urlopen(req_206, timeout=5) as res:
                assert res.status == 206, f"Expected HTTP 206, got {res.status}"
                content_range = res.headers.get("Content-Range")
                assert content_range == expected_range, f"Expected Content-Range '{expected_range}', got '{content_range}'"
                content_len_hdr = res.headers.get("Content-Length")
                assert content_len_hdr == "1024", f"Expected Content-Length 1024, got {content_len_hdr}"
                body = res.read()
                assert len(body) == 1024, f"Expected 1024 bytes body, got {len(body)}"
                print(f"  Recording #{recording.id} HTTP 206 Verified: Range: {content_range}, Length: {content_len_hdr}")

            # 2. Unsatisfiable Range (bytes 999999999-999999999) -> Expect HTTP 416
            req_416 = urllib.request.Request(
                f"{base_url.rstrip('/')}/recordings/{recording.id}/view/",
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
                f"{base_url.rstrip('/')}/recordings/{recording.id}/view/",
                headers={
                    "Cookie": f"deepvision_django_session={session_cookie}"
                }
            )
            with urllib.request.urlopen(req_200, timeout=5) as res:
                assert res.status == 200, f"Expected HTTP 200 for full stream, got {res.status}"
                assert res.headers.get("Accept-Ranges") == "bytes", "Missing Accept-Ranges: bytes"
                assert res.headers.get("Content-Length") == str(actual_file_size), "Mismatched full Content-Length"
                print(f"  Recording #{recording.id} HTTP 200 Full Stream Verified: Length: {actual_file_size} bytes")
        else:
            from django.test import Client
            client = Client()
            client.cookies["deepvision_django_session"] = session_cookie

            # 1. HTTP 206 Partial Content Range Request
            res_206 = client.get(f"/recordings/{recording.id}/view/", HTTP_RANGE="bytes=0-1023")
            assert res_206.status_code == 206, f"Expected HTTP 206, got {res_206.status_code}"
            assert res_206.headers.get("Content-Range") == expected_range, f"Expected '{expected_range}', got {res_206.headers.get('Content-Range')}"
            assert res_206.headers.get("Content-Length") == "1024", f"Expected Content-Length 1024, got {res_206.headers.get('Content-Length')}"
            body_206 = b"".join(res_206.streaming_content) if hasattr(res_206, "streaming_content") else res_206.content
            assert len(body_206) == 1024, f"Expected 1024 bytes body, got {len(body_206)}"
            print(f"  Recording #{recording.id} HTTP 206 Verified: Range: {expected_range}, Length: 1024")

            # 2. HTTP 416 Out-of-Range
            res_416 = client.get(f"/recordings/{recording.id}/view/", HTTP_RANGE="bytes=999999999-999999999")
            assert res_416.status_code == 416, f"Expected HTTP 416, got {res_416.status_code}"
            assert res_416.headers.get("Content-Range") == f"bytes */{actual_file_size}", "Invalid 416 Content-Range header"
            print(f"  Recording #{recording.id} HTTP 416 Out-of-Range Guard Verified")

            # 3. HTTP 200 Full Stream
            res_200 = client.get(f"/recordings/{recording.id}/view/")
            assert res_200.status_code == 200, f"Expected HTTP 200, got {res_200.status_code}"
            assert res_200.headers.get("Accept-Ranges") == "bytes", "Missing Accept-Ranges: bytes"
            assert res_200.headers.get("Content-Length") == str(actual_file_size), "Mismatched full Content-Length"
            print(f"  Recording #{recording.id} HTTP 200 Full Stream Verified: Length: {actual_file_size} bytes")

        return True
    finally:
        if cleanup_fixture:
            try:
                recording.delete()
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception:
                pass

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
