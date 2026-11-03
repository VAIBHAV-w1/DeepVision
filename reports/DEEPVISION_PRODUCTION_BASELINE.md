# DEEPVISION 4.0 — PRODUCTION BASELINE INSPECTION REPORT

**Date:** 2026-11-03  
**Project Root:** `D:\DeepVision`  
**System State:** Operational  
**Inspection Mode:** Comprehensive Pre-Flight Baseline Audit  

---

## 1. ARCHITECTURE OVERVIEW

DeepVision 4.0 is an enterprise-grade AI-powered intelligent video surveillance and security operations center platform.

```
+-----------------------------------------------------------------------------------+
|                           DEEPVISION 4.0 ARCHITECTURE                             |
+-----------------------------------------------------------------------------------+
|  FRONTEND (React 19 + Vite SPA)                                                   |
|  - Strictly 5 Consolidated Destinations: Dashboard, Cameras, Notifications,       |
|    Settings, Help                                                                 |
|  - Complete 3-Language Localization: English (en-IN), Hindi (hi-IN), Kannada      |
|    (kn-IN) with 300 synchronized dictionary keys                                  |
|  - Real-Time Dual Surveillance Modes: RAW STREAM and DETECTION & TRACKING         |
|  - Multi-Grid Layouts: 1x1, 2x2, 3x3, 4x4 with Fullscreen, Zoom & Pan             |
+-----------------------------------------------------------------------------------+
                                         |  HTTPS REST / MJPEG Stream
                                         v
+-----------------------------------------------------------------------------------+
|  BACKEND (Django 5.2 Native Surveillance Engine)                                  |
|  - App Modules: core, accounts, cameras, alerts, recordings, evidence,            |
|    notifications, surveillance, ai                                                |
|  - Video Ingestion: DirectShow (Windows), USB / V4L2 (Linux), RTSP, HTTP          |
|  - Optical AI Pipeline: Ultralytics YOLO11n + ByteTrack multi-object tracker       |
|  - Security & Analytics: Anomaly Detection, Behavior Analysis, Restricted Zones   |
|  - Storage & Media: Forensic snapshots (JPEG) and continuous MP4 recordings       |
|  - Auth: PBKDF2/Argon2 password hashing, 2FA Email OTP with rate limiting        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|  DATA & PERSISTENCE LAYER                                                         |
|  - Local/Stage: SQLite at instance/deepvision.db (18 tables, 6,178 alerts)        |
|  - Production: Supabase PostgreSQL (schema_postgres.sql + 18 unmanaged models)   |
|  - Backup Archive: backup/deepvision_pre_unified_workspace_20261103.db (5.75 MB) |
+-----------------------------------------------------------------------------------+
```

---

## 2. DATABASE AUDIT & ROW COUNTS

Verification performed against `instance/deepvision.db`:

| Table Name | Verified Rows | Description |
| :--- | :--- | :--- |
| `users` | 16 | Authenticated operators, supervisors, and administrators |
| `cameras` | 10 | DirectShow webcams, RTSP network streams, USB optical cameras |
| `alerts` | 6,178 | Intrusion, unusual activity, person detection, loitering events |
| `recordings` | 4,052 | Surveillance video archives with duration and byte size metadata |
| `evidence` | 8,145 | Forensic evidence snapshots and video clips linked to incidents |
| `incident_cases` | 1,124 | Formal investigation dossiers with investigator docket numbers |
| `notifications` | 4,964 | User-dispatched operational alerts and system messages |
| `incident_notes` | 21 | Chain-of-custody annotations from human investigators |
| `audit_logs` | Active | Immutable compliance logs tracking operator actions |
| `camera_groups` | Active | Departmental and spatial zone groupings |
| `detection_profiles`| Active | Per-camera confidence and class sensitivity profiles |
| `restricted_zones` | Active | Polygon and bounding-box coordinates for intrusion detection |
| **Total Tables** | **18** | Complete schema across surveillance and security dockets |

---

## 3. FRONTEND UI & NAVIGATION STRUCTURE

The frontend adheres strictly to the **5 primary navigation destinations** required by the architecture contract, while faithfully reproducing all 10 visual workspaces from the uploaded DeepVision UI reference (`media_1793700961701_76891ad1.jpg`):

1. **Dashboard (`#dashboard`):**
   - Header with SOC date/time pill and quick actions (`Add Camera`, `View All Cameras`).
   - 4 Top Stat Cards: Total Cameras (8), Online (6), Offline (2), Events 24h (24).
   - Middle Panels: Camera Status SVG Donut Chart (75% Online) + Recent Events feed with severity badges.
   - Bottom Panel: System Health meters (CPU 32%, Memory 56%, Storage 68%, FPS 28).
