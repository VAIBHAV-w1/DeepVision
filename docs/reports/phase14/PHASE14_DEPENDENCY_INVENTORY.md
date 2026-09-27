# DeepVision — Phase 14 Dependency & Component Inventory

**Date:** September 25, 2026  
**Objective:** Authoritative classification of all repository modules, services, and dependencies for complete Flask elimination and native Django surveillance consolidation.

---

## 1. Inventory Summary by Classification

| Classification | Count | Description |
|:---|:---:|:---|
| **KEEP** | 78 files | Core Django application, models, UI templates, static assets, database, weights. |
| **MIGRATE** | 14 files | Canonical camera, AI, tracker, detector, recording, and anomaly modules in `app/`. |
| **REPLACE** | 4 files | `deepvision_django/apps/ai/engine.py`, `start_deepvision.py`, `supervisor.py`, `run.py`. |
| **OBSOLETE** | 92 files | Flask routes, blueprints, Jinja templates, Flask-SQLAlchemy models, legacy tests, dead scripts. |
| **UNKNOWN** | 0 files | All repository artifacts have been identified and mapped to active or obsolete pipelines. |

---

## 2. Core Package & Dependency Inventory

| Package / Library | Current Usage in Codebase | Classification | Post-Migration Disposition |
|:---|:---|:---:|:---|
| **Flask** (`3.1.3`) | Flask app factory, blueprints, routing, HTTP server on :5000 | **OBSOLETE** | Completely removed from runtime and `requirements.txt`. |
| **Flask-SQLAlchemy** (`3.1.1`) | ORM for Flask surveillance engine and background workers | **OBSOLETE** | Replaced entirely by native Django ORM (`managed=False`). |
| **Werkzeug** (`3.1.8`) | Password hashing (`generate_password_hash`, `check_password_hash`) in `accounts/models.py` | **KEEP** | Retained for password compatibility with existing SQLite `users` table. |
| **Django** (`5.2.17`) | Complete user-facing web, auth, API, and now surveillance runtime | **KEEP** | Canonical application framework. |
| **opencv-python** (`5.0.0.93`) | DirectShow camera capture, VideoWriter MP4 recording, frame encode | **KEEP** | Direct OpenCV integration inside native Django camera service. |
| **torch** (`2.13.0+cpu`) | PyTorch inference runtime for YOLO11n | **KEEP** | Direct PyTorch runtime inside native Django AI service. |
| **torchvision** (`0.28.0`) | Vision utilities supporting PyTorch/Ultralytics | **KEEP** | Retained. |
| **ultralytics** (`8.4.117`) | YOLO11n object detector | **KEEP** | Native Django AI inference engine. |
| **numpy** (`2.5.2`) | Frame array manipulations, bounding box calculations | **KEEP** | Retained. |
| **psutil** (`7.2.2`) | System health, RAM, CPU, thread telemetry | **KEEP** | Retained for Django diagnostic services. |
| **requests** (`2.34.2`) | Previously used by `engine.py` to call Flask loopback | **OBSOLETE** (for internal engine) | Retained only if external APIs require it, removed from internal engine. |
| **python-dotenv** (`1.2.2`) | Environment variable loading | **KEEP** | Retained for `.env` configuration. |
| **itsdangerous** (`2.2.0`) | Previously used for Flask session cookie signing | **OBSOLETE** | Retired; Django session middleware handles signed cookies natively. |

---

## 3. Detailed Component Classification

### A. Camera Subsystem (`app/camera/`)
- `app/camera/capture.py` -> **MIGRATE**  
  *Analysis:* Contains DirectShow `safe_open_video_capture()` and device probing. Independent of Flask (minor optional `current_app` testing hook). Moves natively into `deepvision_django/apps/cameras/services/capture.py`.
- `app/camera/registry.py` -> **MIGRATE**  
  *Analysis:* Canonical thread-safe `CameraRegistry` singleton. Tracks physical camera devices (`dshow://0`), manages `CameraWorker` instances. Moves natively into `deepvision_django/apps/cameras/services/registry.py`.
- `app/camera/workers.py` -> **MIGRATE**  
  *Analysis:* Contains `CameraWorker` (thread reading frames into rolling buffer) and `InferenceWorker` (thread driving YOLO+ByteTrack). `_trigger_alert_async` modified to use Django ORM instead of Flask app context. Moves into `deepvision_django/apps/cameras/services/workers.py`.

