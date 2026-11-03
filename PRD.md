

# DEEPVISION 4.0 — PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Document Version:** 4.0.0
**Status:** Approved for Implementation
**Product:** DeepVision AI Intelligent Surveillance Platform
**Target Architecture:** Django Unified Backend + React 18 Single-Page Application
**Authoritative Deployment:** Localhost Windows (`http://127.0.0.1:8000/`)
**Camera Bridge:** `http://127.0.0.1:8554/`

---

## 1. PROJECT OVERVIEW
DeepVision is an enterprise-grade AI video surveillance and Security Operations Center (SOC) platform. It provides real-time video acquisition from physical webcams, DirectShow devices, IP cameras, and RTSP streams, processes frames through singleton YOLO11n object detection and ByteTrack multi-object tracking, enforces configurable perimeter security and behavior anomaly rules, and delivers cryptographic forensic evidence recording and alert management through a responsive web interface.

---

## 2. PROBLEM STATEMENT
Traditional video surveillance systems are passive recording archives that require continuous manual human monitoring to detect security threats. Existing open-source AI surveillance attempts frequently suffer from:
- Multi-second video streaming latency caused by unbounded frame queues.
- Ghost detections and identity switching during brief target occlusions.
- Artificial constraints categorizing cameras into narrow, inflexible roles (e.g. "theft only" vs "intrusion only").
- Fragmented user interfaces with duplicate, conflicting pages and buried controls.
- Fragile background workers that leak camera handles or duplicate heavy neural network models in memory.

---

## 3. PROJECT OBJECTIVES
1. **Sub-100ms Inference Freshness:** Deliver live camera video with bounded buffers (`CAP_PROP_BUFFERSIZE = 1`) and non-blocking worker threads.
2. **Deterministic AI Pipeline:** Maintain a single in-process YOLO11n PyTorch model singleton and ByteTrack tracker.
3. **Universal Camera Capabilities:** Every registered camera can run detection, tracking, loitering, intrusion, rapid motion, abandoned objects, and gathering.
4. **Canonical 10-Destination Frontend:** Provide 10 clean, dedicated operational workspaces without confusing redirects or tabbed wrapping.
5. **Rock-Solid Security & Evidence:** Enforce signed session authentication, role-based access control, RFC 7233 HTTP 206 video seeking, and SHA-256 evidence chain of custody.

---

## 4. TARGET USERS
1. **SOC Operators:** Monitor live camera feeds, triage security events, acknowledge alerts, and capture manual evidence snapshots.
2. **Security Investigators:** Review incident timelines, play back recorded event clips, take investigative notes, and compile case dossiers.
3. **System Administrators:** Register and configure cameras, define restricted zones, adjust AI confidence thresholds, and manage user accounts.

---

## 5. USER ROLES AND PERMISSIONS

| Role | Live Monitoring | Acknowledge Alerts | Manage Cameras | Define Zones | View Evidence | Delete Recordings | Manage Users |
|---|---|---|---|---|---|---|---|
| **Admin** | Full | Yes | Full (Add/Edit/Delete) | Yes | Full (Download/Delete) | Yes | Yes |
| **Supervisor** | Full | Yes | View / Configure | Yes | Full (Download) | No | No |
| **Operator** | Full | Yes | View Only | View / Edit Zones | View / Download | No | No |
| **User / Viewer** | Assigned Cameras | View Only | View Only | View Only | View Only | No | No |

---

## 6. FUNCTIONAL REQUIREMENTS
- **FR-01 Single Authoritative Backend:** The backend must run exclusively on Django 5.x.
- **FR-02 Production SPA Delivery:** Django serves the built React single-page application at root `/` and handles all API requests under `/api/`.
- **FR-03 Live Video Streaming:** Multipart MJPEG streams served over HTTP with low latency and real-time bounding box overlays.
- **FR-04 Video Seeking:** Recorded MP4 video clips must support HTTP Range requests for instant seeking in HTML5 players.
- **FR-05 Forensic Integrity:** Every snapshot and video clip generated must have file size, timestamp, and SHA-256 hash recorded.

---

