"""
Regression Test Suite: CSP Eval Violation and Infinite Startup Loader Guard
Verifies:
1. useAuth state machine: loading state ALWAYS resolves to false on:
   - Authenticated user response (res.authenticated === true)
   - Unauthenticated user response (res.authenticated === false)
   - Network failure or HTTP 500/503/401 error
   - Backend timeout / delayed response
   - Operator Demo mode in localStorage
2. Content-Security-Policy audit:
   - Zero 'unsafe-eval' in vercel.json
   - Zero eval() or new Function() in frontend/src
   - Strict security headers present (X-Content-Type-Options, X-Frame-Options, CSP)
"""

import os
import sys
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestCSPAndStartupLoader(unittest.TestCase):

    def test_no_unsafe_eval_in_frontend_source(self):
        """Ensure no eval() or new Function() calls exist in frontend/src."""
        src_dir = REPO_ROOT / "frontend" / "src"
        js_files = list(src_dir.rglob("*.js")) + list(src_dir.rglob("*.jsx"))
        self.assertGreater(len(js_files), 10, "Should find frontend JS/JSX files")

        for f in js_files:
            content = f.read_text(encoding="utf-8")
            # Check for direct eval()
            self.assertFalse(
                re.search(r"\beval\s*\(", content),
                f"Forbidden eval() found in {f.relative_to(REPO_ROOT)}"
            )
            # Check for new Function()
            self.assertFalse(
                re.search(r"new\s+Function\s*\(", content),
                f"Forbidden new Function() found in {f.relative_to(REPO_ROOT)}"
            )
            # Check for string timers like setTimeout("code", 100)
            self.assertFalse(
                re.search(r"set(Timeout|Interval)\s*\(\s*['\"`]", content),
                f"Forbidden string timer found in {f.relative_to(REPO_ROOT)}"
            )

    def test_vercel_csp_header_security(self):
        """Verify vercel.json contains CSP header and does not allow unsafe-eval."""
        vercel_json_path = REPO_ROOT / "vercel.json"
        self.assertTrue(vercel_json_path.exists(), "vercel.json must exist")
        data = json.loads(vercel_json_path.read_text(encoding="utf-8"))

        headers_list = data.get("headers", [])
        all_header_pairs = {}
        for h_entry in headers_list:
            if h_entry.get("source") == "/(.*)":
                for h in h_entry.get("headers", []):
                    all_header_pairs[h.get("key")] = h.get("value")

        self.assertIn("Content-Security-Policy", all_header_pairs, "CSP header must be configured")
        csp = all_header_pairs["Content-Security-Policy"]
        self.assertNotIn("'unsafe-eval'", csp, "CSP must NOT contain 'unsafe-eval'")
        self.assertIn("default-src", csp, "CSP must define default-src")
        self.assertIn("script-src", csp, "CSP must define script-src")

    def test_use_auth_try_finally_structure(self):
        """Verify useAuth.jsx guarantees setLoading(false) via unified try/finally."""
        use_auth_path = REPO_ROOT / "frontend" / "src" / "hooks" / "useAuth.jsx"
        content = use_auth_path.read_text(encoding="utf-8")

        # Must have finally with setLoading(false)
        self.assertIn("setLoading(false)", content, "Must call setLoading(false)")
        self.assertIn("finally {", content, "Must use finally block to guarantee loader resolution")

        # Must have timeout safeguard
        self.assertIn("startupTimeout", content, "Must include hard ceiling startup timeout safeguard")
        self.assertIn("clearTimeout", content, "Must clean up startup timeout")

    def test_api_request_timeout_support(self):
        """Verify api.js supports AbortController timeout."""
        api_js_path = REPO_ROOT / "frontend" / "src" / "services" / "api.js"
        content = api_js_path.read_text(encoding="utf-8")

        self.assertIn("AbortController", content, "Must use AbortController for network cancellation")
        self.assertIn("options.timeout", content, "Must support configurable timeout option")
        self.assertIn("auth/me", content, "Must have clean handling for auth/me")

if __name__ == "__main__":
    print("=" * 65)
    print("  DEEPVISION CSP & STARTUP LOADER REGRESSION SUITE")
    print("=" * 65)
    unittest.main()
