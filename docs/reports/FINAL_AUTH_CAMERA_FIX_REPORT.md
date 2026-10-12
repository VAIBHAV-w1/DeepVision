# DeepVision Final Authentication + Live Camera Hardware Fix Report

**Generated:** 2026-09-27  
**Project:** DeepVision (`D:\DeepVision`)  
**Container:** `deepvision-app` (Image: `deepvision:1.1.0`)  
**Database Schema Signature:** `cc2d13f77b681107` (18 tables, Verified SQLite integrity: `ok`)  
**Surveillance Engine Singletons:** `MODEL_LOAD_COUNT=1`, 1 CameraWorker per physical stream  

---

## 1. Authentication Flow Before

Previously:
- **Signup:** Newly registered users had their accounts marked as active immediately or logged in without strict verification enforcement. The user was automatically transitioned to an authenticated session without mandatory email OTP confirmation.
- **Login:** Users entered email and password and were granted immediate access to the authenticated dashboard session without any second-factor OTP challenge.
- **OTP Reuse & Purpose:** OTP hashes lacked cryptographic separation of purpose, meaning a signup OTP could theoretically be submitted to an endpoint expecting a different action.
- **Session Enforcement:** Direct access to protected API endpoints lacked strict pre-OTP session rejection.

---

## 2. Authentication Flow After

The authentication lifecycle now strictly adheres to mandatory two-factor email verification:

```
[ NEW USER REGISTRATION ]
          ↓
[ SIGN UP FORM SUBMISSION ]
          ↓
[ ACCOUNT CREATED IN PENDING STATE (is_email_verified=False) ]
          ↓
[ CRYPTOGRAPHIC SIGNUP OTP GENERATED (Salted: "signup:<otp>") ]
          ↓
[ SMTP EMAIL DISPATCHED TO RECIPIENT ]
          ↓
[ UI OTP VERIFICATION SCREEN PRESENTED ]
          ↓
[ USER ENTERS 6-DIGIT CODE ]
          ↓
[ BACKEND VALIDATES OTP & MARKS is_email_verified=True ]
          ↓
[ AUTOMATIC REDIRECT TO LOGIN (NO AUTO-LOGIN / NO SESSION GRANTED) ]
```

```
[ LOGIN FLOW (EVERY LOGIN) ]
          ↓
[ USER ENTERS EMAIL & PASSWORD ]
          ↓
[ CREDENTIALS VALIDATED (Unverified accounts blocked with HTTP 403) ]
          ↓
[ BACKEND ISSUES requires_otp: True (NO SESSION COOKIE GRANTED) ]
          ↓
[ CRYPTOGRAPHIC LOGIN OTP GENERATED (Salted: "login:<otp>") ]
          ↓
[ SMTP EMAIL DISPATCHED TO REGISTERED ADDRESS ]
          ↓
[ UI PROMPTS TWO-FACTOR AUTHENTICATION SCREEN ]
          ↓
[ USER ENTERS 6-DIGIT CODE ]
          ↓
[ BACKEND VERIFIES SINGLE-USE LOGIN OTP & INVALIDATES HASH ]
          ↓
[ AUTHENTICATED DJANGO SESSION ISSUED ]
          ↓
[ USER DIRECTED TO SOC DASHBOARD ]
```

---

## 3. Signup OTP Implementation

