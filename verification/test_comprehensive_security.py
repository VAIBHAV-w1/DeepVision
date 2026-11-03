"""
DeepVision 4.0 — P1 Comprehensive Security Verification Suite
=============================================================
Independently tests and verifies actual application defenses against:
1. Authentication & 2-Step Login OTP enforcement
2. Authorization & Role-Based Access Control (RBAC)
3. Cross-Site Request Forgery (CSRF) across state-changing endpoints
4. Cross-Site Scripting (XSS) & Content-Type / security headers
5. SQL Injection (SQLi) across query & filter parameters
6. IDOR / BOLA (Multi-tenant isolation across Alerts, Cases, Recordings, Evidence, Cameras)
7. Server-Side Request Forgery (SSRF) on camera CRUD and test-connection
8. Path Traversal / File & Media Boundary Validation
9. Session Cookie Security & Secret Exposure Prevention
10. Immutable Security Audit Logging (AuditLog persistence & RBAC access)

Saves machine-verifiable evidence to D:\\DeepVision\\reports\\p1_security_verification.json.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / "deepvision_django"
DB_PATH = ROOT_DIR / "instance" / "deepvision.db"
REPORT_PATH = ROOT_DIR / "reports" / "p1_security_verification.json"

sys.path.insert(0, str(DJANGO_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.signed_cookies import SessionStore
from apps.accounts.models import User
from apps.alerts.models import Alert, IncidentCase
from apps.cameras.models import Camera
from apps.core.models import AuditLog
from apps.evidence.models import Evidence
from apps.recordings.models import Recording

BASE_URL = "http://127.0.0.1:8000"
RESULTS = []


def record(check_id: str, category: str, passed: bool, details: str):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({
        "id": check_id,
        "category": category,
        "status": status,
        "passed": bool(passed),
        "details": details,
    })
    print(f"[{status:4s}] {check_id} ({category}): {details}")


def make_authenticated_session(user_id: int) -> tuple[requests.Session, str]:
    """Create a real Django signed-cookie session + CSRF token for HTTP testing."""
    sess = requests.Session()
    r_csrf = sess.get(f"{BASE_URL}/api/auth/csrf/", timeout=5)
    csrf_token = r_csrf.json().get("csrfToken", "")

    store = SessionStore()
    store["user_id"] = int(user_id)
    store.save()
    cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
    sess.cookies.set(cookie_name, store.session_key, domain="127.0.0.1", path="/")
    return sess, csrf_token


def main():
    print("=" * 72)
    print("  DEEPVISION 4.0 — P1 COMPREHENSIVE SECURITY VERIFICATION SUITE")
    print("=" * 72)

    # Ensure temporary standard-role test user exists cleanly for RBAC & IDOR tests
    temp_email = "sec_verify_standard_user@deepvision.local"
    temp_pw = "SecVerify#2026!Strong"

    User.objects.filter(email=temp_email).delete()
    std_user = User.objects.create(
        email=temp_email,
        full_name="Security Verify Standard User",
        password_hash=make_password(temp_pw),
        role="user",
        is_active=True,
        is_email_verified=True,
    )
    std_user.set_password(temp_pw)
    std_user.save()

    owner_user = User.objects.filter(id=2).first()
    staff_admin = User.objects.filter(role="admin", is_active=True).first()
    if not owner_user or not staff_admin:
        raise RuntimeError("Owner user (id=2) or staff admin user not found in database.")

    try:
        # ------------------------------------------------------------------
        # 1. AUTHENTICATION & 2-STEP OTP GATING
        # ------------------------------------------------------------------
        anon = requests.Session()
        protected_endpoints = [
            "/api/cameras/",
            "/api/alerts/",
            "/api/recordings/",
            "/api/evidence/",
            "/api/cases/",
            "/api/notifications/",
            "/api/audit-logs/",
            "/api/settings/detection/",
            "/api/dashboard/stats/",
        ]
        unauth_statuses = {}
        for ep in protected_endpoints:
            r = anon.get(f"{BASE_URL}{ep}", timeout=5)
            unauth_statuses[ep] = r.status_code
        all_blocked = all(code in (401, 403) for code in unauth_statuses.values())
        record(
            "SEC-01",
            "Authentication",
            all_blocked,
            f"Unauthenticated requests blocked across {len(protected_endpoints)} APIs: {unauth_statuses}",
        )

        # Verify password login requires step-2 OTP and does NOT prematurely authenticate session
        otp_sess = requests.Session()
        csrf_tok = otp_sess.get(f"{BASE_URL}/api/auth/csrf/", timeout=5).json().get("csrfToken", "")
        r_login = otp_sess.post(
            f"{BASE_URL}/api/auth/login/",
            json={"email": temp_email, "password": temp_pw},
            headers={"X-CSRFToken": csrf_tok},
            timeout=15,
        )
        login_json = r_login.json() if r_login.headers.get("Content-Type", "").startswith("application/json") else {}
        r_me_pre_otp = otp_sess.get(f"{BASE_URL}/api/auth/me/", timeout=5).json()
        r_bad_otp = otp_sess.post(
            f"{BASE_URL}/api/auth/verify-login-otp/",
            json={"email": temp_email, "otp": "000000"},
            headers={"X-CSRFToken": csrf_tok},
            timeout=5,
        )
        otp_gated = (
            r_login.status_code == 200
            and login_json.get("requires_otp") is True
            and r_me_pre_otp.get("authenticated") is False
            and r_bad_otp.status_code in (400, 401, 429)
        )
        record(
            "SEC-02",
            "Authentication / 2FA OTP",
            otp_gated,
            f"Step-1 login requires_otp={login_json.get('requires_otp')}, pre-OTP authenticated={r_me_pre_otp.get('authenticated')}, bad OTP status={r_bad_otp.status_code}",
        )

        # ------------------------------------------------------------------
        # 2. AUTHORIZATION & RBAC
        # ------------------------------------------------------------------
        owner_sess, owner_csrf = make_authenticated_session(owner_user.id)
        admin_sess, admin_csrf = make_authenticated_session(staff_admin.id)
        std_sess, std_csrf = make_authenticated_session(std_user.id)

        # Standard user blocked from audit logs, global detection settings mutation, foreign camera edit/delete, foreign zone create
        r_std_audit = std_sess.get(f"{BASE_URL}/api/audit-logs/", timeout=5)
        r_std_det = std_sess.post(
            f"{BASE_URL}/api/settings/detection/",
            json={"confidence_threshold": 0.40},
            headers={"X-CSRFToken": std_csrf},
            timeout=5,
        )
        r_std_cam_edit = std_sess.put(
            f"{BASE_URL}/api/cameras/4/",
            json={"name": "RBAC Unauthorized Rename"},
            headers={"X-CSRFToken": std_csrf},
            timeout=5,
        )
        r_std_cam_del = std_sess.delete(
            f"{BASE_URL}/api/cameras/4/",
            headers={"X-CSRFToken": std_csrf},
            timeout=5,
        )
        r_std_zone_add = std_sess.post(
            f"{BASE_URL}/api/cameras/4/zones/",
            json={"name": "Unauthorized Zone", "x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5},
            headers={"X-CSRFToken": std_csrf},
            timeout=5,
        )
        rbac_blocks_ok = all(
            code in (403, 404)
            for code in [
                r_std_audit.status_code,
                r_std_det.status_code,
                r_std_cam_edit.status_code,
                r_std_cam_del.status_code,
                r_std_zone_add.status_code,
            ]
        )
        record(
            "SEC-03",
            "RBAC Enforcement",
            rbac_blocks_ok,
            f"role='user' blocked: audit={r_std_audit.status_code}, settings_mutate={r_std_det.status_code}, cam4_edit={r_std_cam_edit.status_code}, cam4_del={r_std_cam_del.status_code}, cam4_zone={r_std_zone_add.status_code}",
        )

        # Verify standard user CAN access shared facility Camera 4 read + clip recording permission, and Admin CAN read audit logs
        r_std_cam4 = std_sess.get(f"{BASE_URL}/api/cameras/4/", timeout=5)
        r_adm_audit = admin_sess.get(f"{BASE_URL}/api/audit-logs/", timeout=5)
        rbac_allows_ok = (r_std_cam4.status_code == 200) and (r_adm_audit.status_code == 200)
        record(
            "SEC-04",
            "RBAC Least-Privilege Access",
            rbac_allows_ok,
            f"role='user' shared facility Camera 4 GET={r_std_cam4.status_code}; role='admin' GET /api/audit-logs/={r_adm_audit.status_code}",
        )

        # ------------------------------------------------------------------
        # 3. CSRF PROTECTION
        # ------------------------------------------------------------------
        # Authenticated cookie session WITHOUT X-CSRFToken header MUST be rejected (403)
        csrf_test_endpoints = [
            ("POST", "/api/auth/demo-session/", {}),
            ("POST", "/api/cameras/", {"name": "CSRF Probe", "source_type": "webcam", "source_value": "0"}),
            ("POST", "/api/cameras/4/zones/", {"name": "CSRF Zone", "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}),
            ("POST", "/api/settings/detection/", {"confidence_threshold": 0.35}),
            ("POST", "/api/cameras/4/record/start/", {}),
        ]
        csrf_codes = {}
        for method, ep, payload in csrf_test_endpoints:
            resp = admin_sess.request(
                method,
                f"{BASE_URL}{ep}",
                json=payload,
                headers={"Origin": "http://evil.attacker.example"},
                timeout=5,
            )
            csrf_codes[f"{method} {ep}"] = resp.status_code
        r_demo_get = anon.get(f"{BASE_URL}/api/auth/demo-session/", timeout=5)
        csrf_ok = all(code == 403 for code in csrf_codes.values()) and (r_demo_get.status_code == 405)
        record(
            "SEC-05",
            "CSRF Protection",
            csrf_ok,
            f"Missing CSRF rejected (403): {csrf_codes}; GET /api/auth/demo-session/={r_demo_get.status_code}",
        )

        # ------------------------------------------------------------------
        # 4. XSS & SECURITY HEADERS
        # ------------------------------------------------------------------
        xss_payload = "<script>window.__xss=1</script><img src=x onerror=alert(1)>"
        r_xss_search = admin_sess.get(
            f"{BASE_URL}/api/alerts/",
            params={"q": xss_payload},
            timeout=5,
        )
        ct = r_xss_search.headers.get("Content-Type", "")
        nosniff = r_xss_search.headers.get("X-Content-Type-Options", "")
        xfo = r_xss_search.headers.get("X-Frame-Options", "")
        r_root = anon.get(f"{BASE_URL}/", timeout=5)
        csp = r_root.headers.get("Content-Security-Policy", "")
        xss_ok = (
            r_xss_search.status_code == 200
            and "application/json" in ct.lower()
            and nosniff.lower() == "nosniff"
            and xfo.upper() in ("DENY", "SAMEORIGIN")
        )
        record(
            "SEC-06",
            "XSS & Security Headers",
            xss_ok,
            f"API Content-Type={ct}, X-Content-Type-Options={nosniff}, X-Frame-Options={xfo}, CSP_present={bool(csp)}",
        )

        # ------------------------------------------------------------------
        # 5. SQL INJECTION (SQLi)
        # ------------------------------------------------------------------
        sqli_payloads = [
            "' OR '1'='1",
            "1; DROP TABLE alerts;--",
            "' UNION SELECT username, password_hash FROM users--",
        ]
        sqli_safe = True
        sqli_notes = []
        for pl in sqli_payloads:
            r1 = std_sess.get(f"{BASE_URL}/api/alerts/", params={"severity": pl, "q": pl}, timeout=5)
            r2 = std_sess.get(f"{BASE_URL}/api/recordings/", params={"camera_id": pl}, timeout=5)
            r3 = std_sess.get(f"{BASE_URL}/api/cases/", params={"status": pl}, timeout=5)
            for label, resp in [("alerts", r1), ("recordings", r2), ("cases", r3)]:
                if resp.status_code >= 500:
                    sqli_safe = False
                    sqli_notes.append(f"{label} returned {resp.status_code}")
                body_txt = resp.text
                if "password_hash" in body_txt or "pbkdf2_" in body_txt:
                    sqli_safe = False
                    sqli_notes.append(f"{label} leaked password hash")
                # Standard user owns 0 alerts/recordings/cases -> SQLi must NEVER return admin's rows!
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get(label, [])
                    if len(items) != 0:
                        sqli_safe = False
                        sqli_notes.append(f"{label} leaked {len(items)} foreign rows on {pl!r}")
        record(
            "SEC-07",
            "SQL Injection Defense",
            sqli_safe,
            "Zero 500s, zero hash leaks, zero cross-tenant rows returned across all SQLi payloads"
            if sqli_safe else "; ".join(sqli_notes),
        )

        # ------------------------------------------------------------------
        # 6. IDOR / BOLA (MULTI-TENANT ISOLATION)
        # ------------------------------------------------------------------
        adm_alert = Alert.objects.filter(user_id=owner_user.id).order_by("-id").first()
        adm_case = IncidentCase.objects.filter(user_id=owner_user.id).order_by("-id").first()
        adm_rec = Recording.objects.filter(user_id=owner_user.id).order_by("-id").first()
        adm_ev = Evidence.objects.filter(user_id=owner_user.id).order_by("-id").first()

        # Also create a temporary private camera owned by owner_user to test private camera IDOR
        priv_cam = Camera.objects.create(
            user_id=owner_user.id,
            name="Temp Owner Private Camera IDOR Check",
            location="Private Vault",
            source_type="ip",
            source="http://192.168.99.99:8080/videofeed",
            status="offline",
            is_active=True,
        )
        try:
            idor_checks = {}
            if adm_alert:
                idor_checks["alert_get"] = std_sess.get(f"{BASE_URL}/api/alerts/{adm_alert.id}/", timeout=5).status_code
                idor_checks["alert_ack"] = std_sess.post(
                    f"{BASE_URL}/alerts/{adm_alert.id}/acknowledge/",
                    headers={"X-CSRFToken": std_csrf},
                    timeout=5,
                ).status_code
                idor_checks["alert_res"] = std_sess.post(
                    f"{BASE_URL}/alerts/{adm_alert.id}/resolve/",
                    headers={"X-CSRFToken": std_csrf},
                    timeout=5,
                ).status_code
            if adm_case:
                idor_checks["case_get"] = std_sess.get(f"{BASE_URL}/api/cases/{adm_case.id}/", timeout=5).status_code
            if adm_rec:
                idor_checks["rec_api"] = std_sess.get(f"{BASE_URL}/api/recordings/{adm_rec.id}/", timeout=5).status_code
                idor_checks["rec_view"] = std_sess.get(f"{BASE_URL}/recordings/{adm_rec.id}/view/", timeout=5).status_code
                idor_checks["rec_dl"] = std_sess.get(f"{BASE_URL}/recordings/{adm_rec.id}/download/", timeout=5).status_code
            if adm_ev:
                idor_checks["ev_api"] = std_sess.get(f"{BASE_URL}/api/evidence/{adm_ev.id}/", timeout=5).status_code
                idor_checks["ev_prev"] = std_sess.get(f"{BASE_URL}/evidence/{adm_ev.id}/preview/", timeout=5).status_code
                idor_checks["ev_dl"] = std_sess.get(f"{BASE_URL}/evidence/{adm_ev.id}/download/", timeout=5).status_code
            idor_checks["priv_cam_get"] = std_sess.get(f"{BASE_URL}/api/cameras/{priv_cam.id}/", timeout=5).status_code
            idor_checks["priv_cam_snap"] = std_sess.get(f"{BASE_URL}/api/cameras/{priv_cam.id}/snapshot/", timeout=5).status_code
        finally:
            priv_cam.delete()

        idor_ok = len(idor_checks) >= 6 and all(code in (403, 404) for code in idor_checks.values())
        record(
            "SEC-08",
            "IDOR / BOLA Multi-Tenant Isolation",
            idor_ok,
            f"Cross-tenant probes blocked: {idor_checks}",
        )

        # Also verify Owner (User 2) list-vs-detail consistency (0 false 404s for authorized owner!)
        adm_recs_list = owner_sess.get(f"{BASE_URL}/api/recordings/", timeout=5).json().get("recordings", [])
        adm_evs_list = owner_sess.get(f"{BASE_URL}/api/evidence/", timeout=5).json().get("evidence", [])
        owner_ok = True
        for item in adm_recs_list[:5]:
            if owner_sess.get(f"{BASE_URL}/api/recordings/{item['id']}/", timeout=5).status_code != 200:
                owner_ok = False
        for item in adm_evs_list[:5]:
            if owner_sess.get(f"{BASE_URL}/api/evidence/{item['id']}/", timeout=5).status_code != 200:
                owner_ok = False
        record(
            "SEC-09",
            "Recording & Evidence Owner Permissions",
            owner_ok,
            f"Authorized owner accessed {min(5, len(adm_recs_list))} recordings and {min(5, len(adm_evs_list))} evidence items with 0 false 404s",
        )

        # ------------------------------------------------------------------
        # 7. SSRF PROTECTION (CAMERA CRUD + TEST-CONNECTION)
        # ------------------------------------------------------------------
        ssrf_targets = [
            ("ip", "http://127.0.0.1:8000/api/health/"),
            ("mjpeg", "http://localhost:8000/api/cameras/4/stream/"),
            ("ip", "http://169.254.169.254/latest/meta-data/"),
            ("rtsp", "rtsp://127.0.0.1:8554/live"),
            ("ip", "http://[::1]:8000/"),
            ("ip", "http://[::ffff:127.0.0.1]:8000/"),
            ("ip", "http://0.0.0.0:8000/"),
            ("ip", "http://metadata.google.internal/computeMetadata/v1/"),
            ("ip", "file:///etc/passwd"),
        ]
        ssrf_results = {}
        ssrf_ok = True
        for stype, surl in ssrf_targets:
            r_tc = admin_sess.post(
                f"{BASE_URL}/api/cameras/test-connection/",
                json={"source_type": stype, "source_value": surl},
                headers={"X-CSRFToken": admin_csrf},
                timeout=5,
            )
            r_cr = admin_sess.post(
                f"{BASE_URL}/api/cameras/",
                json={"name": "SSRF Probe", "source_type": stype, "source_value": surl},
                headers={"X-CSRFToken": admin_csrf},
                timeout=5,
            )
            # Clean up if erroneously created
            if r_cr.status_code in (200, 201):
                cid = r_cr.json().get("camera", {}).get("id")
                if cid:
                    Camera.objects.filter(id=cid).delete()
                ssrf_ok = False
            if r_tc.status_code != 400 or r_cr.status_code != 400:
                ssrf_ok = False
            ssrf_results[surl] = {"test_conn": r_tc.status_code, "create": r_cr.status_code}
        record(
            "SEC-10",
            "SSRF Defense",
            ssrf_ok,
            f"All {len(ssrf_targets)} internal/loopback/metadata SSRF payloads blocked (400) on both test-connection and create: {ssrf_results}",
        )

        # ------------------------------------------------------------------
        # 8. PATH TRAVERSAL & MALFORMED INPUT VALIDATION
        # ------------------------------------------------------------------
        traversal_paths = [
            "/static/../../.env",
            "/static/..%2f..%2finstance%2fdeepvision.db",
            "/media/../../.env",
            "/evidence/../../.env/preview/",
        ]
        trav_ok = True
        trav_codes = {}
        for tp in traversal_paths:
            rt = admin_sess.get(f"{BASE_URL}{tp}", timeout=5)
            trav_codes[tp] = rt.status_code
            if "SECRET_KEY" in rt.text or "SQLite format 3" in rt.text:
                trav_ok = False
        # Malformed JSON body test (must return 400, not 500 traceback)
        r_malformed = admin_sess.post(
            f"{BASE_URL}/api/cameras/",
            data="{broken_json:",
            headers={"Content-Type": "application/json", "X-CSRFToken": admin_csrf},
            timeout=5,
        )
        if r_malformed.status_code != 400 or "Traceback" in r_malformed.text:
            trav_ok = False
        record(
            "SEC-11",
            "Path Traversal & Input Validation",
            trav_ok,
            f"Traversal probes safe ({trav_codes}); malformed JSON status={r_malformed.status_code}",
        )

        # ------------------------------------------------------------------
        # 9. SESSION SECURITY & SECRET EXPOSURE
        # ------------------------------------------------------------------
        # Trigger real demo-session POST with CSRF to inspect actual Set-Cookie attributes from Django
        cookie_probe = requests.Session()
        c_tok = cookie_probe.get(f"{BASE_URL}/api/auth/csrf/", timeout=5).json().get("csrfToken", "")
        r_demo = cookie_probe.post(
            f"{BASE_URL}/api/auth/demo-session/",
            json={},
            headers={"X-CSRFToken": c_tok},
            timeout=5,
        )
        raw_set_cookie = " ; ".join(r_demo.headers.get("Set-Cookie", "").splitlines())
        has_httponly = "httponly" in raw_set_cookie.lower()
        has_samesite = "samesite=lax" in raw_set_cookie.lower() or "samesite=strict" in raw_set_cookie.lower()

        r_h1 = anon.get(f"{BASE_URL}/api/health/", timeout=5).text
        r_h2 = anon.get(f"{BASE_URL}/api/surveillance/health/", timeout=5).text
        secret_markers = ["SECRET_KEY", "SMTP_PASS", "EMAIL_HOST_PASSWORD", "pbkdf2_sha256$", "DATABASE_URL"]
        no_secrets = not any(m in (r_h1 + r_h2 + r_root.text) for m in secret_markers)
        sess_ok = (r_demo.status_code == 200) and has_httponly and has_samesite and no_secrets
        record(
            "SEC-12",
            "Session Security & Secret Exposure",
            sess_ok,
            f"HttpOnly={has_httponly}, SameSite={has_samesite}, zero secrets exposed={no_secrets}",
        )

        # ------------------------------------------------------------------
        # 10. AUDIT LOG PERSISTENCE & VERIFICATION
        # ------------------------------------------------------------------
        before_audit_count = AuditLog.objects.count()
        # Read current detection settings and save identical settings to emit an authentic DETECTION_SETTINGS_UPDATED audit event
        cur_det = admin_sess.get(f"{BASE_URL}/api/settings/detection/", timeout=5).json().get("settings", {})
        r_save_det = admin_sess.post(
            f"{BASE_URL}/api/settings/detection/",
            json={
                "confidence_threshold": cur_det.get("confidence_threshold", 0.35),
                "rules": cur_det.get("rules", {}),
            },
            headers={"X-CSRFToken": admin_csrf},
            timeout=5,
        )
        after_audit_count = AuditLog.objects.count()
        r_audit_api = admin_sess.get(f"{BASE_URL}/api/audit-logs/?limit=10", timeout=5)
        audit_json = r_audit_api.json() if r_audit_api.status_code == 200 else {}
        logs = audit_json.get("audit_logs", [])
        actions_seen = [row.get("action") for row in logs]
        audit_ok = (
            r_save_det.status_code == 200
            and after_audit_count > before_audit_count
            and r_audit_api.status_code == 200
            and "DETECTION_SETTINGS_UPDATED" in actions_seen
        )
        record(
            "SEC-13",
            "Audit Logs Persistence & API",
            audit_ok,
            f"AuditLog rows {before_audit_count} -> {after_audit_count}; recent API actions={actions_seen[:5]}",
        )

    finally:
        User.objects.filter(email=temp_email).delete()

    # Verify DB camera count & integrity preserved
    conn = sqlite3.connect(str(DB_PATH))
    integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
    active_cams = conn.execute("SELECT COUNT(*) FROM cameras WHERE is_active=1;").fetchone()[0]
    conn.close()
    record(
        "SEC-14",
        "Database Integrity Post-Security-Suite",
        integrity == "ok" and active_cams == 10,
        f"PRAGMA integrity_check={integrity}, active_cameras={active_cams}",
    )

    passed_count = sum(1 for r in RESULTS if r["passed"])
    total_count = len(RESULTS)
    summary = {
        "suite": "P1_COMPREHENSIVE_SECURITY_VERIFICATION",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed_count,
        "total": total_count,
        "all_passed": passed_count == total_count,
        "results": RESULTS,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("-" * 72)
    print(f"SECURITY VERIFICATION SUMMARY: {passed_count}/{total_count} PASSED")
    print(f"Saved report -> {REPORT_PATH}")
    sys.exit(0 if passed_count == total_count else 1)


if __name__ == "__main__":
    main()
