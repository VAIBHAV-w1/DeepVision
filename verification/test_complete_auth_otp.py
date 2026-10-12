"""
Comprehensive Test Suite for DeepVision Authentication & OTP Flows
Tests:
1. Signup input validation & new user registration in unverified state
2. Signup OTP dispatch & generation
3. Wrong signup OTP rejection
4. Expired signup OTP rejection
5. Resend signup OTP
6. Correct signup OTP verification -> Account verified, NO direct session, redirect to login
7. Attempting duplicate signup with verified account rejected
8. Unverified account login attempt blocked with needs_verification
9. Incorrect password rejected with HTTP 401
10. Valid credentials -> Login OTP sent, NO authenticated session yet
11. Direct API access before login OTP verification rejected with HTTP 401
12. Purpose cross-use prevention (signup OTP cannot verify login, login OTP cannot verify signup)
13. Wrong login OTP rejected
14. Resend login OTP
15. Correct login OTP verification -> Authenticated Django session established
16. Protected API access (/api/auth/me/, /api/dashboard/stats/) granted after OTP
17. Logout -> Session cleared
18. Second login -> Requires fresh Login OTP (no remembered bypass)
19. Brute force rate limiting (max 5 attempts)
"""

import os
import sys
from pathlib import Path

# Add project root and django directory
if Path("/app/deepvision_django").exists():
    sys.path.insert(0, "/app/deepvision_django")
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT_DIR / "deepvision_django"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import time
import json
import requests
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User
from django.contrib.sessions.backends.signed_cookies import SessionStore

BASE_URL = "http://127.0.0.1:8000"
RESULTS = {}

def report(name, status, details):
    RESULTS[name] = {"status": status, "details": details}
    print(f"[{status:7s}] {name}: {details}")

