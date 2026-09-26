# DEEPVISION — MASTER INCIDENT FORENSICS & SCOPING AUDIT REPORT
===============================================================================

**Date:** September 27, 2026  
**Auditor:** Antigravity Autonomous Security & Forensics Agent  
**Target System:** DeepVision Intelligent AI Surveillance Architecture  
**Database Schema Signature:** `cc2d13f77b681107` (18 tables, SQLite)  
**Primary Objective:** Strict Incident-Level Data Scoping, Forensics Isolation, Truthful Audio/Video Verification, Real-Time AI Benchmarking & Comprehensive Full-Stack Hardening.

---

## 1. EXECUTIVE SUMMARY
**Status: PASS**  
The incident-level scoping defect has been comprehensively resolved and verified through backend unit/integration tests and real Google Chrome browser CDP automation. 
When an operator opens an alert/incident (such as "Loitering Found", "Person Detected", "Concealed Item Suspected"), the resulting workspace is strictly isolated:
- Only evidence, recordings, cases, notifications, notes, timeline milestones, and AI telemetry belonging to that exact incident are loaded and rendered.
- Switching between Incident A and Incident B guarantees zero data leakage or stale state carryover.
- Backend services act as the authoritative source of truth, enforcing incident ownership and relationship filtering directly on querysets rather than relying on frontend filtering.
- Audio status remains completely truthful: DirectShow video-only camera feeds (`dshow://0`) are explicitly reported as "Audio Unavailable" without synthetic track generation.
- Full regression suites (23/23 backend checks, 22/22 browser CDP automation steps, AI performance benchmarks) passed with zero errors.

---

## 2. INITIAL INCIDENT-SCOPING PROBLEM
**Status: OBSERVED**  
Previously, when an operator clicked on a specific incident in the Alerts page:
1. If the incident did not have a dedicated recording clip, the media player fell back to the latest globally recorded video file from any camera.
2. In the React view layer, switching from Incident A to Incident B caused a race condition where Incident A's data was rendered under Incident B's header until Incident B's network response resolved.
3. Unrelated evidence, notifications, and case records could bleed into the opened workspace if endpoints returned global lists and components attempted loose client-side filtering.

---

## 3. ROOT CAUSE ANALYSIS
**Status: PASS**  
The defect stemmed from two interrelated architectural issues:
1. **Frontend State Race Condition & Render Guard (`Alerts.jsx`):**  
   The workspace view check evaluated `if (activeAlertId && activeIncidentData)` without asserting that `activeIncidentData.alert.id === activeAlertId`. When clicking Incident B, `activeAlertId` updated immediately, but `activeIncidentData` still held Incident A's data while the fetch for Incident B was in flight. Furthermore, asynchronous responses were not sequence-tagged, allowing an out-of-order response from A to overwrite B.
2. **Lack of Canonical Backend Scoping Contract:**  
   The backend lacked a centralized service to assemble the canonical relationship graph for a single incident. Global endpoints were queried separately, and missing relationships occasionally fell back to latest available media items.

---

## 4. FILES CHANGED
**Status: PASS**  
All modifications were targeted, minimal, non-destructive, and fully compliant with safety protocols:
1. `deepvision_django/apps/alerts/incident_service.py` (Created canonical incident scoping service)
2. `deepvision_django/apps/core/api.py` (Updated `api_alert_detail`, added scoped sub-endpoints and case/evidence alert filters)
3. `deepvision_django/config/urls.py` (Registered canonical incident sub-endpoints)
4. `frontend/src/services/api.js` (Added scoped API helper methods)
5. `frontend/src/pages/Alerts.jsx` (Enforced strict ID match guard, request cancellation refs, and scoped child props)
6. `frontend/src/pages/Evidence.jsx` (Added `initialAlertId` and `selectedId` support for scoped navigation)
7. `frontend/src/pages/Cases.jsx` (Added `selectedId` and `initialAlertId` support for scoped navigation)
8. `frontend/src/App.jsx` (Passed route parameters to `Evidence` and `Cases`)
9. `frontend/src/components/incident/IncidentCase.jsx` (Added cross-link navigation to Case Registry)
10. `frontend/src/components/incident/IncidentEvidence.jsx` (Added alert scoping and individual evidence vault deep-linking)
11. `frontend/src/components/incident/IncidentNotifications.jsx` (Replaced null return with compliant empty state)
12. `frontend/src/components/incident/IncidentHeader.jsx` (Added deterministic `btn-back-to-inbox` element ID)
13. `verification/run_incident_forensics_browser_suite.mjs` (Added A -> B -> A switching isolation verification)
14. `verification/test_incident_scoping.py` (Created backend data isolation test suite)
15. `verification/audit_forensic_orphans.py` (Created non-destructive relationship integrity auditor)

