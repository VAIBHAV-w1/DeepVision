# DeepVision Email Subsystem Health & Diagnostics Report

**Date**: 2026-09-26  
**Component**: Authentication & Transactional Email Services (`apps.accounts.email_service`)  
**Status**: [VERIFIED & REPAIRED]

---

## 1. Configured Email Backend
- **Django Core Backend**: `django.core.mail.backends.smtp.EmailBackend`
- **Application Mailer**: In-process SMTP service (`_send_smtp_email` via Python `smtplib`)
- **Environment Loader**: `python-dotenv` explicitly loading root `.env` in `settings.py`, `start_deepvision.py`, and `email_service.py`

---

## 2. SMTP Host & Port
- **Host**: `smtp.gmail.com` (Resolved IP: `192.178.211.109`)
- **Port**: `587` (Standard ESMTP with STARTTLS)
- **Socket Connectivity**: Verified (TCP connect latency: < 50ms)

---

## 3. Encryption & Security Protocol
- **STARTTLS**: Enabled (`EMAIL_USE_TLS = True`)
- **TLS Negotiation**: Verified (Response code: `220 2.0.0 Ready to start TLS`)
- **SSL**: Disabled (`EMAIL_USE_SSL = False`, standard for port 587 submission)

---

## 4. Sender & Identity Configuration
- **Configured Sender**: `deepvision.mp@gmail.com`
- **Sender Validation**: Matches authenticated SMTP account identity

---

## 5. Credential Presence & Storage
- **Username**: `dee***@gmail.com` (Masked for safety; present in `.env`)
- **Password**: 16-character App Password (Masked for safety; present in `.env`)
- **Security Invariant**: Zero plaintext credentials logged in application logs or reports

---

## 6. Connection & Authentication Results
- **EHLO Handshake**: [PASS] (Response code: `250`)
- **STARTTLS Upgrade**: [PASS] (Response code: `220`)
- **SMTP Authentication**: [PASS] (Response code: `235 2.7.0 Accepted`)

---

## 7. Controlled Email Send Result
- **Test Message**: HTML multipart verification message dispatched to `deepvision.mp@gmail.com`
- **SMTP Transmission**: [PASS] (`client.sendmail()` accepted with 0 rejections)
- **SMTP Quit**: [PASS] (`221 2.0.0 closing connection`)

---

## 8. Delivery Result
- **SMTP Acceptance**: Confirmed (Gmail SMTP server accepted message for delivery with code `235`/`250`)
- **Mailbox Delivery Verification**: Note that final inbox arrival is subject to recipient mail server processing. SMTP acceptance was 100% verified.

---

## 9. Signup OTP Workflow
- **Input Validation**: [PASS] (Rejects invalid email format, empty fields, password mismatch, and passwords < 8 chars without upper/lower/digit/symbol)
- **OTP Generation**: [PASS] (6-digit numeric OTP generated via cryptographic `secrets.choice`)
- **OTP Hashing**: [PASS] (Stored in database as PBKDF2 SHA-256 hash)
- **Email Dispatch**: [PASS] (`send_verification_email` invoked with `full_name` support)
- **OTP Verification**: [PASS] (Valid OTP verifies, clears OTP hash, and activates account)
- **Attempt Limit & Expiry**: [PASS] (Maximum 5 attempts enforced; 15-minute TTL enforced)

---

## 10. Forgot Password & Password Reset Workflow
- **Account Lookup**: [PASS] (Looks up registered account without leaking presence to untrusted callers)
- **Reset OTP Generation**: [PASS] (6-digit reset OTP generated and hashed with PBKDF2)
- **Reset Email Dispatch**: [PASS] (`send_password_reset_email` invoked with `full_name` support)
- **Password Reset Execution**: [PASS] (Verifies reset OTP, enforces password strength, hashes new password with PBKDF2, and clears reset OTP)
- **Credential Swap**: [PASS] (New password accepted on subsequent login; old password rejected)

---

## 11. Root Cause Analysis & Fixes Applied

| Issue Identified | Root Cause | Fix Applied |
| :--- | :--- | :--- |
| **Missing Environment Variables in Runtime** | `.env` was never loaded in `settings.py` or launcher scripts; `python-dotenv` was never invoked. | Added `load_dotenv()` to `settings.py`, `start_deepvision.py`, `manage.py`, and `email_service.py`. |
| **Positional Argument TypeError** | `api_signup`, `api_resend_otp`, and `api_forgot_password` called `send_verification_email(email, otp, full_name)` with 3 arguments, but functions in `email_service.py` only accepted 2 arguments `(recipient_email, otp)`. | Updated `send_verification_email` and `send_password_reset_email` to accept `full_name=None` and personalized greetings. |
| **Missing Django Email Settings** | Standard Django settings (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, etc.) were missing from `settings.py`. | Added standard `EMAIL_*` configuration block to `settings.py`. |
| **Swallowed Exceptions in API** | Generic `except Exception` blocks caught `TypeError` as warning, returning a misleading success response to client. | Fixed signatures and elevated failure logging to `logger.error` for transparency. |

---

## 12. Remaining Failures
- **None**: All 9 automated auth/email tests passed with zero errors.
