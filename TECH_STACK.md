# DeepVision Technology Stack

## 1. Runtime Environment
- **Host OS**: Microsoft Windows 11 (64-bit AMD64)
- **Python**: 3.14.7
- **Virtual Environment**: Isolated virtualenv at `d:\DeepVision\venv`
- **Package Status**: Verified clean via `pip check` (0 broken requirements)

---

## 2. Frontend
- **Framework**: React 19 (`react` 19.2.4, `react-dom` 19.2.4)
- **Build Tool**: Vite 6+ (`vite` 6.4.1)
- **Language**: JavaScript ES6+ / JSX
- **Styling**: Vanilla CSS3 Design System with CSS Custom Properties (Dark SOC theme & Daylight theme)
- **Distribution**: Bundled directly to `deepvision_django/static/dist/` for production serving
- **Icons**: Inline SVG Surveillance Icons (Zero heavy third-party icon packages)
- **API Communication**: Native browser `fetch()` centralized in `frontend/src/services/api.js` with automatic CSRF synchronization

---

## 3. Backend & REST API
- **Web Framework**: Django 5.2.17
- **Architecture**: Single-process unified web & surveillance server
- **Database ORM**: Django ORM (`models.Model` mapped to SQLite tables with `managed = False`)
- **API Format**: RESTful JSON responses (`django.http.JsonResponse`)
- **Session Architecture**: Signed-cookie session engine (`django.contrib.sessions.backends.signed_cookies`)
- **Password Hasher**: PBKDF2 (`pbkdf2_sha256`) via Django's `make_password` / `check_password`
- **Legacy Compatibility**: Backward-compatible check for legacy `scrypt` user hashes via `werkzeug>=3.0.0` with transparent in-place auto-upgrade to PBKDF2

---

## 4. Computer Vision & Streaming Subsystem
- **Capture Engine**: OpenCV 5.0.0 (`opencv-python` 5.0.0.93)
- **Hardware Backend**: DirectShow (`cv2.CAP_DSHOW` targeting `dshow://0`)
- **Matrix Mathematics**: NumPy 2.5.2
- **Streaming Protocol**: HTTP Multipart MJPEG (`multipart/x-mixed-replace; boundary=frame`) via Django `StreamingHttpResponse`
- **Dual View Modes**:
  1. `ORIGINAL`: Raw DirectShow CCTV passthrough
  2. `TRACKING + DETECTION`: Real-time YOLO11n bounding boxes, labels, confidence, and ByteTrack persistent track IDs
- **Snapshot Capture**: Direct JPEG encoding via `cv2.imencode('.jpg', ...)`

---

## 5. Artificial Intelligence & Object Tracking
- **Neural Network Framework**: PyTorch 2.13.0+cpu (`torch.inference_mode()`)
- **Model Loader & Bridge**: Ultralytics 8.4.117
- **Object Detection Model**: YOLO11n (`models/yolo11n.pt`, 5.35 MB, 80 COCO classes)
- **Multi-Object Tracker**: ByteTrack (`bytetrack.yaml`) with Kalman Filtering and Hungarian matching
- **Singleton Management**: Exactly 1 shared `nn.Module` weights instance in RAM; zero duplicate disk loading

---

## 6. Storage & Recording Subsystem
- **Relational Database**: SQLite 3.50.4 (`instance/deepvision.db`, 18 tables, SHA256 signature verified, `PRAGMA integrity_check = ok`)
- **Video Recorder**: OpenCV `VideoWriter` (`cv2.VideoWriter` encoding to MP4)
- **Media Playback**: HTTP 206 Partial Content Range streaming supporting HTML5 `<video>` scrubbing and seekable playback
- **Forensic Storage**:
  - Video Recordings: `instance/recordings/camera_<id>/`
  - Evidence Vault: `instance/evidence/camera_<id>/<date>/`

---

## 7. Eliminated Technologies
The following obsolete and legacy frameworks have been completely removed from both the codebase and virtual environment:
- **Flask**: 0 references, uninstalled, no supervisor, port 5000 eliminated
- **Flask-SQLAlchemy**: 0 references, uninstalled
- **SQLAlchemy & Greenlet**: Confirmed dead, uninstalled
- **Werkzeug User-facing Routing**: Removed (Werkzeug retained solely as backward-compatibility password hasher)
- **Tabler / Bootstrap**: Unused vendor directory `static/vendor/tabler/` completely removed
