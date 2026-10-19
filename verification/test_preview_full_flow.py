"""
Comprehensive End-to-End Verification of Deployed Vercel Preview + Supabase PostgreSQL.
Tests:
1. System Health & PostgreSQL Database Connectivity (/api/health/)
2. CSRF Cookie Negotiation (/api/auth/csrf/)
3. Disposable Test Account Registration (/api/auth/signup/)
4. PostgreSQL Database Persistence of new record
5. Login rejection on unverified account (HTTP 403)
6. Login rejection on invalid password for existing account (HTTP 401)
7. Account enumeration prevention on password reset (/api/auth/forgot-password/)
8. Protected API authorization barriers (HTTP 401) across:
   - Dashboard Stats (/api/dashboard/stats/)
   - Cameras List (/api/cameras/)
   - Alerts List (/api/alerts/)
   - Recordings List (/api/recordings/)
   - Evidence List (/api/evidence/)
   - Cases List (/api/cases/)
9. Cleanup of disposable test record
"""
import os
import time
import requests
import psycopg2
import sys

PREVIEW_BASE_URL = os.getenv("PREVIEW_URL", "https://deepvision-frontend-5gb0ld9ib-vaibhav-wandkar-s-projects.vercel.app")
BYPASS_TOKEN = os.getenv("VERCEL_PROTECTION_BYPASS", "tY9WWoVjHSG0HDs1IfOSC9eprIMynGBS")
PG_URL = os.getenv("DATABASE_URL") or "postgresql://postgres.aqmngllkiepacjrasraf:DeepVision%4012@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres?sslmode=require"

session = requests.Session()
session.headers.update({
    "x-vercel-protection-bypass": BYPASS_TOKEN,
    "Referer": PREVIEW_BASE_URL + "/",
    "Origin": PREVIEW_BASE_URL,
    "Accept": "application/json"
})

def test_health():
    print("[1] Testing System Health & PostgreSQL Verification...")
    res = session.get(f"{PREVIEW_BASE_URL}/api/health/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert data.get("status") == "healthy", f"Expected status healthy, got {data.get('status')}"
    assert data.get("database") == "connected", "Database not connected"
    assert data.get("database_backend") == "postgresql", f"Expected postgresql, got {data.get('database_backend')}"
    assert data.get("schema_ready") is True, "Schema not marked ready"
    assert data.get("tables_count") == 18, f"Expected 18 tables, got {data.get('tables_count')}"
    print(f"    PASS: Database: {data.get('database_backend')}, Schema: Ready ({data.get('tables_count')} tables)")

def test_csrf_and_registration():
    print("[2] Testing CSRF Negotiation & Account Registration Flow...")
    csrf_res = session.get(f"{PREVIEW_BASE_URL}/api/auth/csrf/")
    assert csrf_res.status_code == 200, f"CSRF failed: {csrf_res.status_code}"
    csrf_token = csrf_res.cookies.get("deepvision_django_csrftoken") or session.cookies.get("deepvision_django_csrftoken")
    assert bool(csrf_token), "No CSRF token found in response"
    
    headers = {"X-CSRFToken": csrf_token}
    test_email = f"disposable.test.{int(time.time())}@deepvision.internal"
    test_password = "StrongTestPassword123!"

    signup_res = session.post(f"{PREVIEW_BASE_URL}/api/auth/signup/", json={
        "full_name": "Disposable Test Operator",
        "email": test_email,
        "password": test_password,
        "confirm_password": test_password
    }, headers=headers)
    
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.status_code} - {signup_res.text}"
    signup_data = signup_res.json()
    assert signup_data.get("success") is True, "Signup success was not true"
    print(f"    PASS: User created via Preview API: {test_email}")

    # Verify directly in Supabase PostgreSQL
    conn = psycopg2.connect(PG_URL, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute("SELECT id, full_name, is_email_verified, is_active FROM users WHERE email = %s", (test_email,))
        row = cur.fetchone()
        assert row is not None, "User not found in Supabase PostgreSQL!"
        user_id, full_name, is_verified, is_active = row
        assert is_verified is False, "New user should have is_email_verified = False"
        assert is_active is True, "New user should have is_active = True"
        print(f"    PASS: Confirmed record persisted in Supabase PostgreSQL (ID: {user_id}, Verified: {is_verified})")

        # [3] Test login with unverified account
        print("[3] Testing Login with Unverified Account...")
        login_res = session.post(f"{PREVIEW_BASE_URL}/api/auth/login/", json={
            "email": test_email,
            "password": test_password
        }, headers=headers)
        assert login_res.status_code == 403, f"Expected 403, got {login_res.status_code}"
        assert login_res.json().get("needs_verification") is True
        print("    PASS: Unverified account blocked with 403 and needs_verification=True")

        # Clean up test user
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        print(f"    PASS: Disposable test user cleaned up cleanly (ID: {user_id})")
    conn.close()

def test_auth_security_checks():
    print("[4] Testing Security & Protection Controls...")
    csrf_token = session.cookies.get("deepvision_django_csrftoken") or ""
    headers = {"X-CSRFToken": csrf_token}

    # Test invalid password for existing account
    res = session.post(f"{PREVIEW_BASE_URL}/api/auth/login/", json={
        "email": "envfixed@deepvision.test",
        "password": "WrongPassword999!"
    }, headers=headers)
    assert res.status_code == 401
    assert "Invalid email or password" in res.json().get("error", "")
    print("    PASS: Invalid password rejected with 401 without error disclosure")

    # Test account enumeration prevention on forgot password
    res = session.post(f"{PREVIEW_BASE_URL}/api/auth/forgot-password/", json={
        "email": "nonexistent.random.user.999@deepvision.internal"
    }, headers=headers)
    assert res.status_code == 200
    assert "If an account exists" in res.json().get("message", "")
    print("    PASS: Password recovery returns constant enumeration-safe message")

    # Test reset OTP verification with malformed/invalid code
    res = session.post(f"{PREVIEW_BASE_URL}/api/auth/verify-reset-otp/", json={
        "email": "envfixed@deepvision.test",
        "otp": "000000"
    }, headers=headers)
    assert res.status_code == 400
    print("    PASS: Invalid reset OTP rejected with 400")

def test_protected_routes():
    print("[5] Testing Protected API Authorization Barriers...")
    endpoints = [
        "/api/dashboard/stats/",
        "/api/cameras/",
        "/api/alerts/",
        "/api/recordings/",
        "/api/evidence/",
        "/api/cases/",
    ]
    unauth_session = requests.Session()
    unauth_session.headers.update({
        "x-vercel-protection-bypass": BYPASS_TOKEN,
        "Accept": "application/json"
    })
    for ep in endpoints:
        res = unauth_session.get(f"{PREVIEW_BASE_URL}{ep}")
        assert res.status_code == 401, f"Expected 401 on {ep}, got {res.status_code}"
        print(f"    PASS: {ep:<30} -> HTTP 401 (Protected)")

if __name__ == "__main__":
    try:
        test_health()
        test_csrf_and_registration()
        test_auth_security_checks()
        test_protected_routes()
        print("\nALL FULL-STACK VERIFICATION TESTS COMPLETED AND PASSED!")
    except Exception as e:
        print(f"\nVERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
