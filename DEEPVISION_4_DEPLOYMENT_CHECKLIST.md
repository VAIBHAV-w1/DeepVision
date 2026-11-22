# DeepVision 4.0 — Production Deployment Checklist

**Current Stage:** **`RELEASE CANDIDATE — EXTERNAL GATES REMAIN`**  
**Target Stack:** Render Backend (`deepvision_django`), Vercel Frontend (`frontend`), Supabase PostgreSQL + Persistent Object Storage

---

## 1. Local Engineering & Pre-Deployment Gate

- **PASS** — Python & frontend dependency CVE floors synchronized across [requirements.txt](file:///d:/DeepVision/requirements.txt) and [requirements-surveillance.txt](file:///d:/DeepVision/requirements-surveillance.txt); `pip check` (`0` broken), OSV PyPI audit (`63` pkgs -> `0` CVEs), `npm audit` (`0` vulnerabilities).
- **PASS** — Reverse-proxy IP spoofing hardening enforced consistently in [rate_limiter.py](file:///d:/DeepVision/deepvision_django/apps/core/rate_limiter.py) and [audit.py](file:///d:/DeepVision/deepvision_django/apps/core/audit.py).
- **PASS** — MJPEG SSRF redirect validation (`_SafeMjpegRedirectHandler`) and strictly LAN-scoped optional self-signed TLS (`_ScopedMjpegHTTPSHandler`) verified in [capture.py](file:///d:/DeepVision/deepvision_django/apps/surveillance/camera/capture.py) and [test_mjpeg_redirect_ssrf.py](file:///d:/DeepVision/deepvision_django/apps/surveillance/tests/test_mjpeg_redirect_ssrf.py).
- **PASS** — Production configuration tightened in [settings.py](file:///d:/DeepVision/deepvision_django/config/settings.py): `>=50`-character `DJANGO_SECRET_KEY`, exact domain overrides without `.vercel.app`/`.onrender.com` wildcards, `manage.py check --deploy` = `0 issues`.
- **PASS** — Dead `login_view`/`signup_view`/`forgot_password_view`/`reset_password_view` and unused frontend `loginAsDemo` removed; `assistant_chat_view` rate-limited (`30/60s`); cloud storage `Content-Disposition` sanitized; `Modal.jsx` keyboard focus trap added.
- **PASS** — Vite 8.3.8 / Rolldown WASI builds (`frontend/dist/` & `deepvision_django/static/dist/`) verified with zero bundled secrets.
- **PASS** — Canonical `instance/deepvision.db` integrity verified (`ok`, `18` tables, raw DDL signature `cc2d13f77b681107`; normalized column signature `591d3f29af800a45`).

---

## 2. Pre-Deploy Production Environment Gate (Requires Explicit Approval)

- **BLOCKED** — Commit staged release manifest (`76` files), push to remote branch/main, and run `.github/workflows/ci.yml` (`oxlint` on Linux, Docker build, `gunicorn` runtime startup, strict native AI tests).
- **BLOCKED** — Confirm Render environment variables before redeploying `deepvision-6ie7.onrender.com`:
  - `DJANGO_DEBUG=False`, `DEEPVISION_ENV=production`, `RENDER=true`
  - `DJANGO_SECRET_KEY` (>= 50 unique random characters)
  - Exact `DJANGO_ALLOWED_HOSTS` (no wildcards; include `127.0.0.1` only if container loopback health probes hit it)
  - Exact HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS` (no wildcards)
  - `DATABASE_URL` (PostgreSQL with `sslmode=require`)
  - Email credentials (`RESEND_API_KEY` + verified sender and/or SMTP fallback)
  - Persistent storage (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, S3/R2, or `DEEPVISION_PERSISTENT_STORAGE_DIR`)
  - Keep `DEEPVISION_ALLOW_SELF_SIGNED_LAN_CAMERA=false` unless LAN cameras require self-signed HTTPS
- **ACCEPTED RISK** — Vercel `/api/*` rewrites forward client requests via Vercel edge IPs (`CF-Connecting-IP` shares Vercel POP IP across users); mitigate long-term by setting `VITE_API_BASE_URL` directly to Render with strict CORS if per-client edge rate isolation is required.

---

## 3. Post-Deploy External Verification Gate

- **NOT TESTED** — `GET https://deepvision-6ie7.onrender.com/api/health/` (`200`, `postgresql`, `schema_ready: true`) & `GET /api/health/live/` (`200`, `Strict-Transport-Security`).
- **NOT TESTED** — Real persistent bucket round-trip (upload -> HTTP `206` playback -> container restart -> persistence verify -> cleanup).
- **BLOCKED** — Live external inbox Login OTP, Password Reset + old-session revocation, and alert/test email receipt.
- **NOT TESTED** — Authorized external LAN RTSP camera live ingest, unsandboxed physical `dshow://0` hardware webcam re-verification, and 30-minute (`1800s`) continuous endurance soak.
