# DEEPVISION 4.0 — FILE MIGRATION & RESTRUCTURING MAP

This document maps all created, modified, retired, and consolidated files throughout the DeepVision 4.0 architecture rebuild.

---

## 1. Newly Created Files

| File Path | Purpose & Functionality |
|---|---|
| `PRD.md` | Comprehensive 23-section Product Requirements Document defining system specifications, requirements, acceptance criteria, and system contracts. |
| `docs/PROJECT_AUDIT.md` | Full forensic audit of the pre-existing codebase, identifying dead code, route collisions, security flaws, and performance bottlenecks. |
| `docs/ARCHITECTURE.md` | Authoritative system architecture document defining data pipelines, component roles, thread models, and streaming lifecycles. |
| `docs/DATABASE_DESIGN.md` | Database schema documentation detailing all 18 tables, constraints, indexes, foreign keys, and integrity verification procedures. |
| `docs/API_CONTRACTS.md` | Detailed REST API specification covering endpoints, request/response payloads, authentication headers, error formats, and status codes. |
| `docs/IMPLEMENTATION_PLAN.md` | Phase-by-phase execution blueprint with verification gates, test protocols, and rollback mechanisms. |
| `reports/DEEPVISION_4.0_IMPLEMENTATION_REPORT.md` | Comprehensive architectural implementation report with benchmark data, root cause analyses, and visual evidence references. |
| `reports/DEEPVISION_4.0_TEST_RESULTS.md` | Structured test results documentation detailing 100+ executed test assertions across all test suites. |
| `reports/DEEPVISION_4.0_FILE_MIGRATION_MAP.md` | Complete inventory of created, modified, retired, and consolidated project files (this document). |
| `reports/DEEPVISION_4.0_KNOWN_LIMITATIONS.md` | Operational boundaries, hardware sensor specifications, loopback networking considerations, and runtime notes. |
| `scripts/capture_deepvision4_screenshots.mjs` | Automated Chrome DevTools Protocol (CDP) script for capturing all 11 full-resolution workspace screenshots with authenticated session injection. |
| `verification/screenshots/final_4.0/*` (11 files) | High-resolution PNG screenshots of all 10 independent workspaces and the interactive Webcam 0 zone editor. |

---

## 2. Modified Core Files

| File Path | Scope of Modifications |
|---|---|
| `frontend/src/pages/Cameras.jsx` | Rebuilt from a 12-line stub into a 430-line independent camera inventory workspace with 10-camera grid, search/filtering, status badges, signal ping test, CRUD modals, and direct live view actions. |
| `frontend/src/App.jsx` | Removed `SecurityCenter.jsx` wrapper completely. Wired direct React.lazy imports for all 10 canonical workspaces (`Dashboard`, `Surveillance`, `Cameras`, `Alerts`, `Recordings`, `Evidence`, `Cases`, `Notifications`, `Settings`, `Help`). Added route switch cases for `camera-preview` and direct hash routes. |
| `frontend/src/components/common/Navbar.jsx` | Updated all 10 navigation items to link directly to their own pages (`#/overview`, `#/live`, `#/cameras`, `#/alerts`, `#/recordings`, `#/evidence`, `#/cases`, `#/notifications`, `#/settings`, `#/help`). Ensured active route highlighting matches current workspace. |
| `deepvision_django/apps/surveillance/camera/capture.py` | Configured DirectShow hardware capture with `CAP_PROP_BUFFERSIZE = 1`, single-slot latest-frame overwriting, and decoupled capture threads to eradicate camera lag. |
| `deepvision_django/apps/surveillance/streaming/stream_service.py` | Implemented non-blocking latest-frame consumer for MJPEG multipart delivery, preventing frame queue accumulation during network or inference slowdowns. |
| `deepvision_django/apps/surveillance/ai/model_loader.py` | Hardened thread-safe YOLO11n singleton model loader with CUDA detection fallback to optimized CPU inference. |
| `deepvision_django/apps/surveillance/ai/anomaly/anomaly_detector.py` | Added dynamic polygonal zone registration, ray-casting point-in-polygon intrusion calculation, and automated alert/evidence trigger dispatching. |
| `deepvision_django/apps/surveillance/recording/recording_service.py` | Granted recording and snapshot initiation permissions to both `operator` and `admin` roles; added RFC 7233 byte-range streaming for MP4 scrubbing. |
| `deepvision_django/apps/cameras/views.py` | Added zone management endpoints (`GET /api/cameras/<id>/zones/`, `POST /api/cameras/<id>/zones/`) with instant reload signaling to active camera workers. |
| `deepvision_django/apps/accounts/views.py` | Hardened 2FA OTP generation, PBKDF2 hashing, 15-minute expiration enforcement, and session invalidation on logout. |
| `scripts/host_camera_bridge.py` | Configured DirectShow capture loop for Webcam 0 on port 8554 with latest-frame MJPEG serving and thread safety. |

