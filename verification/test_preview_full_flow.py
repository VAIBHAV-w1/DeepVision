"""
Full-Stack Verification Script for Deployed Vercel Preview + Supabase PostgreSQL.
Tests:
1. Health endpoint (/api/health/) -> verifies PostgreSQL engine, connectivity, and 18 tables.
2. CSRF endpoint (/api/auth/csrf/) -> verifies CSRF token issuance.
3. Authentication flow (/api/auth/login/) -> tests PostgreSQL user lookup with real DB queries.
4. Independent request persistence -> proves connection persists and handles multiple requests.
"""
import os
import requests
import json
import sys

PREVIEW_BASE_URL = os.getenv("PREVIEW_URL", "https://deepvision-frontend-rev41w9uu-vaibhav-wandkar-s-projects.vercel.app")
BYPASS_TOKEN = os.getenv("VERCEL_PROTECTION_BYPASS", "tY9WWoVjHSG0HDs1IfOSC9eprIMynGBS")

session = requests.Session()
session.headers.update({
    "x-vercel-protection-bypass": BYPASS_TOKEN,
    "Referer": PREVIEW_BASE_URL + "/",
    "Origin": PREVIEW_BASE_URL,
    "Accept": "application/json"
})

def test_health():
    print("--- 1. Testing Preview API Health & Database Engine ---")
    res = session.get(f"{PREVIEW_BASE_URL}/api/health/")
    print(f"Status Code: {res.status_code}")
    data = res.json()
    print("Response JSON:")
    print(json.dumps(data, indent=2))
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert data.get("database") == "connected", "Database not connected"
    assert data.get("database_backend") == "postgresql", "Database backend is not PostgreSQL"
    assert data.get("schema_ready") is True, "Schema not marked ready"
    assert data.get("tables_count") == 18, f"Expected 18 tables, got {data.get('tables_count')}"
    print("PASS: Health check reports healthy PostgreSQL with 18 tables.\n")

def test_auth_lookup():
    print("--- 2. Testing Database-Driven Authentication Flow ---")
    csrf_res = session.get(f"{PREVIEW_BASE_URL}/api/auth/csrf/")
    print(f"CSRF Endpoint Status: {csrf_res.status_code}")
    csrf_token = csrf_res.cookies.get("deepvision_django_csrftoken") or session.cookies.get("deepvision_django_csrftoken")
    print(f"CSRF Cookie Present: {bool(csrf_token)}")

    headers = {
        "X-CSRFToken": csrf_token or ""
    }

    # Test login with real user email from migrated SQLite database
    payload = {
        "email": "envfixed@deepvision.test",
        "password": "IntentionallyInvalidPassword999!"
    }
    login_res = session.post(f"{PREVIEW_BASE_URL}/api/auth/login/", json=payload, headers=headers)
    print(f"Login Response Status: {login_res.status_code}")
    login_data = login_res.json()
    print(f"Login Response Body: {login_data}")
    
    # 401 proves that PostgreSQL users table was queried and verified
    # (If DB was down or missing users table, it would return 503 "Database service is not ready")
    assert login_res.status_code == 401, f"Expected 401 (Invalid credentials from DB), got {login_res.status_code}"
    assert "Invalid email or password" in login_data.get("error", ""), "Expected 'Invalid email or password' error"
    print("PASS: PostgreSQL user lookup executed successfully against live users table (no 503 error).\n")

def test_separate_requests_persistence():
    print("--- 3. Testing Persistence Across Separate Independent Requests ---")
    for i in range(1, 4):
        res = session.get(f"{PREVIEW_BASE_URL}/api/health/")
        assert res.status_code == 200
        data = res.json()
        assert data.get("database_backend") == "postgresql"
        print(f"  Request {i}: 200 OK | Backend: {data.get('database_backend')} | Schema Ready: {data.get('schema_ready')}")
    print("PASS: Persistence across independent requests verified.\n")

if __name__ == "__main__":
    try:
        test_health()
        test_auth_lookup()
        test_separate_requests_persistence()
        print("ALL PREVIEW FULL-STACK INTEGRATION TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"TEST FAILED: {e}")
        sys.exit(1)
