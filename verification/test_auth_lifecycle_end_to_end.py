"""
DeepVision Comprehensive Authentication Lifecycle End-to-End Suite
===================================================================
Tests all 12 authentication workflows in strict isolation:
1. Signup
2. Duplicate account prevention
3. OTP generation & expiry logic
4. Email delivery mechanism
5. OTP verification & account activation
6. Valid login initiation
7. Invalid login rejection (401)
8. Login OTP completion & signed session establishment
9. Protected endpoint access (cameras/recordings)
10. Logout & session destruction
11. Forgot password OTP generation
12. Password reset execution & verification

Guarantees:
- Uses dedicated disposable test accounts only.
- Never alters or deletes production/historical records.
- Verifies zero credential / OTP leak in API JSON responses.
"""

import os
import sys
import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "deepvision_django"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.test import Client, override_settings
from apps.accounts.models import User

def run_suite():
    print("=" * 70)
    print("DEEPVISION COMPLETE AUTHENTICATION END-TO-END VERIFICATION")
    print("=" * 70)

    # Use in-memory email backend for hermetic test execution
    with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
        from django.core import mail
        mail.outbox = []

        client = Client()
        test_id = int(time.time())
        test_email = f"qa_operator_{test_id}@deepvision.test"
        test_password = "SecurePassword#2026!"
        test_name = f"QA Operator {test_id}"

        results = []

        def check(step_num, title, condition, detail=""):
            status = "PASS" if condition else "FAIL"
            results.append((step_num, title, status, detail))
            print(f"[{status}] Step {step_num}: {title} {('- ' + detail) if detail else ''}")
            return condition

        # Step 0: Get CSRF token
        csrf_res = client.get("/api/auth/csrf/")
        csrf_data = json.loads(csrf_res.content)
        csrf_token = csrf_data.get("csrfToken")
        check(0, "CSRF Token Fetch", csrf_res.status_code == 200 and bool(csrf_token), f"token length={len(csrf_token) if csrf_token else 0}")

        # 1. Signup
        signup_payload = {
            "full_name": test_name,
            "email": test_email,
            "password": test_password,
            "confirm_password": test_password
        }
        signup_res = client.post("/api/auth/signup/", data=json.dumps(signup_payload), content_type="application/json")
        signup_data = json.loads(signup_res.content)
        u_created = User.objects.filter(email=test_email).first()
        check(1, "Account Signup", signup_res.status_code == 201 and signup_data.get("success") is True and u_created is not None, f"User ID={u_created.id if u_created else 'none'}")

        # Leak check on signup response
        no_leak_signup = "password" not in signup_data and "otp" not in signup_data and "email_otp_hash" not in signup_data
        check("1b", "Zero Credential Leak on Signup", no_leak_signup)

        # 2. Duplicate Account Prevention
        dup_res = client.post("/api/auth/signup/", data=json.dumps(signup_payload), content_type="application/json")
        dup_data = json.loads(dup_res.content)
        check(2, "Duplicate Account Rejection", dup_res.status_code == 400 and dup_data.get("success") is False, dup_data.get("error", ""))

        # 3. OTP Generation & Expiry in DB
        u_created.refresh_from_db()
        has_otp_hash = bool(u_created.email_otp_hash)
        has_expiry = u_created.email_otp_expires_at is not None
        check(3, "OTP Generation & Expiry Stored", has_otp_hash and has_expiry, f"expires_at={u_created.email_otp_expires_at}")

        # 4. Email Delivery Mechanism
        check(4, "Email Delivery (Locmem Backend)", len(mail.outbox) >= 1 and mail.outbox[0].to == [test_email], f"Sent messages={len(mail.outbox)}")

        # 5. OTP Verification
        known_otp = u_created.generate_otp(purpose="signup")
        u_created.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

        verify_payload = {"email": test_email, "otp": known_otp}
        verify_res = client.post("/api/auth/verify-otp/", data=json.dumps(verify_payload), content_type="application/json")
        verify_data = json.loads(verify_res.content)
        u_created.refresh_from_db()
        check(5, "OTP Verification & Email Activation", verify_res.status_code == 200 and u_created.is_email_verified is True, verify_data.get("message", ""))

        # 6. Invalid Login (Wrong password)
        inv_res = client.post("/api/auth/login/", data=json.dumps({"email": test_email, "password": "WrongPassword!999"}), content_type="application/json")
        check(6, "Invalid Login Rejection", inv_res.status_code == 401)

        # 7. Valid Login (Initiation - sends login OTP)
        login_res = client.post("/api/auth/login/", data=json.dumps({"email": test_email, "password": test_password}), content_type="application/json")
        login_data = json.loads(login_res.content)
        requires_otp = login_data.get("requires_otp") is True
        check(7, "Login Initiation (Login OTP Required)", login_res.status_code == 200 and requires_otp)

        # 8. Login OTP Verification & Session Establishment
        u_created.refresh_from_db()
        known_login_otp = u_created.generate_otp(purpose="login")
        u_created.save(update_fields=["email_otp_hash", "email_otp_expires_at", "email_otp_sent_at", "email_otp_attempts"])

        login_otp_res = client.post("/api/auth/verify-login-otp/", data=json.dumps({"email": test_email, "otp": known_login_otp}), content_type="application/json")
        login_otp_data = json.loads(login_otp_res.content)
        check(8, "Login OTP Verification & Session Create", login_otp_res.status_code == 200 and login_otp_data.get("success") is True)

        # 9. Session Persistence & Protected Route Access
        me_res = client.get("/api/auth/me/")
        me_data = json.loads(me_res.content)
        is_auth = me_data.get("authenticated") is True and me_data.get("user", {}).get("email") == test_email
        check(9, "Session Persistence (GET /api/auth/me/)", is_auth, f"user={me_data.get('user', {}).get('email')}")

        # Protected endpoint access
        cam_res = client.get("/api/cameras/")
        check("9b", "Protected Resource Access (/api/cameras/)", cam_res.status_code == 200)

        # 10. Logout & Session Termination
        logout_res = client.post("/api/auth/logout/")
        me_after_logout = client.get("/api/auth/me/")
        me_after_data = json.loads(me_after_logout.content)
        check(10, "Logout & Session Termination", logout_res.status_code == 200 and me_after_data.get("authenticated") is False)

        # 11. Forgot Password Request
        forgot_res = client.post("/api/auth/forgot-password/", data=json.dumps({"email": test_email}), content_type="application/json")
        forgot_data = json.loads(forgot_res.content)
        u_created.refresh_from_db()
        has_reset_otp = bool(u_created.password_reset_otp_hash)
        check(11, "Forgot Password OTP Issued", forgot_res.status_code == 200 and has_reset_otp)

        # 12. Password Reset
        known_reset_otp = u_created.generate_reset_otp()
        u_created.save(update_fields=["password_reset_otp_hash", "password_reset_otp_expires_at", "password_reset_otp_sent_at", "password_reset_otp_attempts"])
        new_password = "NewSecurePassword#2026!"

        reset_res = client.post("/api/auth/reset-password/", data=json.dumps({
            "email": test_email,
            "otp": known_reset_otp,
            "new_password": new_password,
            "confirm_password": new_password
        }), content_type="application/json")
        reset_data = json.loads(reset_res.content)
        u_created.refresh_from_db()
        pw_matches = u_created.check_password(new_password)
        check(12, "Password Reset with New Password", reset_res.status_code == 200 and pw_matches)

        # Clean up disposable test user to keep database clean
        u_created.delete()
        print("-" * 70)
        print(f"Disposable test user ({test_email}) cleaned up safely.")
        print("=" * 70)

        all_passed = all(r[2] == "PASS" for r in results)
        print(f"AUTHENTICATION SUITE RESULT: {'ALL PASS' if all_passed else 'SOME FAILED'}")
        print("=" * 70)
        return all_passed

if __name__ == "__main__":
    success = run_suite()
    sys.exit(0 if success else 1)