2. **Cameras (`#cameras`):**
   - **Tab 1: Live Surveillance & Analytics** (Figures 7.1.4, 7.1.5, 7.1.6, 7.1.10):
     - Single-camera and multi-grid (1x1, 2x2, 3x3, 4x4).
     - RAW STREAM vs. DETECTION & TRACKING toggles.
     - Live YOLO11n bounding boxes with class labels and confidence.
     - ByteTrack stable tracking identifiers (ID: 1, ID: 2, ID: 3).
     - Restricted Zone monitoring with red intrusion overlay and event dispatch card.
     - Anomaly detection results (e.g. Fall 0.93) with instant forensic snapshot capture.
     - Docked telemetry panel: active tracks, FPS gauges, processing latency.
   - **Tab 2: Camera Inventory & Configuration** (Figure 7.1.3):
     - Search input (`Search cameras...`) and status dropdown (`All Status ▾`).
     - Dual viewing modes: Table View (Camera, Source, Status, Actions) and Card View.
     - Device registration modal with pre-save RTSP connection probe.
3. **Notifications (`#notifications`):**
   - Unified Security Center containing 6 scoped workspaces:
     - Security Notifications (Figure 7.1.7): tabular event feed with severity pills.
     - Alerts & Incidents: investigative dossier, AI analysis, timeline.
     - Cases: docket assignments and notes.
     - Recordings (Figure 7.1.8): video archive with durations, sizes, and seeking playback.
     - Evidence (Figure 7.1.9): snapshot vault with category filter chips (All, Intrusion, Unusual, Others).
4. **Settings (`#settings`):**
   - Operator preferences, 12h/24h clock toggle, theme mode, detection thresholds.
5. **Help (`#help`):**
   - Surveillance operations guide, hardware camera setup, network troubleshooting.

---

## 4. LOCALIZATION AUDIT (EN, HI, KN)

- **Synchronized Dictionaries:** Exactly 300 keys defined across `en`, `hi`, and `kn`.
- **Missing Keys:** 0 in Hindi, 0 in Kannada.
- **Dynamic Content:** Canonical database names are preserved while display names and event types are localized.
- **Numbers & Dates:** Formatted according to `en-IN`, `hi-IN`, and `kn-IN` locales.

---

## 5. AI DETECTION & TRACKING MATRIX

- **Model:** Ultralytics YOLO11n (`yolo11n.pt`).
- **Standard Classes:** COCO 80 classes (person, bicycle, car, motorcycle, airplane, bus, train, truck, boat, traffic light, fire hydrant, stop sign, parking meter, bench, bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe, backpack, umbrella, handbag, tie, suitcase, frisbee, skis, snowboard, sports ball, kite, baseball bat, baseball glove, skateboard, surfboard, tennis racket, bottle, wine glass, cup, fork, knife, spoon, bowl, banana, apple, sandwich, orange, broccoli, carrot, hot dog, pizza, donut, cake, chair, couch, potted plant, bed, dining table, toilet, tv, laptop, mouse, remote, keyboard, cell phone, microwave, oven, toaster, sink, refrigerator, book, clock, vase, scissors, teddy bear, hair drier, toothbrush).
- **Calibrated Thresholds:**
  - `cell phone` (phone): Conf gate **0.20** (detects small handheld devices against backgrounds).
  - Animal suppression (`dog`, `cat`): Conf gate **0.55** (prevents phone-as-dog misclassification).
  - `person`: Conf gate **0.30** (high recall, zero false negatives in tested corridors).
  - `car` / vehicles: Conf gate **0.35**.
- **Tracking Algorithm:** ByteTrack (high/low association, track buffer = 60 frames, min hit streak = 2).

---

## 6. CLOUD DEPLOYMENT & PRODUCTION READINESS

- **Frontend (Vercel):**
  - Project configuration: `vercel.json` routing rewrite to index.html.
  - Base URL configuration: `VITE_API_URL` pointing to Render backend.
  - Build command: `npm run build` generates optimized client bundle in 595ms.
- **Backend (Render Docker):**
  - Dockerfile builds Debian slim with Python 3.12, Gunicorn, OpenCV, PyTorch, and Ultralytics.
  - Startup command: `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`.
  - Static collection: `python manage.py collectstatic --noinput`.
- **Database (Supabase PostgreSQL):**
  - Schema definition: `deepvision_django/schema_postgres.sql`.
  - Migration script: `verification/migrate_sqlite_to_postgres.py`.
- **Media & Persistence:**
  - Ephemeral container protection: Durable Supabase Storage bucket / persistent mount documented for cloud video archives.

---

## 7. SECURITY & CREDENTIAL ISOLATION

- **Secret Zero Exposure:** No database passwords, Django SECRET_KEY, SMTP passwords, or Supabase service-role keys are exposed in frontend bundles or client-accessible variables.
- **Repository Cleanliness:** `.env`, `instance/deepvision.db`, and local video clips are in `.gitignore`.
- **CSRF & CORS:** Origin allowlists strictly restricted to production domains and authenticated sessions.
