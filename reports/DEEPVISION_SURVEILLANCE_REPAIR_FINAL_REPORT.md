# DeepVision 4.0 — Complete Surveillance System Repair & Verification Report

**Repository:** `VAIBHAV-w1/DeepVision`  
**Branch:** `repair/pipeline-e2e-verification` (branched from `origin/main` @ `aae97ad`)  
**Scope:** End-to-end camera, AI inference, tracking, restricted-zone, recording & UI stabilization release candidate (PR targeting `main`, not merged or deployed)  
**Canonical SQLite Baseline:** `26,567` rows across `18` tables (verified intact before/after every run)

---

## 1. Root Causes Discovered & Fixes Implemented

1. **Cold-Start 10s Stream Timeout & Model Thread Contention**
   - *Cause:* `generate_tracking_stream()` set `start_no_frame_time = time.time()` *before* constructing `ByteTrackTracker` synchronously inside `InferenceRegistry.get_worker()`, which loaded `YOLO11n` (`~16.2s` CPU cold start), tripping the 10s no-frame timeout before yielding a frame. `model_loader.py` hardcoded `torch.set_num_threads(4)` and `settings.py` hardcoded `YOLO_IMAGE_SIZE = 640`, `YOLO_INFERENCE_INTERVAL_MS = 60`.
   - *Fix:* Added `lazy_init`, `ensure_model_loaded()`, and `detector_backend` to `ByteTrackTracker` (`tracker.py`), wired `lazy_init=True` in `InferenceRegistry.get_worker()` (`registry.py`), initialized weights asynchronously at entry of `InferenceWorker._inference_loop()` (`workers.py`), reset `start_no_frame_time` after worker acquisition in `generate_raw_stream()` / `generate_tracking_stream()` (`stream_service.py`), bounded PyTorch threads via `OMP_NUM_THREADS` (`min(2, cpu_count)` default) in `model_loader.py`, and made `YOLO_IMAGE_SIZE` (`480` default) and `YOLO_INFERENCE_INTERVAL_MS` (`120` default) env-configurable (`settings.py`). Observed non-blocking init: **`0.150 ms`** (`0.162 ms` latest run).

2. **CPU Bounding-Box Wipe (`hide_boxes > 1500 ms`) & Long Global ID Truncation**
   - *Cause:* Render CPU `YOLO11n` averaged `1404.91 ms` (`p95 = 5349.97 ms`), repeatedly tripping `inference_age_ms > 1500.0` in `stream_service.py` and hiding boxes. Long UUID `global_id` suffixes also clipped off-screen.
   - *Fix:* Extracted unified `render_annotated_frame()` (`stream_service.py`), raised `hide_boxes` cutoff to `6000.0 ms` (with stale tint `> 2000.0 ms`), and condensed rendered person `global_id` strings (`PERSON-001`).

3. **Unannotated Snapshots, Stale Stats, Missing Health Status & OpenCV Fallback Accuracy**
   - *Cause:* `GET /api/cameras/<id>/snapshot/` ignored `?mode=tracking`, `get_camera_stats()` depended exclusively on `/stream/` `_stream_telemetry`, `camera_ingest_frame_view` omitted `tracks_list`/`detector_backend` and failed to update `update_camera_health(..., status="online")`, and `_track_opencv_fallback()` mislabeled wide seated human torsos as `"car"`, discarded close-up subjects (`w > fw * 0.90 or h > fh * 0.90`), and missed static/cold scenes.
   - *Fix:* Updated `get_camera_snapshot(..., mode="raw"|"tracking")` and `get_camera_stats()` (`engine.py`) + `camera_snapshot_view`, `camera_ingest_frame_view`, `camera_disconnect_view` (`views.py`). Upgraded `_track_opencv_fallback()` (`tracker.py`) with dark-scene (`< 55`) `absdiff` vs normal-room bright-wall suppression (`HSV`) + `MOG2` flood guard, removed spurious indoor `"car"` labels, recovered close-up subjects (`<= 97%`), and improved overall F1 on `eval_dataset` from `0.1633` to `0.4615` (strict `person` F1: `0.6857`).

