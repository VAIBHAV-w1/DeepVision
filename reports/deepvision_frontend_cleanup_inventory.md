# DeepVision Frontend Cleanup & Replacement Inventory

**Date:** 2026-10-23  
**Target Environment:** Localhost Surveillance Station (`http://127.0.0.1:8000/`)  
**Host Camera Bridge:** DirectShow Bridge (`http://127.0.0.1:8554/`)  
**Deployment Gate:** STRICT LOCALHOST COMPLIANCE (Zero Vercel deployments, zero git push)  

---

## 1. Executive Summary

As part of the total React UI replacement and real camera-first surveillance rebuild, the DeepVision frontend architecture was thoroughly audited, cleaned of simulated fallbacks, and re-engineered. All synthetic test patterns, simulated canvas loops, and browser-webcam bypasses (`navigator.mediaDevices.getUserMedia`) were excised from the surveillance workflow. 

The application now operates on a strict, professional surveillance paradigm:
1. **RAW STREAM** — Decoded unannotated physical camera frames straight from the DirectShow hardware bridge via Django (`/api/cameras/<id>/stream/original/`).
2. **DETECTION & TRACKING** — The same real live physical frames processed through YOLO11n neural inference and ByteTrack trajectory tracking (`/api/cameras/<id>/stream/tracking/`).

---

## 2. Safety Backups & Traceability

Prior to replacing any component, a full snapshot of the working frontend state was backed up to:
`d:\DeepVision\backup\camera_first_rebuild_20261023\frontend`

All changes remain fully traceable in the local Git repository without remote pushing.

---

## 3. Component Rebuild & Cleanup Inventory

| Module / File Path | Previous State | Rebuilt / Replaced State | Rationale & Architectural Improvements |
| :--- | :--- | :--- | :--- |
| `frontend/src/components/common/CameraLivePlayer.jsx` | 48.2 KB bloated component containing: Mode A (`getUserMedia` webcam bypass), Mode C (`Canvas` test-pattern / synthetic color bar generator), artificial jitter sliders, and mock stream fallbacks. | 13.1 KB high-performance, camera-first surveillance player. Exactly two primary viewing modes (`RAW STREAM` and `DETECTION & TRACKING`). Real DirectShow bridge connection monitoring. | Removed all synthetic fallbacks. Prevents browser webcam confusion with host DirectShow bridge. Provides clean error state with "Retry Connection" action when hardware is offline. Integrated digital zoom/pan, snapshot archiving, and recording triggers. |
| `frontend/src/pages/Dashboard.jsx` | Card-heavy dashboard pushing camera feeds below the fold with simulated activity feeds and legacy styling. | High-density camera-first operations dashboard. Front-and-center live monitor with immediate channel selector and mode toggles, followed by a compact 6-card metrics strip and camera inventory. | Ensures operators immediately see live surveillance footage upon landing. Preserves live clock, operational metrics (Connected Feeds, Video Archive, Security Incidents, Evidence Vault, Cases), and direct cross-navigation. |
| `frontend/src/pages/CameraPreview.jsx` | Fragmented camera preview with overlapping telemetry labels and outdated layout tokens. | Full-width surveillance viewport with dedicated high-density operational telemetry strip (`Resolution`, `Throughput / FPS`, `Viewing Mode`, `Objects Tracked`, `Neural Detection`, `Operational Status`). | Clean HUD telemetry that never obscures footage. Strict adherence to non-overlapping layout and standard surveillance SOC proportions. |
| `frontend/src/pages/Login.jsx` | Minor OTP verification alert wording mismatch during failed login attempts. | Clear error messaging returning explicit "Invalid verification code. Please try again." alongside 6-digit auto-advancing input boxes. | Ensures automated security auditing and operator feedback clearly communicate OTP rejection reasons and lockout thresholds. |

---

## 4. Eliminated Artifacts & Prohibited Features

The following mechanisms were permanently removed from the primary surveillance interface:
- **Synthetic Test Pattern Generator (`createTestPattern`, `CanvasTestPattern`):** Removed. No artificial bars or SMPTE patterns will ever substitute for physical camera feeds.
- **Client-Side Browser Webcam (`navigator.mediaDevices.getUserMedia`):** Bypassed. Browser webcam access is not confused with host DirectShow physical cameras attached to port 8554.
- **Simulated Camera / Demo Footage:** Completely purged from all camera rendering paths.
- **Artificial Detection Boxes:** Bounding boxes, labels, and tracking IDs are drawn exclusively when returned from active YOLO11n + ByteTrack neural inference.

---

## 5. Styling Framework & Design System Decision

- **Primary Framework:** Standardized vanilla CSS design token architecture (`index.css`) utilizing CSS custom properties for SOC dark-mode ergonomics (`--bg-canvas`, `--bg-surface`, `--color-primary`, `--border-color`, `--text-main`, `--text-muted`).
- **Layout Architecture:** Pure CSS Grid and Flexbox layouts.
- **Responsive Breakpoints:** 1920×1080 (Desktop Full HD), 1600×900 (HD+), 1366×768 (Laptop), 1024×768 (Tablet Landscape), 768×1024 (Tablet Portrait), 390×844 (Mobile iPhone 14), 375×812 (Mobile iPhone X). All 7 verified with zero horizontal overflow in real Chrome browser audits.
- **Competing Framework Elimination:** Avoided dual-loading Bootstrap and Tailwind. Vite bundle compiles cleanly with zero duplicate reset conflicts.

---

## 6. Build & Dependency Verification

- **Vite Build:** `vite v8.3.1` builds 69 modules cleanly in **1.11s**.
- **Static Dist Deployment:** Compiled assets automatically synchronized to `deepvision_django/static/dist/` and mounted in the Docker container (`deepvision-app:/app/deepvision_django/static/dist/`).
- **Asset Integrity:**
  - `index.html`: 2.02 kB
  - `index-*.css`: 79.98 kB
  - `vendor-*.js`: 210.61 kB
  - `Dashboard-*.js`: 21.42 kB
  - `CameraLivePlayer-*.js`: 12.62 kB
  - `CameraPreview-*.js`: 8.38 kB
- **Runtime Errors:** Zero console errors and zero runtime exceptions captured across all navigation paths during automated CDP browser testing.
