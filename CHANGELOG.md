# Changelog

All notable changes to the DeepVision project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-27

### Added
- **Production Multi-Stage Dockerization**: Multi-stage Docker build pipeline (`Node 20 Alpine` Vite asset builder + `Python 3.11-slim` runtime) delivering an optimized containerized deployment (`deepvision:1.1.0`).
- **Container Healthcheck API**: Integrated `/api/health/` endpoint providing real-time system and database health telemetry for container orchestrators.
- **Docker Compose Orchestration**: Production `docker-compose.yml` supporting persistent volume mounts (`./instance`, `./recordings`, `./evidence`, `./models`), non-root security isolation (`deepvision` UID 1000), and automated health checks.
- **Automated Docker Runtime Verification Suite**: Comprehensive 15-point verification script (`verification/test_docker_container.py`) validating container health, SPA delivery, asset serving, authenticated session handling, API endpoints, AI imports, and restart persistence.
- **Structured Documentation Architecture**: Reorganized repository documentation into hierarchical `docs/` subdirectories (`docs/architecture/`, `docs/technical/`, `docs/reports/`, `docs/releases/`, `docs/project/`) preserving full audit history while ensuring a clean root directory.

### Changed
- Standardized repository root layout preserving only core operational files.
- Enhanced `start_deepvision.py` launcher with environment-driven host/port binding (`DEEPVISION_HOST`, `DEEPVISION_PORT`), automatic virtualenv Python resolution, and static asset fallback flag.
- Extended Django `CSRF_TRUSTED_ORIGINS` to support Docker host network topologies.
- Updated `.env.example` and `.gitignore` with Docker configuration and container exclusion patterns.

### Verified
- Automated 15/15 checks passed in Docker container test suite (`verification/test_docker_container.py`).
- Automated 29/29 checks passed in native Windows regression suite (`verification/verify_final_restructure.py`).
- DirectShow (`dshow://0`) native camera capture, YOLO11n singleton, ByteTrack tracking, recording, and alert generation verified with zero regressions.
- Incident scoping and data isolation verified 100% passed (`verification/test_incident_scoping.py`).

## [1.0.0] - 2026-09-27

### Added
- **Alerts Forensic Operations Center**: Incident-centric workspace in React frontend with unified master inbox and detailed incident inspection.
- **Incident Scoping Architecture**: Scoped evidence vault, video recordings, timeline events, and active case files correlated exclusively to the selected incident.
- **Independent Notification Center**: Dedicated global notifications inbox decoupled from incident-specific alerts with deep-linking to correlated incidents.
- **AI Forensic Analysis**: Incident-level intelligence reporting with severity classification, AI confidence score, and forensic timeline reconstruction.
- **Surveillance Engine Modes**: Dual-mode camera streaming with instant toggle between `ORIGINAL` (raw CCTV direct stream) and `TRACKING + DETECTION` (YOLO11n + ByteTrack real-time bounding boxes and track IDs).
- **Single-Process Video Pipeline**: Zero-overhead in-process worker model with 1 physical `VideoCapture` handle, 1 `CameraWorker`, 1 `InferenceWorker`, and singleton `YOLO11n` model instance.
- **Authentication & Security Guardrails**: PBKDF2 (`pbkdf2_sha256`) password hashing, automatic legacy hash upgrade, 6-digit cryptographic email OTP verification, and signed-cookie sessions.
- **HTTP 206 Partial Content Video Streaming**: Range-header compliant video playback for recorded incident evidence with truthful audio availability metadata.

### Changed
- Consolidated frontend navigation into clean React SPA layout eliminating legacy template redundancies.
- Standardized REST API endpoints under `/api/` for cameras, alerts, recordings, evidence, cases, and notifications.
- Streamlined settings and environment configuration through `.env` and `.env.example`.

### Fixed
- Fixed cross-incident data bleed by enforcing strict incident foreign key filtering across evidence and recording endpoints.
- Fixed stream freeze during camera mode switches by maintaining a persistent capture worker and decoupling inference buffers.
- Fixed CSRF token synchronization in single-page React navigation.

### Verified
- Automated 29-point backend architecture verification suite (`verification/verify_final_restructure.py`).
- Automated incident scoping isolation test suite (`verification/test_incident_scoping.py`).
- Full-stack browser automation test suite using Chrome DevTools Protocol (`verification/run_incident_forensics_browser_suite.mjs`).
- Database schema invariants and zero-loss integrity verification across 18 SQLite tables.