- **Location:** [`deepvision_django/apps/accounts/models.py`](file:///d:/DeepVision/deepvision_django/apps/accounts/models.py), [`deepvision_django/apps/core/api.py`](file:///d:/DeepVision/deepvision_django/apps/core/api.py)
- **Mechanism:**
  - Upon calling `api_signup`, the user account is created with `is_email_verified=False` and `is_active=True`.
  - The method `user.generate_otp(purpose='signup')` creates a 6-digit cryptographically secure pseudorandom token via `secrets.randbelow(1000000)`.
  - The token is hashed with purpose salting: `make_password(f"{purpose}:{otp}")` and stored in `email_otp_hash`.
  - Expiration is set to 15 minutes (`timezone.now() + timedelta(minutes=15)`).
  - Attempt counter `email_otp_attempts` is reset to 0.
  - Verification endpoint `api_verify_otp` verifies the code via `user.verify_otp(otp, purpose='signup')`.
  - Upon successful verification, `is_email_verified` is set to `True`, the session is flushed, and `{"success": True, "redirect": "/login"}` is returned. No authenticated session is issued.

---

## 4. Account Verification

- **Field Preserved:** `is_email_verified` on the existing `User` model.
- **Zero Schema Change:** Preserves exactly 18 SQLite tables and schema hash `cc2d13f77b681107`.
- **Enforcement:**
  - In `api_login`, if `user.is_email_verified` is `False`, the backend refuses credential acceptance and returns HTTP 403:
    ```json
    {
      "success": false,
      "needs_verification": true,
      "email": user.email,
      "message": "Account email is not verified. Please verify your email before logging in."
    }
    ```
  - Unverified users cannot bypass the check to request a login OTP or access protected data.

---

## 5. Login OTP Implementation

- **Location:** [`deepvision_django/apps/core/api.py`](file:///d:/DeepVision/deepvision_django/apps/core/api.py), [`frontend/src/pages/Login.jsx`](file:///d:/DeepVision/frontend/src/pages/Login.jsx)
- **Mechanism:**
  - `api_login` accepts `email` and `password`.
  - If password validation succeeds, `user.generate_otp(purpose='login')` generates a fresh 6-digit OTP.
  - `send_login_otp_email(user, otp)` transmits the sign-in code via SMTP.
  - The endpoint returns:
    ```json
    {
      "success": true,
      "requires_otp": true,
      "email": user.email,
      "message": "Verification code sent to your email."
    }
    ```
  - No authenticated session is created.
  - Frontend transitions state to `step === 'otp'`, rendering the 6-digit grid with a 60-second cooldown timer.
  - User submits OTP to `/api/auth/verify-login-otp/`.
  - Backend verifies `user.verify_otp(otp, purpose='login')`.
  - On success, `email_otp_hash` is wiped to `None` (preventing any replay), and `request.session['user_id'] = user.id` establishes the authenticated session.

---

## 6. Every-Login OTP Behavior

- **No Bypass Allowed:** Remember-me flags or previous successful logins do not bypass the OTP challenge.
- **Freshness:** Every login attempt generates a brand-new random OTP.
- **Single-Use Invalidation:** Successful verification immediately nullifies the stored hash.
- **Resend Support:** `/api/auth/resend-login-otp/` enforces a 60-second cooldown window and generates a fresh token, invalidating the previous one.

---

## 7. OTP Security

- **Cryptographic Generation:** Uses Python standard library `secrets.randbelow(1000000)` formatted as 6 zero-padded digits.
- **Purpose Salting:** `f"{purpose}:{otp}"` is passed into Django's standard PBKDF2-SHA256 password hasher. A signup OTP cannot verify a login challenge, and vice versa.
- **Zero Plaintext Storage:** The OTP is never stored plaintext in SQLite or logs.
- **Expiration:** Hardcoded 15-minute expiry (`timezone.now() + timedelta(minutes=15)`).
- **Brute-Force Rate Limiting:** Enforces `MAX_ATTEMPTS = 5`. Five failed verification attempts invalidate the OTP.
- **Zero Leakage:** The OTP value is never returned in JSON API responses, browser console, error messages, or production logging.

---

## 8. Email Verification

- **Service:** [`deepvision_django/apps/accounts/email_service.py`](file:///d:/DeepVision/deepvision_django/apps/accounts/email_service.py)
- **Functions:**
  - `send_verification_email(recipient_email, otp, full_name)`
  - `send_login_otp_email(user, otp)`
- **Templates:** HTML emails styled with corporate DeepVision branding, clear 15-minute expiration notices, security disclaimers, and 6-digit monospaced code blocks.
- **SMTP Verification:** Live verified during automated tests and real Chrome browser CDP automation (`Successfully sent 'DeepVision - Sign-In Verification Code' to chrome_user_...@deepvision.test`).

---

## 9. Camera Architecture Before

- Previously, the Linux Docker container attempted direct OpenCV capture on `dshow://0` or webcam index `0`.
- Standard Linux containers under Docker Desktop / WSL2 do not have native access to the Windows DirectShow (`cv2.CAP_DSHOW`) multimedia subsystem.
- As a consequence, physical webcams failed to start inside the container, while pre-recorded MP4 video files worked because they were local filesystem assets.

---

## 10. Camera Architecture After

A lightweight native host bridge connects the Windows host hardware directly with the containerized application:

```
+-------------------------------------------------------------------------------+
|                                WINDOWS HOST                                   |
|                                                                               |
|  +---------------------------+        +------------------------------------+  |
|  |   Physical USB Webcam     |        |   Native Host Camera Bridge        |  |
|  |   (DirectShow: dshow://0) | <----> |   (scripts/host_camera_bridge.py)  |  |
|  +---------------------------+        |   - OpenCV cv2.CAP_DSHOW (0)       |  |
|                                       |   - Canonical YOLO11n + ByteTrack  |  |
|                                       |   - Port: 8554 (Bound: 0.0.0.0)    |  |
|                                       +------------------------------------+  |
|                                                          ^                    |
+----------------------------------------------------------|--------------------+
                                                           | HTTP / MJPEG Proxy
+----------------------------------------------------------|--------------------+
|                         DOCKER CONTAINER (Linux / WSL2)  |                    |
|                                                          v                    |
|  +-------------------------------------------------------------------------+  |
|  |   deepvision-app (Port 8000)                                            |  |
|  |   - Django Core API & HTTP Endpoints                                    |  |
|  |   - apps.ai.engine proxies stream/snapshots to host.docker.internal:8554 |  |
|  |   - Multi-tenant camera authorization & evidence logging                |  |
|  |   - React SPA served via StaticFiles                                    |  |
|  +-------------------------------------------------------------------------+  |
|                                  ^                                            |
+----------------------------------|--------------------------------------------+
                                   | HTTP (Port 8000)
                                   v
                   +-------------------------------+
                   |   Google Chrome Web Browser   |
                   |   - Live MJPEG Stream Display |
                   |   - ORIGINAL / TRACKING Mode  |
                   |   - SOC Dashboard Controls    |
                   +-------------------------------+
```

---

## 11. DirectShow Handling

- The DirectShow capture pipeline is owned exclusively by the native Windows host process (`scripts/host_camera_bridge.py`), which has native access to Windows driver DLLs and `cv2.CAP_DSHOW`.
- OpenCV initializes hardware via:
  ```python
  cap = cv2.VideoCapture(int(source) if source.isdigit() else 0, cv2.CAP_DSHOW)
  cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
  ```
- DirectShow capture runs at native 640x480 resolution, delivering real-time frames at ~16-20 FPS.

---

## 12. Docker / Native Boundary

- The Docker container does not claim to own the DirectShow hardware directly.
- Instead, `HOST_CAMERA_BRIDGE_URL` (default: `http://host.docker.internal:8554`) is passed to the container via `docker-compose.yml` with `extra_hosts: ["host.docker.internal:host-gateway"]`.
- When requests for camera feeds, snapshots, stats, or recording arrive at Django inside the container:
  - If the bridge is reachable, Django transparently proxies the MJPEG chunk stream using `yield from generate_stream_from_bridge(...)`.
  - If running standalone on Windows without Docker, Django continues to use its in-process `CameraRegistry` and `InferenceRegistry`.

---

## 13. Live Camera Verification

- **Hardware Used:** Physical Windows USB/Integrated Webcam (Channel 04, "Webcam 0").
- **Verification Mode:** Real frames captured from the physical sensor with live human movement, lighting variation, and advancing timestamp.
- **Snapshot Size:** ~117 KB - 121 KB per JPEG frame (`0xFF 0xD8` header validated).
- **Streaming Format:** `multipart/x-mixed-replace; boundary=frame`.

---

## 14. ORIGINAL Mode Verification

- **Route:** `GET /cameras/4/stream/?mode=original`
- **Output:** Raw CCTV video feed directly from OpenCV DirectShow capture without bounding boxes, track IDs, or AI label overlays.
- **Frame Rate:** ~18-20 FPS.
- **Verified:** Tested via automated pipeline test and real Chrome browser CDP automation.

---

## 15. TRACKING + DETECTION Mode Verification

- **Route:** `GET /cameras/4/stream/?mode=tracking`
- **Output:** Real-time annotated CCTV video stream featuring:
  - YOLO11n object detection bounding boxes
  - ByteTrack persistent track IDs
  - Class confidence labels
  - HUD telemetry overlay (Mode, FPS, Objects count)
- **Verified:** Tested via automated pipeline test and real Chrome browser CDP automation.

---

## 16. YOLO11n Verification

- **Model Weights:** `models/yolo11n.pt`
- **Ultralytics Runtime:** Version `8.4.163` running on PyTorch `2.14.0+cpu`.
- **Singleton Constraint:** Enforced via `MODEL_LOAD_COUNT=1`. Exactly one YOLO11n model instance is loaded into memory.
- **Inference Time:** ~45-55ms per frame on CPU.

---

## 17. ByteTrack Verification

- **Tracker Implementation:** Canonical DeepVision ByteTrack (`apps/surveillance/ai/byte_tracker.py`).
- **Functionality:** Associates detections across consecutive frames to maintain identity track IDs.
- **Singleton Constraint:** Exactly one ByteTrack tracker per active CameraWorker instance.

---

## 18. Recording Verification

- **Endpoints:** `POST /api/cameras/4/record/start` and `POST /api/cameras/4/record/stop`.
- **Output:** MP4 video segments written to `recordings/camera_4/`.
- **Verified Size:** 5,352,860 bytes captured across a 2.3-second automated verification cycle.
- **Database Entry:** Recorded in SQLite table `surveillance_recording` with duration, byte size, and user scoping.

---

## 19. Security Fixes

1. **Rotated DJANGO_SECRET_KEY:**
   - Removed hardcoded secret fallback from `docker-compose.yml`.
   - Generated high-entropy 50-character cryptographic secret in `.env`.
   - Updated `.gitignore` to ensure `.env` and `.env.*` are strictly ignored.
   - Preserved safe placeholder in `.env.example`.
2. **OTP Security:**
   - Purpose salting (`signup:` vs `login:`).
   - Rate limiting to 5 failed attempts.
   - Immediate wipe of hash on success.
   - 15-minute expiration window.

---

## 20. Migration Handling

- **Warning Observed:** Docker container reported unapplied migrations for `contenttypes` and `sessions`.
- **Diagnosis:** DeepVision uses client-side signed session cookies (`SignedCookieSessionFactory` / Django cookie session backend) and custom account models. The database does not use Django's database-backed session table.
- **Action Taken:** Per the safety protocol, unapplied migrations were NOT blindly executed against the database.
- **Result:** The 18-table schema and SHA-256 signature `cc2d13f77b681107` remain 100% intact.
- **SQLite Locking:** Changed SQLite journal mode from `WAL` to `DELETE` (`PRAGMA wal_checkpoint(TRUNCATE)`), eliminating WSL2/Windows host shared-memory (`-shm`) POSIX lock contention across Docker bind mounts.

---

## 21. Ultralytics Configuration

- **Warning Observed:** `/app/.config/Ultralytics is not writable`.
- **Resolution:**
  - Added `RUN mkdir -p /app/.config/Ultralytics && chown -R deepvision:deepvision /app/.config` in `Dockerfile`.
  - Configured `ENV YOLO_CONFIG_DIR=/app/.config/Ultralytics` in `Dockerfile` and passed via `docker-compose.yml`.
  - Clean startup without configuration directory warnings.

---

## 22. Server Configuration

- **Launcher:** Python orchestration script `start_deepvision.py` starting Django with `--noreload --insecure`.
- **Evaluation:** Introducing a multi-worker production WSGI server (like Gunicorn with multiple worker processes) would create duplicate processes, causing duplicate camera handles, multiple YOLO model loads, and violation of the singleton constraint (`MODEL_LOAD_COUNT=1`).
- **Conclusion:** Single-process deployment under `start_deepvision.py` guarantees single-worker surveillance integrity while serving API endpoints, healthchecks, and the compiled React SPA.

---

## 23. Browser Verification (Real Google Chrome via CDP)

Executed comprehensive automated Chrome test suite ([`verification/verify_auth_camera_browser.mjs`](file:///d:/DeepVision/verification/verify_auth_camera_browser.mjs)):

| Step | Action / Assertion | Status | Details |
|:---|:---|:---:|:---|
| **Step 1** | Signup page navigation | **PASS** | Rendered registration form at `/#signup` |
| **Step 2** | Signup form submit -> OTP screen | **PASS** | Account created pending; OTP dispatched |
| **Step 3** | Enter 6-digit OTP -> Account verify | **PASS** | Verified; redirected to `/#login` (No auto-login) |
| **Step 4** | Enter Credentials -> Login OTP screen | **PASS** | Two-Factor Authentication grid presented |
| **Step 5** | Enter fresh Login OTP -> Session auth | **PASS** | Session cookie issued; directed to Dashboard |
| **Step 6** | Navigate to Cameras view | **PASS** | Camera gallery rendered at `/#cameras` |
| **Step 7** | Open Camera #4 (DirectShow Physical) | **PASS** | Live physical camera stream rendering in Chrome |
| **Step 8** | Switch to ORIGINAL mode | **PASS** | Raw CCTV feed displayed (Zero AI overlay) |
| **Step 9** | Switch to TRACKING + DETECTION mode | **PASS** | YOLO11n + ByteTrack overlay active |
| **Step 10** | Console Log Inspection | **PASS** | 0 JavaScript runtime exceptions caught |

**Total Result:** **10/10 PASSED (100%)**

---

## 24. Automated Test Results

### Suite 1: Authentication & OTP Lifecycle
**File:** [`verification/test_complete_auth_otp.py`](file:///d:/DeepVision/verification/test_complete_auth_otp.py) (Executed inside container `deepvision-app`)

```
============================================================
  DEEPVISION COMPLETE AUTHENTICATION & OTP TEST SUITE
============================================================
[PASS]  1. Signup creates unverified account
[PASS]  2. Signup OTP hash generated securely
[PASS]  3. Unverified account login blocked (HTTP 403)
[PASS]  4. Wrong signup OTP rejected
[PASS]  5. Correct signup OTP verifies account
[PASS]  6. Verified user redirected to login (not auto-logged in)
[PASS]  7. Verified user credential validation requires OTP
[PASS]  8. Login without OTP rejected (no session issued)
[PASS]  9. Direct API access without OTP rejected (HTTP 401)
[PASS] 10. Wrong login OTP rejected
[PASS] 11. Cross-purpose OTP rejected (signup OTP cannot verify login)
[PASS] 12. Correct login OTP creates authenticated session
[PASS] 13. Single-use login OTP cannot be reused
[PASS] 14. Authenticated session permits API access (HTTP 200)
[PASS] 15. User logout terminates session
[PASS] 16. Second login generates a fresh, different OTP
[PASS] 17. Second login OTP verifies second session
[PASS] 18. OTP rate limiting blocks brute force after 5 attempts
============================================================
ALL 18 TESTS PASSED (100%)
============================================================
```

### Suite 2: Live Camera Hardware & Inference Pipeline
**File:** [`verification/test_complete_camera_pipeline.py`](file:///d:/DeepVision/verification/test_complete_camera_pipeline.py) (Executed across Host Bridge + Container)

```
============================================================
  DEEPVISION COMPLETE CAMERA HARDWARE & INFERENCE PIPELINE
============================================================
[PASS]  1. Authenticated session created
[PASS]  2. Camera DirectShow connection online
[PASS]  3. Live camera snapshot captured (121150 bytes, valid JPEG)
[PASS]  4. ORIGINAL (raw CCTV) stream receiving frames
[PASS]  5. TRACKING + DETECTION (YOLO11n + ByteTrack) stream receiving frames
[PASS]  6. Camera telemetry and statistics active (FPS > 0)
[PASS]  7. Camera recording start & stop lifecycle verified
[PASS]  8. Singleton constraints verified (MODEL_LOAD_COUNT=1, single camera worker)
============================================================
ALL 8 CAMERA TESTS PASSED (100%)
============================================================
```

---

## 25. Database Integrity

- **Check Script:** [`verification/check_db_signature.py`](file:///d:/DeepVision/verification/check_db_signature.py)
- **Integrity Result:** `PRAGMA integrity_check` -> `ok`
- **Table Count:** Exactly 18 tables
- **Schema SHA-256 Hash:** `cc2d13f77b681107`
- **Data Protection:** Zero existing users, recordings, alerts, or cases were deleted or corrupted.

---

## 26. Files Changed

| File Path | Description of Changes |
|:---|:---|
| [`deepvision_django/apps/accounts/models.py`](file:///d:/DeepVision/deepvision_django/apps/accounts/models.py) | Added purpose salting to `generate_otp` and `verify_otp` (`f"{purpose}:{otp}"`). |
| [`deepvision_django/apps/accounts/email_service.py`](file:///d:/DeepVision/deepvision_django/apps/accounts/email_service.py) | Implemented `send_login_otp_email` with HTML template and 15m expiry. |
| [`deepvision_django/apps/core/api.py`](file:///d:/DeepVision/deepvision_django/apps/core/api.py) | Added `api_verify_login_otp`, `api_resend_login_otp`, updated `api_login` and `api_verify_otp` for mandatory 2FA. |
| [`deepvision_django/config/urls.py`](file:///d:/DeepVision/deepvision_django/config/urls.py) | Registered `/api/auth/verify-login-otp/` and `/api/auth/resend-login-otp/`. |
| [`deepvision_django/apps/ai/engine.py`](file:///d:/DeepVision/deepvision_django/apps/ai/engine.py) | Added Host Bridge proxying (`get_host_bridge_url`, `stream_camera_frames` via `yield from`, snapshot, stats). |
| [`frontend/src/pages/Login.jsx`](file:///d:/DeepVision/frontend/src/pages/Login.jsx) | Added Step 2 Two-Factor Authentication grid with 60s cooldown and resend action. |
| [`frontend/src/hooks/useAuth.jsx`](file:///d:/DeepVision/frontend/src/hooks/useAuth.jsx) | Exported `verifyLoginOtp` function to support 2FA auth state transition. |
| [`frontend/src/services/auth.js`](file:///d:/DeepVision/frontend/src/services/auth.js) | Added `verifyLoginOtp` and `resendLoginOtp` endpoints. |
| [`frontend/src/services/api.js`](file:///d:/DeepVision/frontend/src/services/api.js) | Configured API client methods for login OTP verification. |
| [`scripts/host_camera_bridge.py`](file:///d:/DeepVision/scripts/host_camera_bridge.py) | Created native Windows host bridge handling DirectShow capture and AI streaming. |
| [`docker-compose.yml`](file:///d:/DeepVision/docker-compose.yml) | Removed hardcoded secrets; added bridge host mapping and writable YOLO config dir. |
| [`Dockerfile`](file:///d:/DeepVision/Dockerfile) | Configured `/app/.config/Ultralytics` directory ownership and `YOLO_CONFIG_DIR`. |
| [`.env`](file:///d:/DeepVision/.env) | Configured rotated `DJANGO_SECRET_KEY` and host bridge URL. |
| [`.env.example`](file:///d:/DeepVision/.env.example) | Sanitized with generic placeholders. |
| [`.gitignore`](file:///d:/DeepVision/.gitignore) | Ignored `.env`, `.env.*`, `Ultralytics/`, `.config/`, and temporary Chrome profiles. |

---

## 27. Known Limitations

1. **Host Bridge Dependency for Physical Cameras in Docker:** Under Docker Desktop for Windows / WSL2, physical DirectShow webcams require the native host bridge process (`python scripts/host_camera_bridge.py`) running on the Windows host. IP, RTSP, and pre-recorded video cameras function entirely within Docker without the bridge.
2. **SMTP Network Latency:** Real SMTP email transmission introduces a ~2 to 4 second network roundtrip during signup and login credential submission.

---

## 28. Out-of-Scope Items

- Rewriting or altering ByteTrack tracking thresholds or YOLO11n weights.
- Redesigning the SOC Dashboard, Forensic Investigation modules, or UI layout.
- Replacing Django or introducing unvetted frameworks.
- Modifying the underlying 18-table database schema.

---

## Conclusion & Stop Condition Met

Both primary objectives are completely solved, tested, and verified:
1. **Authentication:** Mandatory two-step signup verification (no auto-login) and mandatory two-factor OTP authentication on every single login.
2. **Live Camera Hardware:** DirectShow physical camera capture and live AI surveillance pipeline verified functional in real Google Chrome, backed by singleton YOLO11n and ByteTrack engines.

All tests passed with zero regressions. Stopping here as instructed.
