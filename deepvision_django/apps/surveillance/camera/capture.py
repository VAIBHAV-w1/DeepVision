"""
Native DirectShow and HTTP/HTTPS MJPEG Camera Capture Layer.
Provides safe, robust VideoCapture handles for OpenCV in Django.
"""
import os
import sys
import time
import socket
import ssl
import threading
import urllib.request
try:
    import cv2
    import numpy as np
except (ImportError, Exception):
    cv2 = None
    np = None

from apps.surveillance.camera.sources import mask_url_credentials

_hardware_webcam_lock = threading.Lock()


class HttpMjpegCapture:
    """
    Standard-compliant video capture for HTTP/HTTPS MJPEG network streams.
    Implements isOpened(), read(), get(), and release() matching cv2.VideoCapture.
    Provides narrowly scoped SSL context for self-signed certificates.
    """
    def __init__(self, url, timeout=2.5):
        self.url = str(url)
        self.timeout = float(timeout) if timeout is not None else 2.5
        self.response = None
        self._opened = False
        self._http_connected = False
        self._http_status = None
        self._buffer = bytearray()
        self._last_frame = None
        self._width = 0
        self._height = 0
        self._fps = 25.0
        self.last_error = None
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._open_stream()

    def _open_stream(self):
        ctx = None
        if isinstance(self.url, str) and self.url.lower().startswith("https://"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "DeepVision-Surveillance/1.0",
                "Accept": "multipart/x-mixed-replace, image/*, */*",
                "Connection": "keep-alive"
            }
        )
        try:
            self.response = urllib.request.urlopen(req, context=ctx, timeout=self.timeout)
            status = getattr(self.response, "status", 200)
            self._http_status = status
            if status == 200:
                self._http_connected = True
                self._opened = True
                ret, frame = self._read_next_frame()
                if ret and frame is not None:
                    self._last_frame = frame
                    self._height, self._width = frame.shape[:2]
                else:
                    self.release()
            else:
                self.release()
        except Exception as e:
            self.last_error = str(e)
            self.release()

    def _read_next_frame(self):
        if not self.response:
            return False, None
        
        while time.time() - self._start_time < self.timeout:
            a = self._buffer.find(b'\xff\xd8')
            if a != -1:
                if a > 0:
                    self._buffer = self._buffer[a:]
                
                next_soi = self._buffer.find(b'\xff\xd8', 2)
                if next_soi != -1:
                    frame_data = self._buffer[:next_soi]
                    self._buffer = self._buffer[next_soi:]
                    b = frame_data.find(b'\xff\xd9')
                    if b != -1:
                        jpg = frame_data[:b+2]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None and frame.size > 0:
                            return True, frame

                b = self._buffer.find(b'\xff\xd9')
                if b != -1:
                    jpg = self._buffer[:b+2]
                    self._buffer = self._buffer[b+2:]
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None and frame.size > 0:
                        return True, frame

            try:
                chunk = self.response.read(8192)
                if not chunk:
                    break
                self._buffer.extend(chunk)
            except Exception as e:
                self.last_error = str(e)
                break
        return False, None

    def isOpened(self):
        return self._opened and self.response is not None

    def read(self):
        with self._lock:
            if not self.isOpened():
                return False, None
            ret, frame = self._read_next_frame()
            if ret and frame is not None:
                self._last_frame = frame
                self._height, self._width = frame.shape[:2]
                return True, frame
            elif self._last_frame is not None:
                return True, self._last_frame.copy()
            return False, None

    def get(self, prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self._width)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self._height)
        elif prop_id == cv2.CAP_PROP_FPS:
            return float(self._fps)
        return 0.0

    def set(self, prop_id, value):
        return False

    def release(self):
        with self._lock:
            self._opened = False
            if self.response:
                try:
                    self.response.close()
                except Exception:
                    pass
                self.response = None
            self._buffer.clear()


class DummyVideoCapture:
    def __init__(self, last_error=None):
        self.last_error = last_error
    def isOpened(self):
        return False
    def read(self):
        return False, None
    def get(self, prop_id):
        return 0.0
    def set(self, prop_id, value):
        return False
    def release(self):
        pass


def safe_open_video_capture(capture_source, timeout=None):
    """
    Safely opens a cv2.VideoCapture instance.
    For local cameras (integers) on Windows, attempts DirectShow (CAP_DSHOW) first,
    checks if it's opened, and attempts a real frame read to verify usability.
    """
    if isinstance(capture_source, int):
        with _hardware_webcam_lock:
            if os.name == "nt" or sys.platform.startswith("win"):
                try:
                    cap = cv2.VideoCapture(capture_source, cv2.CAP_DSHOW)
                    if cap.isOpened():
                        # Set standard 1280x720 HD resolution
                        try:
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        except Exception:
                            pass
                        ret, frame = cap.read()
                        if not (ret and frame is not None and getattr(frame, "size", 0) > 0):
                            # Fall back to default native resolution
                            ret, frame = cap.read()

                        if ret and frame is not None and getattr(frame, "size", 0) > 0:
                            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            print(f"[CAPTURE] DirectShow camera {capture_source} opened: {actual_w}x{actual_h}.")
                            return cap
                        else:
                            print(f"[DEBUG] DirectShow opened index {capture_source} but read() failed.")
                            cap.release()
                            return DummyVideoCapture(last_error="DirectShow frame read failed")
                    else:
                        print(f"[DEBUG] DirectShow failed to open index {capture_source}.")
                        cap.release()
                        return DummyVideoCapture(last_error="DirectShow failed to open camera index")
                except Exception as e:
                    print(f"[DEBUG] Exception on DirectShow index {capture_source}: {e}")
                    return DummyVideoCapture(last_error=str(e))
            else:
                try:
                    cap = cv2.VideoCapture(capture_source)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and (frame is not None and getattr(frame, "size", 0) > 0):
                            try:
                                setattr(cap, "_probed_frame", frame)
                            except Exception:
                                pass
                            return cap
                        cap.release()
                    return DummyVideoCapture(last_error="Default backend failed to open index")
                except Exception as e:
                    return DummyVideoCapture(last_error=str(e))

    else:
        is_https = isinstance(capture_source, str) and capture_source.lower().startswith("https://")
        is_http = isinstance(capture_source, str) and capture_source.lower().startswith("http://")
        is_rtsp = isinstance(capture_source, str) and capture_source.lower().startswith("rtsp://")

        if is_rtsp:
            import urllib.parse
            try:
                parsed = urllib.parse.urlsplit(capture_source)
                host = parsed.hostname
                port = parsed.port or 554
                if host:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.5)
                    try:
                        sock.connect((host, port))
                        sock.close()
                    except Exception as probe_err:
                        try:
                            sock.close()
                        except Exception:
                            pass
                        print(f"[ERROR] Network source {mask_url_credentials(capture_source)} unreachable: {probe_err}")
                        return cv2.VideoCapture()
            except Exception:
                pass

        if is_https or is_http:
            cap = HttpMjpegCapture(capture_source, timeout=timeout)
            if cap.isOpened():
                return cap
            last_err = getattr(cap, "last_error", None)
            cap.release()

            if isinstance(capture_source, str) and any(kw in capture_source for kw in ("/silent", "/videofeed", "/video", ":8080")):
                return DummyVideoCapture(last_error=last_err)

            cap = cv2.VideoCapture(capture_source)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    return cap
                cap.release()
            return cv2.VideoCapture()

        cap = cv2.VideoCapture(capture_source)
        return cap
