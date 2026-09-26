"""
Camera sources normalization, resolution, and credential masking.
Ported natively into Django surveillance architecture.
"""
import os
import sys

def validate_video_path(filename):
    """
    Validates that the filename resolves to a path strictly inside the project's videos/ directory.
    Prevents path traversal, absolute paths, or access to sensitive configurations.
    """
    if not filename:
        return False, "Filename cannot be empty."
        
    if os.path.isabs(filename) or filename.startswith("/") or filename.startswith("\\") or ":" in filename:
        return False, "Absolute paths are not allowed."
        
    from django.conf import settings
    base_dir = os.path.abspath(os.path.join(settings.BASE_DIR.parent, "videos"))
    target_path = os.path.abspath(os.path.join(base_dir, filename))
    
    prefix = base_dir + os.sep
    if not target_path.startswith(prefix):
        return False, "Access denied: Path is outside the authorized videos directory."
        
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        return False, "Video file not found."
        
    return True, target_path


def mask_url_credentials(url):
    """Masks basic auth passwords in camera stream URLs for safe logging."""
    if not isinstance(url, str):
        return str(url)
    if "://" in url:
        try:
            parts = url.split("://", 1)
            scheme = parts[0]
            rest = parts[1]
            if "@" in rest:
                auth, host = rest.split("@", 1)
                if ":" in auth:
                    user, password = auth.split(":", 1)
                    return f"{scheme}://***:***@{host}"
                else:
                    return f"{scheme}://***@{host}"
        except Exception:
            pass
    return url


def normalize_camera_source(source_type, source):
    """
    Normalizes camera source strings.
    - webcam: preserves numeric string or integer.
    - video: preserves filename.
    - phone: auto-prepends 'http://' if missing, appends '/videofeed' if no path provided.
    - rtsp: auto-prepends 'rtsp://' if missing.
    - ipcamera: auto-prepends 'http://' or 'rtsp://' if scheme missing.
    """
    if source is None:
        return ""
    if isinstance(source, int):
        return source
    source = str(source).strip()
    if not source:
        return ""
    
    if source_type in ("webcam", "usb", "video", "file", "local"):
        return source
    elif source_type == "phone":
        if not (source.startswith("http://") or source.startswith("https://") or source.startswith("rtsp://")):
            source = "http://" + source
        try:
            import urllib.parse
            parts = urllib.parse.urlsplit(source)
            if not parts.path or parts.path == "/" or parts.path == "":
                source = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/videofeed", parts.query, parts.fragment))
        except Exception:
            pass
        return source
    elif source_type == "rtsp":
        if not source.startswith("rtsp://"):
            source = "rtsp://" + source
        return source
    elif source_type in ("ipcamera", "http", "https", "ip"):
        if not (source.startswith("http://") or source.startswith("https://") or source.startswith("rtsp://")):
            if ":554" in source or "rtsp" in source.lower():
                source = "rtsp://" + source
            elif source_type == "https":
                source = "https://" + source
            else:
                source = "http://" + source
        return source
    return source


def resolve_camera_capture_source(source_type, source):
    """
    Authoritative source resolver that inspects source_type and source
    and returns the correct capture source representation.
    """
    if source is None:
        raise ValueError("Stream Source is empty or not configured.")
        
    if isinstance(source, str):
        source = source.strip()
        if source == "":
            raise ValueError("Stream Source cannot be empty.")
        
    if source_type in ("webcam", "usb"):
        if isinstance(source, int):
            return source
        if isinstance(source, str) and source.isdigit():
            return int(source)
        try:
            return int(source)
        except Exception:
            raise ValueError("Webcam/USB source must be a numeric device index (e.g., 0, 1, 2).")
            
    elif source_type in ("video", "file", "local"):
        success, resolved_path = validate_video_path(source)
        if not success:
            raise ValueError(resolved_path)
        return resolved_path
        
    elif source_type in ("rtsp", "phone", "ipcamera", "http", "https", "ip"):
        return normalize_camera_source(source_type, source)
        
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


def get_physical_source_key(source_type, source):
    """
    Returns a deterministic canonical physical identifier for any camera source.
    Ensures that multiple logical cameras pointing to the same physical hardware
    (e.g., DirectShow device 0) share a single physical capture worker.
    """
    try:
        cap_source = resolve_camera_capture_source(source_type, source)
    except Exception:
        cap_source = source

    if source_type in ("webcam", "usb") or isinstance(cap_source, int):
        backend = "dshow" if (os.name == "nt" or sys.platform.startswith("win")) else "v4l2"
        return f"{backend}://{cap_source}"
    elif source_type in ("video", "file", "local"):
        return f"file://{os.path.abspath(str(cap_source))}"
    elif source_type in ("rtsp", "phone", "ipcamera", "http", "https", "ip"):
        return f"net://{normalize_camera_source(source_type, source)}"
    return f"generic://{cap_source}"
