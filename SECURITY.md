# DeepVision Security Architecture & Hardening Guide

## 1. Executive Summary & Threat Model

DeepVision is an enterprise-grade video surveillance, AI object tracking, and incident investigation management platform. Given its operational domain, the security architecture addresses both standard web application vulnerabilities (OWASP Top 10:2025) and specialized physical security/surveillance attack surfaces:
- Unauthorized camera stream interception and source hijacking
- Arbitrary file retrieval and path traversal across recording/evidence archives
- Broken Object-Level Authorization (BOLA/IDOR) on forensic cases and audit logs
- Camera endpoint Server-Side Request Forgery (SSRF)
- Denial-of-Service (DoS) through unbounded inference or video streaming loops
- Credential stuffing and OTP enumeration against security operator accounts

---

## 2. OWASP Top 10:2025 Risk Mitigation Matrix

### A01:2025 – Broken Access Control
- **Object-Level Authorization**: Sensitive resources (`/api/cases/`, `/api/recordings/`, `/api/evidence/`, `/api/cameras/`) enforce strict user authentication and ownership checks.
- **Media File Access**: Direct access to media files on the filesystem is blocked. All media streaming (`/recordings/stream/<id>/`) and snapshot downloads (`/api/evidence/<id>/download/`) are routed through `apps.core.media_service.py` using `safe_resolve_path`.
- **Path Traversal Defenses**: Paths are canonicalized via `os.path.abspath` and verified using `os.path.commonpath([resolved_path, allowed_dir]) == allowed_dir`. Attempts to escape the directory root raise `SuspiciousOperation` and return HTTP 403/404.
- **Administrative Endpoints**: Django admin routes require active, authenticated staff credentials.

### A02:2025 – Cryptographic Failures
- **Password Hashing**: User credentials utilize Django's default PBKDF2 with SHA-256 password hashing with a high iteration count. Plaintext passwords are never logged, cached, or persisted.
- **Session Protection**: All session tokens are cryptographically signed cookies (`django.contrib.sessions.backends.signed_cookies`) using the application `SECRET_KEY`. No sensitive operator session data is stored unencrypted in client-accessible storage.
- **No Hardcoded Secrets**: Production deployments require externalized `DJANGO_SECRET_KEY` injected via environment variables (`.env`). Default fallback secret keys trigger deployment warnings.

### A03:2025 – Injection
- **SQL Injection**: All database operations use Django's built-in ORM with parameterized query construction. No raw SQL concatenation (`cursor.execute("SELECT ... " + user_input)`) is utilized in user-facing endpoints.
- **Cross-Site Scripting (XSS)**:
  - React 18/Vite 6 frontend automatically HTML-encodes dynamic JSX values. No usage of `dangerouslySetInnerHTML` with untrusted inputs.
  - Django templates employ automated contextual auto-escaping.
  - HTTP headers enforce `SECURE_BROWSER_XSS_FILTER = True` and `SECURE_CONTENT_TYPE_NOSNIFF = True`.
- **Command Injection**: Native camera capture utilizes DirectShow device indices (`dshow://0`) or validated RTSP URLs via OpenCV `cv2.VideoCapture` APIs; no shell invocation (`subprocess.Popen(shell=True)`) is performed on user-supplied strings.

### A04:2025 – Insecure Design
- **Single Model Ingestion**: YOLO11n inference engine is implemented as a process-level thread-safe singleton (`MODEL_LOAD_COUNT=1`). Request handlers cannot spawn duplicate models, preventing GPU/CPU memory exhaustion.
- **Zero Demo Credentials**: All hardcoded quick-fill credentials, bypass links, and simulated demo authenticators have been completely removed from frontend forms (`Login.jsx`, `Register.jsx`).
- **Fail-Safe Video Pipeline**: Camera worker threads terminate gracefully upon client disconnects or buffer timeouts, preventing worker thread accumulation.

