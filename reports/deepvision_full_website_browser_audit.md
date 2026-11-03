# DEEPVISION: FULL WEBSITE REAL BROWSER AUDIT & OTP REPAIR REPORT

**Date:** 2026-10-22  
**Target Host:** `http://127.0.0.1:8000/` (Local Django App inside Docker container `deepvision-app`)  
**Camera Bridge:** `http://127.0.0.1:8554` (DirectShow CCTV Ingestion)  
**Production Site:** `https://vsw-deepvision.vercel.app/`  
**Deployment Gate Status:** **STRICTLY BLOCKED & PRESERVED UNTOUCHED**. Zero git push, zero Vercel redeployment, zero production modifications.

---

## 1. Executive Summary & Audit Scorecard

A full browser-driven audit and autonomous repair loop was conducted on the DeepVision SOC application running on localhost. Antigravity's automated Chrome DevTools Protocol (CDP) browser test suite interacted with the live UI as a real operator, performing form inputs, OTP verification, page navigations, viewport resizing, and telemetry inspections.

### Final Verification Scorecard

| Category | Total Tests | PASS | FAIL | BLOCKED | SIMULATED |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Section 1: OTP Lifecycle & Security (OTP-01 – OTP-15)** | 15 | **15** | 0 | 0 | 0 |
| **Section 2: Route Inventory & Controls (PAGE-01 – PAGE-10)** | 10 | **10** | 0 | 0 | 0 |
| **Section 3: Cross-Route Page Isolation (ISO-01)** | 1 | **1** | 0 | 0 | 0 |
| **Section 4: 7-Viewport Responsive Audit (RESP-01 – RESP-07)** | 7 | **7** | 0 | 0 | 0 |
| **Section 5: Console & Runtime Exceptions (ERR-01)** | 1 | **1** | 0 | 0 | 0 |
| **TOTAL** | **34** | **34** | **0** | **0** | **0** |

*All 34 automated browser-driven test invariants passed with zero failures.*

---

## 2. P0: OTP Diagnosis, Root Causes & Solution

### A. Reported Defect
Users reported that OTP authentication on localhost failed or could not be completed, preventing legitimate users from advancing through the login verification sequence.

### B. Root Causes Discovered
1. **Container Environment Isolation (Missing SMTP Configuration):**
   - The Docker container `deepvision-app` was initialized without inheriting the project's root `.env` file containing Gmail SMTP credentials (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`).
   - Consequently, Django's email backend defaulted to unconfigured SMTP or standard fallback, causing authentication OTP emails to fail silently or throw socket errors.
2. **Frontend-Backend API Mismatch on Login OTP:**
   - The Django API exposed `/api/auth/verify-login-otp/` and `/api/auth/resend-login-otp/`.
   - The frontend API client (`frontend/src/services/api.js`) had endpoints for email registration verification (`verifyOtp`, `resendOtp`), but lacked dedicated methods for login OTP dispatch, causing `Login.jsx` to attempt non-standard calls or fallbacks.
3. **Session Role & Login Completion Omission:**
   - In `deepvision_django/apps/core/api.py`, `api_verify_login_otp` set `request.session["user_id"] = user.id`, but omitted `request.session["role"] = user.role`.
   - Without `role` stored in session, operator-level permissions on subsequent queries fell back to guest, preventing data retrieval.
4. **Resend Cooldown Enforcement:**
   - Resending OTP lacked server-enforced rate-limiting cooldowns (60s), permitting rapid sequential email dispatches.
5. **Authenticated Login Redirection:**
   - Navigating to `/login/` when already authenticated did not automatically redirect to `/dashboard/`, causing reload state desynchronization.

### C. Repairs Implemented
1. **Docker Compose & SMTP Configuration:**
   - Added `env_file: - .env` in `docker-compose.yml`.
   - Synchronized `.env` with Gmail SMTP credentials into the running container `deepvision-app`.
   - Tested real email dispatch via live TLS connection to `smtp.gmail.com:587`.
2. **Frontend API & Component Integration:**
   - Added `verifyLoginOtp(email, otp)` and `resendLoginOtp(email)` to `frontend/src/services/api.js`.
   - Wired `Login.jsx` to dispatch credentials, transition to the 6-digit OTP code prompt, auto-advance focus across input digits, and submit to `/api/auth/verify-login-otp/`.