## 7. CAMERA MANAGEMENT REQUIREMENTS
- **CMR-01 Heterogeneous Source Support:** DirectShow (`dshow://<index>`), USB webcams (`0`, `1`), RTSP streams (`rtsp://...`), and HTTP/MJPEG streams.
- **CMR-02 Dynamic Camera Identification:** Cameras must be resolved by their actual database record and configured hardware source, not hardcoded IDs.
- **CMR-03 Lifecycle Management:** Worker handles must automatically spin up on stream connection and release cleanly on client disconnect.
- **CMR-04 Truthful State Reporting:** Cameras must report exact hardware resolution, capture frame rate, dropped frame count, and connection status.

---

## 8. VIDEO STREAMING REQUIREMENTS
- **VSR-01 Dual Streaming Modes:**
  - **Raw Stream (`mode=original`):** Pristine camera footage without bounding boxes or text overlays.
  - **Tracking & Detection Stream (`mode=tracking`):** Live video with bounding boxes, class names, track IDs, confidence scores, and restricted zone borders.
- **VSR-02 Zero Stale Buffering:** Capture loop must immediately drop intermediate frames if inference is processing, delivering the newest available frame.
- **VSR-03 Clean Unmount:** Disconnecting from stream must decrement active client counter and release OpenCV capture handle when count reaches zero.

---

## 9. OBJECT DETECTION REQUIREMENTS
- **ODR-01 Model Architecture:** Ultralytics YOLO11n PyTorch neural network running on CPU or GPU.
- **ODR-02 Singleton Lifecycle:** Exactly one model instance loaded in memory across the entire Django process.
- **ODR-03 Confidence & IoU Tuning:** Default detection confidence `0.35`, NMS IoU threshold `0.45`, standard input resolution `640x640`.
- **ODR-04 Multi-Class Support:** Person, bicycle, car, motorcycle, bus, truck, backpack, handbag, suitcase, cell phone, laptop.

---

## 10. MULTI-OBJECT TRACKING REQUIREMENTS
- **TRK-01 Algorithm:** ByteTrack multi-object tracking associating high and low confidence detections using Kalman filters and Hungarian matching.
- **TRK-02 Identity Stability:** Minimum 2 consecutive detections to promote track to `confirmed`. Lost-track persistence buffer of 30 frames (2 seconds).
- **TRK-03 Trajectory Preservation:** Maintain historical centroid coordinates for velocity and direction calculation.

---

## 11. ANOMALY DETECTION REQUIREMENTS
- **ADR-01 Behavior Rules:**
  - **Restricted Area Entry:** Detection of object feet coordinate `(center_x, bottom_y)` inside a defined polygon perimeter.
  - **Loitering:** Object dwell time inside a zone exceeding configurable threshold (e.g. > 10 seconds).
  - **Unusual Movement:** Rapid acceleration or irregular directional changes across consecutive frames.
  - **Abandoned Object:** Static object persisting without an associated person for > 30 seconds.
  - **Crowding / Gathering:** More than `N` persons clustered in a localized region.
- **ADR-02 Cooldown & Deduplication:** Per-camera and per-track alert cooldowns (default 15 seconds) to prevent spamming duplicate alerts.

---

## 12. RESTRICTED-AREA MANAGEMENT
- **RAM-01 Interactive Drawing Canvas:** Operators can draw, move, and resize polygon or rectangular zones directly over live video.
- **RAM-02 Persistence:** Zones stored in SQLite `restricted_zones` table with normalized coordinates `[x1, y1, x2, y2]`.
- **RAM-03 Real-Time Invalidation:** Saving or modifying a zone must instantly invalidate in-memory zone geometry in `InferenceWorker` within 50 ms.

---

## 13. ALERT MANAGEMENT
- **ALM-01 Lifecycle States:** `new` -> `acknowledged` -> `resolved`.
- **ALM-02 Incident Context:** Every alert links to camera ID, timestamp, severity (`low`, `medium`, `high`, `critical`), trigger bounding box, and rule type.
- **ALM-03 Case Escalation:** Operators can escalate any alert into a formal incident investigation case with investigator notes.

---

## 14. RECORDING AND EVIDENCE MANAGEMENT
- **REM-01 Continuous & Event Recordings:** Continuous MP4 video chunking and event-triggered 10-second incident video clips.
- **REM-02 Manual Snapshots:** Operators can trigger high-resolution JPEG snapshots from live streams on demand.
- **REM-03 Forensic Vault:** Cryptographic chain of custody recording SHA-256 hash, file size, camera metadata, and operator identity.

---

