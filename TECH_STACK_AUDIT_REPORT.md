# DEEPVISION — TECH STACK AUDIT & VERIFICATION REPORT
**Evidence-Based Technology Stack Audit After Complete Flask Elimination**  
**Date:** 2026-09-26  
**Auditor:** Antigravity Autonomous Diagnostic Engine  
**Project Root:** `D:\DeepVision`  
**Execution Environment:** Python 3.14.7 AMD64 (Windows 11)

---

## 1. Executive Summary
This report establishes the complete, ground-truth technology stack of DeepVision based exclusively on active source code, AST import parsing, runtime introspection, and physical execution. 

Following the Phase 14 complete elimination of Flask, DeepVision operates strictly as a **Single-Process Django Application** on port 8000. All physical camera hardware capture, neural network inference, multi-object tracking, and forensic recording are executed directly inside native Django services. Flask, Flask-SQLAlchemy, and dual-server proxies are 100% eliminated from the active runtime.

---

## 2. Actual Architecture
DeepVision runs as a unified single-process architecture:

```
Django Web / API Server (:8000)
    │
    ├── Native Surveillance Layer (`apps.surveillance.*`)
    │     ├── CameraRegistry ──► CameraWorker (Singleton thread)
    │     │                           │
    │     │                           ▼
    │     │                   OpenCV VideoCapture (CAP_DSHOW, dshow://0)
    │     │                           │
    │     │                           ▼ (Deep copy)
    │     ├── InferenceRegistry ─► InferenceWorker (Singleton thread)
    │     │                           │
    │     │                           ▼
    │     │                   YOLO11n (PyTorch CPU singleton) + ByteTrack
    │     │                           │
    │     │                           ▼
    │     ├── Stream Generator ◄──────┴─── Spatial Anomaly / Re-ID / Behavior
    │     │         │
    │     │         ▼
    │     │   StreamingHttpResponse (multipart/x-mixed-replace; boundary=frame)
    │     │
    │     └── Recording Service ──► OpenCV VideoWriter (H.264/avc1 MP4 container)
    │
    ├── Django View / Template Layer (HTML5, Semantic Vanilla CSS, Vanilla ES6 JS)
    │
    └── SQLite Database Engine (`instance/deepvision.db`, 18 unmanaged tables)
```

---

## 3. Actual Runtime
- **Python Executable:** `D:\DeepVision\venv\Scripts\python.exe`
- **Python Version:** `3.14.7 (tags/v3.14.7:823f032, Aug 5 2026)`
- **Platform:** `Windows-11-10.0.26100-SP0 (64-bit AMD64)`
- **Virtual Environment:** `D:\DeepVision\venv` (isolated environment)
- **Base Python Prefix:** `C:\Users\vaibh\AppData\Local\Programs\Python\Python314`

---

## 4. Actual Framework Stack
- **Django:** 5.2.17
  - **ORM:** Used across all 6 active apps (`apps.accounts`, `apps.cameras`, `apps.alerts`, `apps.recordings`, `apps.evidence`, `apps.notifications`) with `managed = False` mapped directly to pre-existing SQLite tables.
  - **Views:** Standard Django function-based views with `@login_required`, `@never_cache`, and `@require_POST` decorators.
  - **URL Routing:** Django `urlpatterns` with `path()` in `config/urls.py` (58 named endpoints).
  - **Templates:** Django Template Language (DTL) loading 44 active templates from `deepvision_django/templates/`.
  - **Middleware:** Standard Django security, session, common, CSRF, and messages middleware, plus custom `apps.accounts.middleware.AuthenticationMiddleware`.
  - **Streaming:** `django.http.StreamingHttpResponse` delivering multipart MJPEG video streams.
- **Flask:** **COMPLETELY ABSENT**. 0 active imports, 0 processes, port 5000 is closed, 0 runtime dependencies.

---

## 5. Actual Backend Stack
- **Architecture:** Server-Rendered HTML Pages + Native Django JSON Endpoints.
- **API Format:** Django native `JsonResponse` returning structured JSON for client-side polling and asynchronous controls.
- **Django REST Framework (DRF):** **NOT USED**. DRF is not installed and not in `INSTALLED_APPS`.
- **FastAPI / GraphQL / WebSockets:** **NOT USED**.

---

## 6. Actual Database Stack
- **Database Engine:** SQLite 3.50.4 (embedded in Python runtime).
- **Django Engine:** `django.db.backends.sqlite3`
- **Database File:** `D:\DeepVision\instance\deepvision.db`
- **Table Count:** Exactly 18 tables.
- **Schema Signature:** `cc2d13f77b681107` (SHA256 signature verified identical across all audit steps).
- **Integrity Status:** `PRAGMA integrity_check = ok`.
- **Migrations:** Zero migrations applied during Django operation; tables are managed directly by pre-existing schema.
- **PostgreSQL / MySQL / MongoDB:** **NOT USED** (historical documentation references only).