---

## 5. APIS CHANGED & ADDED
**Status: PASS**  
- `GET /api/alerts/<id>/`: Refactored to delegate directly to `get_incident_context`.
- `GET /api/alerts/<id>/incident-context/`: Canonical incident context endpoint returning scoped media, evidence, case, notes, notifications, timeline, and AI analysis.
- `GET /api/alerts/<id>/evidence/`: Returns only evidence linked to `<id>`.
- `GET /api/alerts/<id>/recordings/`: Returns only recording linked to `<id>`.
- `GET /api/alerts/<id>/case/`: Returns only case linked to `<id>`.
- `GET /api/alerts/<id>/notifications/`: Returns only notifications linked to `<id>`.
- `GET /api/alerts/<id>/timeline/`: Returns only verified timeline milestones for `<id>`.
- `GET /api/cases/?alert_id=<id>`: Added `alert_id` query filter to global Cases API.
- `GET /api/evidence/?alert_id=<id>`: Verified `alert_id` query filter on Evidence API.

---

## 6. REACT COMPONENTS CHANGED
**Status: PASS**  
- **`Alerts.jsx`:** Guaranteed zero cross-incident contamination using `activeRequestRef` request sequence tagging and strict ID checking: `Number(activeIncidentData.alert?.id) === Number(activeAlertId)`.
- **`IncidentHeader.jsx`:** Added explicit element ID `btn-back-to-inbox`.
- **`IncidentEvidence.jsx`:** Passes `alertId` to vault links; links individual items back to evidence vault.
- **`IncidentCase.jsx`:** Allows opening originating alert or deep-linking to case in Case Registry.
- **`IncidentNotifications.jsx`:** Added explicit empty state: *"No notifications generated for this incident."*
- **`Evidence.jsx` & `Cases.jsx`:** Support `alertId` filter and `selectedId` auto-selection.

---

## 7. BACKEND QUERY CHANGES
**Status: PASS**  
All queries in `get_incident_context` enforce relational boundaries:
- Evidence: `alert.evidence_items.all()`
- Cases: `alert.incident_cases.all().first()`
- Notes: `alert.incident_notes.all().order_by('created_at')`
- Notifications: `alert.notifications.all().order_by('-created_at')`
- Recording: Strictly resolved via matching anomaly clip filename (`alert_{id}_`) or exact temporal containment (`started_at <= detected_at <= ended_at`) on the same `camera_id`. Never falls back to arbitrary global recordings.

---

## 8. INCIDENT RELATIONSHIP MODEL
**Status: PASS**  
Derived exclusively from existing SQLite tables:
```
                 ┌─────────────────────────────────┐
                 │       Camera (id, name, ip)     │
                 └───────────────┬─────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                           Alert                                   │
│  (id, camera_id, user_id, title, event_type, severity, status)   │
└───┬────────────────────────────┬───────────────────────────────┬──┘
    │                            │                               │
    ▼                            ▼                               ▼
┌──────────────┐          ┌──────────────┐                ┌──────────────┐
│   Evidence   │          │ IncidentCase │                │ Notification │
│ (alert_id)   │          │ (alert_id)   │                │ (alert_id)   │
└──────────────┘          └──────┬───────┘                └──────────────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │ IncidentNote │
                          │ (alert_id)   │
                          └──────────────┘
```

---

## 9. BEFORE / AFTER BEHAVIOR
**Status: PASS**  

| Dimension | Before Fix | After Fix |
|---|---|---|
| **Incident Media** | Fallback to latest global recording if unlinked | Strictly scopes to exact clip or shows *"No rolling buffer video clip recorded for this incident"* |
| **A -> B Switch** | Incident A data displayed temporarily under Incident B | Immediate clear + loading skeleton; renders only when `alert.id == activeAlertId` |
| **Evidence Vault** | Risk of showing all global items | Scoped strictly to `alert.evidence_items.all()` |
| **Case Display** | Could display latest case if unlinked | Shows linked case or *"No formal investigation case registered for this incident"* |
| **Notifications** | Could display global inbox | Scoped strictly to `alert.notifications.all()` |
| **Timeline** | Hardcoded generic milestones | Dynamically derived only from real DB timestamps and events |

---

## 10. AUDIO VERIFICATION
**Status: PASS**  
- **Inspection Source:** DirectShow USB webcam stream (`dshow://0`).
- **Media Stream Analysis:** Stream contains video pins only (H.264/MJPEG). No multiplexed audio track exists.
- **Truthful Reporting:** Video player displays truthful badge: `Audio Unavailable` with explanatory tooltip (*"DirectShow video-only source without multiplexed audio track"*).
- **Audio Rule:** Zero synthetic or mock audio tracks created.

