# DeepVision Architecture & System Blueprint

## 1. System Overview
DeepVision is a hybrid architecture pairing a high-throughput Django surveillance engine with a modern React SPA frontend:
- **Backend:** Django 5.1.7, Python 3.12, OpenCV 4.10, PyTorch, Ultralytics YOLO11n, ByteTrack.
- **Frontend:** React 18, Vite 6, Vanilla CSS Design System with CSS Tokens.
- **Data Persistence:** Active SQLite database (`instance/deepvision.db`) with prepared MySQL migration tooling.
- **Media Delivery:** HTTP multipart/x-mixed-replace MJPEG streaming and HTTP 206 Partial Content video streaming.

## 2. Component Architecture

```
[ Camera Hardware / RTSP Feeds ]
             │
             ▼
[ CameraWorker & CameraRegistry (OpenCV) ]
             │
             ├──► Frame Buffer (Raw Frames) ─────────► [ Original MJPEG Stream ]
             │
             ▼
[ AI Inference Singleton (YOLO11n + ByteTrack) ]
             │
             ├──► Annotated Frame Buffer ─────────────► [ Tracking MJPEG Stream ]
             ├──► Detection Events ───────────────────► [ Alert Engine & DB ]
             └──► Rolling Video Writer ───────────────► [ MP4 Recording Storage ]
                                                              │
[ Django REST & Auth API ] ◄──────────────────────────────────┘
             │
             ▼
[ React 18 SPA (Vite) ]
  ├── Shell: AppLayout, Navbar, AssistantChat
  ├── Operational Pages:
  │     ├── Dashboard (Operational Overview & Metrics)
  │     ├── Cameras & CameraPreview (Reference 1 Live Monitoring HUD)
  │     ├── Alerts (Forensic Workspace)
  │     ├── Recordings (HTTP 206 Playback)
  │     ├── Evidence (Evidence Vault)
  │     ├── Cases (Case Management)
  │     ├── Notifications (Notification Inbox)
  │     └── Help (Operator Documentation)
  └── Auth Pages: Login, Signup, OTP Verification, Password Reset
```

## 3. Data Flow & Ingestion Pipeline
1. **Camera Ingestion:** `CameraWorker` captures frames continuously via DirectShow (`dshow://0`) or RTSP.
2. **AI Inference:** The worker passes frames to the `AIModelEngine` singleton (`engine.py`). YOLO11n detects persons and objects, passing detections to `ByteTracker` for persistent ID assignment.
3. **Streaming Endpoints:**
   - `/cameras/<id>/stream/?mode=original`: Yields raw frames without neural overlay.
   - `/cameras/<id>/stream/?mode=tracking`: Yields annotated frames with bounding boxes, labels, and tracking IDs.
   - `/cameras/<id>/snapshot/`: Returns latest frame as high-resolution JPEG.
   - `/cameras/<id>/stats/`: Returns live JSON telemetry (FPS, detection count, active track list).
4. **Recording:** `start_camera_recording()` writes MP4 files using OpenCV `VideoWriter`. Completed clips are registered in the `Recording` database table.

## 4. Security & Access Boundaries
- Session-based authentication using Django PBKDF2 password hashing.
- Two-factor email OTP validation for login and registration.
- Custom CSRF cookie handling (`deepvision_django_csrftoken`) and session cookie (`deepvision_django_session`).
- Server-side authorization decorators (`@login_required`) enforce all API boundaries.
