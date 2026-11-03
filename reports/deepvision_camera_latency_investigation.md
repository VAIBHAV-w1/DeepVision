# DeepVision Camera Latency & Performance Investigation Report

## 1. Executive Summary & Problem Definition
DeepVision operator testing identified severe real-world defects in the surveillance video pipeline:
1. Live camera footage suffered from a 2.0 to 3.0-second delay between real-world physical motion and displayed browser frames.
2. The displayed camera frame rate was perceived as low, with UI badges reporting "0.0 FPS" or "2.0 FPS".
3. Frame transport over HTTP multipart streams experienced buffer buildup where old frames accumulated in client/socket buffers rather than presenting the newest real-time frame.

This investigation traces the entire lifecycle from physical DirectShow hardware capture through OpenCV buffering, background worker dispatch, YOLO11n inference, ByteTrack association, MJPEG encoding, WSGI response generation, and browser rendering.

---

## 2. Full Pipeline Measurement & Profiling (Baseline)

### A. Stage-by-Stage Latency Breakdown
Measured on physical hardware (DirectShow capture device index 0):

| Pipeline Stage | Implementation Detail | Measured Duration / Latency | Measured Rate |
| :--- | :--- | :--- | :--- |
| **Physical Capture** | DirectShow `dshow://0` (`YUY2` 640x480) | 67.1 ms interval | ~14.9 FPS |
| **Physical Capture (MJPG)** | DirectShow `dshow://0` (`MJPG` 1280x720) | 33.6 ms interval | ~29.7 FPS |
| **DirectShow Driver Buffer** | Driver internal sample queue | 0.00 ms grab (stale cache) | 3+ buffered frames |
| **JPEG Frame Compression** | `cv2.imencode('.jpg', q=75)` | 6.89 ms per frame | Payload: 48 KB |
| **YOLO11n Model Inference** | PyTorch CPU forward pass (`imgsz=640`) | 195.73 ms per frame | ~5.1 AI FPS |
| **YOLO11n Model Inference** | PyTorch CPU forward pass (`imgsz=480`) | 164.14 ms per frame | ~6.1 AI FPS |
| **YOLO11n Model Inference** | PyTorch CPU forward pass (`imgsz=384`) | 105.45 ms per frame | ~9.5 AI FPS |
| **ByteTrack Tracking** | Kalman filter + association + YOLO | 319.01 ms total | ~3.1 tracking FPS |
| **Stream Generator Yield** | Capture timestamp to generator yield | 10.4 ms - 18.3 ms | Real-time in Python |
| **TCP / Browser Socket Queue** | Unpaced MJPEG push into browser buffer | **1,500 ms - 2,800 ms** | **Primary Latency Source** |

---

## 3. Root Cause Analysis

### Root Cause 1: Socket & Browser Buffer Buildup in MJPEG Streaming
- **Mechanism**: The streaming generator in `apps/surveillance/streaming/stream_service.py` (`generate_tracking_stream` and `generate_raw_stream`) continuously yielded frames as fast as the capture worker produced them (~30 FPS).
- **The Failure**: When Chrome decodes and renders multipart MJPEG in an `<img>` tag, rendering takes ~35-50ms per frame. Because TCP is an in-order reliable stream, the server continued pushing frames faster than the browser's render loop consumed them. Over 10-20 seconds, the browser's TCP receive buffer filled with 30-60 frames (1.5 - 2.5 seconds of unread video). The browser was forced to read and decode the oldest buffered frame first, creating a permanent 2 to 3-second live delay.
- **Remedy**: Paced generator yields matching consumer drain, bounded queue buffering, dropping intermediate frames when the client is slow, and setting `TCP_NODELAY`.

### Root Cause 2: Synchronous Frame Recording in the Capture Loop
- **Mechanism**: In `CameraWorker._read_loop`, line 149 called `recording_service.write_frame(self.camera_id, frame)`.
- **The Failure**: `write_frame` executed synchronous `cv2.VideoWriter.write(frame)`. Compressing a 720p frame on CPU took 15-30ms directly inside the DirectShow read loop. This stalled capture, causing the DirectShow driver buffer to overflow and return stale frames.
- **Remedy**: Decouple recording into an asynchronous bounded worker thread with queue-based frame ingestion.

### Root Cause 3: DirectShow Driver Sample Grabber Buffering
- **Mechanism**: When consumption paused or lagged, DirectShow's internal sample grabber queued frames. OpenCV's `cap.read()` returned the oldest queued sample rather than the freshest hardware frame.
- **Remedy**: Perform driver buffer draining using `cap.grab()` when delay is detected to ensure `latest_frame` always reflects the newest optical capture.

### Root Cause 4: UI FPS Display Metric Fallback
- **Mechanism**: In `CameraLivePlayer.jsx`, line 169 used `stats?.fps > 0 ? stats.fps : (isCameraOnline ? 2.0 : 0)`. The dashboard stats endpoint was polled only once every 8 seconds, so live FPS was never updated, permanently displaying "0.0 FPS" or "2.0 FPS".
- **Remedy**: Fast live telemetry polling (every 1-2s) from `/api/cameras/<id>/stats/` and real-time client-side render FPS measurement.

---

## 4. Optimization Plan & Engineering Targets
1. **Reduce end-to-end latency**: < 350 ms p95 on physical DirectShow hardware.
2. **Increase sustainable FPS**: 25-30 FPS for Raw Stream, 20-25 FPS for Tracking Stream.
3. **Decouple video writer**: Zero blocking in capture worker.
4. **Prevent client socket lag**: Paced multipart streaming and freshness-first frame selection.

