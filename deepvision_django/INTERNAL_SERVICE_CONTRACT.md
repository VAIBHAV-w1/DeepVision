# DeepVision Internal Surveillance Service Contract

**Document Version:** 1.0.0 (Phase 13 Reconciled)  
**Boundary:** Django (:8000 Web/API Layer) ↔ Flask (:5000 Headless Surveillance Engine)  
**Adapter Implementation:** `deepvision_django/apps/ai/engine.py`

---

## 1. Architectural Principles

1. **Sole User-Facing Application:** Django on port 8000 owns all UI, authentication, sessions, dashboards, cases, alerts, notifications, and client-facing APIs.
2. **Headless Surveillance Engine:** Flask on port 5000 owns OpenCV, DirectShow hardware binding (`dshow://0`), CameraRegistry, CameraWorker, InferenceWorker, YOLO11n, ByteTrack, and the canonical recording engine.
3. **Single Channel of Inter-Service Communication:** All communication from Django to Flask MUST traverse `apps/ai/engine.py`. Django views must NEVER construct direct HTTP requests to port 5000 or import OpenCV hardware capture modules.
4. **Reversible Legacy UI Retirement:** `ENABLE_LEGACY_FLASK_UI=false` by default. Legacy Flask UI routes redirect (HTTP 302) to Django equivalents. Internal service endpoints remain available.

---

## 2. Supported User-Facing Surveillance Modes

User-facing modes are strictly normalized to **EXACTLY TWO**:
1. `ORIGINAL` (Normalized internally as `"raw"`): Raw MJPEG stream from the physical camera without AI bounding boxes or tracker overlays.
2. `TRACKING + DETECTION` (Normalized internally as `"tracking"`): MJPEG stream overlaid with YOLO11n bounding boxes, labels, confidence scores, and ByteTrack persistent track IDs.

*Prohibited modes:* "Detection-only", "Tracking-only", or generic "AI mode" aliases are rejected or mapped to the canonical `tracking` mode.

---

## 3. Authoritative Flask Service Endpoint Inventory

| Endpoint | HTTP Method | Auth Required | Query / Payload | Response Type | Description |
|:---|:---:|:---:|:---|:---:|:---|
| `/api/system/health` | GET | Signed Session | None | JSON | System status, RAM usage, and camera subsystem readiness. |
| `/cameras/<id>/stream` | GET | Signed Session | `?mode=raw` or `?mode=tracking` | MJPEG (`multipart/x-mixed-replace`) | Canonical streaming endpoint for raw or AI-overlaid camera frames. |
| `/cameras/<id>/stream/tracking` | GET | Signed Session | None | MJPEG (`multipart/x-mixed-replace`) | Direct stream alias for Tracking + Detection. |
| `/cameras/<id>/snapshot` | GET | Signed Session | None | Image (`image/jpeg`) | Single current JPEG frame (e.g. for previews, evidence creation). |
| `/api/cameras/<id>/stats` | GET | Signed Session | None | JSON | Live camera FPS, active track count, and anomaly events. |
| `/cameras/<id>/warm` | GET | Signed Session | None | JSON | Pre-warms CameraWorker and InferenceWorker prior to active viewing. |
| `/cameras/<id>/record/start` | POST | Signed Session | None | JSON (`{"status": "recording", "recording_id": ...}`) | Initiates recording on the specified camera worker. |
| `/cameras/<id>/record/stop` | POST | Signed Session | None | JSON (`{"status": "stopped", "recording_id": ...}`) | Stops recording and finalizes MP4 file in `outputs/recordings/`. |
| `/api/cameras/test-connection` | POST | Signed Session | JSON (`{"source_type": ..., "source": ...}`) | JSON (`{"success": bool, "message": str}`) | Validates camera hardware feed parameters before registration. |
| `/api/cameras/<id>/test` | POST | Signed Session | None | JSON (`{"success": bool, ...}`) | Tests connectivity of an existing camera record. |
| `/cameras/<id>/health` | GET | Signed Session | None | JSON | Returns per-camera worker health and buffer metrics. |

---

