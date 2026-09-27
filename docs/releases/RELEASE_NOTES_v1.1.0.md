# DeepVision v1.1.0 — Production Repository Cleanup & Containerized Deployment

**Release Tag:** `v1.1.0`  
**Date:** 2026-09-27  
**Architecture:** Django 5.2 + React 19 SPA + OpenCV / YOLO11n + ByteTrack + Multi-Stage Docker  

---

## Executive Summary

DeepVision v1.1.0 delivers production repository organization and fully verified containerization. The release establishes an automated multi-stage Docker build pipeline, verified Docker Compose orchestration, automated container runtime healthchecks, persistent data lifecycle management, and a clean repository hierarchy while maintaining 100% architectural and operational parity with the native Windows DirectShow surveillance reference environment.

---

## Highlights

### 1. Production Multi-Stage Dockerization
- **Multi-Stage Build Architecture**:
  - Stage 1: `node:20-alpine` builds and optimizes the React 19 frontend assets into `deepvision_django/static/dist/`.
  - Stage 2: `python:3.11-slim` runtime environment with essential multimedia libraries (`libgl1`, `libglib2.0-0`, `curl`).
- **Optimized CPU PyTorch Integration**: Utilizes CPU-wheel index to prevent excessive CUDA bloat, keeping container content size compact (~579 MB).
- **Non-Root Security Hardening**: Runs as dedicated `deepvision` user (`UID 1000`) with least-privilege directory permissions.

### 2. Docker Compose Orchestration & Persistence
- **Persistent Volume Architecture**:
  - `./instance:/app/instance`: Preserves SQLite database (`deepvision.db`) across container lifecycles.
  - `./recordings:/app/recordings`: Persistent MP4 surveillance video archive.
  - `./evidence:/app/evidence`: Persistent forensic snapshot and clip storage.
  - `./models:/app/models`: Shared neural network model weights (`yolo11n.pt`).
- **Automated Healthcheck**: Continuous container health probe hitting `/api/health/` every 30 seconds with 3 retries.
- **Port Mapping**: Exposes unified Django and React SPA interface on `8000:8000`.

### 3. Automated Container Verification Suite
- Comprehensive 15-point automated verification script (`verification/test_docker_container.py`):
  - Container status & health probe verification (`Up (healthy)`).
  - React SPA root and static asset delivery (`index-*.js`, `index-*.css`).
  - Unauthenticated and signed-cookie authenticated API communication.
  - SOC Dashboard, Alerts, Notifications, Cameras, Evidence, and Cases API responses.
  - In-container PyTorch and Ultralytics YOLO11n model loading.
  - Container restart persistence test with zero data loss.

### 4. Professional Repository Structure & Documentation Hierarchy
- Clean repository root containing only essential project files (`manage.py`, `start_deepvision.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `.env.example`, `ARCHITECTURE.md`, `TECH_STACK.md`, `DEVELOPMENT_WORKFLOW.md`, `README.md`, `CHANGELOG.md`, `VERSION`).
- Historical phase reports, audit logs, forensic manifests, and presentation materials organized under structured subdirectories in `docs/`:
  - `docs/architecture/`
  - `docs/technical/`
  - `docs/reports/` (`phase14/`, `phase15/`, `audits/`, `forensic/`)
  - `docs/releases/`
  - `docs/project/`

### 5. Preserved Native Windows Surveillance Invariants
- DirectShow (`dshow://0`) physical camera capture remains 100% operational on native Windows.
- 29/29 automated backend architecture tests pass with zero regressions.
- Exact singleton constraints verified: 1 physical `VideoCapture` handle, 1 `CameraWorker`, 1 `InferenceWorker`, and `MODEL_LOAD_COUNT=1`.
- Complete incident scoping and data isolation verified across all forensic endpoints.

---

## Deployment Matrix: Native Windows vs. Docker

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

---

## Verification & Test Results

| Test Category | Suite File | Result | Notes |
| :--- | :--- | :--- | :--- |
| **Docker Container Runtime** | `verification/test_docker_container.py` | **15/15 PASS** | Container healthy, all APIs respond, assets served, persistence verified |
| **Native Architecture & Regression** | `verification/verify_final_restructure.py` | **29/29 PASS** | DirectShow, dual modes, singletons, recording, DB signature verified |
| **Incident Scoping & Isolation** | `verification/test_incident_scoping.py` | **PASS** | 0 cross-incident data bleed across evidence, recordings, cases, and timelines |
| **Frontend Production Build** | `npm run build` (Vite) | **PASS** | Compiled in 385ms into `deepvision_django/static/dist/` |
| **Django System Check** | `python manage.py check` | **PASS** | 0 issues identified |
| **Python Dependency Check** | `pip check` | **PASS** | No broken requirements found |

---

## Quick Start (Docker)

```powershell
# 1. Build Docker image
docker build -t deepvision:1.1.0 .

# 2. Launch container stack
docker compose up -d

# 3. Verify health & run test suite
docker compose ps
python verification/test_docker_container.py

# 4. Stop stack
docker compose down
```
