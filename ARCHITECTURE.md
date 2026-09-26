# DeepVision Architectural Specification

## 1. System Overview

DeepVision is a real-time smart surveillance platform that couples a modern React Single Page Application (SPA) frontend with an in-process Django backend and native OpenCV/YOLO/ByteTrack surveillance engine.

```text
+-----------------------------------------------------------------------+
|                         React SPA (Browser)                           |
|  - Dashboard  - Live View  - Recordings  - Evidence  - Alerts  - Chat |
+-----------------------------------+-----------------------------------+
                                    | (JSON REST APIs & MJPEG Stream)
                                    v
+-----------------------------------------------------------------------+
|                         Django Backend (:8000)                        |
|  - Authentication & Session Middleware (Signed Cookies)              |
|  - REST API Layer (/api/...)                                          |
|  - Media & HTTP 206 Streaming Controllers                            |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                    Native Surveillance Services                       |
|  - CameraRegistry: Manages physical VideoCapture & CameraWorkers      |
|  - InferenceRegistry: Manages asynchronous InferenceWorkers           |
|  - RecordingService: Handles VideoWriter & MP4 storage                |
+-------------------+-------------------------------+-------------------+
                    |                               |
                    v                               v
+-----------------------------------+   +-------------------------------+
|      OpenCV & DirectShow          |   |      YOLO11n + ByteTrack      |
|  - Hardware capture (dshow://0)   |   |  - Ultralytics PyTorch Model  |
|  - Ring buffer frame distribution |   |  - Kalman Filter & Hungarian  |
+-----------------------------------+   +-------------------------------+
                    \                               /
                     +--------------+--------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                      Persistence & Media Storage                      |
|  - SQLite (instance/deepvision.db - 18 Tables)                        |
|  - MP4 Video Storage (instance/recordings/)                           |
|  - Forensic Evidence Vault (instance/evidence/)                       |
+-----------------------------------------------------------------------+
```

---

## 2. Frontend Architecture (React + Vite)

### Technology Stack
- **Framework**: React 19 (Functional components with React Hooks)
- **Tooling**: Vite 5+ build system
- **Routing**: Client-side view controller routing based on URL path (`window.location.pathname`) with seamless browser history navigation
- **Styling**: Vanilla CSS design system with CSS custom properties (`globals.css`, `layout.css`, `components.css`, `camera.css`, `dashboard.css`)
- **Asset Distribution**: Compiled directly to `deepvision_django/static/dist/` for production serving through Django staticfiles.

### Component Hierarchy
```text
App
├── Navbar (Branding, Live System Status, Navigation Links, Unread Count, Theme Toggle)
├── AuthLayout (Login, Signup, VerifyEmail, ForgotPassword)
└── AppLayout
    ├── Sidebar (Section navigation, SOC metrics quick link)
    ├── Page View
    │   ├── Dashboard (MetricCards, CameraGrid, AlertSummary, ActivityFeed)
    │   ├── Cameras (CameraList, AddCameraModal, TestConnection)
    │   ├── CameraPreview (CameraFeed, CameraControls: Mode Toggle, Snapshot, Record)
    │   ├── Recordings (RecordingsList, VideoPlayerModal with HTTP 206 Range seeking)
    │   ├── Evidence (EvidenceGrid, MediaViewerModal)
    │   ├── Alerts (AlertTable, Acknowledge/Resolve Actions, Evidence Links)
    │   ├── Cases (CasesTable, CaseDetailModal, Forensic Timeline Notes)
    │   └── Notifications (NotificationList, MarkRead, FilterTabs)
    └── AssistantChat (Floating interactive surveillance assistant)
```

### State Management & Service Invariants
- Frontend communication is strictly mediated through `services/api.js`.
- No raw browser camera APIs are used (`navigator.mediaDevices` is never invoked).
- Video streams are ingested exclusively as HTTP multipart MJPEG from Django StreamingHttpResponse endpoints.

---

## 3. Django Backend & REST API Layer

### Application Organization
- **`apps.accounts`**: Custom User model, PBKDF2 password hashing, legacy Werkzeug scrypt compatibility, cryptographic OTP generation, and signed session cookies.
- **`apps.core`**: Consolidated REST API controller (`api.py`), React SPA fallback view (`views.py`), media service resolution, and grounded Assistant chat engine.
- **`apps.cameras`**: Camera database models, connection testing, snapshot generation, and DirectShow stream endpoints.
- **`apps.recordings`**: Recording metadata models, HTTP 206 partial content range playback, and file downloads.
- **`apps.alerts`**: Security alert lifecycle, forensic incident cases, timeline notes, and escalation policies.
- **`apps.evidence`**: Forensic evidence vault snapshots and video clips.
- **`apps.notifications`**: User notification delivery and read status tracking.
- **`apps.surveillance`**: In-process surveillance engine, camera workers, inference workers, and recording writers.

