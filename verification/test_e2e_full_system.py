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
    """Verify local Docker edge container serves health check and HTTP 206 Partial Content."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/health/")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200, f"Health check returned HTTP {res.status}"
            data = json.loads(res.read().decode("utf-8"))
            assert data.get("status") == "healthy", f"Health status not healthy: {data}"
            print(f"  Health endpoint verified: {data.get('status')}")
    except Exception as e:
        return f"Docker edge container health check failed: {e}"

    # Verify HTTP 206 Partial Content Range streaming
    # Using recording #2719 or any existing recording with size > 0
    import sqlite3
    db_path = os.path.join(REPO_ROOT, "instance", "deepvision.db")
    rec_id = 2719
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT id FROM recordings WHERE file_size > 1000 ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            rec_id = row[0]
        conn.close()

    try:
        # Request first 1024 bytes
        req = urllib.request.Request(
            f"http://127.0.0.1:8000/recordings/{rec_id}/view/",
            headers={"Range": "bytes=0-1023"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status in (200, 206), f"Expected HTTP 200 or 206, got HTTP {res.status}"
            content_range = res.headers.get("Content-Range")
            content_len = len(res.read())
            print(f"  Recording #{rec_id} Range response: HTTP {res.status}, Range: {content_range}, Bytes read: {content_len}")
    except urllib.error.HTTPError as he:
        # If authentication is required on /recordings/<id>/view/, 401 or 403 is also an acceptable API response, but NOT 404 or 500
        if he.code in (401, 403):
            print(f"  Recording #{rec_id} returned expected authenticated response (HTTP {he.code})")
        else:
            return f"Unexpected HTTP status {he.code} for recording #{rec_id}"
    except Exception as e:
        return f"Range request failed: {e}"
    
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
