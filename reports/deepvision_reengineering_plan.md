# DEEPVISION TARGET ARCHITECTURE & RE-ENGINEERING PLAN

**Date:** 2026-10-22  
**Target:** Localhost SOC Re-engineering (`http://127.0.0.1:8000/`)  
**Deployment Gate:** STRICTLY BLOCKED  

---

## 1. Core Architecture Decisions

### 1.1 Single Authoritative Frontend Source Tree
- **Framework:** React 18 with Vite.
- **Serving Architecture:** Vite builds static assets into `deepvision_django/static/dist/`, which are delivered directly by Django via `WhiteNoise` or Django `staticfiles`.
- **API Communication:** Browser UI communicates via **same-origin relative paths** (`/api/...`), completely eliminating hardcoded `localhost:8000` URLs and CORS friction.
- **State & Session:** Authentication state managed via session cookies with CSRF token header (`X-CSRFToken`) on all mutation requests.
- **Routing:** Authoritative dual router in `App.jsx` supporting both direct URL navigation (`/dashboard/`, `/cameras/`, `/alerts/`, `/recordings/`, `/help/`, etc.) and hash changes without page refresh, with clean browser history preservation and zero content bleeding.

### 1.2 Design System & Visual Foundation
- **Foundation:** Restrained, high-density operational surveillance SOC interface.
- **Palette:** Dark graphite / deep slate (`#0B0F19` canvas, `#111827` surface, `#1F2937` card borders), crisp high-contrast text (`#F3F4F6` primary, `#9CA3AF` secondary), and subtle operational status colors:
  - Nominal / Online: `#10B981` (Emerald)
  - Warning / In Progress: `#F59E0B` (Amber)
  - Critical / Incident: `#EF4444` (Ruby/Red)
  - Focus / Accent: `#3B82F6` / `#06B6D4` (Cyan/Blue)
- **Typography:** Modern clean sans-serif (`Inter`, system fallback) for interface labels, monospace (`JetBrains Mono`, `ui-monospace`) for timestamps, camera channels, FPS, IP addresses, and telemetry.
- **Eliminations:** Purple gradients, oversized cartoonish pill buttons, emojis as application icons, decorative animations, fake metrics.

### 1.3 Backend & Surveillance Data Flow
```
[Browser Client]
       │
       ▼ (Same-origin relative API /api/...)
[Django 4.x in Docker]
       │
   ┌───┴───────────────────────────────┐
   │                                   │
   ▼                                   ▼
[SQLite ORM Persistence]    [Surveillance Engine (OpenCV / DirectShow)]
(Users, Cameras, Alerts,           │
 Cases, Recordings, Evidence)       ▼
                           [YOLO11n + ByteTrack Singleton]
                                    │
                                    ▼
                           [MJPEG / RTSP Frame Stream]
```

---

## 2. Implementation Work Breakdown

### Phase 2: Complete UI Redesign
1. **Design System Tokens (`frontend/src/styles/globals.css`):**
   - Clean slate/graphite theme tokens, unified typography scale, spacing tokens, button variants, card containers, tables, forms, and badges.
   - Respect `prefers-reduced-motion` and support accessible high-contrast light/dark modes.
2. **Application Shell & Navigation (`Navbar.jsx`, `AppLayout.jsx`):**
   - Re-engineer the navigation header into a sleek, compact SOC command bar with live time synchronization, camera system health indicators, navigation items with badge counts, language toggle, theme toggle, and operator session profile dropdown.
3. **Operational SOC Dashboard (`Dashboard.jsx`):**
   - Re-engineer with a high-density operational grid: Live system health strip, operational metric cards (Cameras, Recordings, Alerts, Evidence, Cases, Notifications), multi-channel camera preview gallery with live snapshot updates, recent security alerts investigation feed, and quick actions.
4. **Cameras Fleet Gallery (`Cameras.jsx`):**
   - Clean, scannable camera channel cards with real-time snapshot thumbnails, status indicators (Online/Offline/Standby), search filtering, zone filtering, and direct links to live preview and camera configuration.
5. **Live Camera Monitoring (`CameraPreview.jsx` & `CameraLivePlayer.jsx`):**
   - Clean HUD overlay (FPS, resolution, neural tracking indicator, timestamp), stream mode switcher (Original vs AI Tracking+Detection), snapshot capture, and recording toggle.
6. **Alerts & Threat Intelligence (`Alerts.jsx`):**
   - Operational security event inbox with severity badges (Critical, High, Medium, Low), status filters, real-time search, detail modal, and one-click incident escalation.
7. **Recordings Archive & Playback (`Recordings.jsx`):**
   - Grid and list views of actual archived MP4 recordings with duration, file size, timestamp, camera channel, and integrated modal video player supporting HTTP Range seeking.
8. **Evidence Vault & Cases (`Evidence.jsx`, `Cases.jsx`):**
   - Preserved forensic evidence snapshots and case file registry with formal investigation workflows.
9. **Help & Documentation (`Help.jsx`):**
   - Complete isolation from camera/alert components with clean technical documentation for CCTV setup, RTSP, and AI stream modes.
10. **Authentication (`Login.jsx`, `AuthLayout.jsx`):**
    - High-polish SOC login with credential dispatch, 6-digit OTP verification, 60-second cooldown timer, attempt lockout, and seamless dashboard transition.

### Phase 3: Frontend-to-Django Integration
- Standardize all endpoints in `frontend/src/services/api.js` using same-origin relative URLs.
- Ensure all mutation requests carry `X-CSRFToken`.
- Graceful error states and empty state rendering without fake fallback data.

### Phase 4: Codebase Cleanup
- Remove obsolete or duplicate CSS rules, dead components, and unreferenced assets.
- Document in `reports/deepvision_code_cleanup_inventory.md`.

### Phase 5: Docker & Delivery Validation
- Ensure clean Vite production build.
- Sync static distribution into container.
- Validate health endpoints and container restart integrity.

### Phase 6 & 7: Regression & Verification
- Execute full 34-point browser suite plus dedicated UI/functional tests.