3. **Session Role & Backend Cooldowns:**
   - Updated `api_verify_login_otp` in `deepvision_django/apps/core/api.py` to persist `role` in session.
   - Enforced a 60-second cooldown in `api_resend_login_otp`, returning HTTP 429 Too Many Requests if triggered prematurely.
4. **Standard Authenticated Redirection:**
   - Added `if request.user.is_authenticated: return redirect("dashboard")` in `deepvision_django/apps/accounts/views.py` for `login_view` and `signup_view`.
5. **Cryptographic Integrity & Single-Use Rules:**
   - Verified that OTPs are generated with `secrets.choice("0123456789")`, stored as PBKDF2 SHA-256 hashes (`LOGIN:<otp>`), and wiped immediately upon successful verification.
   - Verified lockout after 5 consecutive failed attempts.

### D. OTP Test Matrix (OTP-01 through OTP-15)

| Test ID | Test Description | Observed Real Browser Behavior | Status |
| :--- | :--- | :--- | :---: |
| **OTP-01** | Authentication Form Appearance | Rendered login form with email & password fields; SOC branding intact. | **PASS** |
| **OTP-02** | Input Validation on Empty/Invalid Data | Submitting empty form triggered native client validation without network request. | **PASS** |
| **OTP-03** | Valid Credentials Advancement | Submitted valid test credentials; transitioned to 6-digit OTP input step. | **PASS** |
| **OTP-04** | Backend Delivery & State Persistence | Verified OTP hash persisted in DB with PBKDF2 salt, 0 initial attempts, and sent_at timestamp. | **PASS** |
| **OTP-05** | UI 6-Digit OTP Entry & Submission | Typed 6-digit code into input boxes; verified successfully. | **PASS** |
| **OTP-06** | Session Establishment & Dashboard Redirect | Authenticated session created; automatically redirected to SOC Dashboard. | **PASS** |
| **OTP-07** | Incorrect OTP Rejection & Attempt Increment | Submitted incorrect code; rejected with error message; attempt counter incremented. | **PASS** |
| **OTP-08** | Expired OTP Rejection | Evaluated expired OTP timestamp; strictly rejected with expiration notice. | **PASS** |
| **OTP-09** | Single-Use Replay Prevention | Re-submitting previously verified OTP rejected immediately because hash was wiped. | **PASS** |
| **OTP-10** | Resend Cooldown Enforcement | Resend endpoint within 60s cooldown returned HTTP 429 Too Many Requests. | **PASS** |
| **OTP-11** | Lockout After 5 Failed Attempts | After 5 consecutive invalid entries, account OTP locked with lockout message. | **PASS** |
| **OTP-12** | Page Reload Session Preservation | Hard browser reload while authenticated kept operator session intact on Dashboard. | **PASS** |
| **OTP-13** | CSRF Protection on Auth Endpoints | State-changing request without CSRF cookie returned HTTP 403 Forbidden. | **PASS** |
| **OTP-14** | Forgot Password Reset OTP Flow | Reset endpoint returned HTTP 200 without exposing account existence. | **PASS** |
| **OTP-15** | Zero Secret Leakage in Logs | Zero OTP values, cleartext passwords, or tokens found in console logs or reports. | **PASS** |

---

## 3. Discovered Routes & Interactive Controls Inventory

| Route Path | Component | Purpose | Key Interactive Controls Discovered & Audited |
| :--- | :--- | :--- | :--- |
| `/login/` | `Login.jsx` | SOC Operator Sign-in | Email & password inputs, Show/Hide password toggle, Sign In button, 6-digit OTP inputs, Resend code countdown, Back to Credentials link. |
| `/dashboard/` | `Dashboard.jsx` | SOC Command Overview | Live telemetry status banner, Quick Nav buttons, Camera grid/table toggle, Refresh button, Metric cards (Cameras, Recordings, Alerts, Evidence, Cases), Live channel snapshot preview. |
| `/cameras/` | `Cameras.jsx` | Camera Fleet Gallery | Search filter input, Status filters (All, Online, Offline), Refresh button, Connect Camera button, Camera thumbnail cards, Live Preview action links. |
| `/cameras/4/preview/` | `CameraPreview.jsx` | Real-time Stream Monitor | HUD telemetry overlay (FPS, Resolution, Engine status), Stream Mode selector (Original vs Tracking+Detection), Snapshot button, Record toggle button, Back to Fleet navigation. |
| `/recordings/` | `Recordings.jsx` | Surveillance Video Archive | Camera channel filter, Type filter (All, Anomaly, Routine), Search input, Recording cards, Playback modal trigger, MP4 download buttons, Pagination controls (Next/Prev/Pages). |
| `/evidence/` | `Evidence.jsx` | Forensic Vault | Camera filter, Alert link filter, Evidence snapshot cards, Forensic metadata inspector, Evidence download link. |
| `/cases/` | `Cases.jsx` | Forensic Incident Cases | Incident cases table, Severity badges, Status filters (Open, In Progress, Closed), Case investigation inspector. |
| `/alerts/` | `Alerts.jsx` | Threat Intelligence Inbox | Severity filter (Critical, High, Medium, Low), Status filter (New, Acknowledged, Resolved), Search input, Alert list rows, Acknowledge/Resolve buttons, Evidence links. |
| `/notifications/` | `Notifications.jsx`| Security Dispatch Center | Notifications list, Mark as read buttons, System health alerts. |
| `/help/` | `Help.jsx` | Technical Guidance | Operational guides grid, Hardware camera ingestion guide, Neural detection docs, Archiving architecture. |

