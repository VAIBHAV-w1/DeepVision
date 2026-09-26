"""
Camera Worker Thread Implementation.
Reads frames continuously from VideoCapture into thread-safe rolling buffers.
"""
import time
import threading
from collections import deque
import cv2

from apps.surveillance.camera.capture import safe_open_video_capture


class CameraWorker:
    """
    Dedicated background capture thread for a single physical camera.
    Reads frames at native FPS and stores them in a thread-safe rolling buffer.
    Multiple stream clients share ONE CameraWorker.
    """
    def __init__(self, camera_id, cap_source, source_type, user_id=None, physical_source_id=None):
        self.camera_id = camera_id
        self.cap_source = cap_source
        self.source_type = source_type
        self.user_id = user_id
        self.physical_source_id = physical_source_id or str(cap_source)
        
        self.capture = None
        self.thread = None
        self.running = False
        self.ref_count = 0
        self.lock = threading.Lock()
        
        self.latest_frame = None
        self.rolling_buffer = deque(maxlen=180)  # ~6-10 seconds at 20-30 FPS
        self.frame_id = 0
        self.fps = 0.0
        self.last_frame_time = 0.0
        self.is_starting = False
        self.start_error = None
        self.start_event = threading.Event()
        self.last_error = None

    def get_current_frame(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None

    def get_recent_buffer(self, max_frames=60):
        with self.lock:
            return list(self.rolling_buffer)[-max_frames:]

    def start(self):
        self.is_starting = True
        self.start_event.clear()
        self.start_error = None
        try:
            with self.lock:
                if not self.running:
                    self.capture = safe_open_video_capture(self.cap_source)
                    if not self.capture.isOpened():
                        raise RuntimeError(f"Failed to open video capture source for camera {self.camera_id}.")
                    self.running = True
                    self.thread = threading.Thread(
                        target=self._read_loop, 
                        name=f"CameraWorker-{self.camera_id}", 
                        daemon=True
                    )
                    self.thread.start()
                    print(f"[CAMERA_WORKER_STARTED] camera_id={self.camera_id} physical_source={self.physical_source_id}")
        except Exception as e:
            self.start_error = e
            raise
        finally:
            self.is_starting = False
            self.start_event.set()

    def _read_loop(self):
        last_fps_time = time.time()
        frames_read = 0
        consecutive_failures = 0
        is_network = self.source_type in ("phone", "ipcamera", "rtsp")
        
        try:
            while True:
                with self.lock:
                    if not self.running:
                        break
                
                success = False
                frame = None
                try:
                    with self.lock:
                        cap_ref = self.capture
                    if cap_ref is not None:
                        success, frame = cap_ref.read()
                except Exception as read_err:
                    success = False
                    self.last_error = str(read_err)

                if success and frame is not None and frame.size > 0:
                    consecutive_failures = 0
                    now = time.time()
                    with self.lock:
                        self.latest_frame = frame
                        self.rolling_buffer.append(frame.copy())
                        self.frame_id += 1
                        self.last_frame_time = now

                    try:
                        from apps.surveillance.recording import recording_service
                        recording_service.write_frame(self.camera_id, frame)
                    except Exception:
                        pass

                    frames_read += 1
                    if frames_read >= 15:
                        dt = now - last_fps_time
                        if dt > 0:
                            self.fps = round(frames_read / dt, 1)
                        frames_read = 0
                        last_fps_time = now

                    # Sleep briefly for non-webcam sources
                    if self.source_type not in ("webcam", "usb") and not isinstance(self.cap_source, int):
                        time.sleep(0.015)
                    else:
                        time.sleep(0.002)
                else:
                    consecutive_failures += 1
                    if consecutive_failures % 30 == 0:
                        print(f"[CAMERA_WORKER_WARN] Camera {self.camera_id}: {consecutive_failures} consecutive frame read failures.")
                    time.sleep(0.05)
                    if consecutive_failures > 300 and not is_network:
                        break
        except Exception as e:
            print(f"[CAMERA_WORKER_ERROR] Camera {self.camera_id} loop exception: {e}")
            self.last_error = str(e)
        finally:
            with self.lock:
                self.running = False
            print(f"[CAMERA_WORKER_EXIT] camera_id={self.camera_id}")

    def stop(self):
        with self.lock:
            self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            self.thread = None
        with self.lock:
            cap = self.capture
            self.capture = None
        if cap:
            try:
                cap.release()
            except Exception:
                pass
        print(f"[CAMERA_WORKER_RELEASED] camera_id={self.camera_id}")
