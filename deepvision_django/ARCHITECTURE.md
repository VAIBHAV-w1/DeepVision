# DeepVision Architecture & System Blueprint
**Phase 10 Production Hardening & Architectural Documentation**

---

## 1. Django Application Role
- **Host / Port:** `127.0.0.1:8000` (User-facing web layer).
- **Responsibilities:**
  - Serves all interactive user-facing HTML pages (Dashboard, Cameras, Recordings, Evidence, Alerts, Cases, Notifications, Help, Profile).
  - Handles user authentication, registration, session management, CSRF validation, and password resets.
  - Exposes secured REST APIs (Notifications polling, Assistant chat, Camera telemetry, Health/Readiness).
  - Proxies live MJPEG video streams and single-frame snapshots from the canonical surveillance engine to authenticated clients.
  - Serves forensic evidence files and MP4 recordings supporting HTTP 206 Partial Content (byte-range seeking).
- **Strict Limitation:** Django holds **ZERO** physical hardware handles, does **NOT** instantiate OpenCV `VideoCapture`, and does **NOT** load the YOLO11n neural network weights.

---

## 2. Flask Surveillance Engine Role
- **Host / Port:** `127.0.0.1:5000` (Internal headless daemon managed by `supervisor.py`).
- **Responsibilities:**
  - Canonical ownership of physical camera hardware (`dshow://0` DirectShow capture).
  - Real-time video frame acquisition via single-instance `CameraWorker`.
  - Computer vision inference loop executing YOLO11n object detection and ByteTrack multi-object tracking via single-instance `InferenceWorker`.
  - Motion analysis, anomaly detection, rule matching, and automated incident case generation.
  - Forensic evidence creation (snapshot images and clip recordings).
  - Exposing secured loopback endpoints for MJPEG streaming, snapshots, telemetry, health, and recording control.
- **Headless Mode:** In Phase 9 & 10, all 83 user-facing Flask UI routes are retired; browser requests to port 5000 are cleanly redirected (HTTP 302) to Django on port 8000.

---

## 3. Camera Ownership
- **Physical VideoCapture Handles:** Exactly 1 (`cv2.VideoCapture(0, cv2.CAP_DSHOW)`).
- **Physical Camera Registry:** `app.camera.registry.CameraRegistry` (Flask).
- **Lifecycle:**
  - CameraWorker runs in a background thread in Flask.
  - Django acts as a consumer proxy over HTTP loopback streaming (`/cameras/<id>/stream?mode=...`).
  - Django physical camera handle count is strictly **0**.

---

## 4. AI Ownership
- **Model:** Ultralytics YOLO11n (`models/yolo11n.pt`).
- **Load Count:** Exactly 1 (`MODEL_LOAD_COUNT=1`, shared CPU weights).
- **Tracker:** ByteTrack (`bytetrack.yaml`).
- **Inference Registry:** `app.ai.inference_registry.InferenceRegistry` (Flask).
- **Lifecycle:**
  - Model weights loaded once at startup in Flask `run.py`.
  - Worker threads share the weight tensor reference via lightweight shallow copy wrapper (`create_camera_model_wrapper()`) with zero disk I/O.
  - Django has **ZERO** direct dependencies on `torch` or `ultralytics` for inference.

---

## 5. Django ↔ Flask Boundary
- **Centralized Adapter:** `deepvision_django/apps/ai/engine.py`.
- **Authentication:** Signed session cookies generated via `itsdangerous.URLSafeTimedSerializer` with the shared surveillance secret key, recognized natively by Flask's session authentication.
- **Internal Service Endpoints:**
  - `GET /cameras/<id>/stream?mode=<mode>` — Real-time MJPEG feed (raw or tracking).
  - `GET /cameras/<id>/snapshot` — Single JPEG frame snapshot.
  - `GET /api/cameras/<id>/stats` — Live telemetry (FPS, tracks, latency).
  - `GET /cameras/<id>/warm` — Pre-warm background workers.
  - `GET /api/system/health` — Surveillance subsystem health and CPU/memory metrics.
  - `POST /cameras/<id>/record/start` — Start physical camera recording.
  - `POST /cameras/<id>/record/stop` — Stop physical camera recording.
  - `POST /api/cameras/test-connection` — Test feed connectivity before saving.
  - `POST /api/cameras/<id>/test` — Test feed connectivity of an existing camera.

---

