# DeepVision Research & Engineering Blueprint (research.md)

**Document Date:** October 2026
**Focus Areas:** Enterprise VMS UX, Incident Investigation Architecture, OWASP Top 10:2025 Security Baseline, Django 5.x Hardening, Container Security, Video Streaming Performance.

---

## 1. Sources Actually Inspected

1. **OWASP Top 10:2025 Vulnerability Categories:**
   - Evaluated the 2025 release containing: A01 Broken Access Control (incorporating SSRF), A02 Security Misconfiguration, A03 Software Supply Chain Failures, A04 Cryptographic Failures, A05 Injection, A06 Insecure Design, A07 Authentication Failures, A08 Software & Data Integrity Failures, A09 Security Logging & Monitoring, A10 Mishandling of Exceptional Conditions.
2. **Enterprise Video Management System (VMS) UX Standards:**
   - Evaluated interaction paradigms from Milestone XProtect Smart Client, Genetec Security Center, and Hanwha Wisenet WAVE.
   - Core UX principles: Exception-based monitoring (alert-driven rather than passive monitoring), non-occluding video HUDs, unified temporal timeline seeking, clear separation between live observation and forensic case workspaces.
3. **Django 5.x Official Documentation & Security Deployment Checklist:**
   - Security middleware (`SecurityMiddleware`, `XFrameOptionsMiddleware`, `CsrfViewMiddleware`), session cookies (`SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`), password hashing, ORM query parameterization, and static asset delivery.
4. **Official Docker Security Best Practices:**
   - Container isolation, non-root user execution (`USER appuser`), read-only root filesystems where practical, minimal base images, multi-stage builds, and avoiding host device exposure without strict isolation.
5. **Web Video & Media Streaming Standards:**
   - RFC 7233 (HTTP 206 Partial Content range requests for seekable MP4 playback), MJPEG `multipart/x-mixed-replace` lifecycle, and browser resource reclamation on unmount.

---

## 2. Relevant Design & Engineering Principles Extracted

### A. VMS & Surveillance Operations Center (SOC) UX
- **Operational Density without Clutter:** Security operators prioritize high signal-to-noise ratio over decorative design. Color is reserved for operational status: Emerald (`#10b981`) for online/nominal, Amber (`#f59e0b`) for warning/motion, Crimson (`#ef4444`) for critical alert/recording.
- **Dedicated Workspaces:**
  - *Dashboard:* Macro-level system health, camera availability count, active recording indicators, recent incident feed. Never dominated by an oversized camera feed.
  - *Cameras:* Micro-level surveillance feed with non-occluding floating HUD (telemetry pills, honest software controls, digital zoom with panning).
  - *Forensics & Evidence:* Scoped investigation drawer, temporal metadata, frame snapshots, and case linkage.
- **Honest Hardware Controls:** If camera hardware lacks motorized PTZ or two-way audio talkback, the UI must clearly label controls as client-side digital zoom/pan or indicate disabled state rather than fabricating physical hardware feedback.

### B. Application Security (OWASP Top 10:2025 & Django Hardening)
- **A01: Broken Access Control & SSRF:** Camera connection endpoints that accept external RTSP/HTTP URLs must be validated against private address spaces and loopback proxies. Object-level access control must be enforced in Django views, ensuring operators only access cameras and recordings assigned to their organization or user account.
- **A02: Security Misconfiguration:** Enforce strict `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy`.
- **A03: Software Supply Chain Failures:** Audit direct and transitive dependencies (`requirements.txt`, `package.json`). Remove obsolete libraries and verify cryptographic checksums.
- **A05: Injection & Path Traversal:** File serving endpoints (`/recordings/<id>/view/`, `/evidence/<id>/download/`) must strictly sanitize file paths using `os.path.abspath` boundary checks to prevent directory traversal (`../`).
- **A07: Authentication Failures:** Session-based authentication with cryptographically random OTP generation, brute-force rate-limiting, secure session invalidation on logout, and no hardcoded credentials in the UI.

### C. Performance Engineering
- **Media Delivery:** Video playback must leverage HTTP 206 Partial Content with `Accept-Ranges: bytes` to enable instant scrubbing without loading entire MP4 files into memory.
- **Frontend Bundle Efficiency:** Asset tree-shaking with Vite 6, fingerprinted bundles, deferred modal mounting, and unmount cleanup of video stream tags to prevent browser thread exhaustion.
- **AI Inference Singleton:** The YOLO11n model must remain a CPU singleton initialized once (`MODEL_LOAD_COUNT=1`) and shared across ingestion loops to avoid multi-gigabyte memory leaks.

---

## 3. Which Principles Apply to DeepVision and Why

| Principle | Relevance to DeepVision | Technical Application |
|---|---|---|
| **Macro Dashboard vs Micro Camera Workspace** | High | DeepVision previously placed a huge camera feed on the Dashboard. Moving live feed to a secondary compact preview restored operational utility to the Dashboard. |
| **Reference 1 Floating HUD** | Critical | Implemented rounded 24px bezel, translucent floating pills (`● Live 240kb/s 15 FPS`, live clock), 3-stage zoom (`[ - \| 1X \| + ]`), and client-side digital panning. |
| **Reference 2 Enterprise Security Language** | Critical | Applied dark obsidian surfaces (`#080c14`, `#0f172a`), refined borders (`rgba(255,255,255,0.08)`), restrained emerald status indicators, and clean typography. |
| **Path Traversal Protection** | High | Media serving routes in `recording_views` and `evidence_views` validate that resolved paths stay within `MEDIA_ROOT`. |
| **SSRF Camera Ingestion Protection** | High | `test_connection` validates IP schemes and prohibits arbitrary loopback exploration. |
| **HTTP 206 Range Playback** | Critical | `view_recording_media_view` uses chunked file streaming with byte ranges for seamless scrubbing. |

---

## 4. Proposed Design & Engineering Decisions

1. **Design System:** Obsidian dark theme canvas (`#080c14`), surface card (`#0f172a`), border (`#1e293b`), emerald accent (`#10b981`), critical red (`#ef4444`).
2. **Navigation:** Global 8-destination navigation (`Dashboard`, `Cameras`, `Alerts`, `Recordings`, `Evidence`, `Cases`, `Notifications`, `Help`) with `● SOC ONLINE` health pill and mobile slide-over drawer.
3. **Security Headers:** Add security headers to Django `settings.py` (`SECURE_CONTENT_TYPE_NOSNIFF = True`, `X_FRAME_OPTIONS = 'DENY'`, `SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'`).
4. **Data Preservation:** SQLite database (`instance/deepvision.db`, 18 tables) is preserved without modification or cutover.
5. **Docker Architecture:** Multi-stage Dockerfile with non-root user, health check endpoint, environment variable configuration, and documentation of native DirectShow webcam constraints on Linux containers.

---

## 5. Risks & Limitations

- **Hardware Camera Containerization:** Windows native DirectShow webcams (`dshow://0`) cannot be accessed directly by Linux Docker containers without specialized USB-over-IP or host streaming bridges. This is honestly documented in `DEPLOYMENT.md`.
- **PTZ Hardware:** USB webcams do not have motorized mechanical pan/tilt/zoom motors. The circular PTZ pad is honestly implemented as client-side digital panning across the digitally zoomed frame.
- **Local Development Scope:** Production HTTPS, TLS certificates, and public DNS are not active in the local development environment (`127.0.0.1:8000`).