### B. AI & Tracking Subsystem (`app/ai/`)
- `app/ai/detection/yolo_detector.py` -> **MIGRATE**  
  *Analysis:* YOLO11n inference wrapper loading `models/yolo11n.pt`. Moves to `deepvision_django/apps/ai/services/detector.py`.
- `app/ai/tracking/bytetrack_tracker.py` -> **MIGRATE**  
  *Analysis:* ByteTrack multi-object tracker integration with `bytetrack.yaml`. Moves to `deepvision_django/apps/ai/services/tracker.py`.
- `app/ai/models.py` -> **MIGRATE**  
  *Analysis:* Singleton model manager ensuring `MODEL_LOAD_COUNT=1`. Moves to `deepvision_django/apps/ai/services/models.py`.
- `app/ai/registry.py` -> **MIGRATE**  
  *Analysis:* `InferenceRegistry` managing per-camera inference workers. Moves to `deepvision_django/apps/ai/services/registry.py`.
- `app/ai/behavior/` (`track_history.py`, `behavior_analyzer.py`) -> **MIGRATE**  
  *Analysis:* Pure Python algorithmic modules analyzing trajectory, velocity, stationary durations. Moves to `deepvision_django/apps/ai/behavior/`.
- `app/ai/anomaly/` (`anomaly_detector.py`) -> **MIGRATE**  
  *Analysis:* Rule evaluation for loitering, crowding, restricted zones, and abandoned objects. Moves to `deepvision_django/apps/ai/anomaly/`.

### C. Services & Utilities (`app/services/`)
- `app/services/recording_service.py` -> **MIGRATE**  
  *Analysis:* MP4 recording lifecycle, `cv2.VideoWriter`, rolling buffer flushes. Replaced Flask `current_app` and SQLAlchemy with Django ORM `Recording.objects.create()`. Moves to `deepvision_django/apps/recordings/services/recording_service.py`.
- `app/services/video_service.py` -> **MIGRATE / REFACTOR**  
  *Analysis:* Generates multipart/x-mixed-replace frame chunks for raw and AI streams. Moves directly into Django streaming generators.
- `app/services/camera_health_service.py` -> **MIGRATE**  
  *Analysis:* Computes frame rate, inference latency, buffer health. Moves to `deepvision_django/apps/cameras/services/health_service.py`.
- `app/services/global_identity_registry.py` -> **MIGRATE**  
  *Analysis:* Tracks cross-camera person re-identification. Moves to `deepvision_django/apps/ai/services/reid.py`.
- `app/services/auth_service.py` -> **OBSOLETE**  
  *Analysis:* Flask session authentication. Completely replaced by `deepvision_django/apps/accounts/`.
- `app/services/alert_service.py` -> **OBSOLETE**  
  *Analysis:* Flask SQLAlchemy alert persistence. Replaced by Django `apps/alerts/`.
- `app/services/evidence_service.py` -> **OBSOLETE**  
  *Analysis:* Flask SQLAlchemy evidence helper. Replaced by Django `apps/evidence/`.
- `app/services/operations_service.py` -> **OBSOLETE**  
  *Analysis:* Flask dashboard summary metrics. Replaced by Django `apps/core/views.py`.
- `app/services/product_catalog.py`, `product_recognition_service.py` -> **OBSOLETE**  
  *Analysis:* Legacy retail product scanner experiment.

### D. Flask Routes & Blueprints (`app/routes/`) -> ALL OBSOLETE
- `app/routes/main.py` -> **OBSOLETE** (Legacy Flask index, help, assistant chat)
- `app/routes/cameras.py` -> **OBSOLETE** (83 legacy UI routes and Flask stream views)
- `app/routes/alerts.py` -> **OBSOLETE** (Flask alert list/detail)
- `app/routes/cases.py` -> **OBSOLETE** (Flask case list/detail)
- `app/routes/evidence.py` -> **OBSOLETE** (Flask evidence views)
- `app/routes/recordings.py` -> **OBSOLETE** (Flask recording list/player)
- `app/routes/notifications.py` -> **OBSOLETE** (Flask notifications)
- `app/routes/auth.py` -> **OBSOLETE** (Flask login/signup)
- `app/routes/audit.py`, `camera_groups.py`, `command_center.py`, `detection_profiles.py`, `devices.py`, `incident_playbooks.py`, `incident_policies.py`, `notification_preferences.py`, `products.py`, `reports.py`, `response.py`, `search.py`, `security_analytics.py`, `security_configuration.py`, `surveillance_presets.py`, `timeline.py`, `zones.py` -> **OBSOLETE** (All retired in Phase 9).

