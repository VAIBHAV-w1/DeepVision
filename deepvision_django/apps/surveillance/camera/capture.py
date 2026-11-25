"""
Native DirectShow and HTTP/HTTPS MJPEG Camera Capture Layer.
Provides safe, robust VideoCapture handles for OpenCV in Django.
"""
import http.client
import ipaddress
import os
import sys
import time
import socket
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
try:
    import cv2
    import numpy as np
except (ImportError, Exception):
    cv2 = None
    np = None

from apps.surveillance.camera.sources import (
    _assert_safe_ip,
    mask_url_credentials,
    resolve_and_validate_network_target,
    validate_network_stream_url,
)

_hardware_webcam_lock = threading.Lock()
_MAX_MJPEG_REDIRECTS = 3


def _resolve_pinned_target(url: str):
    """
    Validates scheme/hostname/port and resolves safe target IPs using capture.socket.getaddrinfo
    so tests and runtime share one consistent, fail-closed SSRF resolution barrier.
    Returns `(reconstructed_url, host, port, safe_ip)`.
    """
    safe_url, host, port, ips = resolve_and_validate_network_target(url, require_dns_resolution=False)
    if ips:
        return safe_url, host, port, ips[0]

    infos = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("Security Error: Stream hostname did not resolve to any permitted IP address.")
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0]:
            raw_ip = str(sockaddr[0]).split("%", 1)[0]
            try:
                ip_obj = ipaddress.ip_address(raw_ip)
            except ValueError:
                continue
            _assert_safe_ip(ip_obj)
            return safe_url, host, port, str(ip_obj)
    raise ValueError("Security Error: Stream hostname resolved only to prohibited addresses.")


def _make_pinned_http_connection(pinned_ip: str):
    """Builds an HTTPConnection class that connects TCP strictly to `pinned_ip` (anti-DNS-rebinding)."""
    validated_ip = str(ipaddress.ip_address(pinned_ip))

    class _PinnedHTTPConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = self._create_connection(
                (validated_ip, self.port), self.timeout, self.source_address
            )
            if self._tunnel_host:
                self._tunnel()

    return _PinnedHTTPConnection


def _make_pinned_https_connection(pinned_ip: str, sni_host: str):
    """Builds an HTTPSConnection class pinning TCP to `pinned_ip` while preserving TLS SNI (`sni_host`)."""
    validated_ip = str(ipaddress.ip_address(pinned_ip))

    class _PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            sock = self._create_connection(
                (validated_ip, self.port), self.timeout, self.source_address
            )
            if self._tunnel_host:
                self.sock = sock
                self._tunnel()
                server_hostname = self._tunnel_host
            else:
                server_hostname = sni_host
            self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)

    return _PinnedHTTPSConnection


def _env_allows_self_signed_lan_camera() -> bool:
    """Explicit opt-in flag for self-signed TLS certificates on private LAN cameras only."""
    return os.getenv("DEEPVISION_ALLOW_SELF_SIGNED_LAN_CAMERA", "false").strip().lower() in ("true", "1", "yes")


def _is_private_lan_ip(ip_obj) -> bool:
    """Returns True strictly for non-loopback, non-link-local, non-multicast private LAN IPs (RFC1918 / ULA)."""
    mapped = getattr(ip_obj, "ipv4_mapped", None)
    candidate = mapped if mapped is not None else ip_obj
    return bool(
        candidate.is_private
        and not candidate.is_loopback
        and not candidate.is_link_local
        and not candidate.is_unspecified
        and not candidate.is_multicast
        and not candidate.is_reserved
    )


def _is_authorized_private_lan_url(url: str) -> bool:
    """
    Checks whether url passes full SSRF policy AND resolves strictly to a private LAN IP.
    Prevents relaxed TLS contexts from ever being applied to public internet hosts or unsafe destinations.
    """
    try:
        validated = validate_network_stream_url(url)
    except Exception:
        return False

    parsed = urllib.parse.urlsplit(validated)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    try:
        ip_obj = ipaddress.ip_address(host)
        return _is_private_lan_ip(ip_obj)
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False

    saw_ip = False
    for info in infos:
        sockaddr = info[4]
        if not sockaddr or not sockaddr[0]:
            continue
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            return False
        if not _is_private_lan_ip(resolved_ip):
            return False
        saw_ip = True
    return saw_ip


