import secrets
from datetime import datetime, timezone as dt_timezone, timedelta
from django.db import models
from django.utils import timezone
try:
    from werkzeug.security import check_password_hash
except ImportError:
    check_password_hash = None


class User(models.Model):
    """
    Django ORM mapping for the existing 'users' SQLite table.
    Preserves exact existing table structure without migrations (managed = False).
    Provides Werkzeug password compatibility and OTP lifecycle methods.
    """
    id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=100)
    email = models.CharField(max_length=120, unique=True)
    password_hash = models.CharField(max_length=255)
    role = models.CharField(max_length=20, default='user')
    is_email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    # Email Verification OTP fields
    email_otp_hash = models.CharField(max_length=255, blank=True, null=True)
    email_otp_expires_at = models.DateTimeField(blank=True, null=True)
    email_otp_attempts = models.IntegerField(default=0)
    email_otp_sent_at = models.DateTimeField(blank=True, null=True)

    # Password Reset OTP fields
    password_reset_otp_hash = models.CharField(max_length=255, blank=True, null=True)
    password_reset_otp_expires_at = models.DateTimeField(blank=True, null=True)
    password_reset_otp_attempts = models.IntegerField(default=0)
    password_reset_otp_sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'users'

    # Django user compatibility properties
    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_staff(self):
        return self.role in ('admin', 'supervisor')

    @property
    def is_superuser(self):
        return self.role == 'admin'

    def get_username(self):
        return self.email

    def set_password(self, raw_password):
        """
        Hashes password with PBKDF2 (Django standard PBKDF2PasswordHasher).
        """
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        """
        Verifies plaintext password against password hash.
        Supports Django PBKDF2 hashes and legacy Werkzeug scrypt hashes.
        If verified using legacy scrypt, automatically upgrades hash to PBKDF2.
        """
        if not self.password_hash:
            return False

        from django.contrib.auth.hashers import check_password as django_check_password
        if self.password_hash.startswith(('pbkdf2_', 'pbkdf2_sha256$', 'pbkdf2_sha1$', 'argon2', 'bcrypt')):
            return django_check_password(raw_password, self.password_hash)

        # Legacy Werkzeug compatibility (scrypt)
        try:
            from werkzeug.security import check_password_hash as werkzeug_check_password
            if werkzeug_check_password(self.password_hash, raw_password):
                # Seamless transparent upgrade to Django PBKDF2
                try:
                    self.set_password(raw_password)
                    self.save(update_fields=['password_hash'])
                except Exception:
                    pass
                return True
        except ImportError:
            pass
        return False

    # Email OTP lifecycle (Supports distinct purpose: "signup" vs "login")
    def generate_otp(self, purpose: str = "signup"):
        """
        Generates 6-digit numeric OTP, sets 15-minute expiry, resets attempts.
        Hashes token with purpose salt (e.g. 'SIGNUP:<otp>' or 'LOGIN:<otp>') using Django PBKDF2.
        Returns the plaintext OTP.
        """
        from django.contrib.auth.hashers import make_password
        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        purpose_tag = purpose.strip().upper()
        self.email_otp_hash = make_password(f"{purpose_tag}:{otp}")
        now = timezone.now()
        self.email_otp_expires_at = now + timedelta(minutes=15)
        self.email_otp_sent_at = now
        self.email_otp_attempts = 0
        return otp

    def verify_otp(self, otp: str, purpose: str = "signup"):
        """
        Validates OTP against stored hash, purpose salt, expiry, and attempt limit (max 5).
        Returns (True, None) on success or (False, error_message) on failure.
        """
        if self.email_otp_attempts >= 5:
            return False, "Maximum incorrect verification attempts reached. Please request a new code."

        if not self.email_otp_hash:
            return False, "No verification code exists. Please request a new code."

        now = timezone.now()
        expires_at = self.email_otp_expires_at
        if expires_at and timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

        if not expires_at or now > expires_at:
            return False, "Verification code has expired. Please request a new code."

        from django.contrib.auth.hashers import check_password as django_check_password
        purpose_tag = purpose.strip().upper()
        salted_token = f"{purpose_tag}:{otp}"

        valid = False
        if self.email_otp_hash.startswith(('pbkdf2_', 'pbkdf2_sha256$', 'pbkdf2_sha1$')):
            # First check purpose-salted token
            valid = django_check_password(salted_token, self.email_otp_hash)
            # If not valid and purpose is signup, check legacy unsalted token for backward compatibility
            if not valid and purpose_tag == "SIGNUP":
                valid = django_check_password(otp, self.email_otp_hash)
        else:
            try:
                from werkzeug.security import check_password_hash as werkzeug_check_password
                valid = werkzeug_check_password(self.email_otp_hash, salted_token)
                if not valid and purpose_tag == "SIGNUP":
                    valid = werkzeug_check_password(self.email_otp_hash, otp)
            except ImportError:
                pass

        if not valid:
            self.email_otp_attempts += 1
            return False, "Invalid verification code."

        if purpose_tag == "SIGNUP":
            self.is_email_verified = True

        self.email_otp_hash = None
        self.email_otp_expires_at = None
        self.email_otp_attempts = 0
        return True, None

    # Password Reset OTP lifecycle
    def generate_reset_otp(self):
        """
        Generates 6-digit numeric OTP for password reset, sets 15-minute expiry.
        Hashes with Django PBKDF2. Returns the plaintext OTP.
        """
        from django.contrib.auth.hashers import make_password
        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        self.password_reset_otp_hash = make_password(otp)
        now = timezone.now()
        self.password_reset_otp_expires_at = now + timedelta(minutes=15)
        self.password_reset_otp_sent_at = now
        self.password_reset_otp_attempts = 0
        return otp

    def verify_reset_otp(self, otp):
        """
        Validates password reset OTP.
        Returns (True, None) on success or (False, error_message) on failure.
        """
        if self.password_reset_otp_attempts >= 5:
            return False, "Maximum incorrect reset attempts reached. Please request a new code."

        if not self.password_reset_otp_hash:
            return False, "No reset verification code exists. Please request a new code."

        now = timezone.now()
        expires_at = self.password_reset_otp_expires_at
        if expires_at and timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, dt_timezone.utc)

        if not expires_at or now > expires_at:
            return False, "Reset verification code has expired. Please request a new code."

        from django.contrib.auth.hashers import check_password as django_check_password
        valid = False
        if self.password_reset_otp_hash.startswith(('pbkdf2_', 'pbkdf2_sha256$', 'pbkdf2_sha1$')):
            valid = django_check_password(otp, self.password_reset_otp_hash)
        else:
            try:
                from werkzeug.security import check_password_hash as werkzeug_check_password
                valid = werkzeug_check_password(self.password_reset_otp_hash, otp)
            except ImportError:
                pass

        if not valid:
            self.password_reset_otp_attempts += 1
            return False, "Invalid verification code."

        return True, None

    def clear_reset_otp(self):
        """
        Clears password reset OTP columns after successful reset.
        """
        self.password_reset_otp_hash = None
        self.password_reset_otp_expires_at = None
        self.password_reset_otp_attempts = 0
        self.password_reset_otp_sent_at = None

    def __str__(self):
        return f"{self.email} ({self.full_name})"
