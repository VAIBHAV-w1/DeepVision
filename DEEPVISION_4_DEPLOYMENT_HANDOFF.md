# DeepVision 4.0 — Deployment Handoff Document

**Preparation Date:** 2026-11-21  
**Project Root:** `D:\DeepVision`  
**Current Branch:** `repair/pipeline-e2e-verification`  
**Last Known-Good Git Commit on Branch:** `7d3d47d` (`fix(surveillance): repair AI cold-start, camera viewport, zone scaling, and OpenCV fallback`)  
**Previous Merged Production PR Commit:** `aae97ad` (`Merge pull request #3 from VAIBHAV-w1/fix/production-launch`)  
**Release Classification:** **`RELEASE CANDIDATE — EXTERNAL GATES REMAIN`**

---

## 1. Exact Release Scope (Approved Staged Manifest vs Excluded Artifacts)

### A. Include in Release Commit (`76` Explicitly Verified Files)
- **CI, Containers & Dependencies (`4`):** `.github/workflows/ci.yml`, `Dockerfile`, `requirements.txt`, `requirements-surveillance.txt`
- **Django Backend (`43`):**
  - `deepvision_django/config/`: `settings.py`, `urls.py`
  - `deepvision_django/apps/accounts/`: `email_service.py`, `middleware.py`, `views.py`, `tests/test_email_service.py`, `tests/test_security_hardening.py`
  - `deepvision_django/apps/ai/`: `engine.py`
  - `deepvision_django/apps/alerts/`: `views.py`
  - `deepvision_django/apps/cameras/`: `surveillance_config.py`, `views.py`
  - `deepvision_django/apps/core/`: `api.py`, `audit.py`, `media_service.py`, `models.py`, `rate_limiter.py`, `storage_service.py`, `views.py`
  - `deepvision_django/apps/notifications/`: `delivery_service.py`, `models.py`, `views.py`
  - `deepvision_django/apps/surveillance/`: `ai/` (`detector.py`, `model_loader.py`, `motion_analyzer.py`, `onnx_runtime.py`, `registry.py`, `reid.py`, `tracker.py`, `workers.py`, `anomaly/anomaly_detector.py`, `anomaly/zones.py`, `trackers/__init__.py`, `botsort_core.py`, `bytetrack_core.py`, `gmc.py`, `kalman.py`, `matching.py`, `ocsort_core.py`), `camera/` (`capture.py`, `workers.py`), `health/health_service.py`, `streaming/stream_service.py`, `tests/test_mjpeg_redirect_ssrf.py`
- **SQL & PostgreSQL Scripts (`4`):** `scripts/migrate_sqlite_to_postgres.py`, `deepvision_django/schema_postgres.sql`, `deepvision_django/schema_postgres_post_import.sql`, `deepvision_django/supabase_setup_restricted_role.sql`
- **Frontend (`18`):** `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.js`, `frontend/scripts/build.mjs`, and `frontend/src/` (`App.jsx`, `components/cameras/RestrictedZoneEditor.jsx`, `components/common/Modal.jsx`, `Navbar.jsx`, `hooks/useAuth.jsx`, `i18n/translations.js`, `pages/Cameras.jsx`, `Cases.jsx`, `Legal.jsx`, `Login.jsx`, `Notifications.jsx`, `Settings.jsx`, `services/api.js`, `utils/csrf.js`)
- **Verification & Release Docs (`7`):** `verification/test_yolo_and_tracker.py`, `DEEPVISION_4_DEPLOYMENT_CHECKLIST.md`, `DEEPVISION_4_DEPLOYMENT_HANDOFF.md`, `DEEPVISION_4_PRODUCTION_READINESS_REPORT.md`, `DEEPVISION_4_PRODUCTION_SECURITY_AUDIT.md`, `DEEPVISION_4_RELEASE_VERIFICATION_MATRIX.md`, `DEEPVISION_4_SECURITY_REMEDIATION_LOG.md`

### B. Exclude / Do NOT Stage or Commit
- `=` *(0-byte stray file)*, `requirements-lock-win314.txt` *(local Windows freeze snapshot)*, `*.pre-audit.bak`
- `ov_telemetry/`, `backups/`, `backup/`, `instance/` (`deepvision.db`), `.env`, `.vercel/`, `frontend/dist/`, `deepvision_django/static/dist/`
- Unrelated `reports/*` and scratch `verification/*` probes not in the manifest above

---

## 2. Render & Vercel Deployment Configuration