class _SafeMjpegRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validates every HTTP redirect destination against DeepVision's SSRF network policy."""
    max_redirects = _MAX_MJPEG_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved_url = urllib.parse.urljoin(req.full_url, str(newurl))
        parsed_next = urllib.parse.urlsplit(resolved_url)
        scheme = (parsed_next.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"Security Error: Prohibited HTTP redirect protocol '{scheme or 'none'}'.")

        validated_url = validate_network_stream_url(resolved_url)

        hops = int(getattr(req, "_dv_redirect_hops", 0)) + 1
        if hops > self.max_redirects:
            raise urllib.error.HTTPError(
                validated_url,
                code,
                f"Exceeded maximum safe HTTP redirects ({self.max_redirects}).",
                headers,
                fp,
            )

        next_req = super().redirect_request(req, fp, code, msg, headers, validated_url)
        if next_req is None:
            return None

        orig_parsed = urllib.parse.urlsplit(req.full_url)
        if (orig_parsed.scheme.lower(), orig_parsed.netloc.lower()) != (
            parsed_next.scheme.lower(),
            parsed_next.netloc.lower(),
        ):
            next_req.remove_header("Authorization")
            next_req.remove_header("Proxy-authorization")

        next_req._dv_redirect_hops = hops
        return next_req


class _PinnedMjpegHTTPHandler(urllib.request.HTTPHandler):
    """Opens plain HTTP MJPEG connections strictly against SSRF-validated pinned IPs."""

    def http_open(self, req):
        _, _, _, pinned_ip = _resolve_pinned_target(req.full_url)
        return self.do_open(_make_pinned_http_connection(pinned_ip), req)


class _ScopedMjpegHTTPSHandler(urllib.request.HTTPSHandler):
    """
    Enforces strict TLS certificate verification by default, allowing self-signed certs
    ONLY when explicitly opted in AND scoped per-request strictly to private LAN hosts,
    and pins socket connections to SSRF-validated IP addresses.
    """
    def __init__(self, allow_self_signed_lan: bool = False):
        self.allow_self_signed_lan = bool(allow_self_signed_lan)
        self._strict_ctx = ssl.create_default_context()
        self._relaxed_ctx = None
        if self.allow_self_signed_lan:
            relaxed = ssl.create_default_context()
            relaxed.check_hostname = False
            relaxed.verify_mode = ssl.CERT_NONE
            self._relaxed_ctx = relaxed
        super().__init__(context=self._strict_ctx)

    def https_open(self, req):
        _, host, _, pinned_ip = _resolve_pinned_target(req.full_url)
        chosen_ctx = self._strict_ctx
        if (
            self.allow_self_signed_lan
            and self._relaxed_ctx is not None
            and _is_authorized_private_lan_url(req.full_url)
        ):
            chosen_ctx = self._relaxed_ctx
        return self.do_open(
            _make_pinned_https_connection(pinned_ip, host),
            req,
            context=chosen_ctx,
        )