### API Contract Summary
| Path | Method | Purpose |
| :--- | :--- | :--- |
| `/api/auth/csrf/` | GET | Obtains fresh CSRF token and sets cookie |
| `/api/auth/me/` | GET | Returns session user profile and verification status |
| `/api/auth/login/` | POST | Authenticates user credentials via PBKDF2 |
| `/api/auth/logout/` | POST | Terminates session cookie |
| `/api/dashboard/stats/` | GET | System-wide camera status, alert counts, and engine telemetry |
| `/api/cameras/` | GET/POST | Lists configured cameras or creates a new camera |
| `/api/cameras/<id>/` | GET/PUT/DEL | Camera detail, configuration updates, deletion |
| `/api/cameras/test-connection/` | POST | Validates capture source viability |
| `/api/surveillance/health/` | GET | Returns live camera handles, active workers, and YOLO status |
| `/cameras/<id>/stream/original/` | GET | Multipart MJPEG raw CCTV stream |
| `/cameras/<id>/stream/tracking/` | GET | Multipart MJPEG YOLO11n + ByteTrack stream |
| `/cameras/<id>/snapshot/` | GET | Captures instantaneous JPEG frame |
| `/cameras/<id>/record/start` | POST | Initiates MP4 VideoWriter session |
| `/cameras/<id>/record/stop` | POST | Finalizes and closes MP4 recording |
| `/api/recordings/` | GET | Lists surveillance video recordings |
| `/recordings/<id>/view/` | GET | HTTP 206 Partial Content video streaming |
| `/api/evidence/` | GET | Lists forensic evidence snapshots and clips |
| `/evidence/<id>/preview/` | GET | Streams evidence JPEG snapshot or MP4 clip |
| `/api/alerts/` | GET | Lists security alerts |
| `/alerts/<id>/acknowledge/` | POST | Acknowledges pending alert |
| `/alerts/<id>/resolve/` | POST | Resolves alert |
| `/api/cases/` | GET/POST | Lists incident cases or files new case |
| `/api/cases/<id>/` | GET | Fetches case details and investigation notes |
| `/api/cases/<id>/note/` | POST | Appends investigation note to case's alert |
| `/api/notifications/unread-count/` | GET | Returns count of unread notifications |
| `/api/assistant/chat/` | POST | Grounded assistant query answering |

---

## 4. Surveillance & AI Subsystem

### Protected Concurrency Invariant
During active surveillance monitoring, the system enforces the following singleton guarantees:
1. **Exactly 1 physical VideoCapture handle** per physical hardware device (DirectShow index `0` / `dshow://0`).
2. **Exactly 1 CameraWorker thread** pulling frames into an internal lock-free ring buffer.
3. **Exactly 1 InferenceWorker thread** consuming frames for AI processing.
4. **Exactly 1 YOLO11n model weights instance** in host RAM / CPU memory (avoiding redundant disk I/O and duplicate neural networks).

### Dual Stream Modes
1. **ORIGINAL Mode**:
   - Camera -> OpenCV -> Ring Buffer -> MJPEG Multipart Stream -> Browser.
   - Zero AI overhead; pristine raw video for identification and high-framerate verification.
2. **TRACKING + DETECTION Mode**:
   - Camera -> OpenCV -> InferenceWorker -> YOLO11n -> ByteTrack -> Overlay Engine -> MJPEG Multipart Stream -> Browser.
   - Real-time bounding boxes, object class classification, confidence levels, and persistent tracking IDs across occlusions.

---

## 5. Security & Authentication Architecture

1. **Password Hashing**:
   - Uses Django's standard PBKDF2 implementation (`PBKDF2PasswordHasher` with SHA-256).
   - Retains backward compatibility with existing user records stored with legacy `scrypt` hashes.
   - Transparently re-hashes legacy credentials to standard PBKDF2 upon successful user login.
2. **Session Security**:
   - Signed cookie sessions (`deepvision_django_session`) with `HttpOnly` and `SameSite=Lax`.
   - Zero database session table overhead; cryptographically signed with `SECRET_KEY`.
3. **Media & Path Traversal Guards**:
   - All recording and evidence file requests are sanitized using `safe_resolve_recording` and `safe_resolve_evidence`.
   - Raw internal filesystem paths are never exposed to the client or returned in JSON responses.
4. **CSRF Enforcement**:
   - All mutating REST requests (`POST`, `PUT`, `DELETE`) require a valid `X-CSRFToken` header matching the signed CSRF cookie.