---

## 7. Actual AI Stack
- **Inference Runtime:** PyTorch `2.13.0+cpu` (CPU forward pass execution).
- **Model Loader / Manager:** Ultralytics `8.4.117`.
- **Active Model:** YOLO11n (`models/yolo11n.pt`, 5.35 MB, 80 COCO classes).
- **Model Weights Lifecycle:** Singleton architecture (`_shared_yolo_model` loaded exactly once from disk into RAM; per-camera instances share PyTorch `nn.Module` weights via shallow copy to prevent memory bloat).
- **Inference Concurrency:** Thread-safe execution using `_inference_lock` and `torch.inference_mode()`.
- **TensorFlow / Keras:** **NOT USED**.
- **YOLOv8:** **NOT USED** (superseded by YOLO11n).

---

## 8. Actual Computer Vision Stack
- **Core Library:** OpenCV `5.0.0` (`opencv-python` package version `5.0.0.93`).
- **Array Processing:** NumPy `2.5.2` (frame slicing, HSV color space conversion, histogram calculation).
- **Hardware Capture Backend:** DirectShow (`cv2.CAP_DSHOW` on Windows).
- **Image Compression:** `cv2.imencode('.jpg', ...)` at JPEG quality 80 for low-latency live streaming.
- **Video Writing:** `cv2.VideoWriter` with Microsoft Media Foundation (`CAP_MSMF`) H.264 / `avc1` codec.
- **Re-ID Engine:** Classical appearance-based Re-ID (`apps/surveillance/ai/reid.py`) using HSV 2D color histograms and histogram correlation (`cv2.HISTCMP_CORREL`). *(Note: Deep neural metric learning Re-ID is NOT implemented).*
- **Facial Recognition / Action Recognition:** **NOT IMPLEMENTED**.

---

## 9. Actual Tracking Stack
- **Tracker:** ByteTrack multi-object tracker.
- **Implementation:** Ultralytics ByteTrack integration configured via `apps/surveillance/ai/bytetrack.yaml`.
- **Parameters:**
  - `track_high_thresh`: 0.25
  - `track_low_thresh`: 0.05
  - `new_track_thresh`: 0.35
  - `track_buffer`: 90 frames
  - `match_thresh`: 0.80
- **Acceleration:** Python package `lap` (0.5.13) provides C-accelerated Linear Assignment Problem (Hungarian algorithm) solving.

---

## 10. Actual Streaming Stack
- **Streaming Protocol:** multipart MJPEG over standard HTTP (`multipart/x-mixed-replace; boundary=frame`).
- **Django Component:** `StreamingHttpResponse` wrapping an in-memory frame generator.
- **Supported User-Facing Modes:**
  1. `ORIGINAL`: Raw camera frames without overlays.
  2. `TRACKING + DETECTION`: Annotated frames with YOLO11n detections, labels, and ByteTrack track IDs.
- **WebSockets / WebRTC / HLS / GStreamer:** **NOT USED**.
- **RTSP:** Supported as an input URL scheme parsed by `sources.py` and passed to `cv2.VideoCapture()`.

---

## 11. Actual Recording Stack
- **Service:** `apps/surveillance/recording/recording_service.py`.
- **Recording Mechanism:** Dedicated per-camera recording thread writing frames via `cv2.VideoWriter`.
- **Codec / Container:** H.264 (`avc1`) in `.mp4` container.
- **Output Directory:** `instance/recordings/camera_<id>/cam_<id>_rec_<timestamp>.mp4`.
- **Playback Protocol:** Standard HTTP 206 Partial Content range requests (`serve_file_with_ranges` in `apps/core/media_service.py`), enabling seekable inline HTML5 `<video controls>`.
- **External FFmpeg Binary:** **NOT REQUIRED / NOT USED** (OpenCV with Media Foundation encodes MP4 natively).

---

## 12. Actual Frontend Stack
- **Markup:** HTML5 with semantic tags, responsive layout shells, and ARIA attributes.
- **Styling:** Custom Vanilla CSS Design System with CSS Custom Properties (`static/css/app.css` and `static/css/components.css`).
- **Themes:** Client-side Dark / Light / System theme switching via `static/js/theme.js` using `data-theme` attribute on `<html>`.
- **JavaScript:** Pure Vanilla ES6+ (`static/js/app.js`, `static/js/camera-preview.js`, `static/js/chatbot.js`, `static/js/cameras.js`, `static/js/recordings.js`).
- **Networking:** Native `window.fetch()` API with CSRF headers.
- **UI Frameworks:** Zero React, zero Vue, zero Angular, zero jQuery, zero Tailwind, zero Vite/Webpack.
- **Tabler / Bootstrap:** Legacy static vendor files exist in `static/vendor/tabler/`, but are **NOT LINKED** in active templates.

