# ORIGINAL DEEPVISION UI INVENTORY & VISUAL CONTRACT
**Date**: September 26, 2026  
**Source of Truth Directory**: `d:\DeepVision\deepvision_django\templates\` and `d:\DeepVision\deepvision_django\static\css\`  
**Target Migration**: React 19 + Vite SPA (`d:\DeepVision\frontend\src\`)

---

## 1. Executive Summary & Design System Source

The original DeepVision UI was built upon the **Editorial SaaS / Modern Surveillance SOC** design system.
Unlike generic admin templates or futuristic AI concepts, DeepVision's visual identity combines:
1. High-clarity operational surveillance interfaces (dense telemetry, HUD overlays, high-contrast video feeds).
2. Refined editorial typography and layout (`Plus Jakarta Sans` for headers, `Inter` for interface elements, `JetBrains Mono` for video timestamps and telemetry).
3. A dual-theme palette: **Light Canvas** (`#fbfbfe` surface with `#ffffff` cards) and **Dark SOC** (`#0b0f17` surface with `#121824` cards) governed by standard CSS custom properties.
4. Top header navigation centered on pill buttons (`.nav-link-pill`), a dedicated brand logo with custom emblem (`.brand-emblem`), a 3-way theme switcher (Light / Dark / System), and a floating interactive Assistant chatbot widget.

---

## 2. Design Tokens & Color Palette

### 2.1 Color Tokens
| Token | Light Theme Value | Dark Theme Value (`[data-theme="dark"]`) | Description |
|---|---|---|---|
| `--bg-canvas` | `#fbfbfe` | `#0b0f17` | Root background |
| `--bg-surface` | `#ffffff` | `#121824` | Primary card / container background |
| `--bg-surface-secondary` | `#f4f6fa` | `#182030` | Sub-panels, table headers, hover states |
| `--text-primary` | `#0f172a` | `#f8fafc` | Main headings and high-contrast text |
| `--text-secondary` | `#475569` | `#94a3b8` | Subtitles, helper text, labels |
| `--text-muted` | `#64748b` | `#64748b` | Timestamps, inactive states, placeholder text |
| `--border-subtle` | `#e2e8f0` | `#1e293b` | Divider lines and container borders |
| `--border-focus` | `#3b82f6` | `#60a5fa` | Focus outlines and active states |
| `--color-primary` | `#2563eb` | `#3b82f6` | DeepVision signature blue |
| `--color-success` | `#10b981` | `#34d399` | Live streams, active cameras, operational badges |
| `--color-warning` | `#f59e0b` | `#fbbf24` | System warnings, pending alerts |
| `--color-danger` | `#ef4444` | `#f87171` | Critical alerts, recording indicators, offline state |
| `--color-info` | `#06b6d4` | `#22d3ee` | Telemetry highlights, tracking IDs |

### 2.2 Typography
- **Headings / Brand**: `'Plus Jakarta Sans', system-ui, -apple-system, sans-serif`
- **Body / Interface**: `'Inter', system-ui, -apple-system, sans-serif`
- **Telemetry / Timestamps / Monospace**: `'JetBrains Mono', 'Fira Code', monospace`

### 2.3 Radius & Elevation
- `--radius-sm`: `6px`
- `--radius-md`: `10px`
- `--radius-lg`: `16px`
- `--radius-full`: `9999px`
- `--shadow-sm`: `0 1px 2px rgba(0, 0, 0, 0.05)`
- `--shadow-card`: `0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)`
- `--shadow-hover`: `0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04)`

---

## 3. Structural Layout Inventory

### 3.1 App Header (`.app-header`)
- **Brand Column (Left)**:
  - `.brand-emblem`: 36x36px rounded square with gradient background and eye/camera SVG icon.
  - `.brand-title`: "DeepVision" (`1.25rem`, bold `Plus Jakarta Sans`).
  - `.brand-tagline`: "Intelligent Surveillance" (`0.75rem`, muted uppercase).
- **Navigation (Center)**:
  - Container: `.nav-links-center`
  - Items: Pill tabs (`.nav-link-pill`) with subtle hover and active state (`.active` with primary accent background and text).
  - Links:
    1. Dashboard
    2. Cameras
    3. Alerts
    4. Evidence
    5. Recordings
    6. Cases
    7. Notifications
- **Controls (Right)**:
  - Theme Toggle: 3-way segmented or toggle button (Dark / Light / System auto).
  - Notifications Bell: Badge count indicator (`.badge-counter`).
  - User Badge (`.user-profile-badge`): User initials avatar, username display, and dropdown menu (Settings, Logout).

### 3.2 Floating DeepVision Assistant (`.deepvision-assistant-widget`)
- Located in bottom right corner (`fixed bottom: 24px; right: 24px; z-index: 1000`).
- Trigger button with pulse ring animation and robot/chat icon.
- Slide-up panel with chat interface, quick suggestion chips, message history, and typing indicator.