## 6. Database Ownership
- **Engine:** SQLite (`instance/deepvision.db`).
- **Tables Count:** Exactly 18 tables.
- **Schema Modifications:** **ZERO**. Django uses `managed = False` for legacy surveillance models (`cameras`, `recordings`, `evidence`, `alerts`, `incident_cases`, `notifications`, `devices`).
- **ORM Mappings:** Read-only access to surveillance history; status transitions (e.g. marking alerts acknowledged/resolved, notifications read) update only existing columns.
- **Session & Messages:** 100% cookie-based (`SignedCookiesError`, `CookieStorage`) requiring zero additional database tables.

---

## 7. Recordings and Evidence Ownership
- **Storage Locations:**
  - Recordings: `instance/recordings/`
  - Evidence: `instance/evidence/`
- **Creation:** Automated recording and forensic evidence clipping are executed solely by the Flask surveillance engine.
- **Serving:** Django serves recordings and evidence via `apps.core.media_service`:
  - Path traversal protection via `safe_resolve_path` and `os.path.commonpath`.
  - Full HTTP 206 Partial Content support with `Range` header parsing for HTML5 video seeking.
  - Evidence detail views verify cryptographic SHA-256 hashes against database records.

---

## 8. Authentication Architecture
- **User Source:** Existing `users` SQLite table (`apps.accounts.models.User`).
- **Password Hashes:** Werkzeug-compatible scrypt password hashing (`check_password_hash` / `generate_password_hash`).
- **Sessions:** Signed-cookie session engine (`deepvision_django_session`) with `HttpOnly`, `SameSite=Lax`, and configurable `Secure` flags.
- **Security:**
  - Open redirect prevention via `url_has_allowed_host_and_scheme`.
  - CSRF cookie protection on all state-changing POST requests.
  - Clickjacking protection via `X-Frame-Options: DENY`.
  - Content sniffing protection via `X-Content-Type-Options: nosniff`.
  - Unauthenticated API/JSON requests return HTTP 401 JSON instead of redirecting to HTML login pages.

---

## 9. Camera Modes
User-facing camera modes are strictly limited to **two**:
1. **ORIGINAL:** Raw CCTV feed without detection or tracking overlays (`mode=raw`).
2. **TRACKING + DETECTION:** YOLO11n bounding boxes + ByteTrack trajectory IDs (`mode=tracking`, Default).

---

## 10. Legacy Flask UI Retirement Mechanism
- **Configuration Toggle:** `ENABLE_LEGACY_FLASK_UI` in `app/__init__.py`.
  - Default: `False` (Headless mode).
  - Only `main_bp` is registered for surveillance endpoints.
  - Global `redirect_legacy_ui` hook returns HTTP 302 redirects to `http://127.0.0.1:8000/<path>` for all browser navigation to legacy routes (`/login`, `/signup`, `/dashboard`, `/cameras`, `/recordings`, `/evidence`, `/alerts`, `/cases`, `/notifications`).
  - Reversibility: Setting `ENABLE_LEGACY_FLASK_UI=true` instantly restores all 22 Flask UI blueprints without modifying code.

---

## 11. Startup Order
1. **Flask Surveillance Daemon:**
   `python supervisor.py` (spawns `run.py` on port 5000, warms YOLO11n weights).
2. **Django Web Application:**
   `python manage.py runserver 127.0.0.1:8000 --noreload`.

---

## 12. Recovery & Degradation Behavior
- If Flask is unavailable:
  - Django health check reports status `degraded`.
  - Camera preview UI displays a clean `Surveillance Stream Unavailable` placeholder.
  - Django does **NOT** attempt to fall back to opening local webcams or loading YOLO weights.
  - Background polling automatically reconnects the stream once Flask recovers.
- If Django restarts:
  - Flask surveillance engine continues capturing, tracking, and recording without interruption.

---

## 13. Rollback Strategy
- To roll back the legacy UI retirement: set environment variable `ENABLE_LEGACY_FLASK_UI=true` and restart Flask.
- To roll back Django configuration changes: revert `config/settings.py` and `config/urls.py` via git.
- Database is unmodified and backward-compatible with legacy Flask.

---

## 14. Known Limitations
- Single active physical camera capture (`dshow://0`). Multi-camera support requires adding secondary video capture indexes or RTSP sources.
- Windows DirectShow initialization latency (1-2 seconds on cold start).

---

## 15. Absolute Invariants — Do NOT Change Without Approval
1. Do NOT delete Flask.
2. Do NOT delete or modify `app/camera/*`, `app/ai/*`, `models/yolo11n.pt`, `bytetrack.yaml`, or `supervisor.py`.
3. Do NOT open physical camera handles or load YOLO in Django.
4. Do NOT execute `makemigrations` or modify the 18 existing database tables.
5. Do NOT add WebSockets, SSE, or Django Channels.
6. Do NOT remove the two user-facing camera modes (Original and Tracking + Detection).