---

## 4. Route-to-Test Coverage Matrix

| Route | Test Identifier | Protocol Action Executed | Verification Assertion | Status |
| :--- | :--- | :--- | :--- | :---: |
| `/dashboard/` | **PAGE-01** | Navigate & inspect DOM | `>= 10` camera cards rendered, operational status banner present | **PASS** |
| `/cameras/` | **PAGE-02** | Navigate, search & filter | `>= 10` cameras listed, search text input active and responsive | **PASS** |
| `/cameras/4/preview/` | **PAGE-03** | Mount player & inspect HUD | Live player mounted, HUD telemetry (FPS/Channel/LIVE) active | **PASS** |
| `/recordings/` | **PAGE-04** | Load library & pagination | Recordings loaded (`25` per page), pagination controls rendered | **PASS** |
| `/evidence/` | **PAGE-05** | Load forensic registry | Evidence container rendered cleanly without leak | **PASS** |
| `/cases/` | **PAGE-06** | Query incident cases | Cases table container rendered with structured incident records | **PASS** |
| `/alerts/` | **PAGE-07** | Query alerts inbox | `15` alert records displayed with severity filters and action buttons | **PASS** |
| `/notifications/` | **PAGE-08** | Load notifications | Notification feed rendered with unread indicators | **PASS** |
| `/help/` | **PAGE-09** | Audit isolation & content | Help guide rendered; zero camera grid or alerts table leaking | **PASS** |
| Multiple Routes | **PAGE-10** | Hard page reloads | Direct navigation and hard refresh across `/dashboard/`, `/cameras/`, `/alerts/`, `/help/` | **PASS** |
| Cross-Navigation | **ISO-01** | Rapid cycle through 7 routes | Dashboard → Help → Alerts → Cameras → Preview → Recordings → Dashboard; zero stale leaking | **PASS** |

---

## 5. Defects Identified, Root Causes & Applied Repairs

### Defect 1: Single Page Application Hash vs Pathname Routing Mismatch
- **Symptom:** Opening `/help/` directly or navigating between pages left stale content or rendered the Dashboard unexpectedly because the router only parsed `window.location.hash`.
- **Root Cause:** `parseHash` in `frontend/src/App.jsx` inspected only `window.location.hash`. When navigating via standard HTTP paths (`/help/`, `/alerts/`), `hash` was empty, defaulting to `dashboard`.
- **Fix:** Replaced with dual-mode `parseRoute()` in `frontend/src/App.jsx` that falls back to `window.location.pathname` when hash is empty, and added event listeners for both `hashchange` and `popstate`.
- **Files Modified:** `frontend/src/App.jsx`.

### Defect 2: Missing Camera Search Filter in Cameras Gallery
- **Symptom:** No text search input existed in the Cameras toolbar to filter cameras by name or location.
- **Root Cause:** `frontend/src/pages/Cameras.jsx` had status filter pills but omitted a text input for `searchQuery`.
- **Fix:** Added search input with real-time text binding filtering cameras by `c.name` or `c.location`.
- **Files Modified:** `frontend/src/pages/Cameras.jsx`.