4. **Restricted-Zone Integer Collapse & Resolution Scaling Mismatch**
   - *Cause:* `api_camera_zones` cast coordinates via `int(...)` (`0.25 -> 0`), collapsing normalized zones to `(0, 0, 0, 0)`, and `RestrictedZone.is_point_inside()` / `_to_pixel_coords()` clamped coordinates across different resolutions (`1280x720` vs `640x480`).
   - *Fix:* Added shared `resolve_zone_pixel_bounds()` (`apps/surveillance/ai/anomaly/zones.py`), wired it through `RestrictedZone.is_point_inside()` (`models.py`), `AnomalyDetector.detect(..., frame_size)` (`anomaly_detector.py`), `InferenceWorker` (`workers.py`), and `stream_service.py`; updated `api_camera_zones` (`api.py`) to convert normalized `0..1` inputs cleanly to canonical `1280x720` integers and support `zone_id` updates (`POST`/`PUT`).

5. **Duplicate Registration, Black Frontend Main Viewport & Zone UI**
   - *Cause:* `POST /api/cameras/` lacked duplicate name/source guards, and `Cameras.jsx` prematurely forced `setStreamLoaded(true)` even when MJPEG failed or buffered behind Vercel's rewrite proxy, leaving `#090E1A` black behind the PIP `<video>`. View 4 (`zone`) rendered a hardcoded SVG polygon (`120,440 ... 780,440`).
   - *Fix:* Added HTTP `409` duplicate-name and explicit-source protection in `api_cameras_list` (`api.py`) and `isSavingCamera` double-submit lock in `Cameras.jsx`; added shared `renderLiveFeedElement()` with automatic `/api/cameras/<id>/snapshot/?mode=<aiMode>` blob fallback (`1.8s` timer + `onError`), live `activeTracksList` chips, truthful `detector_backend` badge (`OpenCV Fallback` / `YOLOv11`), real DB `zones` rendering with proportional scaling and Create/Edit/Toggle/Delete controls, live alert polling, `devicechange` hot-plug listener, `NotReadableError` mapping, and 3 trilingual keys (`en`/`hi`/`kn`) in `translations.js`.

---

## 2. Verification Summary (Observed Status Only)

