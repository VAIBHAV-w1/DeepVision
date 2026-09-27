# DeepVision Architecture & Project Structure

DeepVision is an enterprise-grade AI-powered surveillance and suspicious activity detection platform built with Flask, SQLAlchemy, OpenCV, YOLO11, ByteTrack, and Tabler UI.

---

## 1. Directory Overview

```text
DeepVision/
├── app/
│   ├── core/                  # Core foundational infrastructure
│   │   ├── extensions.py      # Global SQLAlchemy instance and app extensions
│   │   ├── security.py        # Centralized login_required & role decorators
│   │   ├── errors.py          # HTTP 403, 404, 500 error handlers
│   │   └── __init__.py
│   ├── camera/                # Modular camera ingestion & streaming engine
│   │   ├── sources.py         # Source URL normalization & validation
│   │   ├── capture.py         # OpenCV / HTTP MJPEG capture (dual-SOI parser, SO_LINGER)
│   │   ├── workers.py         # Thread-safe CameraWorker & decoupled InferenceWorker
│   │   ├── registry.py        # Global CameraRegistry & InferenceRegistry singletons
│   │   └── __init__.py
│   ├── models/                # SQLAlchemy database models
│   │   ├── user.py            # User identity, roles, and password hashing
│   │   ├── camera.py          # Camera definitions, types, endpoints, and credentials
│   │   ├── recording.py       # Recording sessions, paths, sizes, and metadata
│   │   ├── alert.py           # Real-time incident logs and detections
│   │   ├── device.py          # Physical surveillance edge hardware
│   │   └── ...
│   ├── routes/                # Modular Flask blueprint controllers
│   │   ├── auth.py            # /login, /signup, /logout, /forgot-password
│   │   ├── main.py            # /dashboard, /profile, /devices
│   │   ├── cameras.py         # /cameras, /cameras/add, /cameras/<id>/preview
│   │   ├── recordings.py      # /recordings, /recordings/<id>/view, download
│   │   └── ...
│   ├── services/              # High-level business logic
│   │   ├── video_service.py   # Streaming generators (raw, detection, tracking)
│   │   ├── recording_service.py# Segment recording orchestrator
│   │   ├── auth_service.py    # Authentication & token verification
│   │   └── ...
│   ├── ai/                    # Computer vision & neural network pipeline
│   │   ├── detection.py       # YOLO11 inference engine
│   │   ├── tracking.py        # ByteTrack multi-object tracking
│   │   └── behavior.py        # Loitering, intrusion, and perimeter rules
│   ├── templates/             # Modern Tabler UI Jinja2 templates
│   │   ├── layouts/           # base.html, auth.html
│   │   ├── components/        # sidebar, topbar, flash_messages, camera_card
│   │   └── pages/             # Organized per-feature subdirectories
│   │       ├── dashboard/
│   │       ├── cameras/
│   │       ├── recordings/
│   │       ├── auth/
│   │       ├── help/
│   │       └── errors/
│   └── static/                # Static assets & client JavaScript
│       ├── vendor/tabler/     # Tabler CSS/JS bundled locally offline
│       ├── css/               # Modular stylesheet architecture (app, components, pages)
│       ├── js/                # Modular vanilla ES6+ scripts (theme, camera-preview, etc.)
│       └── images/            # DeepVision aperture brand mark and favicon
├── instance/
│   └── deepvision.db          # SQLite persistent database (retained & preserved)
├── recordings/                # Local surveillance MP4 archive storage
├── run.py                     # WSGI server entrypoint
└── requirements.txt
```

---

## 2. Core Subsystems

### `app/core/`
Centralizes foundational Flask infrastructure:
- **`extensions.py`**: Exports the canonical `db = SQLAlchemy()` instance.
- **`security.py`**: Supplies `login_required` decorators and role verification.
- **`errors.py`**: Standard error handlers for 403 Forbidden, 404 Not Found, and 500 Server Error.

### `app/camera/`
Decoupled camera ingestion engine designed for robust, zero-hang streaming across hardware types:
- **`sources.py`**: Normalizes local indices (`0`, `1`), network RTSP (`rtsp://`), and HTTP MJPEG URLs (`http://ip:port/videofeed`), with credential masking.
- **`capture.py`**: Implements `HttpMjpegCapture` featuring:
  - Resilient dual-SOI JPEG boundary parsing (`0xFF 0xD8 ... 0xFF 0xD9`).
  - `SO_LINGER(1, 0)` socket teardown to discard unread network buffers immediately on probe abort, eliminating Windows socket hangs.
  - Fail-safe fallback to standard OpenCV `cv2.VideoCapture`.
- **`workers.py`**:
  - `CameraWorker`: Background thread continuously pulling frames into a thread-safe circular buffer.
  - `InferenceWorker`: Separate thread performing YOLO11 and ByteTrack inference, preventing inference latency from dropping ingestion FPS.
- **`registry.py`**: Lock-free worker lifecycle management, reference counting, and deduplication for webcam device `0`.

### `app/models/`
SQLAlchemy ORM definitions with cascade deletion, relational integrity, and secure password hashing.

### `app/routes/`
RESTful controllers organized by blueprint (`auth`, `cameras`, `recordings`, `main`, etc.).

### `app/templates/` & `app/static/`
Modern surveillance UI powered by Tabler (Bootstrap 5):
- Light / Dark / System theme switching with zero FOUC (flash of unstyled content).
- Full offline independence (no CDN runtime dependency).
- Real database metrics (no simulated/mock telemetry).
- Responsive Cinema Viewport with RAW / DETECTION / TRACKING stream modes.
