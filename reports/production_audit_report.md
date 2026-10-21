# DeepVision Production Audit & Deployment Verification Report

**Date & Time:** October 21, 2026  
**Auditor:** Autonomous Senior Systems & Security Engineer (Antigravity)  
**Repository:** [https://github.com/VAIBHAV-w1/DeepVision.git](https://github.com/VAIBHAV-w1/DeepVision.git)  
**Live Production URL:** [https://vsw-deepvision.vercel.app/](https://vsw-deepvision.vercel.app/)  
**Production Branch:** `main`

---

## 1. Deployment Identity

| Property | Value |
| :--- | :--- |
| **Production URL** | `https://vsw-deepvision.vercel.app/` |
| **Production Aliases** | `vsw-deepvision.vercel.app`, `deepvision-soc.vercel.app`, `deepvision-vsw.vercel.app`, `frontend-ten-tau-nm1m468imk.vercel.app` |
| **Vercel Project** | `deepvision-frontend` (`prj_PQWC1sBTk5KXNiAXE0UgrkEHNUIT`) |
| **Active Deployment ID** | `dpl_4GyahcUxoKEdEd6YQQ9EvqQK6V1Z` |
| **Direct Deployment URL**| `https://deepvision-frontend-9a38q534v-vaibhav-wandkar-s-projects.vercel.app` |
| **Git Commit SHA** | `be9a08f51a4471fe4339e083c27daae9fe66c1b5` |
| **Git Branch** | `main` |
| **Ready State** | `READY` (HTTP 200 on all routes and health check) |

---

## 2. Baseline Findings

Prior to this engineering loop, several underlying defects were reproduced and diagnosed:

1. **Unsynchronized Codebase on GitHub**:
   - *Severity:* Critical
   - *Reproduction:* Local tree had extensive modifications that were never committed or pushed to `origin/main`. Vercel had been serving deployment `deepvision-frontend-4wozas69h` from an outdated commit (`623e3f1`).
   - *Result:* The live public website lacked the UI redesign and latest backend endpoints.

2. **Serverless Database Configuration Mismatch on Production**:
   - *Severity:* High
   - *Reproduction:* `GET https://vsw-deepvision.vercel.app/api/health/` returned `HTTP 503` (`pending_configuration`) and login returned `HTTP 503 Database service is not ready`.
   - *Root Cause:* `DATABASE_URL` and `MAIL_*` environment variables in Vercel were scoped to `Preview` environments only, leaving `Production` lambdas without the Supabase PostgreSQL connection string.

3. **HTTP Range Test False-Positive**:
   - *Severity:* Medium
   - *Reproduction:* `test_e2e_full_system.py` reported `Recording #2724 Range response: HTTP 200, Range: None, Bytes read: 1755`.
   - *Root Cause:* The test request lacked an authenticated session cookie. Django's `@login_required` redirected to `/login/`, which returned HTTP 200 with 1755 bytes of HTML, concealing the lack of actual HTTP 206 streaming verification.

4. **Residual Pill Radius in Camera Monitor Badges**:
   - *Severity:* Low
   - *Reproduction:* Grepping for `9999px` revealed `border-radius: var(--radius-full, 9999px)` in `.monitor-live-badge`, `.monitor-pill-camname`, and `.monitor-pill-clock`.
   - *Root Cause:* Incomplete token cleanup during HUD styling.

5. **Sandbox Playwright Binary Isolation**:
   - *Severity:* Medium
   - *Reproduction:* Headless browser subagent failed to download Playwright driver due to external CDN 404 in isolated sandbox.
   - *Root Cause:* Driver download blocked by sandbox network isolation.

---

## 3. Fixes Applied

1. **Vercel Production Environment Scope Update**:
   - *Files Changed:* Remote Vercel configuration via API.
   - *Fix:* Updated target environments for `DATABASE_URL`, `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER` from `["preview"]` to `["production", "preview"]`.
   - *Result:* `/api/health/` immediately transitioned from `HTTP 503` to `HTTP 200` (`database: "connected"`, `database_backend: "postgresql"`, `schema_ready: true`, 18 tables).

2. **Strict HTTP 206 Partial Content Verification**:
   - *Files Changed:* `verification/test_e2e_full_system.py`
   - *Fix:* Generated genuine signed-cookie sessions (`deepvision_django_session`), tested `Range: bytes=0-1023` (asserting `HTTP 206`, `Content-Range: bytes 0-1023/<total>`, `Content-Length: 1024`), tested unsatisfiable ranges (asserting `HTTP 416`), and tested full downloads (asserting `HTTP 200`).

3. **Elimination of Oversized Pill Radius**:
   - *Files Changed:* `frontend/src/styles/camera.css`
   - *Fix:* Replaced `border-radius: var(--radius-full, 9999px)` with crisp rectangular `border-radius: 4px` on monitor badges.

4. **Real-Browser CDP Automation Suite**:
   - *Files Changed:* `verification/test_real_browser_cdp.py`
   - *Fix:* Engineered an autonomous Chrome DevTools Protocol (CDP) test suite leveraging the local Google Chrome 155 installation without requiring external Playwright binary downloads.

5. **Legal & Compliance Integration**:
   - *Files Changed:* `frontend/src/pages/Legal.jsx`, `frontend/src/App.jsx`, `frontend/src/components/common/Footer.jsx`, `frontend/src/layouts/AuthLayout.jsx`
   - *Fix:* Added Privacy Policy and Terms of Service modal and direct routes (`#privacy`, `#terms`).

6. **Documentation Synchronization**:
   - *Files Changed:* `README.md`
   - *Fix:* Added **DeepVision Live Demo** section linking to `https://vsw-deepvision.vercel.app/`.

---

## 4. Test Matrix

| Area | Test Command / Action | Expected Result | Observed Result | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Vercel Routing** | `test_e2e_full_system.py` suite 1 | API / SPA routing contract verified | Routing & rewrites pass | **PASS** |
| **Camera Telemetry** | `test_e2e_full_system.py` suite 2 | Live DirectShow stats without mock FPS | Telemetry verified | **PASS** |
| **Brand Identity** | `test_e2e_full_system.py` suite 3 | SVG logos & SOC theme assets present | Assets verified | **PASS** |
| **Code Splitting** | `test_e2e_full_system.py` suite 4 | Entry chunk < 100 KB | `index-jxAJdhRJ.js` = 36.95 KB | **PASS** |
| **HTTP 206 Streaming** | `test_e2e_full_system.py` suite 5 | Genuine Range response: HTTP 206, 1024 B | `HTTP 206`, `bytes 0-1023/13737505` | **PASS** |
| **Range 416 Guard** | `test_e2e_full_system.py` suite 5 | Out-of-bounds range rejected | `HTTP 416`, `bytes */13737505` | **PASS** |
| **Evidence Vault** | `test_e2e_full_system.py` suite 6 | Defensive rendering against missing files | Resilience verified | **PASS** |
| **Secret Safety** | `test_e2e_full_system.py` suite 7 | Zero secrets committed in tracked files | Zero leaks found | **PASS** |
| **Rate Limiting** | `test_rate_limiting.py` | HTTP 429 + `Retry-After` enforcement | 3/3 tests pass | **PASS** |
| **Health Diagnostics** | `test_health_and_readiness.py` | Fail-safe DB diagnostics (Postgres/SQLite) | 4/4 tests pass | **PASS** |
| **Migration Safety** | `test_migration_safety_gate.py` | Refuses unconfirmed schema overwrites | 5/5 tests pass | **PASS** |
| **Chrome App Loading** | `test_real_browser_cdp.py` step 1 | Zero fatal exceptions, valid DOM | Zero fatal exceptions | **PASS** |
| **Responsiveness** | `test_real_browser_cdp.py` step 2 | 0px horizontal overflow (desktop/tab/mob) | 0px overflow across all viewports | **PASS** |
| **Legal Routes** | `test_real_browser_cdp.py` step 3 | `#privacy` and `#terms` render content | Content verified | **PASS** |
| **Form Validation** | `test_real_browser_cdp.py` step 4 | Handles empty submit safely | Validated cleanly | **PASS** |
| **Theme Switching** | `test_real_browser_cdp.py` step 5 | Toggles `data-theme` between dark & light | State toggle verified | **PASS** |
| **Rectangular SOC UI**| `test_real_browser_cdp.py` step 6 | 0 oversized pill buttons (`> 16px`) | 0 pill buttons | **PASS** |
| **Production Health** | `GET /api/health/` on public URL | HTTP 200, Postgres connected, 18 tables | HTTP 200, healthy, 18 tables | **PASS** |
| **Production Auth API**| `POST /api/auth/login/` on public URL| Evaluates DB credentials, returns 401 | HTTP 401 `Invalid email or password.` | **PASS** |

---

## 5. Live Production Verification

### Public Endpoint Responses
- `GET https://vsw-deepvision.vercel.app/` -> `HTTP 200 OK` (Vite SPA HTML shell referencing `index-jxAJdhRJ.js` and `index-CERUvgxe.css`).
- `GET https://vsw-deepvision.vercel.app/assets/Legal-BaB2gO-Y.js` -> `HTTP 200 OK` (10,447 bytes).
- `GET https://vsw-deepvision.vercel.app/api/health/` -> `HTTP 200 OK`:
  ```json
  {
    "status": "healthy",
    "django_app": "online",
    "database": "connected",
    "database_backend": "postgresql",
    "schema_ready": true,
    "tables_count": 18,
    "diagnostic": "Database connected and schema verified.",
    "surveillance_engine": "healthy",
    "timestamp": "2026-10-21T07:14:41.643410+00:00"
  }
  ```
- `GET https://vsw-deepvision.vercel.app/api/auth/me/` -> `HTTP 200 OK` (`{"authenticated": false, "user": null}`).
- `GET https://vsw-deepvision.vercel.app/api/auth/csrf/` -> `HTTP 200 OK` (Returns CSRF token and sets `deepvision_django_csrftoken` cookie).
- `POST https://vsw-deepvision.vercel.app/api/auth/login/` -> `HTTP 401 Unauthorized` (`{"success": false, "error": "Invalid email or password."}`).

### Real Browser CDP Validation Results
- Executed with Google Chrome `155.0.8059.84` in headless mode.
- Rendered title: `"DeepVision : Intelligent Surveillance SOC"`.
- Layout dimensions:
  - Desktop (1920x1080): `scrollWidth = 1920`, `clientWidth = 1920`, `overflow = 0px`.
  - Tablet (768x1024): `scrollWidth = 768`, `clientWidth = 768`, `overflow = 0px`.
  - Mobile (375x812): `scrollWidth = 375`, `clientWidth = 375`, `overflow = 0px`.
- Console Errors: 0 fatal exceptions; clean hydration and routing.

---

## 6. Camera, Evidence & Recording Verification

1. **Camera Feed & Telemetry**:
   - Hardware: Local host DirectShow camera (index 0) driven via `scripts/host_camera_bridge.py` on `127.0.0.1:8554`.
   - Streaming pipeline: OpenCV `VideoCapture` -> frame queue -> MJPEG generator.
   - FPS and bitrate telemetry are calculated dynamically from frame timestamps.
   - *Architectural boundary:* Physical USB/DirectShow cameras run on the local edge host; the public Vercel frontend connects to persistent backend gateways for camera ingestion.

2. **Persistent Snapshot Capture**:
   - `POST /api/cameras/<id>/snapshot/` captures raw DirectShow BGR frames, encodes to JPEG, writes to `instance/evidence/camera_<id>/<date>/snapshot_<uuid>.jpg`, and persists correlated `Alert` and `Evidence` records in the database.

3. **Recording Playback & HTTP Range (RFC 7233)**:
   - Genuine test against recording `#2724` (`13,737,505` bytes):
     - `Range: bytes=0-1023` -> `HTTP 206 Partial Content`, `Content-Range: bytes 0-1023/13737505`, `Content-Length: 1024`, `1024` bytes delivered.
     - `Range: bytes=999999999-999999999` -> `HTTP 416 Range Not Satisfiable`, `Content-Range: bytes */13737505`.
     - Full request -> `HTTP 200 OK`, `Content-Length: 13737505`, `Accept-Ranges: bytes`.

---

## 7. Security Review

- **Credential & Secret Exposure**: Automated scanner in `test_e2e_full_system.py` verified zero private keys, plaintext database connection strings, or secret tokens across all tracked project files.
- **CSRF Protection**: Native Django CSRF middleware enforces strict token verification and `Referer` / `Origin` validation across HTTPS requests (`CSRF_COOKIE_HTTPONLY = False`, `CSRF_COOKIE_SAMESITE = 'Lax'`).
- **Session Security**: Session tokens are signed using cryptographic PBKDF2 signatures (`SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'`).
- **Rate Limiting**: Critical authentication endpoints (`login`, `signup`, `otp`, `reset`) are protected by a shared database audit log rate limiter returning `HTTP 429` with `Retry-After`.
- **Media Access Control**: Recording and evidence endpoints verify file ownership and path traversal boundaries (`safe_resolve_recording`, `safe_resolve_evidence`).

---

## 8. GitHub Synchronization

- **Target Repository**: `https://github.com/VAIBHAV-w1/DeepVision.git`
- **Branch**: `main`
- **Commits Pushed**:
  - `ab15d0f` — `feat: SOC UI redesign, persistent evidence snapshots, database rate limiting, and Vercel sync`
  - `b795dcc` — `style(camera): enforce rectangular 4px badge radius across HUD controls`
  - `be9a08f` — `test: add Chrome CDP real-browser audit suite and enforce strict HTTP 206 Range assertions`
- **Working Tree**: Clean (`git status` reports `nothing to commit, working tree clean`).

---

## 9. Vercel Deployment

- **Deployment URL**: `https://deepvision-frontend-9a38q534v-vaibhav-wandkar-s-projects.vercel.app`
- **Assigned Public Host**: `https://vsw-deepvision.vercel.app/`
- **Live Asset Hashes**:
  - Main bundle: `/assets/index-jxAJdhRJ.js` (37.84 KB)
  - Core stylesheet: `/assets/index-CERUvgxe.css` (79.77 KB)
  - Legal chunk: `/assets/Legal-BaB2gO-Y.js` (10.44 KB)
  - Vendor chunk: `/assets/vendor-BuL4xlPh.js` (210.61 KB)

---

## 10. Status & Remaining Environment Constraints

| Item | Status | Concrete Context & Next Action |
| :--- | :---: | :--- |
| **UI Redesign** | **PASS** | Complete SOC layout with rectangular styling active on live production. |
| **Vercel Deployment** | **PASS** | Deployment `dpl_4GyahcUxoKEdEd6YQQ9EvqQK6V1Z` active on `vsw-deepvision.vercel.app`. |
| **PostgreSQL Cloud DB**| **PASS** | Supabase connection verified live (18 tables ready). |
| **Auth & Rate Limiting**| **PASS** | Database rate limiting verified with HTTP 429 and `Retry-After`. |
| **HTTP 206 Range** | **PASS** | Strict range seeking verified on actual MP4 files. |
| **Real Browser CDP** | **PASS** | Google Chrome 155 executed 6/6 automated test steps. |
| **Hardware Boundary** | **DOCUMENTED** | Physical USB camera DirectShow bridge is local to the edge host; serverless Vercel operates as API & UI layer. |
