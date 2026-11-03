# DEEPVISION — UI & Route Consolidation Specification
**Date:** October 25, 2026  
**Status:** IMPLEMENTED & VERIFIED  
**Architecture:** Single Camera-First Surveillance Workflow  
**Target Environment:** Localhost `http://127.0.0.1:8000/`  

---

## 1. Executive Summary

DeepVision previously suffered from duplicated surveillance interfaces, where `Dashboard`, `CameraPreview`, and disparate live monitoring concepts presented fragmented representations of live camera footage. 

Under the unified information architecture:
1. **`Monitor`** is the single canonical surveillance workspace. Camera footage is the primary, dominant screen content.
2. The player exposes exactly two unambiguous viewing modes:
   - **`RAW STREAM`**: Unannotated live camera feed directly from the physical DirectShow sensor (`dshow://0`).
   - **`DETECTION & TRACKING`**: Live camera feed with active YOLO11n object detections and ByteTrack persistent track IDs.
3. All legacy, redundant, or bookmark routes (`/dashboard`, `#dashboard`, `#camera-preview`, `/cameras/:id/preview`, `/live`, `/live-monitoring`) cleanly redirect to `/monitor` (or `/monitor?camera=:id`) without duplicate UI renderings or duplicate camera background threads.

---

## 2. Route Ownership Matrix

| Legacy / Requested Path | Canonical Route | Primary Job / Responsibility | Resolution Action |
|:---|:---|:---|:---|
| `/` or `#` | `/monitor` (`#monitor`) | Primary surveillance workspace with live hero camera | Canonical Default |
| `/monitor` or `#monitor` | `/monitor` (`#monitor`) | Primary surveillance workspace, RAW STREAM + DETECTION & TRACKING modes, camera quick-switcher, telemetry HUD, live recording/snapshot controls | **Canonical Surveillance Workspace** |
| `/dashboard` or `#dashboard` | `/monitor` (`#monitor`) | Previously duplicate camera view + overview metrics | **Redirects to `/monitor`** |
| `/cameras/<id>/preview` or `#camera-preview` | `/monitor?camera=<id>` | Previously separate single-camera preview player | **Redirects to `/monitor?camera=<id>`** |
| `/live`, `/live-monitoring`, `/live-feeds` | `/monitor` | Duplicate live stream variants | **Redirects to `/monitor`** |
| `/cameras` or `#cameras` | `/cameras` (`#cameras`) | Camera inventory, grid/table view, health/status filtering, connection test | **Canonical Cameras Inventory** |
| `/alerts` or `#alerts` | `/alerts` (`#alerts`) | Security incident listing, severity filter (critical, high, medium, low), details drawer, status transitions (acknowledged, resolved) | **Canonical Alerts Workspace** |
| `/recordings` or `#recordings` | `/recordings` (`#recordings`) | Surveillance recordings inventory, video playback player, filter by camera/date | **Canonical Recordings Archive** |
| `/evidence` or `#evidence` | `/evidence` (`#evidence`) | Forensics vault, snapshot and video evidence viewer, export/download, association to alerts and cases | **Canonical Evidence Vault** |
| `/cases` or `#cases` | `/cases` (`#cases`) | Incident investigation case management, case creation, alert linkage, status updates | **Canonical Cases Workspace** |
| `/notifications` or `#notifications`| `/notifications` (`#notifications`) | Real notifications history, unread counters, mark as read, clear | **Canonical Notifications Log** |
| `/settings` or `#settings` | `/settings` (`#settings`) | Operational AI parameters (YOLO threshold slider, anomaly rules toggles), hardware bridge status, user profile & session info | **Canonical Settings Workspace** |
| `/help` or `#help` | `/help` (`#help`) | SOC user guide, keyboard shortcuts (`1` RAW, `2` TRACKING, `S` Snapshot, `R` Record, `F` Fullscreen), DirectShow diagnostics | **Canonical Help & Diagnostics** |
| `/login`, `/signup`, `/forgot-password`, `/verify-email` | Auth Routes | Authenticated Django session, CSRF protection, demo session login | **Canonical Authentication** |

---

## 3. Brand Identity & Logo Assets Created

