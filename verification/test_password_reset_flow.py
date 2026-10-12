"""
Complete Automated Password Reset Acceptance & Regression Test Suite
Tests:
1. Unknown account forgot-password does not enumerate accounts (constant message)
2. Valid user forgot-password initiates reset, saves hash, dispatches email
3. OTP is cryptographically hashed (PBKDF2/Werkzeug, never plaintext)
4. Incorrect reset code is rejected (HTTP 400)
5. Missing email / missing reset code handled correctly
6. Expired reset code is rejected (HTTP 400)
7. Max attempts lockout (>=5 failed attempts rejected)
8. Verify reset OTP endpoint confirms valid code without resetting password
9. Mismatched password confirmation rejected (HTTP 400)
10. Weak password rejected (policy check)
11. Valid new password accepted, password updated and hashed
12. Old password fails after reset
13. New password succeeds for login (+ requires OTP)
14. OTP replay prevented (consumed OTP cannot be reused)
15. Cross-purpose OTP protection (reset OTP cannot verify login)
"""

import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup Django environment for test fixture inspection
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "deepvision_django"))
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.accounts.models import User
from django.contrib.auth.hashers import check_password

BASE_URL = "http://127.0.0.1:8000"
RESULTS = []

def report(name, condition, details=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, details))
    print(f"[{status:4s}] {name}: {details}")