## 15. AUTHENTICATION AND AUTHORIZATION
- **AAR-01 Signed Cookie Sessions:** `deepvision_django_session` signed using HMAC-SHA256, HTTP-only, SameSite=Lax.
- **AAR-02 Two-Factor Authentication:** Email-based 6-digit OTP verification for both registration and login with salt separation.
- **AAR-03 Role-Based Gating:** API endpoints and views enforce `@login_required` and role-based permissions.

---

## 16. SECURITY REQUIREMENTS
- **SEC-01 CSRF Protection:** Mandatory CSRF token verification on all state-mutating requests (`POST`, `PUT`, `DELETE`).
- **SEC-02 Path Traversal Prevention:** Strict path normalization rejecting `../`, `..%2F`, and absolute paths on media endpoints.
- **SEC-03 SSRF & Protocol Rejection:** Camera source URLs must only accept validated `dshow://`, `rtsp://`, `http://`, and `https://` schemes.

---

## 17. DATABASE DESIGN
- **DBD-01 Engine:** SQLite 3 in development and local operations; PostgreSQL compatible for enterprise deployments.
- **DBD-02 Schema Preservation:** Exact 18 tables matching SHA-256 preflight signature `cc2d13f77b681107`.
- **DBD-03 Indexes:** 11 secondary B-tree indexes for high-speed alert filtering and user lookup.

---

## 18. API DESIGN
- Standardized REST JSON APIs under `/api/`:
  - `/api/auth/*`: Login, OTP verification, demo session, logout, current user.
  - `/api/dashboard/stats/`: System-wide KPI metrics and health.
  - `/api/cameras/*`: Camera inventory, detail, stream telemetry, zone CRUD.
  - `/api/alerts/*`: Security event triage, state transitions, case escalation.
  - `/api/recordings/*`: Video clip metadata and playback URLs.
  - `/api/evidence/*`: Forensic snapshots and incident video clips.
  - `/api/cases/*`: Incident case dossiers and investigator notes.
  - `/api/notifications/*`: Operator alert notifications and unread counts.
  - `/api/health/`: System liveness and DB connectivity.

---

## 19. FRONTEND ARCHITECTURE
- **FE-01 Canonical 10-Item Navigation:**
  1. Overview (`#/overview`)
  2. Live Monitoring (`#/live`)
  3. Cameras (`#/cameras`)
  4. Security Events (`#/alerts`)
  5. Recordings (`#/recordings`)
  6. Evidence (`#/evidence`)
  7. Cases (`#/cases`)
  8. Notifications (`#/notifications`)
  9. Settings (`#/settings`)
  10. Help and Support (`#/help`)
- **FE-02 Dedicated Page Components:** Each route renders its own independent, top-level React component.
- **FE-03 Professional Design Standards:** Linear / shadcn/ui aesthetic with deep obsidian palette (`#080c14`), cyan accents, Lucide icons, accessible contrast, and zero horizontal scroll overflow.

---

## 20. BACKEND ARCHITECTURE
- Single authoritative Django application running on port 8000.
- Decoupled `CameraCaptureWorker` and `InferenceWorker` communicating via lock-free single-slot frame buffers.
- Unified REST API layer with standard JSON error responses and structured HTTP status codes.

---

## 21. PERFORMANCE REQUIREMENTS
- **Capture-to-Display Frame Age:** Mean < 50 ms, P95 < 100 ms.
- **Live Stream Delivery:** 15.0 - 30.0 FPS sustained.
- **Inference Latency:** < 65 ms per frame on standard CPU.
- **API Response Latency:** < 25 ms average for JSON endpoints.

---

## 22. TESTING STRATEGY
- **Automated Localhost Regression Suite:** 30 mandatory tests covering all subsystem boundaries.
- **Independent Security Audit:** 23 tests verifying path traversal, SSRF, IDOR, and auth gating.
- **Full Auth & OTP Suite:** 18 tests verifying 2FA lifecycle and salt separation.
- **Physical Hardware Verification:** Live DirectShow camera capture, tracking stream verification, and zone intrusion triggering.
- **Browser CDP Viewport Audit:** 7 viewport resolutions (375x812 to 1920x1080) verifying zero horizontal overflow.

---

## 23. DEPLOYMENT AND MAINTENANCE
- Zero external Git push or remote modifications during local engineering loops.
- Automatic database preflight signature verification on startup.
- Full backup snapshot created before any schema or structural refactoring.
