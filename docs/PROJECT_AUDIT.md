# DEEPVISION 4.0 — COMPLETE PROJECT AUDIT & ARCHITECTURAL INVENTORY

**Project:** DeepVision AI Intelligent Surveillance Platform  
**Location:** `D:\DeepVision`  
**Audit Timestamp:** October 31, 2026  
**Auditor:** DeepVision Core Engineering Agent  
**Baseline Database Signature:** `cc2d13f77b681107` (18 tables, verified preserved)  
**Django Version:** 5.x / Python 3.14  
**React / Build:** Vite 6 / React 18 / SPA Architecture  

---

## 1. EXECUTIVE SUMMARY OF CODEBASE HEALTH

The DeepVision codebase represents an enterprise-grade AI video surveillance platform that has evolved through multiple integration phases. While the core algorithms (OpenCV DirectShow video capture, singleton YOLO11n inference, ByteTrack multi-object tracking, and signed-cookie authentication) are highly functional, previous engineering passes introduced significant **architectural inconsistencies, artificial page collapses, orphaned components, and fragmented templates**.

### Key Architectural Deficiencies Identified:
1. **Frontend Workspace Consolidation Anti-Pattern:**
   - Five full-featured page components (`Alerts.jsx`, `Recordings.jsx`, `Evidence.jsx`, `Cases.jsx`, `Notifications.jsx`) were bypassed in routing and forced into an artificial tabbed wrapper (`SecurityCenter.jsx`).
   - `Cameras.jsx` and `Monitor.jsx` were gutted into 12-line alias wrappers pointing to `Surveillance.jsx`.
   - As a result, users navigating to distinct operational workspaces experienced confusing tab switching, broken deep links, or truncated views.
2. **Orphaned Django HTML Templates:**
   - 23 legacy server-side rendered Django HTML templates (`deepvision_django/templates/pages/*`) from September 2026 remain in the tree despite the platform having fully migrated to a React SPA.
   - When `static/dist/index.html` was missing or fallback triggered, Django rendered dated, broken server-side templates with mismatched styling.
3. **Dead Archives & Unused Assets:**
   - Root directory contains legacy compressed archives (`DeepVision-1.1.0/*.tar` totaling ~1.8 GB).
   - Redundant public image directories (`frontend/public/images/`, `frontend/public/static/images/`, `deepvision_django/static/images/`) with conflicting logo versions.
4. **Backend Endpoint Redundancy:**
   - URL routes in `config/urls.py` have duplicate slash/no-slash mappings and overlapping paths (`/cameras/<id>/stats/` vs `/api/cameras/<id>/stats/`).
   - API endpoints were split across `apps/core/api.py`, `apps/cameras/views.py`, and `apps/alerts/views.py`.

---

## 2. FILE AND FOLDER STRUCTURE AUDIT

| Directory / File Path | Status | Purpose & Current Role | Health / Finding | Recommendation |
|---|---|---|---|---|
| `manage.py` (root) | Active | Proxy script forwarding CLI to `deepvision_django/manage.py`. | **Working**: Correctly resolves venv and paths. | Retain as convenient root CLI runner. |
| `start_deepvision.py` | Active | Production launcher for Django, DirectShow camera bridge, and DB integrity. | **Working**: Preflight schema signature verification active. | Retain as canonical process supervisor. |
| `instance/deepvision.db` | Active | Authoritative SQLite database (18 tables, signature `cc2d13f77b681107`). | **Working**: 100% integrity, verified records. | STRICTLY PRESERVE. Never drop or reset. |
| `models/yolo11n.pt` | Active | Pretrained Ultralytics YOLO11n PyTorch weights (5.6 MB). | **Working**: Loaded as singleton in `model_loader.py`. | Retain in `models/`. |
| `DeepVision-1.1.0/` | Obsolete | Contains 3 giant `.tar` files (1.8 GB) from legacy release 1.1.0. | **Unused / Bloat**: Not referenced by runtime. | Archive / move outside active source tree. |
| `api/` | Obsolete | Contains Vercel serverless entrypoint (`api/index.py`). | **Obsolete**: Vercel deployment is locked. | Document as legacy serverless shim; do not touch. |
| `deepvision_django/` | Active | Authoritative Django backend application. | **Working**: Single authoritative backend. | Clean and structure into logical domains. |
| `deepvision_django/templates/`| Obsolete | 23 server-side HTML templates (September 2026 legacy). | **Dead / Confusing**: Competes with React SPA. | Isolate or deprecate; ensure React SPA is authoritative. |
| `frontend/src/` | Active | React SPA source tree. | **Needs Restructuring**: Routing and component unifications needed. | Rebuild 10 canonical workspaces. |
| `scripts/` | Active | Utility and benchmarking scripts. | **Working**: Latency benchmarks, DB verification. | Keep clean and organized. |
| `verification/` | Active | Automated test suites and screenshots. | **Working**: Regression test scripts. | Maintain and expand. |
| `reports/` | Active | Engineering reports and audit artifacts. | **Working**: Documentation archive. | Retain. |