## 4. Django Engine Adapter Mapping (`apps/ai/engine.py`)

| Adapter Python Function | Target Flask Route | Method | Timeout (Connect, Read) | Fallback / Degradation Behavior |
|:---|:---|:---:|:---:|:---|
| `is_engine_reachable()` | `127.0.0.1:5000` | TCP Socket | 1.0s | Returns `False` without exception. |
| `get_engine_status()` | N/A (Static metadata + socket) | Probe | 1.0s | Returns diagnostic dict indicating engine reachability. |
| `get_engine_health(user_id)` | `/api/system/health` | GET | 1.5s | Returns `status: "unavailable"` when engine offline; never crashes. |
| `normalize_mode(mode)` | N/A (Local logic) | In-Memory | N/A | Maps input to `"raw"` or `"tracking"`. |
| `stream_camera_frames(id, user_id, mode)` | `/cameras/<id>/stream?mode=<mode>` | GET (Stream) | 3.0s, 15.0s | Yields chunks; handles `GeneratorExit` cleanly upon client disconnect. |
| `get_camera_snapshot(id, user_id)` | `/cameras/<id>/snapshot` | GET | 4.0s | Returns `bytes` or `None` on failure. |
| `get_camera_stats(id, user_id)` | `/api/cameras/<id>/stats` | GET | 2.0s | Returns zeroed telemetry dict (`fps: 0.0`) on engine outage. |
| `warm_camera(id, user_id)` | `/cameras/<id>/warm` | GET | 2.0s | Returns `bool` success flag. |
| `start_camera_recording(id, user_id)` | `/cameras/<id>/record/start` | POST | 5.0s | Returns error JSON with HTTP status message on failure. |
| `stop_camera_recording(id, user_id)` | `/cameras/<id>/record/stop` | POST | 5.0s | Returns error JSON with HTTP status message on failure. |
| `test_camera_connection(...)` | `/api/cameras/test-connection` | POST | 6.0s | Returns `{"success": false, "message": "Surveillance engine is unreachable."}`. |
| `test_existing_camera(id, user_id)` | `/api/cameras/<id>/test` | POST | 6.0s | Returns `{"success": false, "message": "Surveillance engine is unreachable."}`. |

---

## 5. Security & Session Token Architecture

- **Inter-Service Authentication:** Django generates an HMAC-signed session cookie using `itsdangerous.URLSafeTimedSerializer` with SHA-1 digest matching Flask's session signer and `SURVEILLANCE_ENGINE_SECRET`.
- **Session Payload:** Cryptographically binds `{"user_id": <int>}` ensuring Flask enforces ownership rules identically to native sessions.
- **Header & Token Security:**
  - `trust_env = False` configured in requests session to prevent localhost requests traversing OS proxy configurations.
  - Secret keys and service tokens are strictly forbidden from logging and error messages.
  - Path parameters are validated as positive integers (`<int:id>`).

---

## 6. Route Reconciliations & Aliases Audit

1. **Stream Endpoints:**
   - Canonical: `/cameras/<int:id>/stream?mode=raw` and `/cameras/<int:id>/stream?mode=tracking`
   - Active Aliases: `/cameras/<int:id>/stream/tracking` (maps to `main.track_camera`), `/cameras/<int:id>/track`
   - Resolution: Both canonical parameterized and legacy alias routes remain active on Flask for backward compatibility. Django standardizes on `/cameras/<id>/stream?mode={mode}`.
2. **Recording Endpoints:**
   - Canonical in Engine: `/cameras/<int:id>/record/start` and `/cameras/<int:id>/record/stop`
   - Active Aliases: `/api/cameras/<int:id>/record/start` and `/api/cameras/<int:id>/record/stop`
   - Resolution: Both endpoints invoke the identical `main.start_camera_recording_route` and `main.stop_camera_recording_route` handlers.
3. **Telemetry & Stats Endpoints:**
   - Canonical in Engine: `/api/cameras/<int:id>/stats`
   - Active Aliases: `/api/cameras/<int:id>/status` and `/cameras/<int:id>/status`
   - Resolution: All routes resolve to `main.camera_status`.