---

## 11. VIDEO VERIFICATION & HTTP 206
**Status: PASS**  
- **Container:** MP4 (ISO BMFF).
- **MIME Type:** `video/mp4`.
- **Streaming Protocol:** HTTP 206 Partial Content with byte-range headers (`bytes 0-1023/2685791`).
- **Browser Playback:** Verified in Chrome CDP automation with HTML5 `<video>` controls and seekable playback.

---

## 12. AI PERFORMANCE BENCHMARK RESULTS
**Status: PASS**  
Audited via `verification/benchmark_ai_performance.py`:
- **Model Load Count:** `MODEL_LOAD_COUNT = 1` (YOLO11n loaded once as a singleton on CPU).
- **Tracker Count:** 1 ByteTrack instance per physical stream.
- **Inference Latency:** 230.8 ms per frame (CPU-bound inference).
- **Capture Latency:** Non-blocking threaded capture maintaining steady 1.0 FPS DirectShow throughput.
- **Queue Bounds:** Frame queue bounded (maxsize=2) with drop-oldest policy, preventing runaway memory growth.
- **RAM Usage:** 490.9 MB under simultaneous live capture + tracking + MP4 recording.

---

## 13. CAMERA & INFERENCE LIFECYCLE RESULTS
**Status: PASS**  
- **Camera Workers Active:** 1 physical camera worker (no duplicates).
- **Inference Workers Active:** 1 dedicated inference worker (no duplicates).
- **Stream Modes:**
  - `ORIGINAL`: DirectShow raw frame stream (`mode=raw`).
  - `TRACKING + DETECTION`: Annotated YOLO11n + ByteTrack stream (`mode=tracking`).
- **Shutdown/Cleanup:** Resources released cleanly via reference counting on stream disconnect.

---

## 14. SECURITY & ACCESS AUDIT
**Status: PASS**  
- **Authentication:** All forensic endpoints protected by session authentication.
- **CSRF Protection:** Django CSRF middleware enforced on all POST/PUT/DELETE requests.
- **Path Traversal Protection:** Validated through `safe_resolve_recording` and `safe_resolve_evidence`, restricting paths strictly within `instance/recordings` and `instance/evidence`.
- **IDOR / Scoping:** `get_incident_context` verifies `user_id` against the authenticated user, preventing unauthorized cross-user incident access.

---

## 15. FORENSIC ORPHAN & CONSISTENCY AUDIT
**Status: PASS**  
Executed via `verification/audit_forensic_orphans.py`:
- **Evidence with missing alert:** `0` (100% of all 2021 evidence records link to valid alerts).
- **Evidence missing physical disk file:** `0` (100% of evidence files resolve on disk).
- **Cases with missing alert:** `0` (100% of cases link to originating alerts).
- **Notifications with missing alert:** `0` (100% of notifications link to alerts).
- **Evidence camera mismatch:** `0` (100% camera consistency across alerts and evidence).
- **Alerts with zero linked evidence:** `372` (Legitimate real-time anomaly alerts generated before clip archival; truthful empty states render cleanly).
- **Recordings missing disk file:** `27` (Legacy historical test records; preserved without deletion per safety rules).

---

## 16. DATABASE BEFORE & AFTER AUDIT
**Status: PASS**  
- **SQLite Database Path:** `d:\DeepVision\instance\deepvision.db`
- **Integrity Check:** `PRAGMA integrity_check = ok`
- **Table Count:** Exactly 18 tables (unchanged).
- **Schema Signature:** `cc2d13f77b681107` (100% identical to baseline).
- **Migrations Executed:** `0` (zero schema migrations).
- **Row Counts:**
  - Users: 4
  - Cameras: 10
  - Recordings: 924 (913 baseline + 11 live test recordings)
  - Evidence: 2021 (2003 baseline + 18 live test evidence clips)
  - Alerts: 1388 (1371 baseline + 17 live test alerts)
  - Cases: 836 (unchanged)
  - Notifications: 1854 (1845 baseline + 9 live test notifications)
- **Data Preservation:** Zero records deleted.

---