class HttpMjpegCapture:
    """
    Standard-compliant video capture for HTTP/HTTPS MJPEG network streams.
    Implements isOpened(), read(), get(), and release() matching cv2.VideoCapture.
    Revalidates every HTTP redirect destination, pins DNS resolution at socket connect time,
    and restricts relaxed TLS strictly to explicitly opted-in private LAN camera targets.
    """
    def __init__(self, url, timeout=2.5, allow_self_signed=None):
        self.url = str(url)
        self.timeout = float(timeout) if timeout is not None else 2.5
        self.allow_self_signed = (
            _env_allows_self_signed_lan_camera()
            if allow_self_signed is None
            else bool(allow_self_signed)
        )
        self.response = None
        self._opened = False
        self._http_connected = False
        self._http_status = None
        self._buffer = bytearray()
        self._last_frame = None
        self._probed_frame = None
        self._width = 0
        self._height = 0
        self._fps = 25.0
        self.last_error = None
        self.policy_rejected = False
        self._lock = threading.Lock()
        self._open_stream()

    def _open_stream(self):
        try:
            raw_scheme = (urllib.parse.urlsplit(self.url).scheme or "").lower()
            if raw_scheme not in ("http", "https"):
                raise ValueError(f"Unsupported HTTP MJPEG scheme: {raw_scheme or 'none'}")
            safe_scheme = "https" if raw_scheme == "https" else "http"
            validated_url, validated_host, validated_port, _ = _resolve_pinned_target(self.url)
            parsed = urllib.parse.urlsplit(validated_url)
            safe_host_hdr = f"{validated_host}:{validated_port}" if parsed.port else validated_host
            safe_path_query = f"{parsed.path or '/'}?{parsed.query}" if parsed.query else (parsed.path or "/")
            safe_target_url = urllib.parse.urlunsplit((safe_scheme, parsed.netloc, safe_path_query.split("?", 1)[0], parsed.query, ""))

            req = urllib.request.Request(
                safe_target_url,
                headers={
                    "Host": safe_host_hdr,
                    "User-Agent": "DeepVision-Surveillance/1.0",
                    "Accept": "multipart/x-mixed-replace, image/*, */*",
                    "Connection": "keep-alive",
                },
            )
            opener = urllib.request.build_opener(
                _PinnedMjpegHTTPHandler(),
                _SafeMjpegRedirectHandler(),
                _ScopedMjpegHTTPSHandler(allow_self_signed_lan=self.allow_self_signed),
            )
            self.response = opener.open(req, timeout=self.timeout)
            status = getattr(self.response, "status", 200)
            self._http_status = status
            if status == 200:
                self._http_connected = True
                self._opened = True
                ret, frame = self._read_next_frame()
                if ret and frame is not None:
                    self._last_frame = frame
                    self._probed_frame = frame
                    self._height, self._width = frame.shape[:2]
                else:
                    self.release()
            else:
                self.release()
        except (ValueError, ssl.SSLError) as e:
            self.policy_rejected = True
            self.last_error = str(e)
            self.release()
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), (ValueError, ssl.SSLError)):
                self.policy_rejected = True
            self.last_error = str(e)
            self.release()
        except Exception as e:
            self.last_error = str(e)
            self.release()

    def _read_next_frame(self):
        if not self.response:
            return False, None

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            a = self._buffer.find(b'\xff\xd8')
            if a != -1:
                if a > 0:
                    del self._buffer[:a]

                next_soi = self._buffer.find(b'\xff\xd8', 2)
                if next_soi != -1:
                    frame_data = bytes(self._buffer[:next_soi])
                    del self._buffer[:next_soi]
                    b = frame_data.find(b'\xff\xd9')
                    if b != -1:
                        jpg = frame_data[:b + 2]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None and frame.size > 0:
                            return True, frame

                b = self._buffer.find(b'\xff\xd9')
                if b != -1:
                    jpg = bytes(self._buffer[:b + 2])
                    del self._buffer[:b + 2]
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None and frame.size > 0:
                        return True, frame

            try:
                chunk = self.response.read(8192)
                if not chunk:
                    self.last_error = "MJPEG stream reached EOF / closed by remote host"
                    break
                self._buffer.extend(chunk)
                # Cap malformed unbounded non-JPEG stream buffer at 4 MB
                if len(self._buffer) > 4 * 1024 * 1024:
                    self._buffer.clear()
                    self.last_error = "MJPEG stream buffer overflow without valid JPEG SOI/EOI markers"
                    break
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
            # Never return stale frozen frames when a network MJPEG stream disconnects or times out
            self._opened = False
            if self.response:
                try:
                    self.response.close()
                except Exception:
                    pass
                self.response = None
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