---

## 3. Retired & Eliminated Files / Patterns

| Component / Artifact | Prior Status | Disposition in DeepVision 4.0 | Rationale |
|---|---|---|---|
| `SecurityCenter.jsx` (Wrapper) | Tabbed container wrapping Alerts, Recordings, Evidence, Cases, and Notifications. | **RETIRED & DISBANDED** | Swallowed distinct functional pages into secondary tabs, causing user confusion and navigation opacity. |
| `Cameras.jsx` (12-Line Stub) | Statically redirected to `<Surveillance initialTab="manage" />`. | **REPLACED & REBUILT** | Stripped the camera inventory of its independent route, controls, and management capabilities. |
| `Monitor.jsx` (Duplicate Alias) | Duplicate component mirroring `Surveillance.jsx`. | **CONSOLIDATED** | Redundant routing artifact; consolidated into canonical `Surveillance.jsx` with direct navigation. |
| Legacy Flask/FastAPI Endpoints | Competing Python backend stubs in legacy directories. | **RETIRED** | Eliminated multi-runtime conflicts; Django 5 is the sole authoritative backend. |

---

## 4. Consolidated Architecture Overview

```
Frontend Routes:
  #/overview        -->  Dashboard.jsx       (SOC Overview & Telemetry)
  #/live            -->  Surveillance.jsx    (Live Surveillance HUD & Player)
  #/cameras         -->  Cameras.jsx         (Comprehensive Camera Inventory)
  #/alerts          -->  Alerts.jsx          (Security Events Inbox & Triage)
  #/recordings      -->  Recordings.jsx      (MP4 Recordings Vault & Scrubber)
  #/evidence        -->  Evidence.jsx        (Forensic Evidence & Chain of Custody)
  #/cases           -->  Cases.jsx           (Incident Investigation Cases)
  #/notifications   -->  Notifications.jsx   (Operator Alerts & System Feed)
  #/settings        -->  Settings.jsx        (Security Policies & System Config)
  #/help            -->  Help.jsx            (Operational Manuals & SOC Guides)

Backend Routing (Django 5):
  /api/auth/*       -->  apps.accounts       (Auth, OTP, Session Lifecycle)
  /api/cameras/*    -->  apps.cameras        (Camera Inventory & Polygon Zones)
  /api/alerts/*     -->  apps.alerts         (Security Alert Stream & Triage)
  /api/recordings/* -->  apps.recordings     (MP4 Clips & RFC 7233 Streaming)
  /api/evidence/*   -->  apps.evidence       (Forensic Snapshots & SHA-256 Hashes)
  /api/cases/*      -->  apps.core           (Incident Cases & Notes)
  /api/dashboard/*  -->  apps.core           (Aggregated SOC Metrics)
  /cameras/<id>/stream/  --> apps.surveillance (Real-Time MJPEG Multipart Delivery)

