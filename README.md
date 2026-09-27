# DeepVision — Intelligent Surveillance & Incident Monitoring Platform

DeepVision is a production-grade, local AI surveillance platform structured as a modern **React SPA frontend** connected to a **Django backend**, backed by an embedded native computer vision pipeline utilizing **OpenCV / DirectShow**, **YOLO11n (PyTorch)**, and **ByteTrack** for real-time tracking, incident evidence preservation, and forensic investigation.

---

## Architecture Overview

```text
React SPA Frontend (Vite)
        ↓  (HTTP/JSON REST & Multipart MJPEG)
Django 5.2 Application (:8000)
        ↓  (Native In-Process Services)
Surveillance Engine (CameraRegistry, InferenceRegistry)
        ↓
OpenCV / DirectShow (dshow://0)
        ↓
YOLO11n + PyTorch (Singleton Model Weights)
        ↓
ByteTrack (Kalman Filtering & Hungarian Association)
        ↓
Recording / Alerts / Forensic Evidence / Cases / Notifications
        ↓
SQLite (instance/deepvision.db - 18 Tables)
```

---

## Key Features

- **Alerts Forensic Operations Center & Incident Scoping**:
  - Unified forensic operations workspace: click any alert to open the incident investigation view.
  - Strict incident scoping: evidence snapshots, video recordings, case files, notes, and activity timeline are strictly correlated to the selected incident with zero cross-incident data bleed.
  - Incident-level AI forensic analysis: confidence rating, severity categorization, and chronological timeline reconstruction.
  - Global Notifications Center: separate inbox for system and event alerts with deep-linking directly to the correlated incident.

- **React SPA Frontend**:
  - High-performance Single Page Application built with React 19, JavaScript ES6+, HTML5, and CSS3 via Vite.
  - Zero bloated external component libraries; clean, custom design system preserving DeepVision visual identity (SOC Dark & Daylight modes).
  - Centralized API layer (`services/api.js`) with automatic CSRF token management.
  - Interactive live camera feeds with instantaneous mode toggling between:
    1. **ORIGINAL**: Raw CCTV video passthrough.
    2. **TRACKING + DETECTION**: Deep vision inference with persistent trajectory IDs, bounding boxes, and confidence levels.
  - Dedicated pages for Dashboard, Cameras, Recordings, Forensic Evidence, Security Alerts, Incident Cases, and Notification Center.
  - Integrated Assistant Chat powered by grounded surveillance telemetry.

- **Django Native Surveillance Core**:
  - Unified Django 5.2 architecture hosting both REST APIs and the native surveillance engine.
  - Single-process concurrency model: exactly 1 physical `VideoCapture` handle, 1 `CameraWorker`, 1 `InferenceWorker`, and 1 `YOLO11n` instance during active monitoring.
  - Real-time video ingestion without dropped frames or lock contention.
  - OpenCV VideoWriter recording to MP4 with HTTP 206 Partial Content range playback and truthful audio capability reporting.

- **Authentication & Security**:
  - Django signed-cookie sessions (`deepvision_django_session`).
  - Standard PBKDF2 (`pbkdf2_sha256`) password hashing for all new and updated user credentials.
  - Backward compatibility with legacy `scrypt` password hashes (with transparent auto-upgrade to PBKDF2 upon successful verification).
  - Cryptographic 6-digit OTP verification with 15-minute expiration and rate limiting.
  - Full CSRF protection and path traversal guards across all media access points.

- **Database Safety & Integrity**:
  - Embedded SQLite database (`instance/deepvision.db`) containing 18 relational tables.
  - Zero schema drift, zero unverified migrations.

---

## Directory Structure

```text
D:\DeepVision
│
├── manage.py                     # Root Django management entrypoint
├── start_deepvision.py           # Production application launcher
├── requirements.txt              # Core Python runtime dependencies
├── README.md                     # Project overview and run guide
├── ARCHITECTURE.md               # Detailed architectural specification
├── TECH_STACK.md                 # Verified runtime technology matrix
│
├── deepvision_django/            # Django backend & REST APIs
│   ├── config/                   # Settings, URLs, WSGI, and ASGI
│   ├── apps/
│   │   ├── accounts/             # Authentication, PBKDF2 models, OTP
│   │   ├── core/                 # REST API layer, media services, assistant
│   │   ├── cameras/              # Camera models, stream views, device controls
│   │   ├── recordings/           # Recording registry and playback views
│   │   ├── alerts/               # Security alerts and incident cases
│   │   ├── evidence/             # Evidence vault models and views
│   │   ├── notifications/        # User notifications
│   │   └── surveillance/         # In-process camera & inference worker engine
│   └── static/dist/              # Compiled production React frontend bundle
│
├── frontend/                     # React + Vite source code
│   ├── src/
│   │   ├── components/           # Common, camera, dashboard, and layout components
│   │   ├── pages/                # Dashboard, Cameras, Recordings, Evidence, Alerts, Cases, Auth
│   │   ├── layouts/              # AppLayout (Navbar, Sidebar) & AuthLayout
│   │   ├── services/             # Centralized API clients (auth, camera, recordings, etc.)
│   │   ├── hooks/                # useAuth, useCamera, useNotifications
│   │   ├── styles/               # Design system stylesheets
│   │   ├── utils/                # CSRF, formatters, constants
│   │   ├── App.jsx               # Client-side router and view controller
│   │   └── main.jsx              # React application entrypoint
│   ├── package.json              # Frontend dependencies and build scripts
│   └── vite.config.js            # Vite build configuration (outputs to static/dist/)
│
├── models/
│   └── yolo11n.pt                # YOLO11n weights (5.35 MB)
│
├── instance/
│   ├── deepvision.db             # SQLite database (18 tables)
│   ├── recordings/               # Stored surveillance MP4 files
│   └── evidence/                 # Forensic snapshot images & incident clips
│
├── backups/                      # Configuration & schema archives
└── verification/                 # Automated test and health verification scripts
```

