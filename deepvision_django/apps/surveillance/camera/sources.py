"""
Camera sources normalization, resolution, and credential masking.
Ported natively into Django surveillance architecture.
"""
import os
import sys
import socket
import ipaddress
import urllib.parse

_ALLOWED_STREAM_SCHEMES = frozenset({"http", "https", "rtsp", "rtsps"})
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_PROHIBITED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata",
    "instance-data",
})


def _assert_safe_ip(ip_obj):
    """Rejects loopback, link-local (including 169.254.169.254), unspecified, multicast, CGNAT, and reserved IPs."""
    candidates = [ip_obj]
    mapped = getattr(ip_obj, "ipv4_mapped", None)
    if mapped is not None:
        candidates.append(mapped)
    for addr in candidates:
        if addr.is_loopback:
            raise ValueError("Security Error: Loopback stream addresses (127.0.0.0/8, ::1) are prohibited.")
        if addr.is_link_local:
            raise ValueError("Security Error: Link-local and cloud metadata addresses (169.254.0.0/16) are prohibited.")
        if addr.is_unspecified:
            raise ValueError("Security Error: Unspecified stream addresses (0.0.0.0, ::) are prohibited.")
        if addr.is_multicast:
            raise ValueError("Security Error: Multicast stream addresses are prohibited.")
        if addr.is_reserved:
            raise ValueError("Security Error: Reserved non-routable stream addresses are prohibited.")
        if addr.version == 4 and addr in _CGNAT_NETWORK:
            raise ValueError("Security Error: Carrier-grade shared NAT addresses (100.64.0.0/10) are prohibited.")


def resolve_and_validate_network_target(url: str, require_dns_resolution: bool = False):
    """
    Validates a network stream URL and resolves candidate IPs cleanly against SSRF rules.
    Returns `(reconstructed_url, host, port, validated_ips)`.
    When `require_dns_resolution=True`, unresolvable hostnames fail closed to block DNS TOCTOU/rebinding bypasses.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Network stream URL cannot be empty.")

    parsed = urllib.parse.urlsplit(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_STREAM_SCHEMES:
        raise ValueError(f"Unsupported or prohibited stream protocol: {scheme or 'none'}")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Network stream URL must specify a valid hostname or IP address.")

    if host in _PROHIBITED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".internal"):
        raise ValueError(f"Security Error: Prohibited internal or loopback hostname '{host}'.")

    default_port = 443 if scheme == "https" else (554 if scheme in ("rtsp", "rtsps") else 80)
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise ValueError("Network stream URL contains an invalid port.") from exc
    if not (1 <= int(port) <= 65535):
        raise ValueError("Network stream URL port is out of valid range.")

    host_part = f"[{host}]" if ":" in host else host
    auth_part = ""
    if parsed.username or parsed.password:
        user_enc = urllib.parse.quote(urllib.parse.unquote(parsed.username or ""), safe="")
        if parsed.password is not None:
            pwd_enc = urllib.parse.quote(urllib.parse.unquote(parsed.password), safe="")
            auth_part = f"{user_enc}:{pwd_enc}@"
        else:
            auth_part = f"{user_enc}@"
    port_part = f":{parsed.port}" if parsed.port else ""
    safe_netloc = f"{auth_part}{host_part}{port_part}"
    safe_path = parsed.path or ""
    reconstructed = urllib.parse.urlunsplit((scheme, safe_netloc, safe_path, parsed.query, ""))

    # Fast path for IPv4 / IPv6 literals
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        _assert_safe_ip(ip_obj)
        return reconstructed, host, int(port), [str(ip_obj)]

    # Hostname DNS resolution check to prevent DNS-rebinding / alias SSRF
    try:
        infos = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        if require_dns_resolution:
            raise ValueError("Security Error: Stream hostname could not be safely resolved.") from exc
        infos = []

    validated_ips = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0]:
            raw_ip = str(sockaddr[0]).split("%", 1)[0]
            try:
                resolved_ip = ipaddress.ip_address(raw_ip)
            except ValueError:
                continue
            _assert_safe_ip(resolved_ip)
            ip_text = str(resolved_ip)
            if ip_text not in validated_ips:
                validated_ips.append(ip_text)

    if require_dns_resolution and not validated_ips:
        raise ValueError("Security Error: Stream hostname did not resolve to any permitted IP address.")

    return reconstructed, host, int(port), validated_ips


def validate_network_stream_url(url: str) -> str:
    """
    Centralized SSRF guard for all network camera streams (RTSP, HTTP, HTTPS, MJPEG, Phone, IP camera).
    Blocks loopback, link-local / cloud metadata (169.254.169.254), unspecified, multicast, CGNAT,
    prohibited internal hostnames, and DNS-resolved loopback/metadata targets while permitting
    valid private LAN camera subnets (192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12).
    """
    safe_url, _, _, _ = resolve_and_validate_network_target(url, require_dns_resolution=False)
    return safe_url

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

    if source_type == "browser":
        cleaned = str(source).replace("\x00", "").replace("\r", "").replace("\n", "").strip()[:255]
        return cleaned or "0"
    elif source_type in ("webcam", "usb", "video", "file", "local"):
        return source
    elif source_type == "phone":
        if "://" not in source:
            source = "http://" + source
        try:
            import urllib.parse
            parts = urllib.parse.urlsplit(source)
            if parts.scheme in ("http", "https") and (not parts.path or parts.path == "/" or parts.path == ""):
                source = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/videofeed", parts.query, parts.fragment))
        except Exception:
            pass
        return source
    elif source_type == "rtsp":
        if "://" not in source:
            source = "rtsp://" + source
        return source
    elif source_type in ("ipcamera", "http", "https", "ip", "mjpeg"):
        if "://" not in source:
            if source_type != "mjpeg" and (":554" in source or "rtsp" in source.lower()):
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

    if source_type == "browser":
        norm = str(source or "0").replace("\x00", "").replace("\r", "").replace("\n", "").strip()[:255] or "0"
        return f"browser://{norm}"

    elif source_type in ("webcam", "usb"):
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

    elif source_type in ("rtsp", "phone", "ipcamera", "http", "https", "ip", "mjpeg"):
        normalized = normalize_camera_source(source_type, source)
        return validate_network_stream_url(normalized)

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

    if source_type == "browser":
        return f"browser://{normalize_camera_source('browser', source)}"
    elif source_type in ("webcam", "usb") or isinstance(cap_source, int):
        backend = "dshow" if (os.name == "nt" or sys.platform.startswith("win")) else "v4l2"
        return f"{backend}://{cap_source}"
    elif source_type in ("video", "file", "local"):
        return f"file://{os.path.abspath(str(cap_source))}"
    elif source_type in ("rtsp", "phone", "ipcamera", "http", "https", "ip", "mjpeg"):
        return f"net://{normalize_camera_source(source_type, source)}"
    return f"generic://{cap_source}"