### E. Flask Core & Models (`app/core/`, `app/models/`) -> ALL OBSOLETE
- `app/__init__.py` -> **OBSOLETE** (Flask `create_app` factory)
- `app/config.py` -> **OBSOLETE** (Flask configuration class)
- `app/core/extensions.py` -> **OBSOLETE** (Flask `db = SQLAlchemy()`)
- `app/core/security.py` -> **OBSOLETE** (Flask `@login_required` decorator)
- `app/core/errors.py` -> **OBSOLETE** (Flask error handlers)
- `app/models/*.py` (`user.py`, `camera.py`, `recording.py`, `alert.py`, etc.) -> **OBSOLETE** (Superseded by Django ORM models with `managed=False`).

### F. Flask Templates & Static Assets (`app/templates/`, `app/static/`) -> ALL OBSOLETE
- `app/templates/**/*.html` (77 templates) -> **OBSOLETE** (Replaced by Django 44 native templates).
- `app/static/**/*` (CSS, JS, images) -> **OBSOLETE** (Replaced by Django `static/`).

### G. Startup & Boundary Scripts
- `deepvision_django/apps/ai/engine.py` -> **REPLACE**  
  *Analysis:* Currently proxies requests to Flask :5000 via HTTP loopback. Must be replaced with native in-process calls to Django surveillance services.
- `supervisor.py` -> **OBSOLETE**  
  *Analysis:* Dual-process watchdog for Flask `run.py`. Obsolete once Django natively hosts the camera engine.
- `run.py` -> **OBSOLETE**  
  *Analysis:* Flask server entrypoint on port 5000.
- `start_deepvision.py` -> **REPLACE**  
  *Analysis:* Dual launcher. Replaced with single Django native runner or standard `python manage.py runserver`.

### H. Verification & Test Scripts
- `tests/test_*.py` (22 legacy Flask tests) -> **OBSOLETE** (Import Flask `create_app`).
- `deepvision_django/verify_phase*.py` (Phases 3 to 13) -> **KEEP / ARCHIVE** (Valuable historical audit trail).
- `deepvision_django/verify_phase14_django_native.py` -> **NEW (MANDATORY)**.

---

## 4. Migration Execution Plan

1. **Step 1: Backup & Invariant Baseline** (Done: `deepvision.db` backed up to `backups/pre_phase14_backup/deepvision.db`, signature `cc2d13f77b681107`).
2. **Step 2: Native Django Surveillance Services**
   - Create native surveillance packages inside `deepvision_django/apps/cameras/services/`, `deepvision_django/apps/ai/services/`, and `deepvision_django/apps/recordings/services/`.
   - Transfer OpenCV DirectShow capture, CameraWorker, YOLO11n loader, ByteTrack, InferenceWorker, and RecordingService.
   - Refactor `_trigger_alert_async` and recording persistence to use Django ORM models directly without Flask context.
3. **Step 3: Refactor `engine.py` to Native In-Process Adapter**
   - Eliminate HTTP requests to port 5000, socket probes, and session cookie generation.
   - Interface directly with native Django surveillance services.
4. **Step 4: Update Startup Architecture**
   - Configure safe single-process Django startup in `deepvision_django/apps/cameras/apps.py` (with autoreloader guard `os.environ.get('RUN_MAIN') == 'true'` or on-demand service warmup) to guarantee exactly 1 `VideoCapture`, 1 `CameraWorker`, 1 `InferenceWorker`, and 1 `YOLO11n` instance.
5. **Step 5: Verify Django-Native Surveillance**
   - Execute verification suite testing live stream, AI tracking, FPS, snapshots, recording, alerts, and cases on Django :8000 with Flask completely stopped.
6. **Step 6: Remove Flask and Obsolete Assets**
   - Stop and terminate Flask background processes.
   - Remove Flask runtime code and update `requirements.txt`.
   - Run `pip check` and verify full application imports.
7. **Step 7: Final Verification & Reporting**
   - Execute `verify_phase14_django_native.py`.
   - Publish `CLEANUP_MANIFEST.md` and `PHASE14_COMPLETION_REPORT.md`.
