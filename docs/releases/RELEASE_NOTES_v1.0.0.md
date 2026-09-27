# DeepVision v1.0.0 — Full-Stack Intelligent Surveillance & Forensic Operations Center

**Release Tag:** `v1.0.0`  
**Commit SHA:** `3327901`  
**Date:** 2026-09-27  
**Architecture:** Django 5.2 + React 19 SPA + OpenCV / YOLO11n + ByteTrack  

---

## Highlights

### 1. Alerts Forensic Operations Center
- Incident-centric workspace in React frontend with unified master inbox and detailed incident inspection.
- Instant switching between incidents with zero cross-incident data bleed.
- Integrated quick actions for status triage (New, In Progress, Resolved, Dismissed).

### 2. Incident-Scoped Evidence, Recordings & Cases
- **Evidence Vault**: Strictly filtered to the selected incident (`/api/incidents/<id>/evidence/`).
- **Video Recordings**: Scoped playback clips matching the incident timeframe (`/api/incidents/<id>/recordings/`).
- **Active Cases**: Case management, notes, and activity timeline strictly correlated to the selected incident.
- **Audio Truthfulness**: Video player metadata truthfully indicates audio availability (`Audio: Not Available` for video-only CCTV streams).

### 3. Independent Notification Center
- Global notification inbox decoupled from incident-specific alerts (`/notifications`).
- Deep-linking directly from notifications into the correlated incident workspace.
- Clear/read controls for operator workflow management.

### 4. High-Performance Surveillance Engine & Dual Modes
- Single-process concurrency model hosting Django REST APIs and native surveillance engine.
- Exactly 1 physical `VideoCapture` handle, 1 `CameraWorker`, 1 `InferenceWorker`, and singleton `YOLO11n` instance during active monitoring.
- Instant mode toggling:
  - **ORIGINAL**: Raw CCTV direct stream with low latency.
  - **TRACKING + DETECTION**: Real-time object detection and trajectory tracking using YOLO11n and ByteTrack.

### 5. Production Authentication & Security Guardrails
- Standard PBKDF2 (`pbkdf2_sha256`) password hashing for all operator accounts.
- Backward compatibility and auto-upgrade from legacy password hashes upon successful login.
- Cryptographic 6-digit OTP verification for secure email password reset.
- Signed-cookie sessions (`deepvision_django_session`) and full CSRF protection.

---

## Verification & Test Results

All verification suites executed and verified:
- **Backend Architecture & APIs**: 29/29 invariant checks passed (`verification/verify_final_restructure.py`).
- **Incident Scoping & Forensic Isolation**: Passed with zero cross-incident data bleed (`verification/test_incident_scoping.py`).
- **End-to-End Browser Automation**: Passed across 13 core SOC workflows using Chrome DevTools Protocol (`verification/run_incident_forensics_browser_suite.mjs`).
- **Database Schema Invariants**: 18 SQLite tables verified intact with zero schema drift.
- **Single-Process Engine**: Verified singleton AI weights and zero lock contention.

---

## Quick Start

```powershell
# 1. Virtual Environment & Dependencies
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Environment Configuration
copy .env.example .env

# 3. Compile Frontend Bundle
cd frontend
npm install
npm run build
cd ..

# 4. Launch DeepVision
python start_deepvision.py
```
Open **http://127.0.0.1:8000/** in your browser.
