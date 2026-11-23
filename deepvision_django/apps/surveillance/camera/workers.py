"""
Camera Worker Thread Implementation.
Reads frames continuously from VideoCapture into thread-safe rolling buffers.
"""
import time
import threading
from collections import deque
try:
    import cv2
except (ImportError, Exception):
    cv2 = None

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
        self.last_capture_monotonic = 0.0
        self.frame_condition = threading.Condition(self.lock)
        self.is_starting = False
        self.start_error = None
        self.start_event = threading.Event()
        self.last_error = None

        self.last_valid_frame_time = 0.0
        self.consecutive_black_frames = 0
        self.state = "CONNECTING"
        self.is_reconnecting = False
        self.last_acquisition_ms = 0.0
        self.acquisition_samples = deque(maxlen=180)
        self.is_browser_pushed = False
        self._browser_fps_window_start = time.time()
        self._browser_frames_pushed = 0
        self.last_ingest_seq = -1

    def start_browser_mode(self):
        """Activates worker in passive browser-pushed mode (navigator.mediaDevices.getUserMedia bridge)."""
        with self.lock:
            self.is_browser_pushed = True
            self.running = True
            self.is_starting = False
            self.start_error = None
            self.last_error = None
            self.last_ingest_seq = -1
            if self.state in ("OFFLINE", "ERROR"):
                self.state = "CONNECTING"
            self.start_event.set()

    def ingest_external_frame(self, frame, seq=None):
        """Injects a decoded BGR numpy frame from an authenticated browser/mobile push client."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return False
        now = time.time()
        now_mono = time.monotonic()
        with self.frame_condition:
            if seq is not None and int(seq) < self.last_ingest_seq:
                return False
            if seq is not None:
                self.last_ingest_seq = int(seq)
            prev_mono = self.last_capture_monotonic
            self.is_browser_pushed = True
            self.running = True
            self.latest_frame = frame
            self.rolling_buffer.append(frame)
            self.frame_id += 1
            self.last_capture_monotonic = now_mono
            self.last_frame_time = now
            self.last_valid_frame_time = now
            self.consecutive_black_frames = 0
            self.last_error = None
            self.state = "ONLINE"
            self._browser_frames_pushed += 1
            dt = now - self._browser_fps_window_start
            if self._browser_frames_pushed >= 2 and dt > 0:
                self.fps = round(self._browser_frames_pushed / dt, 1)
                if self._browser_frames_pushed >= 6 or dt >= 1.5:
                    self._browser_frames_pushed = 0
                    self._browser_fps_window_start = now
            if prev_mono and now_mono > prev_mono:
                self.last_acquisition_ms = round(min(1000.0, (now_mono - prev_mono) * 1000.0), 3)
            else:
                self.last_acquisition_ms = 0.5
            self.frame_condition.notify_all()

        try:
            from apps.surveillance.recording import recording_service
            from apps.surveillance.camera.registry import get_camera_registry
            bound_ids = set(get_camera_registry().get_bound_camera_ids(self.physical_source_id))
            bound_ids.add(self.camera_id)
            for cid in bound_ids:
                recording_service.write_frame(cid, frame)
        except Exception:
            pass
        return True

    def get_frame_age_seconds(self):
        """Returns seconds elapsed since last valid frame, or None if no valid frame has been acquired."""
        with self.lock:
            ts = float(self.last_valid_frame_time or 0.0)
        if ts <= 0.0:
            return None
        return round(max(0.0, time.time() - ts), 2)

    def get_operational_status(self):
        """Returns standard surveillance state: CONNECTING, ONLINE, STALE, RECONNECTING, OFFLINE, ERROR."""
        now = time.time()
        with self.lock:
            if not self.running:
                return "OFFLINE"
            if self.is_reconnecting:
                return "RECONNECTING"
            if self.last_error and self.consecutive_black_frames > 30:
                return "ERROR"
            if self.last_valid_frame_time == 0.0:
                return "CONNECTING"
            dt = now - self.last_valid_frame_time
            online_ttl = 6.0 if self.is_browser_pushed else 4.0
            stale_ttl = 15.0 if self.is_browser_pushed else 12.0
            if dt <= online_ttl:
                return "ONLINE"
            elif dt <= stale_ttl:
                return "STALE"
            else:
                return "OFFLINE"

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
        self.state = "CONNECTING"
        try:
            with self.lock:
                if not self.running:
                    self.capture = safe_open_video_capture(self.cap_source)
                    if not self.capture.isOpened():
                        err_detail = getattr(self.capture, "last_error", None)
                        try:
                            self.capture.release()
                        except Exception:
                            pass
                        self.capture = None
                        suffix = f" ({err_detail})" if err_detail else ""
                        raise RuntimeError(f"Failed to open video capture source for camera {self.camera_id}{suffix}.")
                    probed = getattr(self.capture, "_probed_frame", None)
                    if probed is not None and getattr(probed, "size", 0) > 0:
                        now = time.time()
                        self.latest_frame = probed
                        self.rolling_buffer.append(probed)
                        self.frame_id = 1
                        self.last_capture_monotonic = time.monotonic()
                        self.last_frame_time = now
                        sample = probed[::16, ::16]
                        if float(sample.mean()) >= 1.0 or float(sample.std()) >= 0.5:
                            self.last_valid_frame_time = now
                            self.state = "ONLINE"
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
            self.state = "ERROR"
            raise
        finally:
            self.is_starting = False
            self.start_event.set()

    def _read_loop(self):
        last_fps_time = time.time()
        frames_read = 0
        consecutive_failures = 0
        reconnect_attempts = 0
        is_network = self.source_type in ("phone", "ipcamera", "rtsp", "http", "https", "ip", "mjpeg")
        
        try:
            while True:
                with self.lock:
                    if not self.running:
                        break
                
                success = False
                frame = None
                t_acq0 = time.monotonic()
                try:
                    with self.lock:
                        cap_ref = self.capture
                    if cap_ref is not None:
                        success, frame = cap_ref.read()
                except Exception as read_err:
                    success = False
                    self.last_error = str(read_err)
                acq_ms = (time.monotonic() - t_acq0) * 1000.0

                if success and frame is not None and frame.size > 0:
                    now = time.time()
                    now_mono = time.monotonic()
                    consecutive_failures = 0
                    reconnect_attempts = 0
                    self.last_acquisition_ms = round(acq_ms, 3)
                    self.acquisition_samples.append(acq_ms)

                    # Detect dead zeroed DirectShow buffers (contended device lock vs dark room with real sensor noise)
                    sample = frame[::16, ::16]
                    is_dead_black = (float(sample.mean()) < 1.0 and float(sample.std()) < 0.5)

                    if is_dead_black:
                        self.consecutive_black_frames += 1
                        if self.consecutive_black_frames == 30:
                            self.last_error = "Sustained zero-luminance buffer detected from capture source"
                            print(f"[CAMERA_WORKER_WARN] Camera {self.camera_id}: {self.consecutive_black_frames} consecutive zero-luminance frames.")
                        if self.consecutive_black_frames >= 35 and not is_network:
                            self._attempt_reconnect()
                            last_fps_time = time.time()
                            frames_read = 0
                            continue
                        if self.latest_frame is not None and self.consecutive_black_frames < 35:
                            time.sleep(0.02)
                            continue
                    else:
                        self.consecutive_black_frames = 0
                        self.last_error = None

                    with self.frame_condition:
                        self.latest_frame = frame
                        self.rolling_buffer.append(frame)
                        self.frame_id += 1
                        self.last_capture_monotonic = now_mono
                        self.last_frame_time = now
                        if not is_dead_black:
                            self.last_valid_frame_time = now
                            self.state = "ONLINE"
                        self.frame_condition.notify_all()

                    try:
                        from apps.surveillance.recording import recording_service
                        from apps.surveillance.camera.registry import get_camera_registry
                        bound_ids = set(get_camera_registry().get_bound_camera_ids(self.physical_source_id))
                        bound_ids.add(self.camera_id)
                        for cid in bound_ids:
                            recording_service.write_frame(cid, frame)
                    except Exception:
                        pass

                    frames_read += 1
                    target_window = 4 if self.fps == 0.0 else 10
                    if frames_read >= target_window:
                        dt = now - last_fps_time
                        if dt > 0:
                            self.fps = round(frames_read / dt, 1)
                        frames_read = 0
                        last_fps_time = now

                    # Sleep briefly for non-webcam sources; let DirectShow block naturally at sensor frame rate
                    if self.source_type not in ("webcam", "usb") and not isinstance(self.cap_source, int):
                        time.sleep(0.015)
                    else:
                        time.sleep(0.001)
                else:
                    consecutive_failures += 1
                    if consecutive_failures % 10 == 0:
                        print(f"[CAMERA_WORKER_WARN] Camera {self.camera_id}: {consecutive_failures} consecutive frame read failures.")
                    time.sleep(0.05)
                    
                    reconnect_threshold = 3 if is_network else 25
                    max_reconnect_attempts = 3 if is_network else 6
                    if consecutive_failures >= reconnect_threshold:
                        reconnect_attempts += 1
                        reconnected = self._attempt_reconnect()
                        if reconnected:
                            consecutive_failures = 0
                            reconnect_attempts = 0
                        elif reconnect_attempts >= max_reconnect_attempts:
                            self.state = "OFFLINE"
                            try:
                                from apps.cameras.models import Camera
                                from apps.surveillance.camera.registry import get_camera_registry
                                from apps.accounts.email_service import send_camera_offline_email
                                bound = set(get_camera_registry().get_bound_camera_ids(self.physical_source_id))
                                bound.add(self.camera_id)
                                transitioned = list(
                                    Camera.objects.filter(id__in=bound).exclude(status="offline").values_list("id", flat=True)
                                )
                                if transitioned:
                                    Camera.objects.filter(id__in=transitioned).update(status="offline")
                                    for cid in transitioned:
                                        try:
                                            send_camera_offline_email(cid, reason="Max capture reconnect attempts exceeded.")
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            break
        except Exception as e:
            print(f"[CAMERA_WORKER_ERROR] Camera {self.camera_id} loop exception: {e}")
            self.last_error = str(e)
            self.state = "ERROR"
        finally:
            with self.lock:
                self.running = False
                cap = self.capture
                self.capture = None
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
            print(f"[CAMERA_WORKER_EXIT] camera_id={self.camera_id}")

    def _attempt_reconnect(self):
        """Attempts to safely release and re-open the underlying VideoCapture."""
        with self.lock:
            self.is_reconnecting = True
            self.state = "RECONNECTING"
            old_cap = self.capture
            self.capture = None
        if old_cap:
            try:
                old_cap.release()
            except Exception:
                pass
        time.sleep(0.4)
        try:
            new_cap = safe_open_video_capture(self.cap_source)
            if new_cap and new_cap.isOpened():
                with self.lock:
                    self.capture = new_cap
                    self.is_reconnecting = False
                    self.consecutive_black_frames = 0
                print(f"[CAMERA_WORKER_RECONNECT_SUCCESS] Camera {self.camera_id} reconnected to source {self.cap_source}")
                return True
        except Exception as rec_err:
            print(f"[CAMERA_WORKER_RECONNECT_FAIL] Camera {self.camera_id}: {rec_err}")
        with self.lock:
            self.is_reconnecting = False
        return False

    def stop(self):
        with self.frame_condition:
            self.running = False
            self.state = "OFFLINE"
            self.frame_condition.notify_all()
        thread_ref = self.thread
        if thread_ref and thread_ref.is_alive():
            thread_ref.join(timeout=2.5)
        if thread_ref is None or not thread_ref.is_alive():
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