| Target | Parameter | Configured Value | Notes |
|---|---|---|---|
| **Render Backend** | URL & Runtime | `https://deepvision-6ie7.onrender.com` / `Dockerfile` | Multi-stage: Node 20 builds React static assets to `deepvision_django/static/dist/`; Python 3.11 installs `requirements.txt` + SHA-256-verified `yolo26s.onnx`/`yolo26n.onnx`; runs `gunicorn config.wsgi:application --workers 1 --threads 12 --worker-class gthread --timeout 90` on `0.0.0.0:${PORT:-8000}` |
| **Vercel Frontend** | URL & Build | `https://vsw-deepvision.vercel.app` / [vercel.json](file:///d:/DeepVision/vercel.json) | `buildCommand: npm --prefix frontend install && npm --prefix frontend run build`, `outputDirectory: frontend/dist` (`VERCEL=1`), `.vercelignore` excludes `/deepvision_django/`, `/api/`, `/instance/`, `/models/` |
| **API Rewrites & Edge Note** | Proxied Paths | `/api/(.*)`, `/cameras/(.*)`, `/recordings/(.*)`, `/evidence/(.*)`, `/alerts/(.*)`, `/notifications/(.*)`, `/health(.*)` | Proxies to `https://deepvision-6ie7.onrender.com/...`; note Vercel edge IPs appear in `CF-Connecting-IP` unless calling Render directly via `VITE_API_BASE_URL` |
| **Security Headers & TLS** | Local Release Candidate | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `SECURE_HSTS_SECONDS=31536000` (preload), `SECURE_SSL_REDIRECT` auto-enabled on `RENDER`/`VERCEL` | Health endpoints (`/health/`, `/api/health/`, `/health/live/`, `/api/health/live/`) exempt from HTTPS redirect; `manage.py check --deploy` = `0 issues` |

---

## 3. Production Environment Variable Checklist (Values Never Printed)

### Required on Render (`deepvision-6ie7.onrender.com`)
| Variable | Requirement | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `False` | Enforces production secret validation, `Secure` cookies, HSTS, HTTPS redirect |
| `DEEPVISION_ENV` | `production` | Activates fail-closed production PostgreSQL & Gunicorn checks |
| `RENDER` | `true` | Auto-set by Render; activates `CF-Connecting-IP` trust & HTTPS redirect default |
| `DJANGO_SECRET_KEY` | **>= 50 unique random chars** | Must differ from `_DEV_FALLBACK_KEY` / `_COMPROMISED_KEY` (`security.W009` compliant) |
| `DJANGO_ALLOWED_HOSTS` | **Exact comma-separated hostnames** | e.g. `deepvision-6ie7.onrender.com,vsw-deepvision.vercel.app,deepvision-soc.vercel.app,vsw-deepvision.com,www.vsw-deepvision.com` (+ `127.0.0.1` only if container loopback health probes need it); **wildcards are ignored when set** |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | **Exact HTTPS origins** | e.g. `https://vsw-deepvision.vercel.app,https://deepvision-soc.vercel.app,https://deepvision-6ie7.onrender.com,https://vsw-deepvision.com,https://www.vsw-deepvision.com` |
| `DATABASE_URL` | PostgreSQL/Supabase URI (`?sslmode=require`) | Required persistent production database |
| `RESEND_API_KEY` + `MAIL_DEFAULT_SENDER` | API key + verified sender domain | HTTPS API OTP, reset, and alert email delivery |
| Persistent Media Storage (`Option A / B / C`) | `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (+ buckets) **OR** `S3_*` **OR** `DEEPVISION_PERSISTENT_STORAGE_DIR` | Render container local filesystem (`instance/`) is ephemeral across deploys |

### Optional on Render / Vercel
- `MAIL_SERVER`, `MAIL_PORT=587`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_TLS=True`: SMTP fallback alongside Resend API.
- `DEEPVISION_PURGE_LOCAL_AFTER_UPLOAD=true`: Enable after verifying remote `verify_object()` reliability.
- `DEEPVISION_ALLOW_SELF_SIGNED_LAN_CAMERA=false`: Keep `false` unless private RFC1918 LAN cameras require self-signed HTTPS.
- `VITE_API_BASE_URL` (Vercel only): Leave unset for same-origin `/api/*` rewrites, or set to `https://deepvision-6ie7.onrender.com` with strict CORS if avoiding shared Vercel POP egress IPs in `CF-Connecting-IP`.

---

## 4. Safe Deployment & Rollback Sequence

1. **Approval & Commit:** After user review, commit ONLY the `76` staged release files (do not commit `.env`, DBs, backups, or stray files) and push to trigger `.github/workflows/ci.yml` (`oxlint` on Linux, Docker build, `gunicorn` check, E2E + strict native AI tests).
2. **Pre-Deploy Backup:** Take a Supabase PostgreSQL snapshot before triggering deployment.
3. **Deploy Backend First (Render) -> Frontend Second (Vercel):** Confirm `/api/health/` (`200`, `postgresql`, `schema_ready: true`) and `/api/health/live/` (`200`, `Strict-Transport-Security`), then promote Vercel frontend.
4. **Post-Deploy Gates:** Complete live inbox Login OTP + password-reset session revocation test, live persistent storage upload/`206`/restart test, authorized LAN RTSP test, and monitored 30-minute soak before upgrading status beyond `RELEASE CANDIDATE`.
5. **Rollback:** In Render -> *Events / Deploys* -> roll back to previous working deploy (`200 /api/health/`); in Vercel -> *Deployments* -> promote prior stable deployment. No database schema migration was introduced in this release. Pre-edit backups exist under `D:\DeepVision\backups\`.
