# DEEPVISION 4.0 — KNOWN OPERATIONAL LIMITATIONS & RUNTIME BOUNDARIES

This document transparently outlines the operational boundaries, physical hardware constraints, and environment characteristics of the DeepVision 4.0 intelligent surveillance deployment at `D:\DeepVision`.

---

## 1. Physical Hardware & Sensor Boundaries

### 1.1 DirectShow Single-Process Hardware Lock (Windows)
- **Constraint:** The Windows DirectShow driver architecture enforces exclusive device access on physical imaging hardware (e.g., `HP Wide Vision HD Camera`, index 0). If two processes attempt to instantiate `cv2.VideoCapture(0, cv2.CAP_DSHOW)` simultaneously, the second process will either hang indefinitely or fail with an error.
- **Architectural Mitigation:** In DeepVision 4.0, physical webcam acquisition is centralized into `scripts/host_camera_bridge.py` running on localhost port 8554. This bridge acts as the sole DirectShow master grabber, broadcasting the raw stream to multiple consumers (inference workers, live streamers, recording daemons) via non-blocking memory buffers.
- **Operator Recommendation:** Avoid running third-party video conferencing software (Zoom, Microsoft Teams, Skype) or external Python capture scripts concurrently on the host machine while DeepVision is active.

### 1.2 Webcam Sensor Framerate & Auto-Exposure
- **Constraint:** The built-in laptop sensor (HP Wide Vision HD Camera) operates with a hardware ceiling of 30 frames per second at 1280x720 resolution. Under low-light conditions, the hardware camera firmware automatically throttles its sensor integration time (auto-exposure), reducing effective capture rate from 30 FPS to 15–20 FPS to maintain exposure.
- **Architectural Mitigation:** The capture loop dynamically measures delta timestamps per frame and logs exposure-induced FPS drops in telemetry headers (`X-Capture-FPS`).
- **Operator Recommendation:** Maintain adequate ambient room lighting when evaluating high-cadence tracking and intrusion detection benchmarks.

---

## 2. Neural Inference & Tracking Bounds

### 2.1 CPU vs. GPU Inference Throughput
- **Constraint:** When running on CPU mode (Intel Core i7 host without dedicated high-compute CUDA GPU), the YOLO11n forward pass requires approximately 35–45 ms per frame. This yields an inference ceiling of ~22–28 FPS per single CPU thread.
- **Architectural Mitigation:** YOLO11n singleton inference is decoupled from display rendering. Display frames are presented at full 30 FPS, while inference detections and ByteTrack Kalman filter updates execute asynchronously at 22–25 FPS, interpolating bounding box positions between frames.
- **Operator Recommendation:** In high-density deployments with 10+ concurrent AI streams, configure CUDA hardware acceleration or leverage edge inference accelerators.

### 2.2 Object Occlusion & Visual Overlap
- **Constraint:** Extreme optical occlusion (e.g., a person stepping entirely behind an opaque physical barrier for > 30 frames) causes ByteTrack to lose trajectory association, assigning a new track ID upon re-emergence.
- **Architectural Mitigation:** The ByteTrack buffer is tuned to retain lost tracks for up to 30 frames (approx. 1.0 second), maintaining track continuity across brief occlusions.

---

## 3. Network & Streaming Considerations

### 3.1 Localhost Loopback vs. Distributed RTSP
- **Constraint:** On local development environments (`127.0.0.1:8000`), video transport operates over HTTP multipart MJPEG. While MJPEG provides instantaneous rendering with zero browser decoding latency and sub-100ms freshness, it consumes higher network bandwidth (~2–4 Mbps per 720p stream) compared to H.264/WebRTC.
- **Architectural Mitigation:** Live streaming frames are JPEG-compressed with quality factor 80, maintaining sharp edge definition for bounding boxes while keeping per-channel bandwidth under 2.5 Mbps.
- **Operator Recommendation:** For multi-client enterprise networks, future milestones can activate the WebRTC gateway for WAN distribution.

### 3.2 Browser Audio-Video Autoplay Policies
- **Constraint:** Modern web browsers (Google Chrome, Edge) restrict unmuted video playback unless triggered by an explicit user gesture (click/tap).
- **Architectural Mitigation:** Live surveillance streams and recording preview players default to `muted` with visual volume controls, ensuring immediate zero-click stream playback upon navigation.

---

## 4. Containerization & Docker Considerations

### 4.1 USB Webcams in Windows Docker / WSL2
- **Constraint:** Docker containers running on Windows under WSL2 backend cannot natively access DirectShow USB webcams without third-party USB/IP kernel bridging (`usbipd-win`).
- **Architectural Mitigation:** DeepVision 4.0 employs the Host Camera Bridge pattern (`scripts/host_camera_bridge.py` on port 8554). The bridge runs directly on the Windows host with native DirectShow access, allowing containerized or host Django services to ingest the camera feed over high-speed HTTP loopback without kernel driver complications.

---

## 5. Security & Maintenance Boundaries

### 5.1 SQLite Concurrency & Database Locking
- **Constraint:** SQLite allows multiple concurrent readers but serializes write transactions with a file-level write lock. Under heavy simultaneous alert generation across 10 streams, high write volume requires brief WAL (Write-Ahead Logging) waits.
- **Architectural Mitigation:** Database connections are configured with `timeout=30.0` and WAL mode enabled (`PRAGMA journal_mode=WAL;`), preventing `database is locked` operational errors.
- **Operator Recommendation:** SQLite easily handles up to 50 write transactions per second in WAL mode. For enterprise clusters with 50+ cameras, migrating to PostgreSQL is documented in `verification/migrate_sqlite_to_postgres.py`.