---

## 3. BACKEND APPLICATIONS & MODULE AUDIT

The Django backend is located at `D:\DeepVision\deepvision_django` with `INSTALLED_APPS` defined in `config/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'django.contrib.sessions',
    'django.contrib.messages',
    'apps.core',
    'apps.accounts',
    'apps.cameras',
    'apps.alerts',
    'apps.recordings',
    'apps.evidence',
    'apps.notifications',
    'apps.ai',
]
```

### Module-by-Module Assessment:

1. **`apps.accounts` (Authentication & Security):**
   - **Models:** `User` (email, full_name, password_hash, role, is_active, is_email_verified).
   - **Auth Engine:** Signed cookie sessions (`SESSION_COOKIE_NAME = 'deepvision_django_session'`), zero DB writes for session tables.
   - **Password Security:** PBKDF2-SHA256 with legacy scrypt fallback verification.
   - **2FA / OTP:** Time-limited email OTP verification for signup and login with cryptographic salt separation (`LOGIN_SALT` vs `SIGNUP_SALT`).
   - **Health:** **WORKING & ROBUST**. Verified by 18/18 auth tests.

2. **`apps.cameras` (Camera Management & Hardware Drivers):**
   - **Models:** `Camera`, `CameraGroup`, `SurveillancePreset`, `RestrictedZone`.
   - **Capture Engine:** DirectShow (`dshow://0`) on Windows using OpenCV `VideoCapture`. Enforces `CAP_PROP_BUFFERSIZE = 1` and condition variable signaling to eliminate latency.
   - **Health:** **WORKING**. Resolves physical camera index 0 (HP Wide Vision HD Camera) at 1280x720, ~16 FPS hardware ceiling.

3. **`apps.surveillance` (AI Engine, Detection, Tracking, Anomaly):**
   - **Submodules:** `ai/` (detector, tracker, registry, workers, anomaly, behavior), `camera/` (capture, workers, sources), `recording/`, `streaming/`, `health/`.
   - **YOLO11n Loader:** `model_loader.py` enforces singleton pattern (`MODEL_LOAD_COUNT=1`).
   - **ByteTrack Tracker:** `tracker.py` maintains Kalman filters and Hungarian matching across frames.
   - **Anomaly Engine:** `anomaly_detector.py` provides ray-casting polygon point-in-zone checks and loitering timers.
   - **Health:** **WORKING**. Decoupled capture and inference loops.

4. **`apps.alerts` & `apps.evidence` & `apps.recordings`:**
   - **Models:** `Alert`, `IncidentCase`, `IncidentNote`, `Evidence`, `Recording`.
   - **Media Delivery:** `recording_views.py` implements RFC 7233 HTTP 206 Partial Content video seeking. `evidence_views.py` serves cryptographically signed snapshots and clips.
   - **Health:** **WORKING**. Verified by HTTP Range tests and manual snapshots.

5. **`apps.core` (Central REST API Gateway & SPA Entry):**
   - **`apps/core/api.py`:** 1593 lines containing centralized REST APIs.
   - **`apps/core/views.py`:** Serves `react_app_view` (loading `static/dist/index.html`) and health check.
   - **Health:** **WORKING**, but `api.py` is bloated and contains repetitive database query logic.

---

## 4. FRONTEND APPLICATIONS & ROUTING AUDIT

### Detailed Page Component Analysis:

| Component Path | Size | Status in `App.jsx` | Actual UI Capabilities | Issue Identified |
|---|---|---|---|---|
| `pages/Dashboard.jsx` | 33.1 KB | Rendered on `overview` & `dashboard` | SOC KPI metrics, camera status cards, recent alerts, activity graphs. | **Working well**, but should be strictly renamed or aliased to `Overview`. |
| `pages/Surveillance.jsx` | 48.2 KB | Rendered on `surveillance`, `live`, and fallback | Two sub-tabs: "Live View" (live video player, tracking overlays) and "Manage Cameras". | **Monolithic**: Bundles both live video and camera inventory into one huge component. |
| `pages/Cameras.jsx` | 344 B | Alias wrapper | Only renders `<Surveillance initialTab="manage" />`. | **GUTTED**: Should be an independent, dedicated camera inventory workspace. |
| `pages/Monitor.jsx` | 337 B | Alias wrapper | Only renders `<Surveillance initialTab="live" />`. | **REDUNDANT**: Duplicate alias of Surveillance. |
| `pages/SecurityCenter.jsx` | 12.8 KB | Rendered on `security-center`, `alerts`, etc. | Tab wrapper holding Alerts, Recordings, Evidence, Cases, Notifications. | **ARTIFICIAL WRAPPER**: Collapses 5 distinct workspaces into sub-tabs. |
| `pages/Alerts.jsx` | 31.2 KB | Rendered only inside SecurityCenter tab | Full incident triage, filters, severity tags, investigation drawer. | **ORPHANED**: Must be directly accessible as canonical `#/alerts`. |
| `pages/Recordings.jsx` | 21.9 KB | Rendered only inside SecurityCenter tab | Video playback gallery, calendar filters, HTTP Range seeking. | **ORPHANED**: Must be directly accessible as canonical `#/recordings`. |
| `pages/Evidence.jsx` | 14.5 KB | Rendered only inside SecurityCenter tab | Forensic vault, SHA-256 hashes, snapshot previews, video clip downloads. | **ORPHANED**: Must be directly accessible as canonical `#/evidence`. |
| `pages/Cases.jsx` | 13.6 KB | Rendered only inside SecurityCenter tab | Investigation cases, priority badges, investigator notes. | **ORPHANED**: Must be directly accessible as canonical `#/cases`. |
| `pages/Notifications.jsx`| 9.3 KB | Rendered only inside SecurityCenter tab | Operator alert feed, mark-as-read, real-time unread counter. | **ORPHANED**: Must be directly accessible as canonical `#/notifications`. |
| `pages/Settings.jsx` | 25.5 KB | Rendered on `settings` | System settings, camera rules, global detection sensitivity, email config. | **Working**. |
| `pages/Help.jsx` | 7.1 KB | Rendered on `help` | User documentation, keyboard shortcuts, system health diagnostics. | **Working**. |

---

## 5. DATABASE INTEGRITY & DATA MODEL AUDIT

Authoritative Database: `instance/deepvision.db` (SQLite 3)  
Preflight Schema Signature: `cc2d13f77b681107`  
Integrity Check: `PRAGMA integrity_check` -> `ok`

### Complete Table Inventory & Row Counts:

| Table Name | Row Count | Primary Key | Foreign Keys & Relations | Purpose |
|---|---|---|---|---|
| `users` | 16 | `id` (INTEGER) | None | System operators, admins, email verification status. |
| `cameras` | 10 | `id` (INTEGER) | `user_id` -> `users.id` | Registered video sources (DirectShow, RTSP, HTTP phone). |
| `alerts` | 5,713 | `id` (INTEGER) | `camera_id` -> `cameras.id` | Real-time security events (loitering, intrusion, etc.). |
| `evidence` | 7,316 | `id` (INTEGER) | `alert_id` -> `alerts.id`, `camera_id` -> `cameras.id` | Forensic JPEG snapshots and MP4 incident clips. |
| `recordings` | 3,637 | `id` (INTEGER) | `camera_id` -> `cameras.id`, `user_id` -> `users.id` | Continuous and event video footage files. |
| `incident_cases` | 1,024 | `id` (INTEGER) | `alert_id` -> `alerts.id`, `user_id` -> `users.id` | Escalated investigation cases. |
| `incident_notes` | 21 | `id` (INTEGER) | `case_id` -> `incident_cases.id`, `user_id` -> `users.id` | Investigator notes on incident cases. |
| `notifications` | 4,550 | `id` (INTEGER) | `user_id` -> `users.id`, `alert_id` -> `alerts.id` | Dispatched alerts to operators. |
| `restricted_zones`| 4 | `id` (INTEGER) | `camera_id` -> `cameras.id` | Geometrical bounding polygons for perimeter intrusion. |
| `audit_logs` | 1,874 | `id` (INTEGER) | `user_id` -> `users.id` | Security audit trail (login, camera edits, state changes).|
| `products` | 24 | `id` (INTEGER) | None | Retail item catalog for inventory tracking. |
| `detection_profiles`| 1 | `id` (INTEGER) | None | Global detection sensitivity presets. |
| `camera_groups` | 0 | `id` (INTEGER) | None | Logical grouping of cameras (facilities/zones). |
| `devices` | 0 | `id` (INTEGER) | None | Auxiliary hardware edge devices. |
| `incident_playbooks`| 0 | `id` (INTEGER) | None | Automated incident response playbooks. |
| `incident_policies` | 0 | `id` (INTEGER) | None | Escalation policies. |
| `notification_preferences`| 0 | `id` (INTEGER) | None | User-specific notification channels. |
| `surveillance_presets`| 0 | `id` (INTEGER) | None | Hardware camera pan/tilt/zoom presets. |