def safe_open_video_capture(capture_source, timeout=None, target_width=None, target_height=None):
    """
    Safely opens a cv2.VideoCapture instance.
    For local cameras (integers) on Windows, attempts DirectShow (CAP_DSHOW) first,
    negotiating MJPG + requested target resolution without distorting aspect ratio.
    """
    req_w = int(target_width or 1280)
    req_h = int(target_height or 720)
    if isinstance(capture_source, int):
        with _hardware_webcam_lock:
            if os.name == "nt" or sys.platform.startswith("win"):
                win_pref = (os.getenv("DEEPVISION_WIN_CAPTURE_BACKEND") or "msmf").strip().lower()
                backend_order = (
                    [(cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "MSMF")]
                    if win_pref in ("dshow", "directshow")
                    else [(cv2.CAP_MSMF, "MSMF"), (cv2.CAP_DSHOW, "DirectShow")]
                )
                last_err = "Windows camera capture failed to open camera index"
                mjpg = cv2.VideoWriter_fourcc(*'MJPG')
                for api_flag, api_label in backend_order:
                    cap = None
                    try:
                        if api_flag == cv2.CAP_DSHOW:
                            try:
                                cap = cv2.VideoCapture(
                                    capture_source,
                                    api_flag,
                                    [
                                        cv2.CAP_PROP_FOURCC, mjpg,
                                        cv2.CAP_PROP_FRAME_WIDTH, req_w,
                                        cv2.CAP_PROP_FRAME_HEIGHT, req_h,
                                        cv2.CAP_PROP_FPS, 30,
                                    ],
                                )
                            except TypeError:
                                cap = cv2.VideoCapture(capture_source, api_flag)
                        else:
                            cap = cv2.VideoCapture(capture_source, api_flag)

                        if cap is not None and cap.isOpened():
                            try:
                                cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
                                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)
                                if api_flag == cv2.CAP_DSHOW:
                                    cap.set(cv2.CAP_PROP_FOURCC, mjpg)
                                cap.set(cv2.CAP_PROP_FPS, 30)
                                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            except Exception:
                                pass

                            # Warm up auto-exposure and discard initial blank buffers (up to 10 reads / 0.55s)
                            ret, frame = False, None
                            t_warm = time.monotonic()
                            for _ in range(10):
                                r, f = cap.read()
                                if r and f is not None and getattr(f, "size", 0) > 0:
                                    ret, frame = r, f
                                    sample = f[::16, ::16]
                                    if float(sample.mean()) >= 2.0 or float(sample.std()) >= 1.0:
                                        break
                                if time.monotonic() - t_warm > 0.55:
                                    break

                            if ret and frame is not None and getattr(frame, "size", 0) > 0:
                                actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or frame.shape[1]
                                actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or frame.shape[0]
                                try:
                                    fcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
                                    fcc_raw = "".join(chr((fcc_int >> (8 * i)) & 0xFF) for i in range(4))
                                    fcc_str = fcc_raw.strip("\x00 ") if all(32 <= ord(c) < 127 for c in fcc_raw) else ""
                                    if not fcc_str:
                                        fcc_str = api_label.upper()
                                    setattr(cap, "_probed_frame", frame)
                                    setattr(cap, "_negotiated_fourcc", fcc_str)
                                except Exception:
                                    pass
                                print(f"[CAPTURE] {api_label} camera {capture_source} opened: {actual_w}x{actual_h} (luma={float(frame[::16, ::16].mean()):.1f}).")
                                return cap
                            last_err = f"{api_label} frame read failed"
                            print(f"[DEBUG] {api_label} opened index {capture_source} but read() failed.")
                        else:
                            last_err = f"{api_label} failed to open camera index"
                            print(f"[DEBUG] {api_label} failed to open index {capture_source}.")
                        if cap is not None:
                            cap.release()
                    except Exception as e:
                        last_err = str(e)
                        print(f"[DEBUG] Exception on {api_label} index {capture_source}: {e}")
                        if cap is not None:
                            try:
                                cap.release()
                            except Exception:
                                pass
                return DummyVideoCapture(last_error=last_err)
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
        is_rtsp = isinstance(capture_source, str) and capture_source.lower().startswith(("rtsp://", "rtsps://"))

        if is_rtsp:
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;4000000")
            import urllib.parse
            try:
                parsed = urllib.parse.urlsplit(capture_source)
                host = parsed.hostname
                port = parsed.port or (322 if capture_source.lower().startswith("rtsps://") else 554)
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
                        return DummyVideoCapture(last_error=str(probe_err))
            except Exception:
                pass

        if is_https or is_http:
            cap = HttpMjpegCapture(capture_source, timeout=timeout)
            if cap.isOpened():
                return cap
            last_err = getattr(cap, "last_error", None)
            policy_rejected = bool(getattr(cap, "policy_rejected", False))
            cap.release()

            if policy_rejected or (
                isinstance(capture_source, str) and any(kw in capture_source for kw in ("/silent", "/videofeed", "/video", ":8080"))
            ):
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
