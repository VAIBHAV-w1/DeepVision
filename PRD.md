# DeepVision — Product Requirements Document (PRD)

## 1. Product Purpose & Overview
DeepVision is an enterprise-grade AI-powered Video Management System (VMS) and Surveillance Operations Center (SOC) designed for continuous optical ingestion, hardware camera management, real-time computer vision inference (YOLO11n + ByteTrack), forensic recording retention, and incident response workflows.

## 2. Target Users
- **SOC Operators:** Monitor live camera channels, track active detections, respond to security alerts, and initiate recordings.
- **Forensic Investigators:** Analyze captured incidents, review preserved evidence frames, organize cases, and playback recorded footage.
- **System Administrators:** Manage camera hardware devices (DirectShow, RTSP, IP Webcams), configure AI models, and audit system health.

## 3. Core Functional Requirements
1. **Live Camera Surveillance:**
   - Ingest physical webcams via DirectShow (`dshow://0`) and IP/RTSP streams via OpenCV.
   - Dual-mode streaming:
     - `ORIGINAL`: Unprocessed CCTV stream with lowest possible latency.
     - `TRACKING + DETECTION`: Real-time YOLO11n neural inference with ByteTrack multi-object tracking IDs.
   - Live camera telemetry: Inference FPS, detection count, active track IDs, bitrate, and resolution.
   - Operational HUD: Translucent floating telemetry pills, digital zoom (1x, 1.5x, 2x), client-side digital panning, snapshot capture, and manual recording controls.
2. **Operational Dashboard:**
   - Operational summary providing high-level system status without dominating the screen with an oversized camera feed.
   - Service health indicators: Surveillance Engine, Database, AI pipeline.
   - Live metrics: Online vs offline camera counts, active recordings, open alerts, preserved evidence, linked cases.
   - Secondary compact live monitor for quick visual inspection of the primary camera.
   - Recent security alerts feed and recent recordings list with direct operational navigation.
3. **Alerts & Incident Forensics:**
   - Real-time anomaly and intrusion alerts generated from neural detections.
   - Scoped forensic workspace for investigating alerts with associated evidence, recordings, and cases.
   - Status transitions: Acknowledge, Investigate, Resolve.
4. **Recordings & Media Playback:**
   - On-demand and triggered video recording.
   - HTTP 206 Partial Content video streaming for smooth timeline seeking.
   - Downloadable video archives.
5. **Evidence & Chain of Custody:**
   - Immutable snapshot storage linked to alerts.
   - Integrity and metadata review.
6. **Incident Cases:**
   - Multi-alert incident grouping, investigator notes, and case status management.
7. **Notifications:**
   - System and security notification inbox with unread tracking and bulk actions.
8. **Help & Documentation:**
   - Grounded operator instructions for camera setup, feed modes, and troubleshooting.
9. **Authentication & Security:**
   - Session-based authentication with CSRF protection.
   - Two-factor email OTP verification for signup and login.
   - Role-based access control (Admin, Investigator, Operator).

## 4. Visual & Experience Requirements
- **Reference 1 Direction:** Floating translucent telemetry pills, rounded monitor bezel, clean action bars, responsive HUD.
- **Reference 2 Direction:** Dark obsidian and slate operational workspace (`#080c14`, `#0f172a`), restrained emerald accents (`#10b981`), high-contrast typography, clear component hierarchy.
- **Strict Prohibitions:** No purple gradients, no emojis, no em dashes in copy, no fake statistics, no un-functional decorative buttons, and no oversized marketing sections.

## 5. Non-Functional Requirements
- **Performance:** Stream latency < 250ms, inference >= 15 FPS on CPU.
- **Stability:** Zero server-side unhandled crashes; graceful signal reacquisition.
- **Responsive Design:** Desktop-first (1440x900+) with full tablet and mobile support (390x844).