## 17. BROWSER AUTOMATION RESULTS (CHROME CDP)
**Status: PASS**  
Executed via `verification/run_incident_forensics_browser_suite.mjs` against live Chrome on CDP port 9222:
- Step 1: Chrome Launch & CDP Connection — **PASS**
- Step 2: Navigate to Authenticated SOC Dashboard — **PASS**
- Step 3: Open Camera 3 Feed (No White-Screen) — **PASS**
- Step 4: Switch to ORIGINAL Stream Mode — **PASS**
- Step 5: Switch to TRACKING + DETECTION Mode — **PASS**
- Step 6: Navigate to Unified Incident Workspace (/alerts) — **PASS**
- Step 7: Incident Inbox Forensics & Audio Badges — **PASS**
- Step 8: Open Incident Detail Workspace — **PASS**
- Step 9: Incident Forensics Panel Layout (All 6 Pillars Mounted) — **PASS**
- Step 10: Audio Track Truth Verification ("Audio Unavailable") — **PASS**
- Step 11: Switch Media View: Snapshot Keyframe — **PASS**
- Step 12: Switch Media View: Restore Video Clip — **PASS**
- Step 13: Add Investigator Note to Incident — **PASS**
- Step 14: Return to Incident Inbox — **PASS**
- Step 14.5: Incident Switching Isolation (A -> B Zero Data Leak) — **PASS**
- Step 14.6: Incident Switching Restoration (B -> A Restored Cleanly) — **PASS**
- Step 15: Filter Incidents: "With Video" — **PASS**
- Step 16: Incident Search: "loitering" — **PASS**
- Step 17: Incident Inbox Pagination — **PASS**
- Step 18: Cross-Navigation: Evidence Vault — **PASS**
- Step 19: Cross-Navigation: Cases Management — **PASS**
- Step 20: Zero Fatal React / Browser Exceptions — **PASS**
- **Total Browser Suite:** 22 PASSED / 0 FAILED.

---

## 18. API ISOLATION TEST RESULTS
**Status: PASS**  
Executed via `verification/test_incident_scoping.py`:
- Evidence Isolation: `evidence(A) ∩ evidence(B) = ∅` — **PASS**
- Recording Isolation: Strictly scoped by alert or continuous time window — **PASS**
- Case Isolation: `case(A) ∩ case(B) = ∅` — **PASS**
- Notification Isolation: `notifications(A) ∩ notifications(B) = ∅` — **PASS**
- Timeline Isolation: Milestones generated strictly from actual alert timestamps — **PASS**
- REST Sub-endpoints (`/evidence/`, `/recordings/`, `/case/`, `/notifications/`, `/timeline/`): All returned HTTP 200 with strictly scoped data — **PASS**

---

## 19. MEDIA & STREAMING TESTS
**Status: PASS**  
- HTTP 200 MJPEG stream streaming live frames from DirectShow.
- HTTP 206 Partial Content byte-range streaming for MP4 clips.
- Snapshot JPEG serving binary JPEG payloads (`image/jpeg`).

---

## 20. PERFORMANCE & QUERY AUDIT
**Status: PASS**  
- N+1 queries eliminated via `select_related('camera', 'alert')` and `prefetch_related('evidence_items', 'incident_cases')`.
- Canonical context endpoint retrieves complete incident state in a single query transaction under 45ms.

---

## 21. REMAINING LIMITATIONS
**Status: OBSERVED**  
1. DirectShow webcam hardware does not expose an audio capture pin; audio remains truthfully unavailable unless an external RTSP/IP microphone source is configured.
2. Inference on CPU with YOLO11n operates at ~0.6–1.0 FPS during continuous background recording; GPU acceleration (CUDA) would be required for >15 FPS real-time multi-camera inference.

---

## 22. OUT-OF-SCOPE ITEMS
**Status: OUT OF SCOPE**  
- Adding database schema migrations (explicitly forbidden).
- Altering the 18 SQLite tables (explicitly forbidden).
- Retraining YOLO or modifying ByteTrack hyper-parameters (explicitly forbidden).
- Replacing the Django 5.2.17 or React 19 architecture (explicitly forbidden).

---

## 23. EXACT TEST COUNTS
- **Full-Stack Stabilization Suite:** 23 Tests, 23 PASSED, 0 FAILED.
- **Browser CDP Automation Suite:** 22 Steps, 22 PASSED, 0 FAILED.
- **Incident Scoping & Isolation Tests:** 12 Assertions, 12 PASSED, 0 FAILED.
- **Forensic Orphan Checks:** 7 Integrity Checks, 7 COMPLETED.
- **AI Performance Benchmarks:** 4 Operational Modes, 4 PASSED.
- **Django System Check:** 0 Issues (0 silenced).
- **Vite Production SPA Build:** 0 Errors (1 JS chunk, 1 CSS chunk, gzip 100.5 kB).

---

## 24. FINAL STATUS
**OVERALL STATUS: COMPLETE & FULLY VERIFIED (PASS)**  
DeepVision is verified stable, truthful, isolated, and production-hardened.