---

## 13. Actual Authentication Stack
- **Session Architecture:** 100% Signed-Cookie based (`django.contrib.sessions.backends.signed_cookies`) using cookie `deepvision_django_session`. Zero database writes for session management.
- **User Authentication:** Custom `apps.accounts.middleware.AuthenticationMiddleware` populating `request.user` from session `user_id`.
- **Password Security:** Werkzeug `scrypt` hashing compatibility (`check_password_hash`, `generate_password_hash` via `Werkzeug 3.1.8`).
- **CSRF Defense:** `CsrfViewMiddleware` enforcing `deepvision_django_csrftoken` on all POST/PUT/DELETE requests.
- **Authorization:** Custom `@login_required` decorator guarding user-facing pages and API endpoints.

---

## 14. Actual Storage Stack
- **Database:** `instance/deepvision.db` (SQLite relational store).
- **Recordings Storage:** `instance/recordings/camera_<id>/` (Local MP4 files).
- **Evidence Storage:** `instance/evidence/camera_<id>/<YYYY-MM-DD>/` (Local forensic snapshots and clips).
- **Static Assets:** `deepvision_django/static/` (Served via Django staticfiles).
- **Model Weights:** `models/yolo11n.pt` (Local 5.35 MB PyTorch weights file).
- **Cloud Storage (AWS S3, Azure Blob, GCP):** **NOT USED** (100% local filesystem storage).

---

## 15. Actual Dependency Versions

| Component | Reported Version | Detection Mechanism |
|---|---|---|
| Python | 3.14.7 | `sys.version` |
| Django | 5.2.17 | `django.get_version()` |
| OpenCV | 5.0.0.93 | `cv2.__version__` |
| PyTorch | 2.13.0+cpu | `torch.__version__` |
| Ultralytics | 8.4.117 | `ultralytics.__version__` |
| NumPy | 2.5.2 | `numpy.__version__` |
| psutil | 7.2.2 | `psutil.__version__` |
| Werkzeug | 3.1.8 | `importlib.metadata.version('werkzeug')` |
| PyYAML | 6.0.3 | `importlib.metadata.version('pyyaml')` |
| python-dotenv | 1.2.2 | `importlib.metadata.version('python-dotenv')` |
| requests | 2.34.2 | `requests.__version__` |
| SQLite | 3.50.4 | `sqlite3.sqlite_version` |

---

## 16. Required Dependencies
The minimal set of top-level dependencies required to run DeepVision:
1. `Django` (5.2.17)
2. `opencv-python` (5.0.0.93)
3. `ultralytics` (8.4.117)
4. `torch` (2.13.0)
5. `numpy` (2.5.2)
6. `PyYAML` (6.0.3)
7. `Werkzeug` (3.1.8)
8. `python-dotenv` (1.2.2)
9. `psutil` (7.2.2)
10. `requests` (2.34.2)

---

## 17. Unused Dependencies (Installed in venv)
The following 6 packages are installed in `venv` but have **0 active imports** in `deepvision_django` and are unneeded by the native architecture:
1. `SQLAlchemy` (2.0.51) — Legacy ORM from retired Flask architecture.
2. `greenlet` (3.5.5) — Dependency of SQLAlchemy.
3. `itsdangerous` (2.2.0) — Legacy Flask session serializer.
4. `blinker` (1.9.0) — Legacy Flask signals package.
5. `click` (8.4.2) — Legacy Flask CLI parser.
6. `colorama` (0.4.6) — Dependency of click.

---

## 18. Legacy Technologies
- **Flask (v3.1):** Completely eliminated from runtime, virtualenv, and service architecture.
- **Flask-SQLAlchemy:** Completely removed.
- **Supervisor (`supervisor.py`):** Obsolete; replaced by `manage.py runserver` / `start_deepvision.py`.
- **Tabler UI (`static/vendor/tabler/`):** Legacy vendor bundle unreferenced in active Django templates.

---

## 19. Documentation Inaccuracies Audited