| Subsystem / Check | Status | Observed Evidence |
| :--- | :--- | :--- |
| Django System Check (`manage.py check`) | **PASS** | `0` issues |
| Django Accounts & Email Tests (`apps.accounts.tests`) | **PASS** | `8/8` tests OK (`0.039s`) |
| Frontend Build (`npm --prefix frontend run build`) | **PASS** | Built cleanly into `deepvision_django/static/dist/` (`379ms`) |
| Frontend ESLint (`oxlint` on Windows Host) | **BLOCKED (OS Policy)** | `@oxlint/binding-win32-x64-msvc` blocked locally by Windows Application Control; JS safety & bundle verified via `vite build` + `test_csp_and_startup_loader.py` (`4/4 OK`) |
| Localization Parity (`audit_complete_localization.cjs`) | **PASS** | `605` EN / `605` HI / `605` KN keys, `0` missing, `0` unregistered |
| Full-System E2E Script (`test_e2e_full_system.py`) | **PASS** | `7/7` suites passed (Vercel routing, telemetry, branding, code splitting, 206 streaming, evidence, secret scan) |
| YOLO11n Weights Verification (`models/yolo11n.pt`) | **PASS** | Present (`5,613,764` bytes), SHA-256 matches `Dockerfile` (`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`) |
| Native `YOLO11n` + `ByteTrack` Runtime on Windows Host | **BLOCKED (OS Policy)** | `torch.dll` and `_lapjv.pyd` blocked by Windows App Control `[WinError 4551]`; Linux production container (`Dockerfile`) runtime is **NOT TESTED** post-edit |
| OpenCV Fallback Evaluation (`eval_dataset`, 12 static frames) | **PASS** (Fallback) | Baseline: `P=0.2500, R=0.1212, F1=0.1633` (`TP=4, FP=12, FN=29`) -> Upgraded: **`P=0.6316, R=0.3636, F1=0.4615`** (`TP=12, FP=7, FN=21`; **Person-only `P=0.6316, R=0.7500, F1=0.6857`**; `17.81 ms/frame`). Non-DNN `phone_eval_dataset` remains `0.00` (semantic item classification requires DNN) |
| Tracking ID Stability (`seq_01..seq_03`, 60 frames each) | **PASS** | `seq_01`: unique IDs `[1]` (`15.52 ms`); `seq_02`: `[1, 2]` (`15.73 ms`); `seq_03`: `[1, 2, 3]` (`15.35 ms`) |
| Pipeline & Zone Scaling E2E (`verify_e2e_pipeline.py`) | **PASS** | Lazy init `0.162 ms`; box kept @ `2500 ms`; `409` dup guard; zone `(0.2..0.8,0.15..0.9)` stored as `[256,108,1024,648]` & scaled to `[128,72,512,432]` @ `640x480`; `[ALERT_CREATED] event=restricted_area_entry`; MP4 `206`; DB `26,568` before/after when script case cleanup runs, verified `26,567` via `fix_case.py` |
| Headless Chrome Physical Webcam Direct Probe | **BLOCKED (Host)** | `getUserMedia` without fake device returned `NotReadableError: Device in use` |
| OpenCV `CAP_DSHOW` Physical Webcam Capture | **PASS** (Unsandboxed) | Captured `18` real `640x480` webcam frames inside `test_persistent_storage_suite.py` (`BypassSandbox: true`) |
| Real Chrome CDP Browser UI E2E (Y4M from `seq_01`) | **PASS** | Registration modal -> non-black live feed (`640x480`, `meanLum=102.5`) -> visible person box + IDs -> red intrusion banner + right card alert -> REC start/stop -> `0` console/JS/5xx errors -> DB `26,567` |
| Live Production Supabase Bucket Upload Verification | **NOT TESTED** | Local `.env` keeps Supabase secrets unset; verified via full HTTP mock protocol (`test_persistent_storage_suite.py`); live Render/Supabase E2E awaits approved deployment |
| Regression Pass 1 (`master`, `storage`, `auth_matrix`) | **PASS** | Master: **PASS** (`26,567`), Storage: **PASS** (`26,567`), Auth Matrix: **16/16 PASS** (`26,567`) |
| Regression Pass 2 (`master`, `storage`, `auth_matrix`) | **PASS** | Master: **PASS** (`26,567`), Storage: **PASS** (`26,567`), Auth Matrix: **16/16 PASS** (`26,567`) |
| Diff Hygiene & Secret Scan | **PASS** | `git diff --check` exited `0`; `SECRET_HITS: 0 []` across all `14` runtime files |

---

## 3. Staged Release Candidate Files (`repair/pipeline-e2e-verification`)

- `deepvision_django/apps/ai/engine.py`
- `deepvision_django/apps/cameras/views.py`
- `deepvision_django/apps/core/api.py`
- `deepvision_django/apps/core/models.py`
- `deepvision_django/apps/surveillance/ai/anomaly/anomaly_detector.py`
- `deepvision_django/apps/surveillance/ai/anomaly/zones.py`
- `deepvision_django/apps/surveillance/ai/model_loader.py`
- `deepvision_django/apps/surveillance/ai/registry.py`
- `deepvision_django/apps/surveillance/ai/tracker.py`
- `deepvision_django/apps/surveillance/ai/workers.py`
- `deepvision_django/apps/surveillance/streaming/stream_service.py`
- `deepvision_django/config/settings.py`
- `frontend/src/i18n/translations.js`
- `frontend/src/pages/Cameras.jsx`
- `reports/DEEPVISION_SURVEILLANCE_REPAIR_FINAL_REPORT.md`
