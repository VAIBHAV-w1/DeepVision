"""
DeepVision Media Service.
Provides safe, range-aware file serving for HTML5 video playback and forensic images
without exposing underlying filesystem paths or allowing path traversal.
"""

import os
import re
import logging
from typing import Optional, Tuple
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse, FileResponse, Http404

logger = logging.getLogger(__name__)

RECORDINGS_DIR = os.path.normpath(os.path.join(settings.BASE_DIR.parent, "instance", "recordings"))
EVIDENCE_DIR = os.path.normpath(os.path.join(settings.BASE_DIR.parent, "instance", "evidence"))


def safe_resolve_path(base_dir: str, rel_path: str) -> Optional[str]:
    """
    Safely resolves a relative path within a base directory,
    strictly preventing path traversal attacks.
    """
    if not rel_path:
        return None
    # Normalize path separators
    normalized_rel = rel_path.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
    full_path = os.path.normpath(os.path.join(base_dir, normalized_rel))
    
    # Verify path remains within allowed base directory
    try:
        common = os.path.commonpath([full_path, base_dir])
        if common != base_dir:
            logger.warning(f"Path traversal attempt blocked: {rel_path}")
            return None
    except ValueError:
        return None
        
    return full_path if os.path.isfile(full_path) else None


def safe_resolve_recording(file_path: str) -> Optional[str]:
    """Resolves and validates a recording file path."""
    if not file_path:
        return None
    # 1. Check in standard RECORDINGS_DIR (instance/recordings)
    res = safe_resolve_path(RECORDINGS_DIR, file_path)
    if res:
        return res
    # 2. Check if relative path starts with 'evidence/' or is located in EVIDENCE_DIR
    norm = file_path.replace("\\", "/").lstrip("/")
    if norm.startswith("evidence/"):
        res = safe_resolve_path(EVIDENCE_DIR, norm[9:])
        if res:
            return res
    # 3. Check directly in EVIDENCE_DIR
    res = safe_resolve_path(EVIDENCE_DIR, file_path)
    if res:
        return res
    # 4. Check in instance/ directory root
    instance_dir = os.path.normpath(os.path.join(settings.BASE_DIR.parent, "instance"))
    res = safe_resolve_path(instance_dir, file_path)
    if res:
        return res
    return None


def safe_resolve_evidence(file_path: str) -> Optional[str]:
    """Resolves and validates an evidence file path."""
    return safe_resolve_path(EVIDENCE_DIR, file_path)


def serve_file_with_ranges(request, full_path: str, content_type: str, as_attachment: bool = False, download_name: Optional[str] = None):
    """
    Serves a media file supporting HTTP 206 Partial Content (Range requests)
    for seamless HTML5 video seeking and low-latency playback.
    """
    if not full_path or not os.path.isfile(full_path):
        raise Http404("Media file not found on disk.")

    file_size = os.path.getsize(full_path)

    if as_attachment:
        resp = FileResponse(open(full_path, "rb"), content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{download_name or os.path.basename(full_path)}"'
        resp["Content-Length"] = str(file_size)
        return resp

    range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
    if not range_header or "=" not in range_header:
        resp = FileResponse(open(full_path, "rb"), content_type=content_type)
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Length"] = str(file_size)
        resp["Content-Disposition"] = "inline"
        return resp

    # Parse Range: bytes=start-end
    match = re.match(r"^bytes=(\d*)-(\d*)$", range_header.strip())
    if not match:
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{file_size}"
        return resp

    start_str, end_str = match.groups()
    if start_str and end_str:
        byte_start = int(start_str)
        byte_end = int(end_str)
    elif start_str:
        byte_start = int(start_str)
        byte_end = file_size - 1
    elif end_str:
        byte_start = max(0, file_size - int(end_str))
        byte_end = file_size - 1
    else:
        byte_start = 0
        byte_end = file_size - 1

    if byte_start >= file_size or byte_end >= file_size or byte_start > byte_end:
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{file_size}"
        return resp

    length = (byte_end - byte_start) + 1

    def file_chunk_generator():
        with open(full_path, "rb") as f:
            f.seek(byte_start)
            remaining = length
            chunk_size = 65536
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    response = StreamingHttpResponse(file_chunk_generator(), status=206, content_type=content_type)
    response["Content-Range"] = f"bytes {byte_start}-{byte_end}/{file_size}"
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = "inline"
    return response
