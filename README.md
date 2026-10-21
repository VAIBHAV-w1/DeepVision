# DeepVision — Intelligent Surveillance & Incident Monitoring Platform

## DeepVision Live Demo
Live website: [https://vsw-deepvision.vercel.app/](https://vsw-deepvision.vercel.app/)  
[Open DeepVision](https://vsw-deepvision.vercel.app/)

**GitHub Repository:** [https://github.com/VAIBHAV-w1/DeepVision](https://github.com/VAIBHAV-w1/DeepVision)  
**Live API Health Check:** [https://vsw-deepvision.vercel.app/api/health/](https://vsw-deepvision.vercel.app/api/health/)

DeepVision is a production-grade AI surveillance and incident monitoring platform structured with a decoupled **React SPA frontend** on Vercel, a **Django backend** for REST APIs and authentication, and an embedded native computer vision pipeline utilizing **OpenCV / DirectShow**, **YOLO11n (PyTorch)**, and **ByteTrack** for real-time tracking, incident evidence preservation, and forensic investigation.

---

## Component Deployment Matrix

| Component | Target Architecture | Status | URL / Location |
| :--- | :--- | :---: | :--- |
| **Vite / React SPA Frontend** | Vercel Edge CDN | **DEPLOYED (LIVE)** | [https://vsw-deepvision.vercel.app/](https://vsw-deepvision.vercel.app/) |
| **PostgreSQL Database** | Supabase Free Tier | **SCHEMA & MIGRATION READY** | DDL: `deepvision_django/schema_postgres.sql` |
| **Django REST API Gateway** | Persistent Host / Cloud VM | **PENDING PERSISTENT HOST** | Container image: `deepvision:1.1.0-hardened-candidate` |
| **AI Surveillance Engine** | On-Premises Edge / VM with GPU/CPU | **DEPLOYED (LOCAL DOCKER)** | `deepvision-app` container (port 8000) |
| **Recordings & Evidence** | Persistent Volume / Supabase Storage | **READY FOR STORAGE** | Local mount `./recordings/`, `./evidence/` |

> [!IMPORTANT]
> **HTTP 405 Method Not Allowed Resolution:**
> The previous HTTP 405 error occurred because a single blanket SPA rewrite (/(.*) -> /index.html) routed API POST requests to static HTML, which Vercel CDN rejects. This is resolved with an explicit routing precedence in root ercel.json:
> 1. /api/(.*) routes to the serverless Python WSGI bridge (pi/index.py).
> 2. /(.*) routes to the Vite single-page application (index.html).
> Both frontend and backend share the same origin, eliminating CORS issues and preserving native CSRF and session cookie security.
>
> [!NOTE]
> **Surveillance Hardware & Cloud Feasibility Boundaries:**
> Serverless cloud functions (Vercel) have bounded execution times (10s-60s) and cannot access local physical USB/DirectShow camera hardware or sustain long-lived background capture threads. Full neural YOLO11n + ByteTrack pipelines also require significant RAM/GPU beyond standard serverless function limits. DeepVision keeps its physical camera workers and YOLO inference intact on the dedicated edge / Docker host (deepvision-app), while the REST API, incident reporting, and frontend are unified on Vercel.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                   React SPA Frontend                        │
│            (Deployed on Vercel Edge CDN)                    │
│            https://vsw-deepvision.vercel.app/               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                HTTP REST & CSRF (VITE_API_BASE_URL)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    Django 5.2 Application                   │
│             (Persistent Host / Docker Runtime)              │
├──────────────────────────────┬──────────────────────────────┤
│      Database Layer          │      Surveillance Engine     │
│   • Supabase PostgreSQL      │   • CameraRegistry           │
│   • Canonical SQLite fallback│   • OpenCV / DirectShow      │
│   • PBKDF2 Password Hashing  │   • YOLO11n + PyTorch        │
│   • 18 Relational Tables     │   • ByteTrack Tracking       │
└──────────────────────────────┴──────────────────────────────┘
```

---

## Key Features

- **Alerts Forensic Operations Center & Incident Scoping**:
  - Unified forensic operations workspace: click any alert to open the incident investigation view.
  - Strict incident scoping: evidence snapshots, video recordings, case files, notes, and activity timeline are strictly correlated to the selected incident with zero cross-incident data bleed.
  - Incident-level AI forensic analysis: confidence rating, severity categorization, and chronological timeline reconstruction.
  - Global Notifications Center: separate inbox for system and event alerts with deep-linking directly to the correlated incident.

- **React SPA Frontend & Multi-Mode Surveillance Player**:
  - High-performance Single Page Application built with React 19, JavaScript ES6+, HTML5, and CSS3 via Vite.
  - Zero bloated external component libraries; clean, custom design system preserving DeepVision visual identity (Enterprise SOC Dark & Light modes).
  - Centralized API layer (`services/api.js`) with automatic CSRF token management and dynamic backend base URL configuration via `VITE_API_BASE_URL`.
  - **Multi-Mode Camera Architecture**:
    1. **Mode A (Browser-Local Hardware Webcam)**: Direct browser camera access via `navigator.mediaDevices.getUserMedia()` with user permission, hardware device enumeration, live advancing frame counter, real measured FPS & resolution telemetry, and local canvas snapshot export. Operational in all modern browsers and public cloud deployments.
    2. **Mode B (Edge Surveillance Gateway & Host Bridge)**: High-speed OpenCV / DirectShow acquisition via `scripts/host_camera_bridge.py` on `127.0.0.1:8554` connected to Django for YOLO11n detection & ByteTrack tracking. Bound privately to preserve network security.
    3. **Mode C (Synthetic SOC Calibration Feed)**: Canvas-based animated test pattern with dynamic UTC/Local timestamps, simulated moving targets, and calibrated 30 FPS feed for automated testing and calibration.
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

- **Database Safety & Multi-Database Engine Support**:
  - Embedded SQLite database (`instance/deepvision.db`) containing 18 relational tables.
  - Native Supabase / PostgreSQL engine support via `DATABASE_URL` with SSL connection pooling.
  - Automated SQLite-to-PostgreSQL migration and sequence synchronization tool (`verification/migrate_sqlite_to_postgres.py`).

---

## Supabase PostgreSQL & Storage Setup

DeepVision includes production-grade PostgreSQL DDL schema and automated data migration tooling compatible with Supabase's Free Tier.

### 1. Supabase Dashboard Steps
1. Create a free account at [supabase.com](https://supabase.com).
2. Create a dedicated project (e.g., `deepvision-db`) and set a strong database password. Keep this password safe and never share or commit it.
3. Under **Project Settings > Database**, retrieve the connection URIs:
   - **For Vercel Serverless Function (`DATABASE_URL`)**: Use the **Transaction Pooler** (port `6543` with PgBouncer) so serverless lambdas reuse connections efficiently:
     ```text
     postgresql://postgres.[project-ref]:[db-password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
     ```
   - **For Initial Data Migration (`--pg-url`)**: Use the **Direct Connection** (port `5432`) or Session Pooler:
     ```text
     postgresql://postgres.[project-ref]:[db-password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require
     ```
4. Under **Storage**, create two private storage buckets:
   - `recordings` (private)
   - `evidence` (private)

### 2. Apply PostgreSQL Schema & Migrate Data
DeepVision provides an automated, non-destructive migration script that copies data from a verified SQLite backup without touching the live SQLite database:

```powershell
# Step 1: Create a consistent, verified SQLite backup using SQLite Online Backup API
python verification/create_consistent_backup.py

# Step 2: Test migration in dry-run mode (read-only inspection)
python verification/migrate_sqlite_to_postgres.py --dry-run

# Step 3: Apply PostgreSQL schema and migrate all 18 tables to isolated Supabase test target
$env:DATABASE_URL="postgresql://postgres.[project-ref]:[db-password]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require"
python verification/migrate_sqlite_to_postgres.py --apply --confirm-isolated-target
```

The migration tool automatically:
- Enforces safety gates prohibiting migration from `instance/deepvision.db`.
- Requires `--confirm-isolated-target` to prevent accidental overwrites.
- Executes `deepvision_django/schema_postgres.sql` (creating all 18 tables, primary keys, and secondary indexes) inside an atomic transaction.
- Aborts repeat runs safely (`check_destination_populated`) unless `--drop-first` is explicitly specified.
- Inserts data while preserving primary keys, user roles, and password hashes.
- Resets all serial sequences (`setval`) to match `MAX(id) + 1`.
- Compares source and target row counts, ID ranges, and credentials.
- Redacts all passwords and credentials from console output.

---

## Environment Variables Configuration

Copy `.env.example` to `.env` and configure appropriate variables. **Never commit `.env` to version control.**

```ini
# Django Core Settings
DJANGO_SECRET_KEY=your_secure_random_django_secret_key_at_least_32_chars
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,your-backend-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,https://frontend-ten-tau-nm1m468imk.vercel.app

# Database Configuration (Defaults to embedded SQLite if USE_POSTGRES is false)
DATABASE_URL=sqlite:///instance/deepvision.db

# Supabase / PostgreSQL Configuration (Uncomment to use Supabase):
# USE_POSTGRES=True
# DATABASE_URL=postgresql://postgres.[project-ref]:[db-password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require
# SUPABASE_URL=https://[project-ref].supabase.co
# SUPABASE_ANON_KEY=your_supabase_anon_key_here
# SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here

# Frontend Configuration (for Vercel)
# VITE_API_BASE_URL=https://your-backend-domain.com
```

---

## Directory Structure

```text
D:\DeepVision
│
├── manage.py                     # Root Django management entrypoint
├── start_deepvision.py           # Production application launcher
├── requirements.txt              # Core Python runtime dependencies
├── Dockerfile.hardened           # Production hardened Dockerfile
├── docker-compose.yml            # Production container configuration
├── README.md                     # Project overview and run guide
├── ARCHITECTURE.md               # Detailed architectural specification
│
├── deepvision_django/            # Django backend & REST APIs
│   ├── config/                   # Settings, URLs, WSGI, and ASGI
│   ├── schema_postgres.sql       # Canonical PostgreSQL/Supabase schema DDL
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
│   ├── vercel.json               # Vercel SPA routing configuration
│   ├── vite.config.js            # Vite build configuration (Vercel & Docker dual-target)
│   ├── src/
│   │   ├── components/           # UI components (cameras, alerts, modals)
│   │   ├── pages/                # Dashboard, Cameras, Recordings, Evidence, Alerts
│   │   ├── services/             # API services with dynamic VITE_API_BASE_URL
│   │   └── App.jsx               # Client-side router
│
├── instance/
│   ├── deepvision.db             # Canonical SQLite database (18 tables)
│   ├── recordings/               # Stored surveillance MP4 files
│   └── evidence/                 # Forensic snapshot images & incident clips
│
├── verification/                 # Automated verification & test suites
│   ├── create_consistent_backup.py      # SQLite Online Backup API tool
│   ├── migrate_sqlite_to_postgres.py    # PostgreSQL/Supabase migration & verification
│   ├── secret_scanner.py                # Secret and credential protection scanner
│   ├── test_backup_and_rollback_safety.py # Backup consistency validation
│   └── verify_hardened_container.py     # Container regression test suite
└── DeepVision-1.1.0/             # Release distribution package & setup scripts
```

---

## Docker Deployment

DeepVision provides a hardened, non-root Docker container image (`deepvision:1.1.0-hardened-candidate`) packaged for production deployment.

### 1. Build or Load the Image
```powershell
# Build from source:
docker build -f Dockerfile.hardened -t deepvision:1.1.0-hardened-candidate .

# Or load from release archive:
docker load -i DeepVision-1.1.0\DeepVision-1.1.0-hardened-candidate.tar
```

### 2. Run with Docker Compose
```powershell
docker compose up -d
```

### 3. Verify Health & Status
```powershell
docker compose ps
curl http://127.0.0.1:8000/api/health/
```

---

## Native Windows Quick Start

### Prerequisites
- Python 3.10+ (Running on Python 3.14.7 / 3.11 AMD64)
- Node.js 18+ and npm (for frontend building)
- Local webcam or DirectShow-compatible capture device (`dshow://0`)

### 1. Backend Setup
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Frontend Build
```powershell
cd frontend
npm install
npm run build
cd ..
```

### 3. Launch Application
```powershell
python start_deepvision.py
```
Access locally at **http://127.0.0.1:8000/**.

---

## Running Verification Tests

```powershell
# 1. Full security & secret scan:
python verification/secret_scanner.py

# 2. SQLite Online Backup verification:
python verification/create_consistent_backup.py

# 3. PostgreSQL migration dry-run inspection:
python verification/migrate_sqlite_to_postgres.py --dry-run

# 4. Production container health test:
python verification/verify_hardened_container.py
```

---

## License & Compliance

DeepVision is developed and maintained for secure video surveillance and operational intelligence. All source code, dependencies, and deployment templates adhere to strict security isolation and data preservation standards.
