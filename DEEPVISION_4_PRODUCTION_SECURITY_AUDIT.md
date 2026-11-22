# DeepVision 4.0 — Production Security Audit Report

**Audit Date:** 2026-11-21  
**Target Workspace:** `D:\DeepVision`  
**Audit Scope:** Full Django 5.2.17 + React 19 / Vite 8.3.8 application, REST/JSON APIs, session & OTP auth, RBAC & multi-tenant isolation, SSRF & MJPEG redirect/TLS protections, reverse-proxy rate limiting & audit logging, PyPI/npm CVE audits, persistent storage backends, and AI/camera subsystems.  
**Release Classification:** **`RELEASE CANDIDATE — EXTERNAL GATES REMAIN`** *(all locally verifiable engineering & security controls PASS; live deployment, remote cloud storage, external email inbox, Linux CI, LAN RTSP, and 30-min soak remain external promotion gates)*

---

## 1. Executive Summary & Applied Security Remediations

1. **Viewer Role Write & Email-Trigger Enforcement (`HIGH` — Resolved):** Enforced read-only `viewer` RBAC (`403`) across `get_user_camera_or_404(..., require_write=True)`, camera mutations, zone CRUD/toggle, test-connection, browser frame ingest, alert ack/resolve, case creation/notes, notification preferences, and test email APIs.
2. **Test-Email Recipient Abuse & Missing Rate Limit (`HIGH` — Resolved):** Added `@ratelimit(scope="test_email", limit=5, window=300)` to `api_notification_test_email_view` and restricted external `recipient`/`email` overrides strictly to privileged staff (`admin`, `supervisor`, `operator`, `superuser`).
3. **Cloudflare / Reverse-Proxy IP Spoofing & Audit Log IP Parity (`HIGH` — Resolved):** Removed unconditional trust of spoofable `HTTP_TRUE_CLIENT_IP` / `HTTP_X_REAL_IP` in [rate_limiter.py](file:///d:/DeepVision/deepvision_django/apps/core/rate_limiter.py), restricted `HTTP_CF_CONNECTING_IP` trust strictly to `RENDER=true`, traversed `X-Forwarded-For` right-to-left skipping internal proxy hops, and updated [audit.py](file:///d:/DeepVision/deepvision_django/apps/core/audit.py) `get_client_ip()` to delegate to `rate_limiter.get_client_ip()` (eliminating spoofable left-most `X-Forwarded-For` in `AuditLog`).
4. **Online Python & Frontend Dependency CVEs (`CRITICAL` / `HIGH` — Resolved):** Fixed 7 PyPI CVEs in local `venv` and synchronized CVE minimum floors across [requirements.txt](file:///d:/DeepVision/requirements.txt) and [requirements-surveillance.txt](file:///d:/DeepVision/requirements-surveillance.txt) (`werkzeug>=3.1.9`, `certifi>=2026.10.18`, `urllib3>=2.8.0`, `pillow>=13.0.0`, `filelock>=4.2.1`). Online OSV check: `63` Python packages -> `0` CVEs; `npm audit`: `0` vulnerabilities.
5. **MJPEG HTTP Redirect SSRF & Unconditional `CERT_NONE` (`MEDIUM` — Resolved):** Added `_SafeMjpegRedirectHandler` and `_ScopedMjpegHTTPSHandler` in [capture.py](file:///d:/DeepVision/deepvision_django/apps/surveillance/camera/capture.py). Initial URLs and every redirect hop (`max 3`) are validated against `validate_network_stream_url()`, non-`http`/`https` redirect schemes are rejected, cross-origin `Authorization` headers are stripped, and self-signed TLS relaxation defaults to `False` (`DEEPVISION_ALLOW_SELF_SIGNED_LAN_CAMERA`) and applies per-hop strictly to private RFC1918 LAN targets.
6. **Production Host/CSRF Wildcards & Secret Key Floor (`MEDIUM` — Resolved):** Removed platform wildcard suffixes (`.vercel.app`, `.onrender.com`, `https://*.vercel.app`, `https://*.onrender.com`) from [settings.py](file:///d:/DeepVision/deepvision_django/config/settings.py), enforced exact configured `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` overrides when `DEBUG=False`, and raised production `DJANGO_SECRET_KEY` minimum length from `32` to `50` characters (`security.W009` compliant).
7. **Session Revocation, Dead Legacy Auth Views, Header Injection & Assistant Guard (`MEDIUM`/`LOW` — Resolved):**
   - Bound 16-char `pw_fp` SHA-256 hash into OTP sessions and flushed mismatched sessions in [middleware.py](file:///d:/DeepVision/deepvision_django/apps/accounts/middleware.py).
   - Removed unrouted password-only legacy views (`login_view`, `signup_view`, `forgot_password_view`, `reset_password_view`) from [accounts/views.py](file:///d:/DeepVision/deepvision_django/apps/accounts/views.py) and dead `loginAsDemo` from [useAuth.jsx](file:///d:/DeepVision/frontend/src/hooks/useAuth.jsx).
   - Sanitized `Content-Disposition` filenames via `_safe_attachment_filename()` across [storage_service.py](file:///d:/DeepVision/deepvision_django/apps/core/storage_service.py) (matching [media_service.py](file:///d:/DeepVision/deepvision_django/apps/core/media_service.py)).
   - Added `@ratelimit(scope="assistant", limit=30, window=60)` and 1000-char payload limit to `assistant_chat_view` in [core/views.py](file:///d:/DeepVision/deepvision_django/apps/core/views.py).

---

## 2. OWASP Verification Summary

| Domain | Status | Evidence & Notes |
|---|---|---|
| **A01 Broken Access Control** | **PASS** | `24` viewer mutation vectors -> `403`, cross-tenant BOLA -> `404`/`403`, `/api/audit-logs/` staff-only |
| **A02 Cryptographic Failures & TLS** | **PASS** (Local) / **BLOCKED** (Live Render Parity) | Local `DEBUG=False` & `_ScopedMjpegHTTPSHandler` enforce strict TLS + HSTS + `Secure` cookies; live Render still requires redeploy |
| **A03 Injection & Traversal** | **PASS** | Parameterized ORM, `validate_object_key()`, `os.path.commonpath()`, `_safe_attachment_filename()`, `url_has_allowed_host_and_scheme()` |
| **A04 Insecure Design** | **PASS** | `/api/auth/demo-session/` returns `410`, dead `loginAsDemo` / `login_view` removed, assistant & test-email rate-limited |
| **A05 Security Misconfiguration** | **PASS** | `manage.py check --deploy` (`0 issues`), `50`-char `SECRET_KEY`, exact host/origin overrides, `X-Frame-Options: DENY`, `nosniff`, CSP |
| **A06 Vulnerable Components** | **PASS** | `npm audit`: `0` CVEs; OSV PyPI audit: `63` pkgs -> `0` CVEs; `requirements-surveillance.txt` & `requirements.txt` synchronized |
| **A07 Auth & Session Lifecycle** | **PASS** (Local) / **BLOCKED** (Live Inbox) | Two-step OTP, cross-purpose isolation, `pw_fp` revocation (`15/15` auth matrix + `6/6` release cert); live inbox untested |
| **A08 Integrity** | **PASS** | YOLO26s ONNX SHA-256 verified (`d26b65c43211...`), `PersistentDirectoryStorageBackend` SHA-256 + S3/Supabase size verify |
| **A09 Logging & Rate Limiting** | **PASS** (`ACCEPTED RISK` on Vercel Rewrites) | `audit.py` & `rate_limiter.py` reject spoofed headers; direct Render recommended if independent client IPs are needed instead of Vercel proxy POP IPs |
| **A10 SSRF** | **PASS** | Initial & 30x redirect destinations validated via `validate_network_stream_url()`; loopback, link-local/metadata, `*.internal`, DNS rebinding & unsafe schemes blocked |
