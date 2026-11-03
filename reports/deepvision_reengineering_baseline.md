# DEEPVISION RE-ENGINEERING BASELINE AUDIT

**Date:** 2026-10-22  
**Target Host:** `http://127.0.0.1:8000/`  
**Backend Container:** `deepvision-app` (Django on Port 8000)  
**Camera Bridge:** `http://127.0.0.1:8554` (DirectShow capture `dshow://0`)  
**Production Site:** `https://vsw-deepvision.vercel.app/` (Strictly untouched & blocked)

---

## 1. Safety, Git & Recovery State

- **Active Branch:** `main`
- **HEAD Commit:** `1b4ccab` (`fix(camera-pipeline): repair camera video rendering, YOLO tracking, and 30 mandatory smoke tests`)
- **Safety Backup Created:** `d:\DeepVision\backup\reengineering_baseline_20261022` containing intact copies of `frontend/src`, `docker-compose.yml`, and working tree snapshots.
- **Active Docker Containers:**
  - `deepvision-app` (ID `26e42df79cc7`), port `0.0.0.0:8000->8000/tcp`, status `Up (healthy)`.
- **Local Camera Service:** Port `8554` listening (`Test-NetConnection` passed with `TcpTestSucceeded: True`).
- **Production Status:** Guaranteed untouched. No remote git push or Vercel actions performed.

---

## 2. Existing Database Inventory (SQLite)

Queried via Django ORM in `deepvision-app`:
- **Users:** 16 accounts (including test operator `audit.test@deepvision.internal`)
- **Cameras:** 10 configured CCTV channels
- **Alerts:** 4,487 operational threat events
- **Incident Cases:** 841 formal investigation files
- **Surveillance Recordings:** 2,742 archived video clips
- **Forensic Evidence Assets:** 5,558 preserved items
- **Notifications:** 3,621 security notices

All existing database records and media files are mounted persistently and will remain completely intact.

---

## 3. Discovered Routes & Component Mapping

| Route URL | Component | State & Notes |
| :--- | :--- | :--- |
| `/login/` | `Login.jsx` | Fully working. 6-digit OTP verification with 60s cooldown and attempt lockout. |
| `/signup/` | `Signup.jsx` | Registration workflow with email validation. |
| `/forgot-password/` | `ForgotPassword.jsx` | Password reset OTP flow. |
| `/dashboard/` | `Dashboard.jsx` | Operational SOC metrics, camera channels grid, recent alerts feed, health status banner. |
| `/cameras/` | `Cameras.jsx` | Camera fleet gallery with status filter pills and live search. |
| `/cameras/4/preview/` | `CameraPreview.jsx` | Live streaming HUD, DirectShow feed, YOLO11n + ByteTrack detection overlay. |
| `/recordings/` | `Recordings.jsx` | Archived video library with pagination, MP4 playback modal, and Range request streaming. |
| `/evidence/` | `Evidence.jsx` | Forensic vault registry for preserved incident media. |
| `/cases/` | `Cases.jsx` | Forensic incident case tracking and investigation registry. |
| `/alerts/` | `Alerts.jsx` | Threat alerts table with severity filters, acknowledgment, and resolution workflows. |
| `/notifications/` | `Notifications.jsx` | Real-time security notice center. |
| `/help/` | `Help.jsx` | Technical operator guidance (isolated from camera grid and alerts). |

---

## 4. Current Architecture & Integration

- **Frontend:** React 18 SPA bundled with Vite into `frontend/dist` and served statically via Django's `deepvision_django/static/dist/` at `http://127.0.0.1:8000/`.
- **Backend:** Django 4.x running in Python 3.11 container (`deepvision-app`), exposing REST endpoints under `/api/`.
- **Routing:** Dual-mode routing in `App.jsx` handling both hash paths (`#dashboard`, `#cameras`) and direct pathname URLs (`/dashboard/`, `/help/`, `/alerts/`).
- **Authentication:** Session-based authentication via signed cookies with PBKDF2 password and OTP hashing, with CSRF protection enforced.
- **Inference & Streaming:** DirectShow camera input `dshow://0`, YOLO11n neural model singleton, ByteTrack object tracking, streaming over HTTP multipart and RTSP bridge.

---

## 5. UI Deficiencies to Address in Phase 2

1. **Visual Cohesion & Hierarchy:**
   - Previous designs suffered from disjointed inline styles, legacy CSS files (`app.css`, `camera.css`, `components.css`, `globals.css`) containing overlapping and redundant classes.
   - The top navigation bar and layout lack a unified operational SOC feel (some elements use oversized badges, inconsistent borders, or conflicting color schemes).
2. **Design Tokens & Spacing Scale:**
   - Design tokens are scattered across multiple CSS files with differing dark theme color variables (`--bg-canvas`, `--bg-surface`, `--color-primary`).
   - Need a single authoritative design token system in `globals.css` with clean slate/graphite dark mode, restrained status indicators (emerald green, amber warning, red critical, subtle cyan accents), and accessible typography (Inter / system sans-serif + JetBrains Mono for telemetry).
3. **Component Reusability:**
   - Common controls (buttons, badge status pills, table headers, filter bars, search inputs, modal dialogs) should be unified in `components/common/` rather than re-implemented inline across each page.
4. **Monitoring Density:**
   - Operational surveillance interfaces require high data density, clear visual hierarchy, minimal visual clutter, zero emoji icons, zero gratuitous animations, and rapid keyboard/mouse navigation.