### A05:2025 – Security Misconfiguration
- **HTTP Security Headers**:
  - `X-Frame-Options: DENY` (Mitigates clickjacking)
  - `X-Content-Type-Options: nosniff` (Prevents MIME confusion)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Cross-Origin-Opener-Policy: same-origin`
- **CSRF Protection**:
  - `CsrfViewMiddleware` is enabled across all state-changing endpoints.
  - Cookie configured with `SameSite='Lax'`, `HttpOnly=False` (to permit CSRF token retrieval in standard API fetch headers), and verified CSRF token validation on all POST/PUT/DELETE requests.
- **DEBUG Flag Protection**: `DJANGO_DEBUG` defaults to `False` in production containers.

### A06:2025 – Vulnerable and Outdated Components
- **Dependency Audit**:
  - Python: `pip check` confirmed zero broken requirements across Django 5.2.17, PyTorch, Ultralytics, and OpenCV.
  - Node.js: `npm audit fix` executed to resolve vulnerabilities (including `source-map-js` GHSA-68fv-2mgg-jv7q), resulting in 0 active vulnerabilities.
- **Base Images**: Docker runtime utilizes minimal `python:3.11-slim` with apt package cache purging (`rm -rf /var/lib/apt/lists/*`).

### A07:2025 – Identification and Authentication Failures
- **Two-Factor Authentication (2FA)**: Account verification and login support 6-digit email OTP challenges with time-limited validity (10 minutes) and automated expiration.
- **Rate Limiting**: Authentication endpoints enforce throttling against brute-force login and OTP enumeration.
- **Session Hijacking Defenses**: Session cookies configure `HttpOnly = True`, `SameSite = 'Lax'`, and support `Secure = True` when served over TLS (`DJANGO_SECURE_COOKIES=True`).

### A08:2025 – Software and Data Integrity Failures
- **Model Loading**: Inference weights (`yolo11n.pt`) are loaded from a trusted local repository path (`models/yolo11n.pt`). Remote untrusted pickle loading is disabled.
- **Evidence Immutability Verification**: Evidence artifacts are referenced by SHA-256 file hashes stored in database records to detect tampering or corruption.

### A09:2025 – Security Logging and Monitoring Failures
- **Audit Trails**: Security events (failed logins, OTP attempts, camera status changes, incident escalations) are logged with ISO-8601 timestamps and client IP addresses through Python standard logging (`apps.security`, `django.request`).
- **Masked Data**: Authentication tokens and password strings are excluded from diagnostic console and file logs.

### A10:2025 – Server-Side Request Forgery (SSRF)
- **Camera Stream Validation**: Camera source URLs are validated against allowed URI schemes (`rtsp://`, `http://`, `https://`, `dshow://`) and restricted to authorized local network camera segments.
- **Private Subnet Restrictions**: Loopback and link-local IP addresses (`127.0.0.1`, `169.254.0.0/16`) are blocked for external camera creation unless explicitly allowed in local development mode.

---

## 3. Surveillance-Specific Risk Mitigation

| Surveillance Vector | Threat | Applied Mitigation |
| :--- | :--- | :--- |
| **Stream Interception** | Unauthenticated sniffing of live video | MJPEG multipart stream endpoints (`/cameras/<id>/stream/`) require authenticated session cookies. |
| **Storage Traversal** | Accessing raw recordings via manipulated path | All downloads use `safe_resolve_path` restricting paths to `instance/recordings` and `instance/evidence`. |
| **Model DOS** | Submitting repeated burst requests to starve AI pipeline | Global inference rate limiter limits processing to 150ms intervals; frames are dropped if queue is full. |
| **Camera Tampering** | Changing physical camera parameters without authorization | Camera CRUD and mode switching (`ORIGINAL` vs `TRACKING`) restricted to authenticated operators. |

---

## 4. Production Deployment Hardening Checklist

When transitioning from local development to production launch:

1. **Enable TLS/HTTPS**:
   - Set `DJANGO_SECURE_COOKIES=True`
   - Set `SECURE_SSL_REDIRECT=True`
   - Enable `SECURE_HSTS_SECONDS = 31536000` (1 year)
   - Enable `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`
   - Enable `SECURE_HSTS_PRELOAD = True`
2. **Reverse Proxy Configuration (Nginx / Caddy)**:
   - Terminate SSL at reverse proxy
   - Forward `X-Forwarded-Proto: https` and `X-Forwarded-For`
   - Set proxy buffer sizes appropriate for multipart video streaming (`proxy_buffering off` for `/cameras/*/stream/`)
3. **Secret Key**:
   - Generate a cryptographically strong 50+ character string: `openssl rand -base64 48`
   - Inject via environment variable `DJANGO_SECRET_KEY`
4. **Database Hardening**:
   - If utilizing MySQL, restrict database user permissions to `SELECT, INSERT, UPDATE, DELETE` on `DeepVision` schema only. Do not grant `SUPER` or `FILE` privileges.
5. **Firewall Rules**:
   - Only expose port `443` (and port `80` for ACME challenges/HTTP redirection) to public networks. Keep database and internal RTSP streams isolated in a private VPC or VLAN.

---

## 5. Security Incident Reporting

To report a vulnerability or operational security issue, please contact:
- **Security Team**: `security@deepvision.local` or the designated repository owner.
- Please provide reproduction steps, impact assessment, and proof-of-concept without publishing publicly.