---

## 4. Page-by-Page Inventory & Visual Layout

### 4.1 Dashboard (`pages/dashboard/index.html`)
1. **Hero Editorial Section (`.hero-editorial`)**:
   - Left side: Prominent welcome headline ("Operational Intelligence Platform"), summary statement, and Primary Action ("View Live Cameras" / "System Status").
   - Right side: Hero visual container with CCTV frame graphic (`hero_camera.png`) and live status badge.
2. **System Status Ribbon (`.status-overview-strip`)**:
   - Metrics strip showing: Cameras Online, Native Django Engine (DirectShow/OpenCV), YOLO11n + ByteTrack Inference, Active Recordings, Database Integrity (`cc2d13f77b681107`).
3. **Core Metrics Grid (`.metrics-grid`)**:
   - 4 Cards: Active Cameras, Total Alerts, Active Cases, Stored Recordings.
   - Clean card styling with icon, value, change indicator, and direct link.
4. **Live Cameras Snapshot Grid (`.dashboard-cameras-grid`)**:
   - Quick preview cards of active camera feeds with Live badge, camera ID, and "Open Monitor" CTA.
5. **Recent Events & Activity Log (`.recent-activity-panel`)**:
   - Split panel showing recent system alerts and recent recordings.

### 4.2 Cameras Page (`pages/cameras/index.html`)
1. **Header & Action Bar**:
   - Title: "Surveillance Cameras"
   - Active stream counters (Online / Offline).
   - "Refresh Feeds" button.
2. **Camera Grid (`.cameras-grid`)**:
   - Camera cards displaying:
     - 16:9 thumbnail preview container.
     - Live stream state badge (`LIVE` green / `STANDBY` amber / `OFFLINE` gray).
     - Camera Name / Index (e.g. `Camera 0 (DirectShow Native)`).
     - Resolution & FPS badge.
     - Quick action buttons: "Launch Monitor", "Toggle Recording", "Take Snapshot".

### 4.3 Camera Preview Monitor (`pages/cameras/preview.html`) — Highest Priority
**Layout**: 3-Column Surveillance Control Desk (`.preview-layout-grid`)
1. **Column 1: Camera Specs & Telemetry (`.camera-telemetry-col`)**:
   - Device Info card (Device Name, Driver: DirectShow Native, Backend: OpenCV 5.0, Resolution: 640x480, FPS Target: 30).
   - Stream Telemetry card (Stream latency, Bandwidth, Frame counter, Encoding: MJPEG).
   - Active Storage card (Recording status, Evidence captures count).
2. **Column 2: Center Monitor (`.center-monitor-col`)**:
   - 16:9 monitor frame (`.video-monitor-frame`) with dark bezel and scanline-free glass reflection styling.
   - **In-Stream Header Overlay**:
     - Left: Live badge (`● LIVE`) + Camera Identifier + Resolution (`640x480`).
     - Right: Live digital clock with millisecond precision (`HH:mm:ss.ms`) in `JetBrains Mono`.
   - **MJPEG Video Stream**:
     - `<img>` element rendering `/api/v1/cameras/<id>/stream/?mode=<mode>`.
   - **Mode Switch Overlay**:
     - Floating smooth spinner/toast showing "Switching to Tracking + Detection..." or "Switching to Original...".
   - **Bottom HUD Telemetry Bar (`.monitor-hud-bar`)**:
     - Left: Stream Mode (`ORIGINAL` or `TRACKING + DETECTION`).
     - Center: FPS counter (`~30.0 FPS`) & Detected Objects counter (`Objects: 0`).
     - Right: Inference Latency (`~28ms`) & Model Tag (`YOLO11n + ByteTrack`).
3. **Column 3: Control & AI Inspection Panel (`.controls-panel-col`)**:
   - **Mode Selection Box**:
     - **Segmented Control** with EXACTLY TWO modes:
       1. `ORIGINAL` (Clean raw CCTV feed)
       2. `TRACKING + DETECTION` (YOLO11n bounding boxes + ByteTrack persistent IDs)
   - **Surveillance Actions**:
     - "Start / Stop Recording" (with red blinking recording indicator).
     - "Capture Snapshot" (instant snapshot to Evidence library).
     - "Fullscreen Monitor" (expands monitor to full display).
     - "Reconnect Feed" (forces stream refresh).
   - **AI Pipeline Telemetry**:
     - Inference Engine: PyTorch CPU (YOLO11n).
     - Object Tracker: ByteTrack.
     - Tracked IDs inspector table / tag list.

### 4.4 Recordings Page (`pages/recordings/index.html` & `detail.html`)
1. **Header & Filter Toolbar**:
   - Search by filename or camera.
   - Date range selector.
   - Filter by status / duration.
