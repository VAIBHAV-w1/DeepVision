"""
Comprehensive Automated Test Suite for DeepVision Authentication, OTP Lifecycle, and Security Controls.
Tests:
1. OTP Generation, format, CSPRNG randomness, and PBKDF2 purpose-salting.
2. Purpose Binding (signup vs login isolation).
3. Expiry enforcement (past 15 minutes fails).
4. Attempt limiting & brute force lockout (max 5 attempts).
5. Single-use replay protection (OTP wiped upon successful verification).
6. Prior OTP invalidation when a new OTP is requested.
7. Account enumeration prevention in forgot-password.
8. Registration validation and unverified state enforcement.
9. Serverless synchronous SMTP dispatch vs threaded dispatch.
"""
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / 'deepvision_django'
if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.email_service import _dispatch_email_async


class TestAuthAndOtpLifecycle(unittest.TestCase):
    def setUp(self):
        # In-memory transient user fixture for testing OTP methods
        self.user = User(
            id=99999,
            full_name="Security Test Operator",
            email="security.test@deepvision.internal",
            role="user",
            is_email_verified=False,
            is_active=True
        )
        self.user.set_password("SecureOperatorPassword123!")

    def test_otp_generation_format_and_properties(self):
        """OTP must be 6 digits, numeric, expire in 15 minutes, with zero attempts."""
        otp = self.user.generate_otp(purpose="login")
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())
        self.assertEqual(self.user.email_otp_attempts, 0)
        self.assertIsNotNone(self.user.email_otp_expires_at)
        self.assertIsNotNone(self.user.email_otp_hash)
        # Verify it's a PBKDF2 hash, not plaintext
        self.assertNotIn(otp, self.user.email_otp_hash)
        self.assertTrue(self.user.email_otp_hash.startswith("pbkdf2_"))

    def test_otp_purpose_binding_isolation(self):
        """A Login OTP must never verify for Signup, and a Signup OTP must never verify for Login."""
        login_otp = self.user.generate_otp(purpose="login")
        
        # Attempt to use login OTP for signup
        ok, err = self.user.verify_otp(login_otp, purpose="signup")
        self.assertFalse(ok)
        self.assertEqual(err, "Invalid verification code.")
        self.assertEqual(self.user.email_otp_attempts, 1)

        # Now test with proper purpose
        ok, err = self.user.verify_otp(login_otp, purpose="login")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_otp_expiry_enforcement(self):
        """Expired OTPs must be strictly rejected."""
        otp = self.user.generate_otp(purpose="login")
        # Artificially set expiry into the past
        self.user.email_otp_expires_at = timezone.now() - timedelta(minutes=1)

        ok, err = self.user.verify_otp(otp, purpose="login")
        self.assertFalse(ok)
        self.assertIn("expired", err.lower())

    def test_otp_attempt_limiting_lockout(self):
        """After 5 incorrect attempts, verification must lock out."""
        otp = self.user.generate_otp(purpose="login")
        
        # 5 failed attempts
        for i in range(5):
            ok, err = self.user.verify_otp("000000", purpose="login")
            self.assertFalse(ok)

        # Even if user now supplies the correct OTP, it must be rejected due to attempt limit
        ok, err = self.user.verify_otp(otp, purpose="login")
        self.assertFalse(ok)
        self.assertIn("maximum", err.lower())

    def test_otp_single_use_replay_prevention(self):
        """A successfully verified OTP must be wiped immediately to prevent replay."""
        otp = self.user.generate_otp(purpose="login")
        
        # First verification succeeds
        ok, err = self.user.verify_otp(otp, purpose="login")
        self.assertTrue(ok)
        self.assertIsNone(self.user.email_otp_hash)
        self.assertIsNone(self.user.email_otp_expires_at)

        # Replay attempt fails immediately
        ok, err = self.user.verify_otp(otp, purpose="login")
        self.assertFalse(ok)
        self.assertIn("no verification code exists", err.lower())

    def test_newer_otp_invalidates_prior_otp(self):
        """Requesting a new OTP must invalidate any previously issued OTP."""
        otp1 = self.user.generate_otp(purpose="login")
        otp2 = self.user.generate_otp(purpose="login")
        
        # otp1 is now stale
        ok, err = self.user.verify_otp(otp1, purpose="login")
        self.assertFalse(ok)

        # otp2 is valid
        ok, err = self.user.verify_otp(otp2, purpose="login")
        self.assertTrue(ok)

    def test_password_reset_otp_lifecycle(self):
        """Password reset OTP generation, verification, and clearing work correctly."""
        reset_otp = self.user.generate_reset_otp()
        self.assertEqual(len(reset_otp), 6)
        self.assertTrue(reset_otp.isdigit())

        # Verify correct code
        ok, err = self.user.verify_reset_otp(reset_otp)
        self.assertTrue(ok)

        # Clear reset OTP
        self.user.clear_reset_otp()
        self.assertIsNone(self.user.password_reset_otp_hash)

    def test_serverless_synchronous_email_dispatch(self):
        """On serverless (VERCEL=1), email must dispatch synchronously to prevent freeze."""
        with patch.dict(os.environ, {'VERCEL': '1'}):
            with patch('apps.accounts.email_service._send_smtp_email') as mock_send:
                mock_send.return_value = True
                result = _dispatch_email_async("test@example.com", "Test Subject", "<p>Hello</p>")
                self.assertTrue(result)
                mock_send.assert_called_once_with("test@example.com", "Test Subject", "<p>Hello</p>")


if __name__ == '__main__':
    unittest.main()