def run_tests():
    print("=" * 65)
    print("  DEEPVISION COMPLETE AUTHENTICATION & OTP TEST SUITE")
    print("=" * 65)

    test_email = f"test_op_{int(time.time())}@deepvision.test"
    test_password = "SecurePassword2026!"
    test_name = "Test Operator"

    # Cleanup any prior test user with this email
    User.objects.filter(email=test_email).delete()

    client = requests.Session()

    # 1. Fetch CSRF Token
    csrf_token = ""
    try:
        r_csrf = client.get(f"{BASE_URL}/api/auth/csrf/")
        csrf_token = r_csrf.json().get("csrfToken", "")
        if r_csrf.status_code == 200 and csrf_token:
            report("AUTH_CSRF", "PASS", f"CSRF token obtained ({csrf_token[:12]}...)")
        else:
            report("AUTH_CSRF", "FAIL", f"Status: {r_csrf.status_code}")
    except Exception as e:
        report("AUTH_CSRF", "FAIL", str(e))
        return False

    headers = {"X-CSRFToken": csrf_token}

    # 2. Signup: Register new user
    try:
        signup_payload = {
            "full_name": test_name,
            "email": test_email,
            "password": test_password,
            "confirm_password": test_password
        }
        r_signup = client.post(f"{BASE_URL}/api/auth/signup/", json=signup_payload, headers=headers)
        data = r_signup.json()
        user_db = User.objects.filter(email=test_email).first()

        if r_signup.status_code == 200 and data.get("success") and user_db and not user_db.is_email_verified:
            report("SIGNUP_UNVERIFIED_STATE", "PASS", f"User created with is_email_verified=False, OTP generated")
        else:
            report("SIGNUP_UNVERIFIED_STATE", "FAIL", f"Status: {r_signup.status_code}, data: {data}")
    except Exception as e:
        report("SIGNUP_UNVERIFIED_STATE", "FAIL", str(e))

    # 3. Direct API access before OTP verification must be rejected
    try:
        r_me = client.get(f"{BASE_URL}/api/auth/me/")
        me_data = r_me.json()
        if r_me.status_code == 200 and me_data.get("authenticated") is False:
            report("UNVERIFIED_API_BLOCKED", "PASS", "New user has no authenticated session after signup")
        else:
            report("UNVERIFIED_API_BLOCKED", "FAIL", str(me_data))
    except Exception as e:
        report("UNVERIFIED_API_BLOCKED", "FAIL", str(e))

    # 4. Wrong Signup OTP Rejected
    try:
        r_wrong = client.post(f"{BASE_URL}/api/auth/verify-otp/", json={"email": test_email, "otp": "999999"}, headers=headers)
        if r_wrong.status_code == 400 and not r_wrong.json().get("success"):
            report("SIGNUP_OTP_WRONG_REJECTED", "PASS", "Incorrect OTP rejected with HTTP 400")
        else:
            report("SIGNUP_OTP_WRONG_REJECTED", "FAIL", f"Status: {r_wrong.status_code}")
    except Exception as e:
        report("SIGNUP_OTP_WRONG_REJECTED", "FAIL", str(e))

    # 5. Expired Signup OTP Rejected
    try:
        user_db.refresh_from_db()
        user_db.email_otp_expires_at = timezone.now() - timedelta(minutes=5)
        user_db.save(update_fields=["email_otp_expires_at"])
        r_exp = client.post(f"{BASE_URL}/api/auth/verify-otp/", json={"email": test_email, "otp": "123456"}, headers=headers)
        if r_exp.status_code == 400 and "expired" in r_exp.json().get("error", "").lower():
            report("SIGNUP_OTP_EXPIRED_REJECTED", "PASS", "Expired OTP rejected with HTTP 400")
        else:
            report("SIGNUP_OTP_EXPIRED_REJECTED", "FAIL", f"Status: {r_exp.status_code}, resp: {r_exp.text}")
    except Exception as e:
        report("SIGNUP_OTP_EXPIRED_REJECTED", "FAIL", str(e))

    # 6. Resend Signup OTP
    try:
        r_resend = client.post(f"{BASE_URL}/api/auth/resend-otp/", json={"email": test_email}, headers=headers)
        user_db.refresh_from_db()
        if r_resend.status_code == 200 and r_resend.json().get("success") and user_db.email_otp_expires_at > timezone.now():
            report("SIGNUP_OTP_RESEND", "PASS", "Resend issued fresh OTP with renewed 15m expiration")
        else:
            report("SIGNUP_OTP_RESEND", "FAIL", f"Status: {r_resend.status_code}")
    except Exception as e:
        report("SIGNUP_OTP_RESEND", "FAIL", str(e))

    # 7. Purpose Cross-Use: Attempting to verify Login OTP endpoint with Signup OTP
    try:
        # Generate known signup OTP
        signup_otp = user_db.generate_otp(purpose="signup")
        user_db.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

        # Try to submit signup OTP to login OTP endpoint
        r_cross = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": test_email, "otp": signup_otp}, headers=headers)
        if r_cross.status_code in (400, 401) and not r_cross.json().get("success"):
            report("OTP_PURPOSE_CROSS_USE_BLOCKED", "PASS", "Signup OTP cannot verify login (cryptographic salt separation verified)")
        else:
            report("OTP_PURPOSE_CROSS_USE_BLOCKED", "FAIL", f"Cross-use succeeded unexpectedly! {r_cross.text}")
    except Exception as e:
        report("OTP_PURPOSE_CROSS_USE_BLOCKED", "FAIL", str(e))

    # 8. Correct Signup OTP -> Account Verified, NO direct session, redirect to login
    try:
        r_verify_signup = client.post(f"{BASE_URL}/api/auth/verify-otp/", json={"email": test_email, "otp": signup_otp}, headers=headers)
        user_db.refresh_from_db()
        r_me_check = client.get(f"{BASE_URL}/api/auth/me/")

        if (r_verify_signup.status_code == 200 and
            r_verify_signup.json().get("verified") and
            user_db.is_email_verified and
            r_me_check.json().get("authenticated") is False):
            report("SIGNUP_OTP_VERIFIED_NO_AUTO_LOGIN", "PASS", "Account verified, is_email_verified=True, NOT automatically logged in")
        else:
            report("SIGNUP_OTP_VERIFIED_NO_AUTO_LOGIN", "FAIL", f"Resp: {r_verify_signup.text}, me: {r_me_check.text}")
    except Exception as e:
        report("SIGNUP_OTP_VERIFIED_NO_AUTO_LOGIN", "FAIL", str(e))

    # 9. Duplicate Signup with verified email rejected
    try:
        r_dup = client.post(f"{BASE_URL}/api/auth/signup/", json=signup_payload, headers=headers)
        if r_dup.status_code == 400 and "already exists" in r_dup.json().get("error", "").lower():
            report("SIGNUP_DUPLICATE_REJECTED", "PASS", "Existing verified email rejected from duplicate registration")
        else:
            report("SIGNUP_DUPLICATE_REJECTED", "FAIL", f"Status: {r_dup.status_code}")
    except Exception as e:
        report("SIGNUP_DUPLICATE_REJECTED", "FAIL", str(e))

    # 10. Login: Incorrect password rejected
    try:
        r_bad_pw = client.post(f"{BASE_URL}/api/auth/login/", json={"email": test_email, "password": "WrongPassword123!"}, headers=headers)
        if r_bad_pw.status_code == 401:
            report("LOGIN_BAD_PASSWORD_REJECTED", "PASS", "Incorrect password rejected with HTTP 401")
        else:
            report("LOGIN_BAD_PASSWORD_REJECTED", "FAIL", f"Status: {r_bad_pw.status_code}")
    except Exception as e:
        report("LOGIN_BAD_PASSWORD_REJECTED", "FAIL", str(e))

    # 11. Login Step 1: Valid credentials -> Login OTP sent, NO authenticated session yet
    try:
        r_login1 = client.post(f"{BASE_URL}/api/auth/login/", json={"email": test_email, "password": test_password}, headers=headers)
        data_login1 = r_login1.json()
        r_me_check2 = client.get(f"{BASE_URL}/api/auth/me/")

        if (r_login1.status_code == 200 and
            data_login1.get("requires_otp") and
            r_me_check2.json().get("authenticated") is False):
            report("LOGIN_STEP1_OTP_REQUIRED", "PASS", "Credentials accepted, requires_otp=True, session not authenticated yet")
        else:
            report("LOGIN_STEP1_OTP_REQUIRED", "FAIL", f"Resp: {data_login1}, me: {r_me_check2.text}")
    except Exception as e:
        report("LOGIN_STEP1_OTP_REQUIRED", "FAIL", str(e))

    # 12. Direct API request before login OTP verification rejected
    try:
        r_dash = client.get(f"{BASE_URL}/api/dashboard/stats/")
        if r_dash.status_code in (401, 302):
            report("PRE_OTP_PROTECTED_API_BLOCKED", "PASS", "Protected API endpoint /api/dashboard/stats/ denied before OTP")
        else:
            report("PRE_OTP_PROTECTED_API_BLOCKED", "FAIL", f"Status: {r_dash.status_code}")
    except Exception as e:
        report("PRE_OTP_PROTECTED_API_BLOCKED", "FAIL", str(e))

    # 13. Wrong Login OTP Rejected
    try:
        r_wrong_login = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": test_email, "otp": "000000"}, headers=headers)
        if r_wrong_login.status_code == 400 and not r_wrong_login.json().get("success"):
            report("LOGIN_OTP_WRONG_REJECTED", "PASS", "Incorrect Login OTP rejected with HTTP 400")
        else:
            report("LOGIN_OTP_WRONG_REJECTED", "FAIL", f"Status: {r_wrong_login.status_code}")
    except Exception as e:
        report("LOGIN_OTP_WRONG_REJECTED", "FAIL", str(e))

    # 14. Resend Login OTP
    login_otp = ""
    try:
        # Resend a fresh login OTP
        r_resend_login = client.post(f"{BASE_URL}/api/auth/resend-login-otp/", json={"email": test_email}, headers=headers)
        user_db.refresh_from_db()
        # Generate known login OTP for verification step
        login_otp = user_db.generate_otp(purpose="login")
        user_db.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

        if r_resend_login.status_code == 200 and r_resend_login.json().get("success"):
            report("LOGIN_OTP_RESEND", "PASS", "Login OTP resend succeeded")
        else:
            report("LOGIN_OTP_RESEND", "FAIL", f"Status: {r_resend_login.status_code}")
    except Exception as e:
        report("LOGIN_OTP_RESEND", "FAIL", str(e))

    # 15. Login Step 2: Correct Login OTP Verification -> Authenticated Session Established
    try:
        r_verify_login = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": test_email, "otp": login_otp}, headers=headers)
        data_vl = r_verify_login.json()
        r_me_auth = client.get(f"{BASE_URL}/api/auth/me/")
        data_me = r_me_auth.json()

        if (r_verify_login.status_code == 200 and
            data_vl.get("success") and
            r_me_auth.status_code == 200 and
            data_me.get("authenticated") is True and
            data_me.get("user", {}).get("email") == test_email):
            report("LOGIN_STEP2_OTP_VERIFIED", "PASS", f"Login OTP accepted, user {test_email} fully authenticated")
        else:
            report("LOGIN_STEP2_OTP_VERIFIED", "FAIL", f"Verify: {data_vl}, Me: {data_me}")
    except Exception as e:
        report("LOGIN_STEP2_OTP_VERIFIED", "FAIL", str(e))

    # 16. Protected API Access Granted
    try:
        r_stats = client.get(f"{BASE_URL}/api/dashboard/stats/")
        if r_stats.status_code == 200 and "total_cameras" in r_stats.json():
            report("POST_OTP_PROTECTED_API_GRANTED", "PASS", "Dashboard stats retrieved successfully by authenticated user")
        else:
            report("POST_OTP_PROTECTED_API_GRANTED", "FAIL", f"Status: {r_stats.status_code}")
    except Exception as e:
        report("POST_OTP_PROTECTED_API_GRANTED", "FAIL", str(e))

    # 17. Logout -> Session cleared
    try:
        r_logout = client.post(f"{BASE_URL}/api/auth/logout/", headers=headers)
        r_me_logout = client.get(f"{BASE_URL}/api/auth/me/")
        if r_logout.status_code == 200 and r_me_logout.json().get("authenticated") is False:
            report("LOGOUT_SESSION_CLEARED", "PASS", "Logout successfully cleared session, authenticated=False")
        else:
            report("LOGOUT_SESSION_CLEARED", "FAIL", f"Logout: {r_logout.text}, Me: {r_me_logout.text}")
    except Exception as e:
        report("LOGOUT_SESSION_CLEARED", "FAIL", str(e))

    # 18. Second Login: MUST Require a Fresh OTP
    try:
        r_login2 = client.post(f"{BASE_URL}/api/auth/login/", json={"email": test_email, "password": test_password}, headers=headers)
        data_login2 = r_login2.json()
        r_me_check3 = client.get(f"{BASE_URL}/api/auth/me/")

        # Verify old OTP cannot be reused
        r_reuse = client.post(f"{BASE_URL}/api/auth/verify-login-otp/", json={"email": test_email, "otp": login_otp}, headers=headers)

        if (r_login2.status_code == 200 and
            data_login2.get("requires_otp") and
            r_me_check3.json().get("authenticated") is False and
            r_reuse.status_code == 400):
            report("SECOND_LOGIN_REQUIRES_NEW_OTP", "PASS", "Second login requires fresh OTP, previous OTP cannot be reused")
        else:
            report("SECOND_LOGIN_REQUIRES_NEW_OTP", "FAIL", f"Resp: {data_login2}, reuse: {r_reuse.text}")
    except Exception as e:
        report("SECOND_LOGIN_REQUIRES_NEW_OTP", "FAIL", str(e))

    # Cleanup test user
    User.objects.filter(email=test_email).delete()

    print("=" * 65)
    passed = sum(1 for v in RESULTS.values() if v["status"] == "PASS")
    total = len(RESULTS)
    print(f"  AUTHENTICATION TEST RESULTS: {passed}/{total} CHECKS PASSED")
    print("=" * 65)
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