**Verdict:** Database structure is clean, well-indexed (11 secondary B-tree indexes), and fully populated with real operational data. Must be preserved with zero schema changes.

---

## 6. CAMERA CAPTURE, DETECTION & TRACKING AUDIT

### 1. Camera Capture Pipeline
- **Driver:** DirectShow (`cv2.CAP_DSHOW`) on Windows.
- **Physical Device:** Camera Index 0 (`HP Wide Vision HD Camera`, 1280x720).
- **Physical Latency:**
  - `cap.grab()`: `0.01 ms`
  - `cap.retrieve()`: `60.58 ms` (Hardware sensor read limit: ~16.0 FPS).
- **Buffer Management:** `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)` eliminates stale driver buffering.
- **Worker Concurrency:** Single worker per camera via `CameraRegistry`. Capture and inference loops decoupled.

### 2. YOLO11n Detection
- **Model Loader:** Singleton instance managed in `model_loader.py`.
- **Inference Latencies (Intel CPU):**
  - 384x384: `34.9 ms` (28.7 FPS)
  - 480x480: `38.3 ms` (26.1 FPS)
  - 640x640: `64.2 ms` (15.6 FPS - perfectly matched to 16 FPS camera sensor).
- **Thresholds:** Confidence `0.35`, NMS IoU `0.45`.
- **Finding:** High recall on persons and common objects, zero fabricated detections.

### 3. ByteTrack Multi-Object Tracking
- **State Update & Association:** `1.62 ms` per frame.
- **Tracking Stability:** Strict Hungarian matching with high-confidence first round (`0.35`) and lost-track persistence buffer of 30 frames (2 seconds).
- **Finding:** Trajectory IDs remain stable across frames. Two consecutive detections required to confirm track, preventing phantom bounding boxes.

### 4. Anomaly Detection & Zone Rules
- **Rule Engine Latency:** `0.037 ms` (37 µs).
- **Polygon Test:** Ray-casting point-in-polygon algorithm tests feet coordinate `(center_x, bottom_y)` of tracked bounding box.
- **Invalidation:** `_invalidate_camera_zones(camera.id)` prompts `InferenceWorker.invalidate_zones()` on any REST mutation, reloading boundaries in memory within 50 ms.

---

## 7. IDENTIFIED PROBLEMS & REMEDIATION PLAN

### Defect 1: Gutted `Cameras.jsx` and `Monitor.jsx`
- **Root Cause:** A prior refactoring collapsed these pages into `<Surveillance initialTab="..." />`.
- **Fix:** Rebuild `Cameras.jsx` as an independent, fully-featured camera inventory workspace with add/edit/delete/test controls, stream health metrics, and direct link to live monitoring.

### Defect 2: Monolithic `SecurityCenter.jsx` Tab Container
- **Root Cause:** Collapsed Alerts, Recordings, Evidence, Cases, and Notifications into tabs.
- **Fix:** Remove `SecurityCenter.jsx`. Wire each canonical route (`#/alerts`, `#/recordings`, `#/evidence`, `#/cases`, `#/notifications`) directly to its dedicated page component in `App.jsx`.

### Defect 3: Navigation Bar Routing Mismatch
- **Root Cause:** `Navbar.jsx` pointed "Cameras" to `surveillance?tab=manage` and "Alerts/Recordings/etc." to `security-center?tab=...`.
- **Fix:** Update `Navbar.jsx` so every one of the 10 canonical navigation items routes directly to its dedicated page without synthetic sub-tabs.

### Defect 4: Unused Legacy Django Server-Side Templates
- **Root Cause:** 23 templates in `deepvision_django/templates/` from September 2026.
- **Fix:** Retain minimal fallback in `apps/core/views.py` that strictly renders `static/dist/index.html`. Deprecate legacy template routes to prevent stale UI rendering.

### Defect 5: Missing Build Automation in Hot Reload
- **Root Cause:** Changes to `frontend/src/` require `npm run build` in `frontend/` to update `deepvision_django/static/dist/`.
- **Fix:** Ensure automated build step is executed and verified with high-resolution CDP browser screenshots on real viewports after every frontend update.