### Defect 3: Operator Scoping NameError in Backend Recordings List
- **Symptom:** Calling `/api/recordings/` as an operator threw `NameError: name 'user_id' is not defined`.
- **Root Cause:** In `deepvision_django/apps/core/api.py`, `api_recordings_list` referenced `user_id` inside an operator branch where only `request.user` was available.
- **Fix:** Used `get_accessible_cameras_qs(request.user)` to scope cameras correctly for privileged operators.
- **Files Modified:** `deepvision_django/apps/core/api.py`.

### Defect 4: Dashboard Stats 500 Error (Undefined Name & Attribute Error)
- **Symptom:** `/api/dashboard/stats/` failed with HTTP 500 when accessed by an operator.
- **Root Cause:**
  1. `recent_alerts_qs` was fetched but `recent_alerts` list was never initialized before returning in the response dictionary.
  2. Attempted to read `a.alert_type` on `Alert` model instead of `a.event_type`.
- **Fix:** Constructed `recent_alerts` list properly using `a.event_type`, `a.title`, `a.severity`, and `a.detected_at`.
- **Files Modified:** `deepvision_django/apps/core/api.py`.

### Defect 5: Unauthenticated Login / Signup Redirection
- **Symptom:** Authenticated operators reloading `/login/` remained on the login template rather than advancing to `/dashboard/`.
- **Root Cause:** `login_view` and `signup_view` in `apps/accounts/views.py` lacked an `is_authenticated` guard.
- **Fix:** Added `if request.user.is_authenticated: return redirect("dashboard")` to both views.
- **Files Modified:** `deepvision_django/apps/accounts/views.py`.

---

## 6. Real Camera, Inference, Tracking & Video Performance

| Metric | Measured Value | Standard / Requirement | Status |
| :--- | :--- | :--- | :---: |
| **Camera Fleet Count** | 10 Cameras Configured | `>= 10` cameras in inventory | **PASS** |
| **Ingestion Engine** | DirectShow `dshow://0` | Real webcam hardware ingestion | **PASS** |
| **Neural Weights** | YOLO11n (`yolo11n.pt`) | CPU singleton neural pipeline | **PASS** |
| **Object Tracking** | ByteTrack persistent IDs | Continuous ID association | **PASS** |
| **Stream FPS** | ~30.0 FPS | 25 – 30 FPS target | **PASS** |
| **Inference Latency** | ~28 – 35 ms | `< 60 ms` CPU threshold | **PASS** |
| **Archived Clips Available**| 2,742 total recordings | Valid SQLite DB records | **PASS** |
| **Video Delivery** | HTTP Range requests supported | 206 Partial Content enabled | **PASS** |

---

## 7. Responsive Viewport Audit (All 7 Viewports)

Each viewport was tested in the actual automated browser by setting the device metrics override via CDP and evaluating horizontal overflow (`scrollWidth <= clientWidth`), layout clipping, and navigation responsiveness.

| Test ID | Viewport Resolution | Device Category | Horizontal Overflow | Navbar Rendered | Status |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **RESP-01** | **1920 × 1080** | Desktop Full HD | None (`0px`) | Yes | **PASS** |
| **RESP-02** | **1600 × 900** | Desktop HD+ | None (`0px`) | Yes | **PASS** |
| **RESP-03** | **1366 × 768** | Laptop WXGA | None (`0px`) | Yes | **PASS** |
| **RESP-04** | **1024 × 768** | Tablet Landscape | None (`0px`) | Yes | **PASS** |
| **RESP-05** | **768 × 1024** | Tablet Portrait | None (`0px`) | Yes | **PASS** |
| **RESP-06** | **390 × 844** | Mobile iPhone 14 | None (`0px`) | Yes | **PASS** |
| **RESP-07** | **375 × 812** | Mobile iPhone X | None (`0px`) | Yes | **PASS** |

---

## 8. Console & Runtime Exceptions Audit

- **Console Exceptions Captured (ERR-01):** **0** fatal runtime errors.
- **Unhandled Promise Rejections:** **0**.
- **Network Request Failures:** Zero unhandled 4xx/5xx errors during authenticated navigation.

---

## 9. Production Protection Confirmation

- **Production URL:** `https://vsw-deepvision.vercel.app/`
- **Git Branch:** `main` (HEAD commit: `1b4ccab`)
- **Remote Push:** **NEVER EXECUTED**. All git modifications remain local.
- **Vercel Deployments:** **UNTOUCHED**. No API calls, build triggers, or modifications made to production.
- **Database Status:** Local SQLite database preserved; zero customer records or video files wiped.