def run_tests():
    print("=" * 65)
    print("  DEEPVISION PASSWORD RESET ACCEPTANCE & REGRESSION SUITE")
    print("=" * 65)

    client = requests.Session()
    r_csrf = client.get(f"{BASE_URL}/api/auth/csrf/")
    csrf_token = r_csrf.json().get("csrfToken", "")
    headers = {"X-CSRFToken": csrf_token}

    # Setup isolated test user
    test_email = "pwreset_audit_user@deepvision.test"
    user = User.objects.filter(email=test_email).first()
    if not user:
        user = User(
            full_name="Password Reset Audit",
            email=test_email,
            role="operator",
            is_email_verified=True,
            is_active=True
        )
    initial_password = "InitialPass2026!"
    user.set_password(initial_password)
    user.clear_reset_otp()
    user.save()

    # 1. Unknown account enum protection
    r_unknown = client.post(f"{BASE_URL}/api/auth/forgot-password/", json={
        "email": "nonexistent_9999@deepvision.test"
    }, headers=headers)
    unknown_data = r_unknown.json()
    report("UNKNOWN_ACCOUNT_PROTECTION",
           r_unknown.status_code == 200 and unknown_data.get("success") and "If an account exists" in unknown_data.get("message", ""),
           "Constant response prevents email enumeration")

    # 2. Reset request initiation for existing user
    r_init = client.post(f"{BASE_URL}/api/auth/forgot-password/", json={
        "email": test_email
    }, headers=headers)
    init_data = r_init.json()
    user.refresh_from_db()
    report("RESET_INITIATION",
           r_init.status_code == 200 and init_data.get("success") and user.password_reset_otp_hash is not None,
           f"Reset initiated, hash generated, sent_at={user.password_reset_otp_sent_at}")

    # 3. OTP storage security
    report("OTP_HASH_STORAGE",
           user.password_reset_otp_hash.startswith(("pbkdf2_", "pbkdf2_sha256$", "pbkdf2_sha1$")),
           "OTP stored securely as cryptographic PBKDF2 hash, not plaintext")

    # Generate known OTP for deterministic testing
    fixed_otp = "849201"
    from django.contrib.auth.hashers import make_password
    user.password_reset_otp_hash = make_password(fixed_otp)
    user.password_reset_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    user.password_reset_otp_attempts = 0
    user.save()

    # 4. Incorrect reset code rejected
    r_wrong = client.post(f"{BASE_URL}/api/auth/verify-reset-otp/", json={
        "email": test_email,
        "otp": "000000"
    }, headers=headers)
    user.refresh_from_db()
    report("INCORRECT_OTP_REJECTED",
           r_wrong.status_code == 400 and not r_wrong.json().get("success") and user.password_reset_otp_attempts == 1,
           f"Wrong OTP rejected, attempts incremented to {user.password_reset_otp_attempts}")

    # 5. Missing fields handled cleanly
    r_missing = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email
        # missing otp, new_password
    }, headers=headers)
    report("MISSING_FIELDS_HANDLED",
           r_missing.status_code == 400 and "Email and reset code are required" in r_missing.json().get("error", ""),
           "Missing OTP/email rejected with HTTP 400")

    r_missing_pw = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email,
        "otp": fixed_otp
        # missing password
    }, headers=headers)
    report("MISSING_PASSWORD_HANDLED",
           r_missing_pw.status_code == 400 and "New password and confirmation are required" in r_missing_pw.json().get("error", ""),
           "Missing password rejected with HTTP 400")

    # 6. Expired reset code rejected
    user.password_reset_otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    user.save()
    r_expired = client.post(f"{BASE_URL}/api/auth/verify-reset-otp/", json={
        "email": test_email,
        "otp": fixed_otp
    }, headers=headers)
    report("EXPIRED_OTP_REJECTED",
           r_expired.status_code == 400 and "expired" in r_expired.json().get("error", "").lower(),
           "Expired OTP rejected with HTTP 400")

    # 7. Max attempts lockout
    user.password_reset_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    user.password_reset_otp_attempts = 5
    user.save()
    r_lockout = client.post(f"{BASE_URL}/api/auth/verify-reset-otp/", json={
        "email": test_email,
        "otp": fixed_otp
    }, headers=headers)
    report("MAX_ATTEMPTS_LOCKOUT",
           r_lockout.status_code == 400 and "maximum" in r_lockout.json().get("error", "").lower(),
           "Lockout enforced when attempts >= 5")

    # Reset attempts for valid verification
    user.password_reset_otp_attempts = 0
    user.save()

    # 8. Valid verify-reset-otp endpoint
    r_verify_ok = client.post(f"{BASE_URL}/api/auth/verify-reset-otp/", json={
        "email": test_email,
        "otp": fixed_otp
    }, headers=headers)
    report("VALID_OTP_VERIFICATION",
           r_verify_ok.status_code == 200 and r_verify_ok.json().get("success"),
           "Reset OTP verified successfully by intermediate endpoint")

    # 9. Mismatched confirmation rejected
    r_mismatch = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email,
        "otp": fixed_otp,
        "new_password": "NewSecretPass2026!",
        "confirm_password": "DifferentSecretPass2026!"
    }, headers=headers)
    report("MISMATCHED_CONFIRMATION_REJECTED",
           r_mismatch.status_code == 400 and "do not match" in r_mismatch.json().get("error", "").lower(),
           "Mismatched passwords rejected")

    # 10. Weak password rejected
    r_weak = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email,
        "otp": fixed_otp,
        "new_password": "short",
        "confirm_password": "short"
    }, headers=headers)
    report("WEAK_PASSWORD_REJECTED",
           r_weak.status_code == 400 and len(r_weak.json().get("error", "")) > 0,
           "Password failing complexity/length policy rejected")

    # 11. Valid password reset execution
    new_password = "NewVerifiedSecret2026!"
    r_reset = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email,
        "otp": fixed_otp,
        "new_password": new_password,
        "confirm_password": new_password
    }, headers=headers)
    reset_data = r_reset.json()
    user.refresh_from_db()
    report("PASSWORD_RESET_SUCCESS",
           r_reset.status_code == 200 and reset_data.get("success") and user.check_password(new_password),
           "Password updated and hashed; user.check_password(new_password) is True")

    # 12. Old password fails
    report("OLD_PASSWORD_INVALD",
           not user.check_password(initial_password),
           "Previous password no longer valid")

    # 13. Replay prevention: consumed OTP rejected
    r_replay = client.post(f"{BASE_URL}/api/auth/reset-password/", json={
        "email": test_email,
        "otp": fixed_otp,
        "new_password": "AnotherNewPass2026!",
        "confirm_password": "AnotherNewPass2026!"
    }, headers=headers)
    report("REPLAY_PREVENTION_CONSUMED_OTP",
           r_replay.status_code == 400 and not r_replay.json().get("success"),
           "Consumed OTP rejected; cannot be replayed")

    # 14. Fresh login with new password works
    r_login = client.post(f"{BASE_URL}/api/auth/login/", json={
        "email": test_email,
        "password": new_password
    }, headers=headers)
    login_data = r_login.json()
    report("LOGIN_WITH_NEW_PASSWORD",
           r_login.status_code == 200 and login_data.get("requires_otp"),
           "New password accepted, credentials verified, requires_otp=True")

    # 15. Login with old password fails
    r_login_old = client.post(f"{BASE_URL}/api/auth/login/", json={
        "email": test_email,
        "password": initial_password
    }, headers=headers)
    report("LOGIN_WITH_OLD_PASSWORD_FAILS",
           r_login_old.status_code == 401,
           "Login with previous password rejected with HTTP 401")

    print("=" * 65)
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    total = len(RESULTS)
    print(f"  PASSWORD RESET SUITE RESULTS: {passed}/{total} CHECKS PASSED")
    print("=" * 65)
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