| Asset File | Format | Purpose & Description |
|:---|:---|:---|
| `frontend/public/logo.svg` | SVG Vector | Primary DeepVision horizontal brand mark with octagonal optical reticle, electric cyan accent, and wordmark |
| `frontend/src/assets/logo.svg` | SVG Vector | Source bundled primary logo asset |
| `frontend/public/logo-monochrome.svg` | SVG Vector | High-contrast monochrome / reversed white-on-dark variant for tactical surveillance viewports |
| `frontend/src/assets/logo-monochrome.svg` | SVG Vector | Source bundled monochrome logo asset |
| `frontend/public/favicon.svg` | SVG Vector | High-contrast 48x48 precision optical reticle favicon readable at 16x16, 24x24, 32x32 |
| `frontend/public/wordmark.svg` | SVG Vector | Standalone typography wordmark with `DEEP` in high-contrast white and `VISION` in electric cyan |
| `frontend/src/assets/wordmark.svg` | SVG Vector | Source bundled wordmark asset |
| `frontend/src/styles/tokens.css` | CSS Tokens | DeepVision SOC Design System Tokens: obsidian dark canvas `#090D14`, tactical cyan `#00E5FF`, cobalt `#0284C7`, emerald `#00E676`, amber `#FFB300`, critical red `#FF3D71` |

---

## 4. Frontend & Django Backend Integration Map

All canonical pages are integrated with real Django backend endpoints:

| Frontend Page / Component | Real Django Endpoint | HTTP Method | Data / Payload Handled |
|:---|:---|:---|:---|
| `Monitor` (Live Player) | `/api/cameras/<id>/stream/original/` | GET | MJPEG multipart stream (`multipart/x-mixed-replace; boundary=frame`) for **RAW STREAM** |
| `Monitor` (Live Player) | `/api/cameras/<id>/stream/tracking/` | GET | MJPEG multipart stream with real-time YOLO11n + ByteTrack overlays for **DETECTION & TRACKING** |
| `Monitor` (Snapshot Action) | `/api/cameras/<id>/snapshot/` | POST | Captures single JPEG frame and persists Evidence record to Django database |
| `Monitor` (Record Action) | `/api/cameras/<id>/record/start/` & `/stop/` | POST | Triggers per-camera surveillance clip recording persistence to `instance/recordings/` |
| `Monitor` (Channel Switcher) | `/api/cameras/` | GET | Returns real camera records from SQLite database (`deepvision.db`) |
| `Monitor` (Telemetry) | `/api/dashboard/stats/` | GET | Real-time counts for online cameras, active alerts, recordings, evidence |
| `Cameras` | `/api/cameras/` & `/api/cameras/<id>/test` | GET/POST | Camera inventory listing and live DirectShow connection verification |
| `Alerts` | `/api/alerts/` & `/api/alerts/<id>/` | GET/PATCH | Incident list, severity filtering, status transition (`acknowledged`, `resolved`) |
| `Recordings` | `/api/recordings/` & `/api/recordings/<id>/` | GET | Archived surveillance video files with HTTP 206 Partial Content streaming |
| `Evidence` | `/api/evidence/` & `/api/evidence/<id>/` | GET | Forensic snapshots and video clips captured during alerts or manual actions |
| `Cases` | `/api/cases/` & `/api/cases/<id>/` | GET/POST | Case management and alert correlation |
| `Notifications` | `/api/notifications/` | GET/PATCH | Notification log and unread counter management |
| `Settings` | `http://127.0.0.1:8554/health` & localStorage | GET | DirectShow hardware bridge health and AI inference threshold persistence |
| Authentication | `/api/auth/csrf/`, `/api/auth/login/`, `/api/auth/demo-session/`, `/api/auth/logout/` | GET/POST | Cookie-based Django session with `X-CSRFToken` verification |

---

## 5. Code & Dependency Cleanup Inventory

- **Eliminated Duplicate Interfaces:**
  - `Dashboard.jsx` was previously duplicating camera monitoring. All surveillance operations are now unified in `Monitor.jsx`. `Dashboard` cleanly routes to `Monitor`.
  - `CameraPreview.jsx` was a secondary camera preview player. Deprecated in favor of the canonical `Monitor.jsx?camera=<id>` workflow.
- **Removed Duplicate Threads / Polling:**
  - Prevented orphaned camera workers on route switching by cleaning stream image references (`imgRef.current.src = ''`) on component unmount.
  - Eliminated duplicate polling across overlapping dashboard/camera timers.
- **CSS Architecture Consolidation:**
  - Built unified `tokens.css` with semantic color variables, reducing ad-hoc hex codes across stylesheets.
  - Mapped legacy CSS variables in `globals.css` to new `--dv-*` design tokens, preserving complete layout stability without breaking existing classes.