---

## Deployment Options: Native Windows vs. Docker

| Capability | Native Windows (Reference Environment) | Linux Docker Container (`deepvision:1.1.0`) |
| :--- | :--- | :--- |
| **Django Application & APIs** | ✅ Full support (`:8000`) | ✅ Full support (`:8000`) |
| **React SPA Production UI** | ✅ Pre-compiled Vite bundle | ✅ Built in multi-stage image |
| **Session & OTP Authentication** | ✅ Supported (PBKDF2) | ✅ Supported (PBKDF2) |
| **Forensic Operations Center** | ✅ Supported | ✅ Supported |
| **HTTP 206 Partial Playback** | ✅ Supported | ✅ Supported |
| **Persistent Storage & DB** | ✅ Host filesystem | ✅ Volume mounts (`./instance`, `./recordings`, etc.) |
| **PyTorch & Ultralytics AI** | ✅ Supported (CPU) | ✅ Supported (CPU) |
| **DirectShow Physical Webcam** | ✅ Supported (`dshow://0`) | ⚠️ **Host-only Limitation** (Linux containers cannot directly access Windows DirectShow drivers) |

> [!NOTE]
> **Hardware Boundary**: DirectShow (`dshow://0`) is a proprietary Windows multimedia framework. Standard Linux containers cannot bind directly to physical DirectShow webcams without host-level virtualization drivers. Native Windows remains the reference operational deployment for live USB/DirectShow camera capture. The Docker deployment serves as the portable application, API, forensic operations, and data management runtime.

---

## Docker Quick Start

### 1. Prerequisites
- Docker Engine 20.10+ / Docker Desktop (WSL 2 on Windows)
- Docker Compose v2+

### 2. Build the Production Image
```powershell
docker build -t deepvision:1.1.0 .
```

### 3. Start with Docker Compose
```powershell
docker compose up -d
```

### 4. Verify Container Health & Status
```powershell
docker compose ps
curl http://127.0.0.1:8000/api/health/
```

### 5. Run the Automated Docker Verification Suite
```powershell
python verification/test_docker_container.py
```

### 6. Stop Container
```powershell
docker compose down
```

---

## Native Windows Quick Start

### Prerequisites
- Python 3.10+ (Running on Python 3.14.7 / 3.11 AMD64)
- Node.js 18+ and npm (for frontend building)
- Local webcam or DirectShow-compatible capture device (`dshow://0`)

### 1. Backend Setup
Activate the virtual environment and ensure dependencies are installed:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy the sample environment file and configure your local settings:
```powershell
copy .env.example .env
```
*(Configure `DJANGO_SECRET_KEY`, database paths, and optional SMTP settings in `.env`)*

### 3. Frontend Build
To compile the React frontend bundle:
```powershell
cd frontend
npm install
npm run build
cd ..
```
The output bundle will be placed directly in `deepvision_django/static/dist/`.

### 4. Launch Application
Launch the unified server using the production runner:
```powershell
python start_deepvision.py
```

The application is accessible locally at:
**http://127.0.0.1:8000/**

---

## Running Verification Tests

### Native Windows Full-Stack & Camera Regression Suite
To execute the 29-point automated test suite covering all APIs, authentication, streams, singletons, and database invariants:
```powershell
python verification/verify_final_restructure.py
```

### Incident Scoping & Data Isolation Suite
To verify zero cross-incident data bleed:
```powershell
python verification/test_incident_scoping.py
```

### Containerized Runtime Verification Suite
To verify the Docker deployment:
```powershell
python verification/test_docker_container.py
```

---

## Development & Release Workflow

DeepVision adheres to Semantic Versioning (`MAJOR.MINOR.PATCH`) with immutable version tags for every verified release. For details on the development process, testing gates, and release procedures, refer to [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) and the [CHANGELOG.md](CHANGELOG.md).