| Technology Claim | Occurrence Location | Reality in Codebase | Classification |
|---|---|---|---|
| **TensorFlow** | Historical README / docs | 0 imports; PyTorch is the sole deep learning framework | **DOCUMENTATION ONLY** |
| **YOLOv8** | Historical README / docs | Replaced by YOLO11n (`models/yolo11n.pt`) | **DOCUMENTATION ONLY** |
| **FastAPI** | Historical comparison docs | Never implemented; Django handles all web/API endpoints | **DOCUMENTATION ONLY** |
| **React / Vue / Vite** | System instructions / docs | Pure Vanilla ES6 JavaScript; no build steps or frameworks | **DOCUMENTATION ONLY** |
| **TailwindCSS** | System instructions / docs | 100% Vanilla CSS custom properties (`app.css`, `components.css`) | **DOCUMENTATION ONLY** |
| **PostgreSQL / MySQL** | Configuration notes | 100% SQLite (`instance/deepvision.db`) | **DOCUMENTATION ONLY** |
| **Redis / Celery** | `.gitignore` template | In-process threading handles surveillance; no broker used | **DOCUMENTATION ONLY** |
| **WebSocket / WebRTC** | Streaming docs | Streaming uses HTTP multipart MJPEG | **DOCUMENTATION ONLY** |
| **FFmpeg** | Video encoding notes | OpenCV VideoWriter handles MP4 container natively | **DOCUMENTATION ONLY** |
| **Twilio** | `.env.example` | Unused placeholder config; email OTP uses SMTP | **DOCUMENTATION ONLY** |

---

## 20. Flask Elimination Verification
- **Virtualenv Check:** `import flask` raises `ModuleNotFoundError`.
- **Process Check:** 0 Flask processes running.
- **Port 5000 Check:** Port 5000 is closed and unmapped.
- **Bridge Check:** `apps/ai/engine.py` calls native Python functions directly; zero HTTP requests to port 5000.
- **Codebase References:** Zero `:5000` or `127.0.0.1:5000` URLs in active application files.

---

## 21. Runtime Verification
- **Server Startup:** Successfully launched via `python manage.py runserver 127.0.0.1:8000 --noreload`.
- **HTTP Status:** All core pages (`/login/`, `/dashboard/`, `/cameras/`, `/recordings/`, `/evidence/`, `/alerts/`, `/cases/`, `/notifications/`) return HTTP 200.
- **MJPEG Streaming:** Both `ORIGINAL` and `TRACKING + DETECTION` stream endpoints deliver continuous valid JPEG chunks.
- **Telemetry Sync:** `/cameras/<id>/stats/` updates dynamically while streams are consumed.

---

## 22. Camera & AI Singleton Verification
Tested under active live streaming with camera feed consuming real frames:
- **Active VideoCapture instances:** Exactly 1 (`cv2.CAP_DSHOW` on hardware index 0).
- **Active CameraWorker instances:** Exactly 1 (managed by `CameraRegistry`).
- **Active InferenceWorker instances:** Exactly 1 (managed by `InferenceRegistry`).
- **YOLO11n Model Disk Loads:** Exactly 1 (`_model_load_count = 1`).
- **Inference Latency:** ~54.9 ms CPU forward pass time.
- **Active Inference Telemetry:** Real inference FPS reported; never reports IDLE while stream is active.

---

## 23. Database Verification
- **Table Count:** Exactly 18 tables.
- **Schema Hash:** `cc2d13f77b681107` (identical before and after audit).
- **Integrity Check:** `PRAGMA integrity_check = ok`.
- **Database Modality:** Unchanged and intact.

---

## 24. Safe-to-Remove Dependency Candidates
The following packages are safe to uninstall if virtualenv thinning is desired:
- `pip uninstall -y sqlalchemy greenlet itsdangerous blinker click colorama`
*(These packages have zero active imports and no dependencies on the active Django surveillance runtime).*

---

## 25. Remaining Unknowns
- **Password Hasher Migration:** `Werkzeug` is currently retained solely for verifying user passwords created in earlier phases using Werkzeug's `scrypt` hasher. Migrating these user passwords to Django's native `PBKDF2PasswordHasher` or Django's built-in `check_password` would allow `Werkzeug` to be cleanly removed as well.

---

## 26. Final Recommended Technology Stack
The official canonical stack for DeepVision:

```
Runtime:         Python 3.14 (Virtualenv, Windows 11 AMD64)
Web Framework:   Django 5.2 (ORM, Templates, StreamingHttpResponse, JsonResponse)
Database:        SQLite 3.50 (instance/deepvision.db, 18 tables)
Computer Vision: OpenCV 5.0 (DirectShow hardware capture, VideoWriter MP4, MJPEG)
Machine Learning:PyTorch 2.13 CPU (YOLO11n singleton forward inference)
Object Tracker:  ByteTrack (Ultralytics integration, lap C-acceleration)
Frontend:        HTML5, Vanilla CSS3 (Custom Tokens), Vanilla JavaScript (ES6+ Fetch)
Security:        Django Signed-Cookie Sessions, Werkzeug scrypt, Django CSRF, SMTP OTP
Storage:         Local Filesystem (instance/recordings, instance/evidence)
```