2. **Recordings Table & Grid View**:
   - Columns: Thumbnail, Filename, Camera, Duration, File Size, Created Timestamp, Actions.
   - Actions: "Play Video", "Download MP4", "File Details".
3. **HTTP 206 Video Player Modal (`.video-playback-modal`)**:
   - Native HTML5 `<video>` player pointing to `/api/v1/recordings/<id>/stream/`.
   - Timeline seeking support via HTTP 206 Partial Content.
   - Metadata overlay (camera ID, duration, timestamp).

### 4.5 Evidence Page (`pages/evidence/index.html` & `detail.html`)
1. **Evidence Gallery**:
   - Grid of forensic snapshots and video clips captured manually or automatically via alerts.
   - Card displays thumbnail preview, incident type, camera tag, timestamp, and alert link.
2. **Evidence Detail Drawer / Modal**:
   - Full resolution image/clip preview.
   - Hash / Integrity signature display.
   - Case linking action.

### 4.6 Alerts Page (`pages/alerts/index.html` & `detail.html`)
1. **Incident Alerts Feed**:
   - Filter by Severity (`CRITICAL`, `WARNING`, `INFO`).
   - Filter by Status (`NEW`, `ACKNOWLEDGED`, `RESOLVED`).
2. **Alert Row / Card Details**:
   - Severity pill (`.badge-danger`, `.badge-warning`).
   - Incident description, Camera, Trigger timestamp.
   - Actions: "Acknowledge", "Escalate to Case", "View Evidence".

### 4.7 Cases Page (`pages/cases/index.html` & `detail.html`)
1. **Investigation Cases Table**:
   - Case Number (e.g. `CASE-2026-001`), Title, Priority, Assigned Investigator, Status.
2. **Case Detail View**:
   - Case header with status pills.
   - Incident Notes section (`case.alert.incident_notes` properly bound).
   - Linked evidence items list.
   - Add note / update status actions.

### 4.8 Notifications Page (`pages/notifications/index.html`)
1. **Notifications Center**:
   - Filter tabs: "All", "Unread", "System", "Security".
   - "Mark all as read" button.
2. **Notification Item**:
   - Icon indicating notification category.
   - Title, message, timestamp, unread indicator dot.
   - Direct link to referenced camera / alert / case.

### 4.9 Authentication Pages (`templates/auth/` & `layouts/auth.html`)
1. **Container (`.auth-page-wrap`)**:
   - Centered card layout with subtle backdrop pattern.
   - Header with `.brand-emblem`, "DeepVision", and page-specific subtitle.
2. **Card Structure (`.auth-card-clean`)**:
   - Form fields with floating labels or clean top labels, focused blue border, and validation error messages.
   - Submit button (`.btn-primary.btn-block`) with loading spinner.
   - Bottom links (e.g. "Forgot password?", "Already have an account? Sign in", "Need an account? Sign up").
3. **Specific Pages**:
   - **Login**: Email/Username, Password, Remember Me, Sign In CTA.
   - **Signup**: Full Name, Email, Password, Confirm Password, Register CTA.
   - **Verify Email (OTP)**: 6-digit OTP code inputs with auto-focus and resend countdown.
   - **Forgot Password**: Email input, Send Reset Code CTA.
   - **Reset Password**: OTP code, New Password, Confirm New Password CTA.

---

## 5. CSS Porting & Asset Plan

1. **CSS Files to Port into React**:
   - Copy or merge exact styles from:
     - `deepvision_django/static/css/app.css` -> `frontend/src/styles/app.css` (root tokens, typography, utilities, buttons, forms).
     - `deepvision_django/static/css/components.css` -> `frontend/src/styles/components.css` (header, nav pills, cards, badges, modals, assistant chatbot).
     - `deepvision_django/static/css/pages/preview.css` -> `frontend/src/styles/preview.css` (3-column camera monitor, HUD overlays, video frame).
     - `deepvision_django/static/css/pages/dashboard.css` -> `frontend/src/styles/dashboard.css` (hero banner, metrics, status strip).
     - `deepvision_django/static/css/pages/cameras.css` -> `frontend/src/styles/cameras.css` (camera cards, stream thumbnails).
     - `deepvision_django/static/css/pages/recordings.css` -> `frontend/src/styles/recordings.css` (recordings table, video modal).
2. **Static Images & Assets**:
   - `hero_camera.png` from `deepvision_django/static/images/` -> `frontend/public/images/` or direct static reference.
   - Eye/Camera emblem SVG inline or as reusable React component.

---

## 6. Verification Checklist
- [x] All 9 core pages inventoried against original templates.
- [x] All CSS classes, design tokens, and typography cataloged.
- [x] Exact camera preview 3-column layout and two modes (`ORIGINAL` and `TRACKING + DETECTION`) defined.
- [x] Theme system (Light / Dark SOC / Auto) documented.
- [x] Ready to implement in React 19 SPA.
